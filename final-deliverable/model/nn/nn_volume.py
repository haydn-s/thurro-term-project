"""Track B: the one target in this project a network can actually be trained on.

Track A asks the project's research question and is limited by **events**: 11
announcements nationally, 7 in the state training split. No model class fixes
that. This file changes the target rather than the model: forecast a state's EV
registrations next month, which is dense (36 states x 105 months, no missing
outcomes) and continuous, so a network has something to fit.

Why this is still useful to the project rather than a detour: EV volume is the
*independent* variable in the research question. A model that forecasts it one
month ahead turns a backward-looking panel into a forward-looking one, which is
what the deliverable needs if it is ever to serve a signal rather than a
historical ratio.

Scope note
----------
The lag and calendar columns below are built here, locally, for this target
only. They are deliberately NOT added to `scripts/features.py` or to the
exploration package's `feature_engineering.py` -- the shared feature layer
belongs to the modelling track, and a second implementation of it would drift.
If this target graduates into the study, the construction moves there.

Leakage
-------
Every feature for state s at month t uses only months <= t for that state, plus
the cross-sectional national total at t (known at t). The target is month t+1.
Scalers are fitted inside a pipeline on training rows only. `test_nn.py` asserts
all of this.
"""
import warnings

import numpy as np
import pandas as pd

from nn_config import (N_SEEDS, RANDOM_STATE, RESULTS, VOLUME_MAX_LOOKBACK,
                       VOLUME_MIN_NONZERO_MONTHS, VOLUME_PANEL, VOLUME_TRAIN_END)
from nn_models import mean_baseline_reg, seed_list, volume_models

warnings.filterwarnings("ignore")

LAGS = [1, 2, 3, 6, 12]
ROLLS = [3, 6, 12]


# =====================================================================
# Panel construction
# =====================================================================
SEGMENT_COLS = ["ev_2w", "ev_3w", "ev_4w", "ev_buses", "ev_small_buses",
                "ev_lcv", "ev_mhcv", "ev_tractors", "ev_constr_eq", "ev_total"]


def load_panel(path=VOLUME_PANEL):
    d = pd.read_csv(path, parse_dates=["month"])
    return d.sort_values(["state", "month"]).reset_index(drop=True)


def complete_panel(d=None):
    """Put every state on an unbroken monthly grid, filling absent months with 0.

    This is not cosmetic. The source panel is **sparse-encoded**: a state-month
    with no registrations has no row at all, and 21 of 36 states have internal
    gaps -- including Gujarat, Kerala and Andhra Pradesh, each missing a 2020
    lockdown month when registrations really were zero.

    `groupby(...).shift(1)` moves by one ROW, not one month. On a sparse panel
    that silently makes `log_lag1` reach back 2, 3 or 31 months for some rows,
    and makes the target "the next month that exists" rather than "next month".
    Both corrupt a forecasting result, and the lag test in test_nn.py is what
    caught it.

    A state's grid starts at its own first observed month: before that it is
    absent from the feed rather than at zero, and inventing zeros there would
    manufacture a growth spike on the month it appears.
    """
    if d is None:
        d = load_panel()
    last = d["month"].max()
    out = []
    for state, g in d.groupby("state", observed=True):
        grid = pd.date_range(g["month"].min(), last, freq="MS")
        g = (g.set_index("month").reindex(grid)
             .rename_axis("month").reset_index())
        g["state"] = state
        g[SEGMENT_COLS] = g[SEGMENT_COLS].fillna(0.0)
        out.append(g)
    full = pd.concat(out, ignore_index=True)
    return full.sort_values(["state", "month"]).reset_index(drop=True)


def build_volume_features(d=None, min_nonzero=VOLUME_MIN_NONZERO_MONTHS):
    """One row per state x month, with next month's log volume as the target."""
    if d is None:
        d = complete_panel()

    # Drop states that are mostly structural zeros: they teach the network to
    # predict 0 and dominate the row count without carrying information.
    nonzero = d.groupby("state")["ev_total"].apply(lambda s: int((s > 0).sum()))
    keep = nonzero[nonzero >= min_nonzero].index
    d = d[d["state"].isin(keep)].copy()

    d["log_total"] = np.log1p(d["ev_total"])
    g = d.groupby("state", observed=True)

    for L in LAGS:
        d[f"log_lag{L}"] = g["log_total"].shift(L)
    for R in ROLLS:
        # shift(1) first: the window must end at t-1 so that nothing at t leaks
        # into a feature used to predict t+1 alongside the t value itself.
        d[f"log_roll{R}"] = g["log_total"].transform(
            lambda s: s.shift(1).rolling(R, min_periods=R).mean())

    d["log_growth_1m"] = d["log_total"] - d["log_lag1"]
    d["log_growth_3m"] = d["log_total"] - d["log_lag3"]
    d["log_growth_12m"] = d["log_total"] - d["log_lag12"]
    d["accel_3m"] = d["log_growth_1m"] - (d["log_growth_3m"] / 3)

    # within-state segment mix, from the current month (known at t)
    total = d["ev_total"].replace(0, np.nan)
    d["share_2w_own"] = (d["ev_2w"] / total).fillna(0.0)
    d["share_4w_own"] = (d["ev_4w"] / total).fillna(0.0)
    d["share_3w_own"] = (d["ev_3w"] / total).fillna(0.0)

    # cross-sectional position at t
    nat = d.groupby("month")["ev_total"].transform("sum").replace(0, np.nan)
    d["share_national"] = (d["ev_total"] / nat).fillna(0.0)
    d["log_size_12m"] = np.log1p(
        g["ev_total"].transform(lambda s: s.rolling(12, min_periods=12).sum()))

    # calendar and trend
    d["month_sin"] = np.sin(2 * np.pi * d["month"].dt.month / 12)
    d["month_cos"] = np.cos(2 * np.pi * d["month"].dt.month / 12)
    months = np.sort(d["month"].unique())
    pos = {m: i / (len(months) - 1) for i, m in enumerate(months)}
    d["time_trend"] = d["month"].map(pos)

    # target: next month, same state
    d["y_log_next"] = g["log_total"].shift(-1)
    d["y_level_next"] = g["ev_total"].shift(-1)
    # Residual target: next month's log *change*. Predicting the level forces a
    # network to spend its capacity re-learning the identity map
    # (y_next ~= log_total) before it can model anything, and standardised inputs
    # make that map awkward to represent. Predicting the change removes it, and
    # the naive forecast becomes exactly "predict 0". This is the fair framing
    # for a network; both are run, because the gap between them is the finding.
    d["y_delta_next"] = d["y_log_next"] - d["log_total"]

    # a full look-back for every row, so all models see identical rows
    d = d.dropna(subset=FEATURES + ["y_log_next", "y_delta_next"]).reset_index(drop=True)
    return d


FEATURES = (
    [f"log_lag{L}" for L in LAGS]
    + [f"log_roll{R}" for R in ROLLS]
    + ["log_total", "log_growth_1m", "log_growth_3m", "log_growth_12m", "accel_3m",
       "share_2w_own", "share_4w_own", "share_3w_own",
       "share_national", "log_size_12m", "month_sin", "month_cos", "time_trend"]
)


# =====================================================================
# Metrics
# =====================================================================
def regression_scores(y_log, p_log):
    """Errors on the log scale (what is fitted) and the level scale (what is read)."""
    y_log, p_log = np.asarray(y_log, float), np.asarray(p_log, float)
    y_lvl, p_lvl = np.expm1(y_log), np.clip(np.expm1(p_log), 0, None)
    denom = (np.abs(y_lvl) + np.abs(p_lvl)) / 2
    smape = np.mean(np.where(denom > 0, np.abs(y_lvl - p_lvl) / np.where(denom > 0, denom, 1), 0.0))
    return {
        "mae_log": float(np.mean(np.abs(y_log - p_log))),
        "rmse_log": float(np.sqrt(np.mean((y_log - p_log) ** 2))),
        "mae_level": float(np.mean(np.abs(y_lvl - p_lvl))),
        "smape_level": float(smape),
        "n": int(len(y_log)),
    }


# =====================================================================
# Comparison
# =====================================================================
def volume_comparison(d=None, train_end=VOLUME_TRAIN_END, n_seeds=N_SEEDS,
                      target_mode="delta"):
    """Compare networks, a ridge and four baselines on next-month state volume.

    target_mode
        "level"  fit y = log1p(registrations) at t+1 directly
        "delta"  fit y = log change from t to t+1, then add log_total back

    Scores are always computed on the reconstructed log level, so the two modes
    are directly comparable.
    """
    if d is None:
        d = build_volume_features()
    if target_mode not in {"level", "delta"}:
        raise ValueError(target_mode)

    train = d[d["month"] <= train_end]
    test = d[d["month"] > train_end]

    y_col = "y_log_next" if target_mode == "level" else "y_delta_next"
    # what must be added back to a prediction to put it on the log-level scale
    offset_train = 0.0 if target_mode == "level" else train["log_total"].to_numpy()
    offset_test = 0.0 if target_mode == "level" else test["log_total"].to_numpy()

    rows = []

    # --- unfitted baselines, straight from the lag columns
    naive = test["log_total"].to_numpy()                 # random walk: next = this
    rows.append({"model": "Naive (last month)", "seed": None, "family": "baseline",
                 **regression_scores(test["y_log_next"], naive)})
    rows.append({"model": "Seasonal naive (12m)", "seed": None, "family": "baseline",
                 **regression_scores(test["y_log_next"], test["log_lag12"].to_numpy())})
    drift = test["log_total"].to_numpy() + train["log_growth_1m"].mean()
    rows.append({"model": "Drift (last + mean growth)", "seed": None, "family": "baseline",
                 **regression_scores(test["y_log_next"], drift)})
    mean_only = mean_baseline_reg().fit(train[FEATURES], train[y_col])
    rows.append({"model": "Mean (train)", "seed": None, "family": "baseline",
                 **regression_scores(test["y_log_next"],
                                     mean_only.predict(test[FEATURES]) + offset_test)})

    # --- fitted models
    for name, (maker, needs_seed) in volume_models().items():
        seeds = seed_list(n_seeds) if needs_seed else [None]
        for seed in seeds:
            model = (maker(seed=seed) if needs_seed else maker())
            model.fit(train[FEATURES], train[y_col])
            p = model.predict(test[FEATURES]) + offset_test
            rows.append({"model": name, "seed": seed,
                         "family": "network" if needs_seed else "linear",
                         **regression_scores(test["y_log_next"], p)})

    per_seed = pd.DataFrame(rows)
    per_seed["target_mode"] = target_mode

    naive_mae = per_seed.loc[per_seed["model"] == "Naive (last month)", "mae_log"].iloc[0]
    per_seed["skill_vs_naive"] = 1 - per_seed["mae_log"] / naive_mae

    averaged = (per_seed.groupby(["model", "family"], as_index=False)
                .agg(mae_log=("mae_log", "mean"), mae_log_sd=("mae_log", "std"),
                     rmse_log=("rmse_log", "mean"),
                     mae_level=("mae_level", "mean"),
                     smape_level=("smape_level", "mean"),
                     skill_vs_naive=("skill_vs_naive", "mean"),
                     n_seeds=("seed", lambda s: int(s.notna().sum()) or 1))
                .sort_values("mae_log"))

    info = {"states": int(d["state"].nunique()),
            "train_rows": len(train), "test_rows": len(test),
            "train_months": int(train["month"].nunique()),
            "test_months": int(test["month"].nunique()),
            "train_end": str(pd.Timestamp(train_end).date()),
            "test_start": str(test["month"].min().date()),
            "test_end": str(test["month"].max().date()),
            "n_features": len(FEATURES), "target_mode": target_mode}
    return per_seed, averaged, info


def per_state_breakdown(d=None, train_end=VOLUME_TRAIN_END, seed=RANDOM_STATE,
                        best_model="MLP (64,32)"):
    """Does the best network beat the naive forecast everywhere, or only on big states?

    A headline MAE can be carried entirely by the largest states. This splits the
    test error by state so that is visible.
    """
    if d is None:
        d = build_volume_features()
    train = d[d["month"] <= train_end]
    test = d[d["month"] > train_end].copy()

    maker, _ = volume_models()[best_model]
    model = maker(seed=seed).fit(train[FEATURES], train["y_delta_next"])
    test["p_mlp"] = model.predict(test[FEATURES]) + test["log_total"]
    test["p_naive"] = test["log_total"]

    rows = []
    for state, grp in test.groupby("state", observed=True):
        mlp = regression_scores(grp["y_log_next"], grp["p_mlp"])
        nai = regression_scores(grp["y_log_next"], grp["p_naive"])
        rows.append({"state": state, "n_test": mlp["n"],
                     "mean_level": float(np.expm1(grp["log_total"]).mean()),
                     "mae_log_mlp": mlp["mae_log"], "mae_log_naive": nai["mae_log"],
                     "skill_vs_naive": 1 - mlp["mae_log"] / nai["mae_log"] if nai["mae_log"] else np.nan})
    out = pd.DataFrame(rows).sort_values("mean_level", ascending=False)
    return out


def fit_diagnostics(d=None, train_end=VOLUME_TRAIN_END, n_seeds=N_SEEDS,
                    target_mode="delta"):
    """Training error vs test error, which separates the two ways a model can fail.

    train << test  -> overfitting: the model memorised the training months.
    train ~= test, both no better than naive -> the signal is not there to fit.

    This is the difference between "wrong architecture" and "wrong target", and
    it is the number that decides whether tuning would help.
    """
    if d is None:
        d = build_volume_features()
    train = d[d["month"] <= train_end]
    test = d[d["month"] > train_end]
    y_col = "y_log_next" if target_mode == "level" else "y_delta_next"
    off_tr = 0.0 if target_mode == "level" else train["log_total"].to_numpy()
    off_te = 0.0 if target_mode == "level" else test["log_total"].to_numpy()

    rows = [{"model": "Naive (last month)", "family": "baseline",
             "mae_log_train": regression_scores(train["y_log_next"], train["log_total"])["mae_log"],
             "mae_log_test": regression_scores(test["y_log_next"], test["log_total"])["mae_log"]}]

    for name, (maker, needs_seed) in volume_models().items():
        seeds = seed_list(n_seeds) if needs_seed else [None]
        tr_errs, te_errs = [], []
        for seed in seeds:
            model = (maker(seed=seed) if needs_seed else maker())
            model.fit(train[FEATURES], train[y_col])
            tr_errs.append(regression_scores(
                train["y_log_next"], model.predict(train[FEATURES]) + off_tr)["mae_log"])
            te_errs.append(regression_scores(
                test["y_log_next"], model.predict(test[FEATURES]) + off_te)["mae_log"])
        rows.append({"model": name, "family": "network" if needs_seed else "linear",
                     "mae_log_train": float(np.mean(tr_errs)),
                     "mae_log_test": float(np.mean(te_errs))})

    out = pd.DataFrame(rows)
    out["gap"] = out["mae_log_test"] - out["mae_log_train"]
    out["target_mode"] = target_mode
    return out


def learning_curve(d=None, train_end=VOLUME_TRAIN_END, seed=RANDOM_STATE,
                   fractions=(0.25, 0.5, 0.75, 1.0), model_name="MLP (64,32)",
                   target_mode="delta"):
    """Test error as a function of how much of the training window is used.

    Taken from the most recent months backwards, so each slice is a contiguous
    block ending at the cut-off rather than a random sample of history. A curve
    still falling at 100% means more data would help; a flat one means it would not.
    """
    if d is None:
        d = build_volume_features()
    train = d[d["month"] <= train_end]
    test = d[d["month"] > train_end]
    y_col = "y_log_next" if target_mode == "level" else "y_delta_next"
    off_te = 0.0 if target_mode == "level" else test["log_total"].to_numpy()

    months = np.sort(train["month"].unique())
    maker, needs_seed = volume_models()[model_name]

    rows = []
    for frac in fractions:
        keep = months[-max(2, int(round(len(months) * frac))):]
        sub = train[train["month"].isin(keep)]
        model = (maker(seed=seed) if needs_seed else maker())
        model.fit(sub[FEATURES], sub[y_col])
        sc = regression_scores(test["y_log_next"], model.predict(test[FEATURES]) + off_te)
        rows.append({"fraction": frac, "train_months": len(keep), "train_rows": len(sub),
                     "mae_log_test": sc["mae_log"]})
    out = pd.DataFrame(rows)
    out["model"] = model_name
    return out


def run():
    RESULTS.mkdir(parents=True, exist_ok=True)
    d = build_volume_features()

    frames, summaries, infos = [], [], {}
    for mode in ("level", "delta"):
        per_seed, averaged, info = volume_comparison(d, target_mode=mode)
        averaged["target_mode"] = mode
        frames.append(per_seed)
        summaries.append(averaged)
        infos[mode] = info

    pd.concat(frames, ignore_index=True).to_csv(RESULTS / "volume_per_seed.csv", index=False)
    summary = pd.concat(summaries, ignore_index=True)
    summary.to_csv(RESULTS / "volume_summary.csv", index=False)

    by_state = per_state_breakdown(d)
    by_state.to_csv(RESULTS / "volume_by_state.csv", index=False)

    diag = pd.concat([fit_diagnostics(d, target_mode=m) for m in ("level", "delta")],
                     ignore_index=True)
    diag.to_csv(RESULTS / "volume_fit_diagnostics.csv", index=False)

    curve = learning_curve(d)
    curve.to_csv(RESULTS / "volume_learning_curve.csv", index=False)

    return {"volume": summary, "volume_info": infos, "by_state": by_state,
            "diagnostics": diag, "learning_curve": curve}


if __name__ == "__main__":
    out = run()
    pd.set_option("display.width", 200, "display.max_columns", 50)
    print("\n=== volume design ===")
    for k, v in out["volume_info"]["delta"].items():
        print(f"  {k}: {v}")
    for mode in ("level", "delta"):
        print(f"\n=== next-month state EV registrations, target = {mode} ===")
        sub = out["volume"][out["volume"]["target_mode"] == mode].drop(columns=["target_mode"])
        print(sub.to_string(index=False))
    print("\n=== train vs test error (delta target) ===")
    dg = out["diagnostics"]
    print(dg[dg["target_mode"] == "delta"].drop(columns=["target_mode"]).to_string(index=False))
    print("\n=== learning curve, MLP (64,32) ===")
    print(out["learning_curve"].to_string(index=False))
    bs = out["by_state"]
    print(f"\n=== per-state: MLP (64,32) beats naive in {int((bs['skill_vs_naive'] > 0).sum())}"
          f"/{len(bs)} states ===")
    print(bs.head(12).to_string(index=False))
