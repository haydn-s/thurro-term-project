"""The baseline's arithmetic, its guards, and the artifact seam."""
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from app.features import CompanyPeriod, FeatureStore
from app.model import (
    CapexIntensityBaseline,
    ModelArtifactError,
    SignalModel,
    load_model,
)


def _row(symbol, period_end, capex, dep, tier="ev_component"):
    return CompanyPeriod(
        company=f"{symbol} Limited", nse_symbol=symbol, tier=tier,
        primary_panel=True, fiscal_period=period_end[:4], period_end=date.fromisoformat(period_end),
        window_start="", window_end="", window_months=12,
        capex_cr=capex, capex_growth_pct=None, depreciation_cr=dep, cfo_cr=None,
        national_ev_production=None, national_ev_registrations=None,
        own_ev_production=None, own_ev_prod_growth_pct=None,
        own_ev_registrations=None, own_ev_reg_growth_pct=None,
        asset_formation_cr=None, x_coverage=("production",),
    )


def _store(rows):
    return FeatureStore(
        rows=tuple(rows), source=Path("synthetic"),
        loaded_at=datetime.now(timezone.utc), source_mtime=None,
    )


def test_baseline_satisfies_the_protocol():
    # The check the fitted model must also pass; see app/model.py::_load_artifact.
    assert isinstance(CapexIntensityBaseline(), SignalModel)


def test_intensity_is_cumulative_capex_over_cumulative_depreciation():
    # 300 of capex against 100 of depreciation over three filed years.
    store = _store([
        _row("ACME", "2024-03-31", 100.0, 40.0),
        _row("ACME", "2025-03-31", 100.0, 30.0),
        _row("ACME", "2026-03-31", 100.0, 30.0),
    ])
    (signal,) = CapexIntensityBaseline().signals(store)
    assert signal.score == pytest.approx(3.0)
    assert signal.basis["cumulative_capex_cr"] == pytest.approx(300.0)
    assert signal.basis["cumulative_depreciation_cr"] == pytest.approx(100.0)
    assert signal.basis["filed_years"] == 3


def test_fewer_than_three_filed_years_is_skipped():
    store = _store([
        _row("ACME", "2025-03-31", 100.0, 50.0),
        _row("ACME", "2026-03-31", 100.0, 50.0),
    ])
    assert CapexIntensityBaseline().signals(store) == []


def test_rows_missing_capex_or_depreciation_do_not_count_toward_the_minimum():
    store = _store([
        _row("ACME", "2023-03-31", None, 50.0),
        _row("ACME", "2024-03-31", 100.0, None),
        _row("ACME", "2025-03-31", 100.0, 50.0),
        _row("ACME", "2026-03-31", 100.0, 50.0),
    ])
    assert CapexIntensityBaseline().signals(store) == []


def test_non_positive_depreciation_is_skipped_not_divided_by():
    store = _store([
        _row("ACME", "2024-03-31", 100.0, 0.0),
        _row("ACME", "2025-03-31", 100.0, 0.0),
        _row("ACME", "2026-03-31", 100.0, 0.0),
    ])
    assert CapexIntensityBaseline().signals(store) == []


@pytest.mark.parametrize(
    "capex, expected",
    [(400.0, "expand"), (100.0, "replace"), (50.0, "contract")],
)
def test_direction_brackets_replacement(capex, expected):
    # Depreciation totals 100 across the three rows, so capex 400 -> 4.0,
    # 100 -> 1.0, 50 -> 0.5.
    store = _store([
        _row("ACME", "2024-03-31", capex / 3, 100 / 3),
        _row("ACME", "2025-03-31", capex / 3, 100 / 3),
        _row("ACME", "2026-03-31", capex / 3, 100 / 3),
    ])
    (signal,) = CapexIntensityBaseline().signals(store)
    assert signal.direction == expected


def test_confidence_is_the_filed_share_of_the_fy23_fy26_window():
    three = _store([
        _row("ACME", "2024-03-31", 10.0, 5.0),
        _row("ACME", "2025-03-31", 10.0, 5.0),
        _row("ACME", "2026-03-31", 10.0, 5.0),
    ])
    four = _store(list(three.rows) + [_row("ACME", "2023-03-31", 10.0, 5.0)])
    assert CapexIntensityBaseline().signals(three)[0].confidence == pytest.approx(0.75)
    assert CapexIntensityBaseline().signals(four)[0].confidence == pytest.approx(1.0)


def test_sector_median_is_shared_and_vs_sector_is_signed():
    rows = []
    for symbol, capex in (("LOW", 60.0), ("MID", 120.0), ("HIGH", 300.0)):
        for end in ("2024-03-31", "2025-03-31", "2026-03-31"):
            rows.append(_row(symbol, end, capex / 3, 20.0))
    signals = {s.nse_symbol: s for s in CapexIntensityBaseline().signals(_store(rows))}
    medians = {s.basis["sector_median_intensity"] for s in signals.values()}
    assert len(medians) == 1, "the median is a property of the cross-section"
    assert signals["LOW"].basis["vs_sector_median"] < 0
    assert signals["MID"].basis["vs_sector_median"] == pytest.approx(0.0)
    assert signals["HIGH"].basis["vs_sector_median"] > 0


def test_nothing_scoreable_yields_no_signals_rather_than_a_median_of_nothing():
    # statistics.median() raises on an empty sequence, so the model has to bail
    # before computing the cross-section rather than after.
    one_year = _store([_row("A", "2026-03-31", 1.0, 1.0)])
    assert CapexIntensityBaseline().signals(one_year) == []


def test_committed_panel_reproduces_the_notebook_order_of_magnitude(store):
    """Sanity-check against notebook 03 s11, which measured ~2.07 sector-wide.

    Pinned as a band, not a figure: the panel is rebuilt as data is re-pulled, and
    a test that fails on a legitimate refresh is a test that gets deleted. A
    sector median outside 1.0-4.0 means something structural changed.
    """
    signals = CapexIntensityBaseline().signals(store)
    assert len(signals) >= 20
    median = signals[0].basis["sector_median_intensity"]
    assert 1.0 < median < 4.0, f"sector median intensity {median} is off the map"
    assert all(s.notes for s in signals), "every baseline signal must carry its caveat"


def test_no_artifact_configured_gives_the_baseline():
    assert isinstance(load_model(None), CapexIntensityBaseline)


def test_missing_artifact_fails_loudly_with_a_mount_hint(tmp_path):
    with pytest.raises(ModelArtifactError, match="does not exist"):
        load_model(tmp_path / "nope.joblib")


def test_present_but_unimplemented_artifact_fails_loudly(tmp_path):
    # The seam. When _load_artifact is implemented this test should be replaced
    # by one that loads a real fixture artifact -- not deleted.
    artifact = tmp_path / "model.joblib"
    artifact.write_bytes(b"not a model")
    with pytest.raises(ModelArtifactError, match="no loader is implemented"):
        load_model(artifact)
