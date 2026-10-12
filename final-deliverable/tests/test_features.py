"""Feature store: typing, filtering and the failure modes that matter."""
import csv

import pytest

from app.features import (
    ANNUAL_PANEL,
    CompanyPeriod,
    FeatureStore,
    FeatureStoreError,
    _opt_float,
)


def test_loads_the_committed_panel(store):
    assert len(store.rows) > 100
    assert store.source.name == ANNUAL_PANEL
    assert store.source_mtime is not None


def test_primary_panel_filter_is_narrower_than_the_file(store):
    assert 0 < len(store.panel()) < len(store.rows)
    assert all(r.primary_panel for r in store.panel())


def test_blank_cells_become_none_not_zero(store):
    # The first period of each company has no prior year to difference against,
    # so capex_growth_pct is blank there. It must not read as 0% growth.
    firsts = [rows[0] for rows in store.by_company().values()]
    assert any(r.capex_growth_pct is None for r in firsts)
    assert all(r.capex_growth_pct != 0.0 for r in firsts if r.capex_growth_pct is None)


def test_opt_float_rejects_garbage():
    assert _opt_float("") is None
    assert _opt_float(None) is None
    assert _opt_float(" 1.5 ") == 1.5
    with pytest.raises(FeatureStoreError):
        _opt_float("n/a")


def test_periods_are_sorted_and_latest_is_last(store):
    periods = store.periods()
    assert list(periods) == sorted(periods)
    assert store.latest_period() == periods[-1]


def test_per_company_rows_are_chronological(store):
    for symbol, rows in store.by_company().items():
        ends = [r.period_end for r in rows]
        assert ends == sorted(ends), symbol


def test_missing_file_names_the_variable_to_fix(tmp_path):
    with pytest.raises(FeatureStoreError, match="FEATURE_STORE"):
        FeatureStore.load(tmp_path)


def test_wrong_csv_is_rejected_rather_than_half_parsed(tmp_path):
    bad = tmp_path / ANNUAL_PANEL
    with bad.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["company", "nse_symbol"])
        writer.writerow(["Acme", "ACME"])
    with pytest.raises(FeatureStoreError, match="missing required columns"):
        FeatureStore.load(tmp_path)


def test_header_only_file_is_an_error(tmp_path, panel_dir):
    header = (panel_dir / ANNUAL_PANEL).read_text().splitlines()[0]
    empty = tmp_path / ANNUAL_PANEL
    empty.write_text(header + "\n")
    with pytest.raises(FeatureStoreError, match="no data rows"):
        FeatureStore.load(tmp_path)


def test_coverage_is_split_on_semicolons():
    row = CompanyPeriod.from_row(
        {
            "company": "Acme", "nse_symbol": "ACME", "tier": "ev_component",
            "primary_panel": "yes", "fiscal_period": "Q4 FY25",
            "period_end": "2025-03-31", "x_coverage": "production;own_reg",
            "capex_cr": "10", "depreciation_cr": "5",
        }
    )
    assert row.x_coverage == ("production", "own_reg")
    assert row.primary_panel is True


def test_bad_period_end_names_the_company():
    with pytest.raises(FeatureStoreError, match="ACME"):
        CompanyPeriod.from_row(
            {
                "company": "Acme", "nse_symbol": "ACME", "tier": "x",
                "primary_panel": "yes", "fiscal_period": "Q4",
                "period_end": "31/03/2025",
            }
        )
