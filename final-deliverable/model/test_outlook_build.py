"""Checks for build_outlook.py and the outlook.json it commits.

Run from the repo root, in the repo-root environment:
    .VENV/bin/python -m pytest final-deliverable/model/test_outlook_build.py -q

The service tests (final-deliverable/tests/) prove the artifact is internally
consistent. These prove it is the *right* artifact: that it is what the current
data and the selected specs produce.
"""
import json
import math
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "exploration"))

import build_outlook as bo  # noqa: E402
import feature_engineering as fe  # noqa: E402
from ice_control_analysis import ablation  # noqa: E402


@pytest.fixture(scope="module")
def rebuilt():
    return bo.build()


@pytest.fixture(scope="module")
def committed():
    return json.loads(bo.OUT.read_text())


def _compare(a, b, where):
    """Assert two JSON trees are equal, numbers to within float noise."""
    if isinstance(a, dict):
        assert isinstance(b, dict) and a.keys() == b.keys(), where
        for k in a:
            _compare(a[k], b[k], f"{where}.{k}")
    elif isinstance(a, list):
        assert isinstance(b, list) and len(a) == len(b), where
        for i, (x, y) in enumerate(zip(a, b)):
            _compare(x, y, f"{where}[{i}]")
    elif isinstance(a, float) or isinstance(b, float):
        assert math.isclose(a, b, rel_tol=1e-9, abs_tol=1e-12), where
    else:
        assert a == b, where


def test_committed_artifact_matches_a_rebuild(rebuilt, committed):
    # The failure this exists for: data/clean/ refreshed, outlook.json not
    # rebuilt, and the container serving last month's model as if it were this
    # month's. Nothing else in the repo would notice.
    rebuilt, committed = dict(rebuilt), dict(committed)
    rebuilt.pop("built_at"), committed.pop("built_at")
    try:
        _compare(rebuilt, committed, "outlook")
    except AssertionError as exc:
        pytest.fail(f"outlook.json no longer matches the data at {exc}. Rebuild it: "
                    f".VENV/bin/python final-deliverable/model/build_outlook.py")


def test_national_evaluation_is_the_studys_own_number(rebuilt):
    # The build composes the study's walk-forward itself rather than calling
    # ablation(), so check the two paths agree on the row that was selected.
    df = fe.national_features()
    table = ablation(df)
    row = table[(table["controls"] == "ice_growth")
                & (table["feature_set"] == "controls+production+mix")].iloc[0]
    ev = rebuilt["national"]["evaluation"]
    assert ev["brier_skill"] == pytest.approx(row["brier_skill"], abs=1e-4)
    assert ev["brier_gain_ci90_low"] == pytest.approx(row["gain_ci_low"], abs=1e-4)
    assert ev["brier_gain_ci90_high"] == pytest.approx(row["gain_ci_high"], abs=1e-4)
    assert ev["auc"] == pytest.approx(row["auc"], abs=1e-4)


@pytest.mark.parametrize("section", ["national", "state"])
def test_the_scored_month_is_not_a_training_month(rebuilt, section):
    # The served fit uses every month with a known outcome; the month it scores
    # must be the one after them, or the "forecast" is a fitted value.
    model = rebuilt[section]
    scored_months = {r["month"] for r in model["scored"]}
    assert scored_months == {max(scored_months)}
    assert max(scored_months) > model["training"]["last_month"]


def test_served_specs_are_the_selected_ones(rebuilt):
    assert rebuilt["national"]["features"] == fe.CONTROLS_ICE + fe.PRODUCTION + fe.SEGMENT_MIX
    assert rebuilt["state"]["features"] == fe.STATE_SETS["share+history"]
