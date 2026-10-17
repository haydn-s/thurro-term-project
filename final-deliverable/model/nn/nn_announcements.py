"""Track A: can a network do what the linear models could not, on the project's
own research question?

This reuses the shared study's features, splits, targets and metrics without
editing any of them, so the numbers land in the same table as the 7 national and
9 state models already compared in ../exploratory-models-card.md. The only new
thing is the model class.

The point of this file is not to win. On the national task a training fold is
16-33 months with 11 events in total; on the state task there are 2,479 training
rows but only **7** positive ones. Those are the numbers that decide the result,
and they are reported alongside it so the scores are read in that light.
"""
import warnings
from functools import partial

import numpy as np
import pandas as pd

from nn_config import N_SEEDS, RANDOM_STATE, RESULTS

# the shared study -- imported, never modified
import feature_engineering as fe
from config import (FIRST_TEST, MAIN_HORIZON, MAIN_TARGET, N_PLACEBO,
                    STATE_TRAIN_END, TOP_K)
from evaluation import bootstrap_vs, placebo_test, score, walk_forward
from models import NATIONAL_MODELS
from national_analysis import resolve_features, y_cols
from state_analysis import EPS as STATE_EPS
from state_analysis import top_k_hit_rate

from nn_models import (baseline_clf, mlp_deep, mlp_small, mlp_tiny,
                       national_nn_models, seed_list, summarise_seeds)

# MLPClassifier warns about non-convergence constantly on 16-row folds. That is
# expected here, not news, and it would bury the actual output.
warnings.filterwarnings("ignore")


# =====================================================================
# National: walk-forward, one month at a time
# =====================================================================
def national_comparison(df, target=MAIN_TARGET, horizon=MAIN_HORIZON, n_seeds=N_SEEDS):
    """Run each network under several seeds through the study's own walk-forward.

    Returns (per-seed table, seed-averaged table, baseline predictions).
    """
    y_any, y_count = y_cols(target, horizon)

    base_spec = NATIONAL_MODELS["Baseline (base rate)"]
    base = walk_forward(df, fe.CONTROLS, y_any, y_count, base_spec, FIRST_TEST, horizon)

    # the best linear and tree models from the shared study, as reference points
    reference = {name: NATIONAL_MODELS[name] for name in
                 ["Logit L2, core", "Logit L1 (lasso), all", "Random forest, all"]}

    rows = []
    for name, spec in reference.items():
        feats = resolve_features(spec["features"], target)
        res = walk_forward(df, feats, y_any, y_count, spec, FIRST_TEST, horizon)
        rows.append({"model": name, "seed": None, "family": "reference",
                     **score(res["y"], res["p"]),
                     **bootstrap_vs(res["y"], res["p"], base["p"])})

    for name, spec in national_nn_models().items():
        feats = resolve_features(spec["features"], target)
        for seed in seed_list(n_seeds):
            seeded = dict(spec, make=partial(spec["make"], seed=seed))
            res = walk_forward(df, feats, y_any, y_count, seeded, FIRST_TEST, horizon)
            rows.append({"model": name, "seed": seed, "family": "network",
                         **score(res["y"], res["p"]),
                         **bootstrap_vs(res["y"], res["p"], base["p"])})

    per_seed = pd.DataFrame(rows)
    per_seed.insert(0, "n_features", [len(resolve_features(
        (reference | national_nn_models())[m]["features"], target)) for m in per_seed["model"]])

    base_brier = score(base["y"], base["p"])["brier"]
    per_seed["brier_skill"] = 1 - per_seed["brier"] / base_brier

    averaged = (per_seed.groupby(["model", "family", "n_features"], as_index=False)
                .agg(brier_mean=("brier", "mean"), brier_sd=("brier", "std"),
                     brier_min=("brier", "min"), brier_max=("brier", "max"),
                     auc_mean=("auc", "mean"), log_loss_mean=("log_loss", "mean"),
                     skill_mean=("brier_skill", "mean"),
                     gain_ci_low=("gain_ci_low", "mean"),
                     gain_ci_high=("gain_ci_high", "mean"),
                     n_seeds=("seed", lambda s: int(s.notna().sum()) or 1))
                .sort_values("brier_mean"))

    baseline_row = pd.DataFrame([{
        "model": "Baseline (base rate)", "family": "baseline",
        "n_features": 0, "brier_mean": base_brier, "brier_sd": 0.0,
        "brier_min": base_brier, "brier_max": base_brier,
        "auc_mean": score(base["y"], base["p"])["auc"],
        "log_loss_mean": score(base["y"], base["p"])["log_loss"],
        "skill_mean": 0.0, "gain_ci_low": 0.0, "gain_ci_high": 0.0, "n_seeds": 1}])
    averaged = pd.concat([baseline_row, averaged], ignore_index=True)

    info = {"test_months": len(base), "events_in_test": int(base["y"].sum()),
            "train_rows_first_fold": FIRST_TEST - horizon + 1,
            "train_rows_last_fold": len(df.dropna(subset=[y_any])) - horizon,
            "total_usable_months": int(df[y_any].notna().sum()),
            "total_events": int(df[y_any].sum())}
    return per_seed, averaged, base, info


def national_placebo(df, target=MAIN_TARGET, horizon=MAIN_HORIZON, n_runs=N_PLACEBO,
                     n_seeds=3):
    """The study's circular-shift placebo, applied to the networks.

    Slide the production columns along the calendar, refit, rescore. A network
    that has genuinely found a lead should beat most shifted copies; one that is
    fitting the trend or the noise will score the same against a fake calendar
    as against the real one. This is the check that decides whether a good Brier
    on 18 test months means anything, so it runs on every network that looked
    competitive, under several seeds each.
    """
    y_any, y_count = y_cols(target, horizon)
    runs = [("MLP (4), core", mlp_tiny, "core"),
            ("MLP (8), core", mlp_small, "core"),
            ("MLP (8), all", mlp_small, "all"),
            ("MLP (32,16), all", mlp_deep, "all")]

    rows = []
    for name, maker, feature_set in runs:
        feats = resolve_features(feature_set, target)
        shuffle_cols = [c for c in feats if c.startswith("prod_")]
        for seed in seed_list(n_seeds):
            spec = {"kind": "prob", "features": feature_set,
                    "make": partial(maker, seed=seed)}
            res = placebo_test(df, feats, shuffle_cols, y_any, y_count, spec,
                               FIRST_TEST, horizon, n_runs)
            res.pop("placebo_briers", None)
            rows.append({"model": name, "seed": seed,
                         "n_shuffled_cols": len(shuffle_cols), **res})
    per_seed = pd.DataFrame(rows)
    averaged = (per_seed.groupby("model", as_index=False)
                .agg(real_brier=("real_brier", "mean"),
                     placebo_brier_median=("placebo_brier_median", "mean"),
                     share_placebo_better_or_equal=("share_placebo_better_or_equal", "mean"),
                     share_sd=("share_placebo_better_or_equal", "std"),
                     n_seeds=("seed", "count")))
    return per_seed, averaged


def national_ablation(df, target=MAIN_TARGET, horizon=MAIN_HORIZON, n_seeds=N_SEEDS):
    """Feature groups added one at a time, as the shared study's ablation does.

    This is the test the project's question actually needs. A network that beats
    the baseline only because it models the trend has found nothing about EV
    production; one whose advantage appears when the production columns are added
    has found something worth placebo-testing.

    Read the winner with care: this picks the best of several feature sets, and
    the interval around it carries no correction for that choice. The placebo
    below is the check that does not have that problem.
    """
    y_any, y_count = y_cols(target, horizon)
    base_spec = NATIONAL_MODELS["Baseline (base rate)"]
    base = walk_forward(df, fe.CONTROLS, y_any, y_count, base_spec, FIRST_TEST, horizon)
    base_brier = score(base["y"], base["p"])["brier"]

    sets = fe.feature_sets(target)
    order = ["controls", "controls+history", "controls+production",
             "controls+demand", "controls+industry", "controls+production+mix", "all"]

    rows = []
    for set_name in order:
        feats = sets[set_name]
        for model_name, maker in [("MLP (8)", mlp_small), ("MLP (4)", mlp_tiny)]:
            for seed in seed_list(n_seeds):
                spec = {"kind": "prob", "features": set_name,
                        "make": partial(maker, seed=seed)}
                res = walk_forward(df, feats, y_any, y_count, spec, FIRST_TEST, horizon)
                rows.append({"feature_set": set_name, "n_features": len(feats),
                             "model": model_name, "seed": seed,
                             **score(res["y"], res["p"]),
                             **bootstrap_vs(res["y"], res["p"], base["p"])})

    per_seed = pd.DataFrame(rows)
    per_seed["brier_skill"] = 1 - per_seed["brier"] / base_brier
    averaged = (per_seed.groupby(["model", "feature_set", "n_features"], as_index=False)
                .agg(brier_mean=("brier", "mean"), brier_sd=("brier", "std"),
                     auc_mean=("auc", "mean"), skill_mean=("brier_skill", "mean"),
                     gain_ci_low=("gain_ci_low", "mean"),
                     gain_ci_high=("gain_ci_high", "mean"),
                     n_seeds=("seed", "count")))
    # keep the study's own group order rather than sorting by score
    averaged["_ord"] = averaged["feature_set"].map({n: i for i, n in enumerate(order)})
    averaged = averaged.sort_values(["model", "_ord"]).drop(columns=["_ord"])
    return per_seed, averaged, base_brier


def placebo_for_set(df, feature_set, maker, model_name, target=MAIN_TARGET,
                    horizon=MAIN_HORIZON, n_runs=N_PLACEBO, n_seeds=3):
    """Circular-shift placebo for one feature set.

    Broken out so the best ablation set can be placebo-tested on its own -- that
    is the number the national result turns on, and a good Brier without it is
    not evidence of a lead.
    """
    y_any, y_count = y_cols(target, horizon)
    feats = resolve_features(feature_set, target) if feature_set in {"controls", "core", "all"} \
        else fe.feature_sets(target)[feature_set]
    shuffle_cols = [c for c in feats if c.startswith("prod_")]

    rows = []
    for seed in seed_list(n_seeds):
        spec = {"kind": "prob", "features": feature_set, "make": partial(maker, seed=seed)}
        res = placebo_test(df, feats, shuffle_cols, y_any, y_count, spec,
                           FIRST_TEST, horizon, n_runs)
        res.pop("placebo_briers", None)
        rows.append({"model": model_name, "feature_set": feature_set, "seed": seed,
                     "n_shuffled_cols": len(shuffle_cols), **res})
    per_seed = pd.DataFrame(rows)
    averaged = (per_seed.groupby(["model", "feature_set"], as_index=False)
                .agg(real_brier=("real_brier", "mean"),
                     placebo_brier_median=("placebo_brier_median", "mean"),
                     share_placebo_better_or_equal=("share_placebo_better_or_equal", "mean"),
                     share_sd=("share_placebo_better_or_equal", "std"),
                     n_seeds=("seed", "count")))
    return per_seed, averaged


# =====================================================================
# State: train before the cut-off, test after
# =====================================================================
def state_comparison(sp, n_seeds=N_SEEDS):
    """Same split, metrics and top-k score as state_analysis.model_comparison."""
    cols = fe.STATE_SETS["all"]
    sp = sp.dropna(subset=["y_any"] + cols)
    train = sp[sp["month"] <= STATE_TRAIN_END]
    test = sp[sp["month"] > STATE_TRAIN_END]

    base = np.clip(baseline_clf().fit(train[cols], train["y_any"])
                   .predict_proba(test[cols])[:, 1], STATE_EPS, 1 - STATE_EPS)

    rows = [{"model": "Baseline (base rate)", "seed": None, "family": "baseline",
             **score(test["y_any"], base), f"top{TOP_K}_hit_rate": top_k_hit_rate(test, base),
             **bootstrap_vs(test["y_any"], base, base)}]

    for name, maker in [("MLP (4), all", mlp_tiny), ("MLP (8), all", mlp_small),
                        ("MLP (32,16), all", mlp_deep)]:
        for seed in seed_list(n_seeds):
            model = maker(seed=seed).fit(train[cols], train["y_any"])
            p = np.clip(model.predict_proba(test[cols])[:, 1], STATE_EPS, 1 - STATE_EPS)
            rows.append({"model": name, "seed": seed, "family": "network",
                         **score(test["y_any"], p),
                         f"top{TOP_K}_hit_rate": top_k_hit_rate(test, p),
                         **bootstrap_vs(test["y_any"], p, base)})

    per_seed = pd.DataFrame(rows)
    averaged = (per_seed.groupby(["model", "family"], as_index=False)
                .agg(brier_mean=("brier", "mean"), brier_sd=("brier", "std"),
                     auc_mean=("auc", "mean"), auc_sd=("auc", "std"),
                     avg_precision_mean=("avg_precision", "mean"),
                     top_k_mean=(f"top{TOP_K}_hit_rate", "mean"),
                     n_seeds=("seed", lambda s: int(s.notna().sum()) or 1))
                .sort_values("brier_mean"))

    info = {"train_rows": len(train), "train_events": int(train["y_any"].sum()),
            "test_rows": len(test), "test_events": int(test["y_any"].sum()),
            "n_features": len(cols),
            "train_base_rate": float(train["y_any"].mean())}
    return per_seed, averaged, info


def run():
    RESULTS.mkdir(parents=True, exist_ok=True)

    df = fe.national_features()
    per_seed, averaged, base, info = national_comparison(df)
    per_seed.to_csv(RESULTS / "national_per_seed.csv", index=False)
    averaged.to_csv(RESULTS / "national_summary.csv", index=False)

    pl_per_seed, pl_averaged = national_placebo(df)
    pl_per_seed.to_csv(RESULTS / "national_placebo_per_seed.csv", index=False)
    pl_averaged.to_csv(RESULTS / "national_placebo.csv", index=False)

    sp = fe.state_features(horizon=1)
    s_per_seed, s_averaged, s_info = state_comparison(sp)
    s_per_seed.to_csv(RESULTS / "state_per_seed.csv", index=False)
    s_averaged.to_csv(RESULTS / "state_summary.csv", index=False)

    return {"national": averaged, "national_info": info, "placebo": pl_averaged,
            "state": s_averaged, "state_info": s_info}


if __name__ == "__main__":
    out = run()
    pd.set_option("display.width", 200, "display.max_columns", 50)
    print("\n=== national design ===")
    for k, v in out["national_info"].items():
        print(f"  {k}: {v}")
    print("\n=== national, walk-forward ===")
    print(out["national"].to_string(index=False))
    print("\n=== placebo, circular shift ===")
    print(out["placebo"].to_string(index=False))
    print("\n=== state design ===")
    for k, v in out["state_info"].items():
        print(f"  {k}: {v}")
    print("\n=== state, time-split ===")
    print(out["state"].to_string(index=False))
