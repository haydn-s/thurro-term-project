"""Checks on Track C, the sequence models.

As in test_nn.py, the ones that matter are leakage. A sequence model sees a whole
window rather than a handful of named lags, so the ways to leak are different:
a window that runs past its origin, a multi-month target that reaches into the
test period, a scaler fitted on test windows. Each has a check here.

Skipped entirely if torch is not installed (it is an optional layer; see
requirements-dl.txt).

Run:
    pytest final-deliverable/model/nn -q
"""
import numpy as np
import pandas as pd
import pytest

torch = pytest.importorskip("torch")

import nn_volume as nv                                       # noqa: E402
import seq_models as sm                                      # noqa: E402
import seq_volume as sv                                      # noqa: E402
from nn_config import (SEQ_HORIZON, SEQ_QUANTILES, SEQ_VAL_MONTHS,  # noqa: E402
                       VOLUME_TRAIN_END)

FIRST_TEST = pd.Timestamp(VOLUME_TRAIN_END) + pd.DateOffset(months=1)


@pytest.fixture(scope="module")
def panel():
    return sv.seq_panel()


@pytest.fixture(scope="module")
def samples(panel):
    return sv.build_samples(panel, window=24)


@pytest.fixture(scope="module")
def splits(samples):
    return sv.split_masks(samples["meta"], samples["y"])


@pytest.fixture(scope="module")
def lookup(panel):
    return {(r.state, r.month): r.log_total for r in panel.itertuples()}


# =====================================================================
# Leakage: windows and targets
# =====================================================================
def test_window_ends_at_the_origin(samples, lookup):
    """Step k of the window is month t-(L-1-k); nothing after t is in it."""
    meta, x, L = samples["meta"], samples["x"], samples["x"].shape[1]
    rng = np.random.default_rng(0)
    for i in rng.choice(len(meta), 150, replace=False):
        state, t, lvl_t = meta.loc[i, ["state", "month", "log_total"]]
        assert x[i, -1, 0] == pytest.approx(0.0), "rel_level must be 0 at the origin"
        for k in range(L):
            month = t - pd.DateOffset(months=L - 1 - k)
            want = lookup.get((state, month))
            if want is None:
                assert x[i, k, -1] == 0 and np.all(x[i, k] == 0), "padding must be all-zero"
            else:
                assert x[i, k, -1] == 1
                assert x[i, k, 0] == pytest.approx(want - lvl_t, abs=1e-5)


def test_targets_are_future_changes(samples, lookup):
    """y[h-1] = level(t+h) - level(t), NaN where t+h is past the data."""
    meta, y = samples["meta"], samples["y"]
    rng = np.random.default_rng(1)
    for i in rng.choice(len(meta), 150, replace=False):
        state, t, lvl_t = meta.loc[i, ["state", "month", "log_total"]]
        for h in range(1, SEQ_HORIZON + 1):
            nxt = lookup.get((state, t + pd.DateOffset(months=h)))
            if nxt is None:
                assert np.isnan(y[i, h - 1])
            else:
                assert y[i, h - 1] == pytest.approx(nxt - lvl_t, abs=1e-5)


def test_no_training_target_falls_in_the_test_window(samples, splits):
    """Every horizon a training row may use ends no later than the first test origin."""
    rows, mask = splits["train"]
    meta = samples["meta"]
    for h in range(1, SEQ_HORIZON + 1):
        used = rows & mask[:, h - 1]
        assert used.any()
        assert sv.target_month(meta[used], h).max() <= FIRST_TEST, f"h={h} leaks"


def test_inner_training_targets_stop_before_validation(samples, splits):
    rows, mask = splits["inner_train"]
    first_val = pd.Timestamp(VOLUME_TRAIN_END) - pd.DateOffset(months=SEQ_VAL_MONTHS - 1)
    meta = samples["meta"]
    for h in range(1, SEQ_HORIZON + 1):
        used = rows & mask[:, h - 1]
        assert sv.target_month(meta[used], h).max() <= first_val, f"h={h} leaks into validation"


def test_splits_are_ordered_and_disjoint(samples, splits):
    m = samples["meta"]["month"]
    tr, va, te, inner = (splits[k][0] for k in ("train", "val", "test", "inner_train"))
    assert m[tr].max() < m[te].min()
    assert m[inner].max() < m[va].min()
    assert not (tr & te).any() and not (inner & va).any()
    assert ((inner | va) == tr).all(), "inner train + validation must be the training origins"
    assert m[va].nunique() == SEQ_VAL_MONTHS


def test_scaler_uses_training_windows_only(samples, splits):
    """Changing the test windows must not change the scaler."""
    rows, _ = splits["train"]
    a = sv.ChannelScaler().fit(samples["x"][rows], samples["s"][rows])
    x = samples["x"].copy()
    x[~rows] *= 100.0
    b = sv.ChannelScaler().fit(x[rows], samples["s"][rows])
    assert np.allclose(a.mu, b.mu) and np.allclose(a.sd, b.sd)


def test_scaled_padding_stays_zero(samples, splits):
    rows, _ = splits["train"]
    sc = sv.ChannelScaler().fit(samples["x"][rows], samples["s"][rows])
    x, _ = sc.transform(samples["x"], samples["s"])
    pad = samples["x"][..., -1] == 0
    assert pad.any(), "a 24-month window should pad some early rows"
    assert np.all(x[pad] == 0)


# =====================================================================
# Comparability with Track B
# =====================================================================
def test_one_step_rows_are_track_b_rows(samples, splits):
    """At h=1 both tracks must score exactly the same (state, month) rows."""
    feats = nv.build_volume_features()
    meta = samples["meta"]
    for k, cond in (("train", feats["month"] <= VOLUME_TRAIN_END),
                    ("test", feats["month"] > VOLUME_TRAIN_END)):
        rows, mask = splits[k]
        mine = meta[rows & mask[:, 0]][["state", "month"]].reset_index(drop=True)
        theirs = feats[cond][["state", "month"]].reset_index(drop=True)
        assert mine.equals(theirs), k


def test_window_length_changes_padding_not_rows(panel):
    a, b = sv.build_samples(panel, 13), sv.build_samples(panel, 24)
    assert a["meta"].equals(b["meta"])
    assert np.array_equal(a["y"], b["y"], equal_nan=True)
    assert np.allclose(a["x"], b["x"][:, -13:]), "the last 13 steps must agree"


def test_one_step_targets_match_track_b(samples, splits):
    feats = nv.build_volume_features()
    rows, mask = splits["test"]
    use = rows & mask[:, 0]
    mine = samples["meta"][use][["state", "month"]].assign(y=samples["y"][use, 0])
    both = mine.merge(feats[["state", "month", "y_delta_next"]], on=["state", "month"])
    assert len(both) == use.sum()
    assert np.allclose(both["y"], both["y_delta_next"], atol=1e-5)


# =====================================================================
# Baselines and scoring
# =====================================================================
def test_ses_with_alpha_one_is_the_random_walk(panel, samples):
    lv = sv.ses_levels(panel, 1.0)
    meta = samples["meta"]
    levels = np.array([lv[(s, m)] for s, m in zip(meta["state"], meta["month"])])
    assert np.allclose(levels, meta["log_total"])


def test_ses_level_uses_only_the_past(panel):
    """Changing a later month must not move an earlier smoothed level."""
    state = panel["state"].iloc[0]
    g = panel[panel["state"] == state]
    cut = g["month"].iloc[len(g) // 2]
    before = sv.ses_levels(panel, 0.5)
    altered = panel.copy()
    altered.loc[(altered["state"] == state) & (altered["month"] > cut), "log_total"] += 5.0
    after = sv.ses_levels(altered, 0.5)
    for m in g["month"][g["month"] <= cut]:
        assert before[(state, m)] == pytest.approx(after[(state, m)])


def test_bootstrap_of_identical_errors_is_zero():
    e = np.abs(np.random.default_rng(0).normal(size=60))
    months = np.repeat(np.arange(12), 5)
    r = sv.month_bootstrap(e, e, months)
    assert r["gain"] == 0 and r["gain_ci_low"] == 0 and r["gain_ci_high"] == 0


def test_bootstrap_resamples_months_not_rows():
    """One month carrying all the gain must give a wide interval, not a tight one."""
    months = np.repeat(np.arange(10), 30)
    base = np.ones(300)
    model = np.ones(300)
    model[months == 0] = 0.0                    # all the gain is in one month
    r = sv.month_bootstrap(base, model, months)
    assert r["gain_ci_low"] == pytest.approx(0.0)
    assert r["gain_ci_high"] > r["gain"]


def test_empirical_interval_keeps_the_point_and_brackets_it(samples, splits, panel):
    point, _ = sv.baseline_forecasts(panel, samples, splits)
    for name in ("Naive (last month)", "SES"):
        q = sv.empirical_quantiles(samples, splits, point[name])
        assert np.allclose(q[..., 1], point[name])
        assert np.all(q[..., 0] <= q[..., 1]) and np.all(q[..., 1] <= q[..., 2])


def test_empirical_interval_uses_training_residuals_only(samples, splits, panel):
    """Corrupting every test target must not move the interval."""
    point, _ = sv.baseline_forecasts(panel, samples, splits)
    te_rows, _ = splits["test"]
    a = sv.empirical_quantiles(samples, splits, point["SES"])
    corrupted = dict(samples, y=np.where(te_rows[:, None], 99.0, samples["y"]))
    b = sv.empirical_quantiles(corrupted, splits, point["SES"])
    assert np.allclose(a, b)


def test_coverage_and_pinball():
    y = np.array([0.0, 1.0, 2.0])
    q = np.array([[-1.0, 0.0, 1.0], [-1.0, 0.0, 0.5], [1.5, 2.0, 2.5]])
    assert sv.coverage(y, q) == pytest.approx(2 / 3)
    exact = np.column_stack([y - 1, y, y + 1])
    assert sv.mean_pinball(y, exact) < sv.mean_pinball(y, q)


# =====================================================================
# The networks
# =====================================================================
DIMS = dict(n_channels=len(sv.CHANNELS), n_static=len(sv.STATIC), n_states=5,
            horizon=SEQ_HORIZON, quantiles=SEQ_QUANTILES, window=13)


def _batch(n=8, seed=0):
    g = torch.Generator().manual_seed(seed)
    x = torch.randn(n, 13, len(sv.CHANNELS), generator=g)
    x[..., -1] = 1.0
    x[0, :5] = 0.0                               # one padded window
    return x, torch.randn(n, 1, generator=g), torch.randint(0, 5, (n,), generator=g)


@pytest.mark.parametrize("arch", list(sm.ARCHITECTURES))
def test_output_shape_and_ordered_quantiles(arch):
    model = sm.build(arch, 0, **DIMS)
    with torch.no_grad():
        out = model(*_batch())
    assert out.shape == (8, SEQ_HORIZON, len(SEQ_QUANTILES))
    assert torch.all(out[..., :-1] <= out[..., 1:]), "quantiles crossed"


@pytest.mark.parametrize("arch", list(sm.ARCHITECTURES))
def test_untrained_network_forecasts_no_change(arch):
    """The zero-initialised head makes an untrained model the random walk."""
    model = sm.build(arch, 0, **DIMS)
    with torch.no_grad():
        out = model(*_batch())
    assert torch.allclose(out[..., len(SEQ_QUANTILES) // 2], torch.zeros(8, SEQ_HORIZON))


@pytest.mark.parametrize("arch", list(sm.ARCHITECTURES))
def test_quantiles_stay_ordered_after_training(arch):
    x, s, idx = _batch(64, seed=3)
    y = torch.randn(64, SEQ_HORIZON) * 0.3
    data = {"x": x.numpy(), "s": s.numpy(), "idx": idx.numpy(), "y": y.numpy(),
            "m": np.ones((64, SEQ_HORIZON), np.float32)}
    model, _, _, _ = sm.fit(sm.build(arch, 0, **DIMS), data, SEQ_QUANTILES, epochs=15)
    q = sm.predict(model, data)
    assert np.all(q[..., :-1] <= q[..., 1:] + 1e-6)


def test_same_seed_reproduces_and_different_seeds_differ():
    x, s, idx = _batch(64, seed=4)
    y = torch.randn(64, SEQ_HORIZON) * 0.3
    data = {"x": x.numpy(), "s": s.numpy(), "idx": idx.numpy(), "y": y.numpy(),
            "m": np.ones((64, SEQ_HORIZON), np.float32)}

    def run(seed):
        model, _, _, _ = sm.fit(sm.build("GRU", seed, **DIMS), data, SEQ_QUANTILES,
                                epochs=5, seed=seed)
        return sm.predict(model, data)

    assert np.allclose(run(7), run(7))
    assert not np.allclose(run(7), run(8))


def test_pinball_at_the_median_is_half_the_absolute_error():
    pred = torch.tensor([[[0.0, 0.0, 0.0]]])
    y = torch.tensor([[2.0]])
    m = torch.ones(1, 1)
    assert float(sm.pinball_loss(pred[..., 1:2], y, m, [0.5])) == pytest.approx(1.0)


def test_pinball_ignores_masked_targets():
    pred = torch.zeros(2, 2, 3)
    y = torch.tensor([[1.0, 1000.0], [1.0, 1000.0]])
    m = torch.tensor([[1.0, 0.0], [1.0, 0.0]])
    a = sm.pinball_loss(pred, y, m, SEQ_QUANTILES)
    b = sm.pinball_loss(pred, torch.tensor([[1.0, 0.0], [1.0, 0.0]]), m, SEQ_QUANTILES)
    assert float(a) == pytest.approx(float(b))


def test_control_reads_track_b_features_in_row_order(samples):
    """The control's inputs must be Track B's feature row for the same (state, month)."""
    feats = nv.build_volume_features().set_index(["state", "month"])[nv.FEATURES]
    fs = sv.with_track_b_features(samples)
    rng = np.random.default_rng(5)
    for i in rng.choice(len(fs["meta"]), 50, replace=False):
        key = tuple(fs["meta"].loc[i, ["state", "month"]])
        assert np.allclose(fs["s"][i], feats.loc[key].to_numpy(), atol=1e-4)


def test_hybrid_offset_is_the_ses_forecast(panel, samples, splits):
    """A hybrid's offset must be exactly SES's forecast, so an untrained hybrid is SES."""
    point, info = sv.baseline_forecasts(panel, samples, splits)
    hs = sv.with_ses_offset(samples, panel, info["ses_alpha"])
    assert np.allclose(hs["offset"], point["SES"], atol=1e-5)
    assert hs["s"].shape[1] == samples["s"].shape[1] + 1


def test_hybrid_trains_on_the_residual_and_adds_it_back(panel, samples, splits):
    hs = sv.with_ses_offset(samples, panel, 0.5)
    rows, mask = splits["train"]
    sc = sv.ChannelScaler().fit(hs["x"][rows], hs["s"][rows])
    d = sv.phase_data(hs, rows, mask, sc)
    want = np.nan_to_num(hs["y"][rows] - hs["offset"][rows], nan=0.0)
    assert np.allclose(d["y"], want)

    dims = dict(DIMS, n_states=len(samples["states"]), n_static=hs["s"].shape[1], window=24)
    model = sm.build("GRU", 0, **dims)                       # untrained: forecasts 0
    q = sv.predict_changes(model, hs, rows, mask, sc)
    assert np.allclose(q[..., 1], hs["offset"][rows], atol=1e-5)


def test_ses_offset_uses_only_the_past(panel, samples):
    """Corrupting months after an origin must not move that origin's offset."""
    a = sv.with_ses_offset(samples, panel, 0.5)["offset"]
    cut = pd.Timestamp(VOLUME_TRAIN_END)
    altered = panel.copy()
    altered.loc[altered["month"] > cut, "log_total"] += 5.0
    b = sv.with_ses_offset(samples, altered, 0.5)["offset"]
    early = (samples["meta"]["month"] <= cut).to_numpy()
    assert np.allclose(a[early], b[early])


def test_a_bounded_test_block_holds_only_the_next_months(samples):
    meta = samples["meta"]
    sp = sv.split_masks(meta, samples["y"], train_end="2023-09-01", test_months=6)
    rows, _ = sp["test"]
    m = meta.loc[rows, "month"]
    assert m.min() == pd.Timestamp("2023-10-01") and m.max() == pd.Timestamp("2024-03-01")
    tr, tr_mask = sp["train"]
    for h in range(1, SEQ_HORIZON + 1):
        used = tr & tr_mask[:, h - 1]
        assert sv.target_month(meta[used], h).max() <= pd.Timestamp("2023-10-01")


def test_rolling_origin_refits_from_each_origin(panel):
    rows = sv.rolling_origin(panel, origins=["2023-09-01", "2024-03-01"], block=3,
                             archs=["N-BEATS on SES"], n_seeds=1, n_jobs=1,
                             max_epochs=2, patience=1)
    for origin, g in rows.groupby("origin"):
        assert g["month"].min() > origin
        assert g["month"].max() <= origin + pd.DateOffset(months=3)
    assert not rows.duplicated(subset=["state", "month", "horizon"]).any()
    assert rows["ses_alpha"].between(0, 1).all()
    summary = sv.score_rolling(rows, majors=sorted(rows["state"].unique())[:5])
    naive = summary[summary["model"] == "Naive (last month)"]
    assert np.allclose(naive["skill_vs_naive"], 0.0)


def test_end_to_end_short_run(panel):
    """The whole validate-then-refit path, on two architectures and a tiny budget."""
    sel, refits, samples, splits = sv.train_sequence_models(
        panel, archs=["GRU", "N-BEATS on SES", sv.CONTROL_ARCHS[0]], n_seeds=1,
        windows=[13, 24], n_jobs=1, max_epochs=3, patience=2)
    assert set(sel["model"]) == {"GRU", "N-BEATS on SES", sv.CONTROL_ARCHS[0]}
    assert (sel["model"] == sv.CONTROL_ARCHS[0]).sum() == 1, "the control has no window to choose"
    assert sel.groupby("model")["chosen"].sum().eq(1).all()
    te_rows, _ = splits["test"]
    for r in refits:
        assert r["test"].shape == (int(te_rows.sum()), SEQ_HORIZON, len(SEQ_QUANTILES))
        assert 1 <= r["epochs"] <= 3
