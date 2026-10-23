"""Checks on the neural-network experiments.

The ones that matter are the leakage tests. Everything in these results is an
out-of-sample claim, and the cheapest way to produce a flattering out-of-sample
number by accident is to let a feature see the future. These assert that no
feature for state s at month t uses anything after t, that the target really is
month t+1, and that both splits are strictly ordered in time.

Run:
    pytest final-deliverable/model/nn -q
"""
import numpy as np
import pandas as pd
import pytest

import nn_volume as nv
from nn_config import VOLUME_TRAIN_END
from nn_models import (mlp_small, mlp_tiny, national_nn_models, seed_list,
                       summarise_seeds, volume_models)


@pytest.fixture(scope="module")
def panel():
    return nv.build_volume_features()


# =====================================================================
# Leakage
# =====================================================================
def test_target_is_next_month(panel):
    """y_log_next for (s, t) equals log_total for (s, t+1)."""
    raw = nv.complete_panel()
    raw["log_total"] = np.log1p(raw["ev_total"])
    lookup = {(r.state, r.month): r.log_total for r in raw.itertuples()}

    checked = 0
    for row in panel.sample(200, random_state=0).itertuples():
        nxt = lookup.get((row.state, row.month + pd.DateOffset(months=1)))
        assert nxt is not None, "a kept row has no following month in the raw panel"
        assert row.y_log_next == pytest.approx(nxt, abs=1e-9)
        checked += 1
    assert checked == 200


def test_lags_are_backward_looking(panel):
    """log_lagL for (s, t) equals log_total at (s, t-L), never t+L."""
    raw = nv.complete_panel()
    raw["log_total"] = np.log1p(raw["ev_total"])
    lookup = {(r.state, r.month): r.log_total for r in raw.itertuples()}

    for row in panel.sample(100, random_state=1).itertuples():
        for L in nv.LAGS:
            want = lookup.get((row.state, row.month - pd.DateOffset(months=L)))
            assert want is not None
            assert getattr(row, f"log_lag{L}") == pytest.approx(want, abs=1e-9)


def test_rolling_windows_end_before_t(panel):
    """log_rollR averages months t-R..t-1 and must exclude month t itself."""
    raw = nv.complete_panel()
    raw["log_total"] = np.log1p(raw["ev_total"])
    lookup = {(r.state, r.month): r.log_total for r in raw.itertuples()}

    for row in panel.sample(60, random_state=2).itertuples():
        for R in nv.ROLLS:
            window = [lookup[(row.state, row.month - pd.DateOffset(months=k))]
                      for k in range(1, R + 1)]
            assert getattr(row, f"log_roll{R}") == pytest.approx(np.mean(window), abs=1e-9)


def test_seasonal_naive_reads_the_same_month_last_year(panel):
    """The seasonal forecast for t+1 is month t+1-12, not t-12.

    Round one used log_lag12, a 13-month lag, which scored a worse seasonal
    baseline than the real one.
    """
    raw = nv.complete_panel()
    raw["log_total"] = np.log1p(raw["ev_total"])
    lookup = {(r.state, r.month): r.log_total for r in raw.itertuples()}

    for row in panel.sample(100, random_state=3).itertuples():
        want = lookup[(row.state, row.month + pd.DateOffset(months=1) - pd.DateOffset(months=12))]
        assert row.log_same_month_last_year == pytest.approx(want, abs=1e-9)
    assert "log_same_month_last_year" not in nv.FEATURES


def test_no_feature_column_is_the_target(panel):
    """A column equal to the target would make the task trivial."""
    for col in nv.FEATURES:
        assert not np.allclose(panel[col], panel["y_log_next"]), f"{col} duplicates the target"
    assert "y_log_next" not in nv.FEATURES
    assert "y_delta_next" not in nv.FEATURES
    assert "y_level_next" not in nv.FEATURES


def test_delta_target_reconstructs_the_level(panel):
    """The delta framing must be an exact re-parameterisation, not an approximation."""
    assert np.allclose(panel["y_delta_next"] + panel["log_total"], panel["y_log_next"])


def test_split_is_ordered_in_time(panel):
    train = panel[panel["month"] <= VOLUME_TRAIN_END]
    test = panel[panel["month"] > VOLUME_TRAIN_END]
    assert len(train) > 0 and len(test) > 0
    assert train["month"].max() < test["month"].min()


def test_every_feature_column_exists(panel):
    missing = [c for c in nv.FEATURES if c not in panel.columns]
    assert missing == []
    assert panel[nv.FEATURES].notna().all().all(), "features must be complete after the dropna"


# =====================================================================
# Panel construction
# =====================================================================
def test_sparse_states_are_dropped():
    raw = nv.complete_panel()
    kept = set(nv.build_volume_features()["state"])
    nonzero = raw.groupby("state")["ev_total"].apply(lambda s: int((s > 0).sum()))
    for state, n in nonzero.items():
        if n < nv.VOLUME_MIN_NONZERO_MONTHS:
            assert state not in kept, f"{state} has only {n} non-zero months"


def test_one_row_per_state_month(panel):
    assert not panel.duplicated(subset=["state", "month"]).any()


# =====================================================================
# Metrics
# =====================================================================
def test_perfect_prediction_scores_zero():
    y = np.array([1.0, 2.0, 3.0])
    s = nv.regression_scores(y, y)
    assert s["mae_log"] == pytest.approx(0.0)
    assert s["rmse_log"] == pytest.approx(0.0)
    assert s["mae_level"] == pytest.approx(0.0)
    assert s["smape_level"] == pytest.approx(0.0)


def test_scores_penalise_error_monotonically():
    y = np.zeros(10)
    near = nv.regression_scores(y, np.full(10, 0.1))
    far = nv.regression_scores(y, np.full(10, 0.5))
    assert near["mae_log"] < far["mae_log"]
    assert near["rmse_log"] < far["rmse_log"]


# =====================================================================
# Models
# =====================================================================
def test_national_specs_match_the_exploration_interface():
    """The specs must be runnable by the study's own fit_predict without edits."""
    from models import fit_predict
    rng = np.random.default_rng(0)
    X_train = pd.DataFrame(rng.normal(size=(24, 3)), columns=list("abc"))
    y = pd.Series(rng.integers(0, 2, 24))
    X_test = pd.DataFrame(rng.normal(size=(2, 3)), columns=list("abc"))

    for name, spec in national_nn_models().items():
        assert set(spec) == {"kind", "features", "make"}, name
        assert spec["kind"] in {"prob", "count"}, name
        p = fit_predict(spec, X_train, y, y, X_test)
        assert len(p) == 2
        assert np.all((p >= 0) & (p <= 1)), f"{name} returned something that is not a probability"


def test_same_seed_is_reproducible():
    rng = np.random.default_rng(0)
    X = pd.DataFrame(rng.normal(size=(40, 4)), columns=list("abcd"))
    y = pd.Series(rng.integers(0, 2, 40))
    a = mlp_tiny(seed=7).fit(X, y).predict_proba(X)[:, 1]
    b = mlp_tiny(seed=7).fit(X, y).predict_proba(X)[:, 1]
    assert np.allclose(a, b)


def test_different_seeds_actually_differ():
    """If seeds did nothing, the multi-seed reporting would be a false comfort."""
    rng = np.random.default_rng(1)
    X = pd.DataFrame(rng.normal(size=(40, 4)), columns=list("abcd"))
    y = pd.Series(rng.integers(0, 2, 40))
    a = mlp_small(seed=1).fit(X, y).predict_proba(X)[:, 1]
    b = mlp_small(seed=99).fit(X, y).predict_proba(X)[:, 1]
    assert not np.allclose(a, b)


def test_scaler_is_inside_the_pipeline():
    """Standardisation must be refitted per fold, or it leaks the test fold's scale."""
    for maker in (mlp_tiny, mlp_small):
        steps = dict(maker().named_steps)
        assert "standardscaler" in steps
    for name, (maker, needs_seed) in volume_models().items():
        model = maker(seed=0) if needs_seed else maker()
        assert "standardscaler" in dict(model.named_steps), name


def test_seed_list_and_summary():
    assert seed_list(3) == [0, 1, 2]
    s = summarise_seeds([1.0, 2.0, 3.0])
    assert s["mean"] == pytest.approx(2.0)
    assert s["min"] == 1.0 and s["max"] == 3.0 and s["n_seeds"] == 3


# =====================================================================
# End-to-end
# =====================================================================
def test_volume_comparison_runs_and_ranks(panel):
    per_seed, averaged, info = nv.volume_comparison(panel, n_seeds=2, target_mode="delta")
    assert len(averaged) >= 5
    assert info["train_rows"] > info["test_rows"]
    assert "Naive (last month)" in set(averaged["model"])
    # the naive forecast is the reference, so its own skill is exactly zero
    naive = per_seed[per_seed["model"] == "Naive (last month)"].iloc[0]
    assert naive["skill_vs_naive"] == pytest.approx(0.0)


def test_both_target_modes_score_naive_identically(panel):
    """The baselines do not depend on the target framing; if they moved, the
    reconstruction in one of the two modes would be wrong."""
    _, lvl, _ = nv.volume_comparison(panel, n_seeds=1, target_mode="level")
    _, dlt, _ = nv.volume_comparison(panel, n_seeds=1, target_mode="delta")
    a = lvl.loc[lvl["model"] == "Naive (last month)", "mae_log"].iloc[0]
    b = dlt.loc[dlt["model"] == "Naive (last month)", "mae_log"].iloc[0]
    assert a == pytest.approx(b)


# =====================================================================
# Panel completion (the bug the lag test caught)
# =====================================================================
def test_completed_panel_has_no_internal_gaps():
    full = nv.complete_panel()
    for state, g in full.groupby("state", observed=True):
        span = pd.date_range(g["month"].min(), g["month"].max(), freq="MS")
        assert len(g) == len(span), f"{state} still has a gap"
        assert g["month"].is_monotonic_increasing


def test_completion_only_adds_zero_months():
    """Completion must not alter a month that was already present."""
    raw = nv.load_panel()
    full = nv.complete_panel()
    merged = raw.merge(full, on=["state", "month"], suffixes=("_raw", "_full"))
    assert len(merged) == len(raw)
    assert np.allclose(merged["ev_total_raw"], merged["ev_total_full"])
    added = len(full) - len(raw)
    assert added > 0, "the source panel is sparse, so completion must add rows"
    only_new = full.merge(raw[["state", "month"]], on=["state", "month"],
                          how="left", indicator=True)
    only_new = only_new[only_new["_merge"] == "left_only"]
    assert (only_new["ev_total"] == 0).all(), "filled months must be zero"


def test_final_month_is_not_partial():
    """The last month of the panel must be a complete month.

    The registrations pull stops mid-month, and a half month looks like a ~55%
    collapse in every state at once -- a target that only rewards models that
    happen to predict a fall. Round one read the uncleaned file and scored
    against it; this is what keeps that from coming back if the pull is extended.
    """
    raw = nv.load_panel()
    nat = raw.groupby("month")["ev_total"].sum().sort_index()
    assert nat.iloc[-1] >= 0.6 * nat.iloc[-4:-1].median(), (
        f"{nat.index[-1].date()} totals {nat.iloc[-1]:,.0f}, far below the months "
        "before it -- probably a partial month that clean.py should drop")


def test_completion_does_not_backfill_before_first_sighting():
    raw = nv.load_panel()
    full = nv.complete_panel()
    first_raw = raw.groupby("state")["month"].min()
    first_full = full.groupby("state")["month"].min()
    for state in first_raw.index:
        assert first_full[state] == first_raw[state], state
