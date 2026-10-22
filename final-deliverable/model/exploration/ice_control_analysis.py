"""Does the segment-mix signal survive swapping the time trend for an ICE-production control?

Model card next steps (a) and (b). Runs the same walk-forward ablation and
placebo as national_analysis.py, once with the original controls (linear time
trend) and once with CONTROLS_ICE (ICE-production growth instead of the trend).

    python final-deliverable/model/exploration/ice_control_analysis.py

Needs only pandas / scikit-learn, so it runs without statsmodels. Writes to results/national/:
    8_ice_control_ablation.csv       Brier skill per feature set and control set
    8b_ice_control_placebo.csv       real vs shifted-timing Brier for the mix model
    8c_ice_control_placebo_draws.csv the 200 shifted-timing scores behind 8b (for the chart)
    8d_mix_model_by_month.csv        the mix model's walk-forward predictions, month by month
"""
import pandas as pd

import feature_engineering as fe
from config import FIRST_TEST, MAIN_HORIZON, MAIN_TARGET, N_PLACEBO, RESULTS
from evaluation import bootstrap_vs, placebo_test, score, walk_forward
from models import NATIONAL_MODELS, logit_l2

OUT = RESULTS / "national"
VARIANTS = {"time_trend": fe.CONTROLS,           # as published in the model card
            "ice_growth": fe.CONTROLS_ICE}       # trend swapped for ICE growth
SETS = ["controls", "controls+production", "controls+production+mix"]
MIX = "controls+production+mix"
SPEC = {"kind": "prob", "make": logit_l2}


def _cols(target=MAIN_TARGET, horizon=MAIN_HORIZON):
    return f"y_any_{target}_h{horizon}", f"y_count_{target}_h{horizon}"


def ablation(df, target=MAIN_TARGET, horizon=MAIN_HORIZON):
    y_any, y_count = _cols(target, horizon)
    base = walk_forward(df, fe.CONTROLS, y_any, y_count, NATIONAL_MODELS["Baseline (base rate)"],
                        FIRST_TEST, horizon)
    base_brier = score(base["y"], base["p"])["brier"]
    rows = []
    for variant, controls in VARIANTS.items():
        sets = fe.feature_sets(target, controls)
        for set_name in SETS:
            p = walk_forward(df, sets[set_name], y_any, y_count, SPEC, FIRST_TEST, horizon)
            row = {"controls": variant, "feature_set": set_name, **score(p["y"], p["p"])}
            row.update(bootstrap_vs(p["y"], p["p"], base["p"]))
            row["brier_skill"] = 1 - row["brier"] / base_brier
            rows.append(row)
    return pd.DataFrame(rows)


def placebo(df, target=MAIN_TARGET, horizon=MAIN_HORIZON):
    y_any, y_count = _cols(target, horizon)
    shifted = fe.PRODUCTION + fe.SEGMENT_MIX
    rows, draws = [], {}
    for variant, controls in VARIANTS.items():
        feats = fe.feature_sets(target, controls)[MIX]
        res = placebo_test(df, feats, shifted, y_any, y_count, SPEC, FIRST_TEST, horizon, N_PLACEBO)
        draws[variant] = res.pop("placebo_briers")
        rows.append({"controls": variant, "n_placebo_runs": N_PLACEBO, **res})
    return pd.DataFrame(rows), pd.DataFrame(draws)


def mix_by_month(df, target=MAIN_TARGET, horizon=MAIN_HORIZON):
    """Mix model (original controls) vs the base rate, one row per test month.

    brier_gain > 0 means the model beat the base rate that month. Shows how much of
    the total gain comes from a few months.
    """
    y_any, y_count = _cols(target, horizon)
    m = walk_forward(df, fe.feature_sets(target)[MIX], y_any, y_count, SPEC, FIRST_TEST, horizon)
    b = walk_forward(df, fe.CONTROLS, y_any, y_count, NATIONAL_MODELS["Baseline (base rate)"],
                     FIRST_TEST, horizon)
    out = m.rename(columns={"p": "p_model"})
    out["p_base"] = b["p"].values
    out["brier_gain"] = (out["p_base"] - out["y"]) ** 2 - (out["p_model"] - out["y"]) ** 2
    return out


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    df = fe.national_features()
    y_any, _ = _cols()
    print(f"{len(df)} months, {df['month'].min():%Y-%m} -> {df['month'].max():%Y-%m}; "
          f"{df[y_any].notna().sum()} with a known target, {int(df[y_any].sum())} events")
    ab = ablation(df)
    ab.to_csv(OUT / "8_ice_control_ablation.csv", index=False)
    pl, draws = placebo(df)
    pl.to_csv(OUT / "8b_ice_control_placebo.csv", index=False)
    draws.to_csv(OUT / "8c_ice_control_placebo_draws.csv", index=False)
    mix_by_month(df).to_csv(OUT / "8d_mix_model_by_month.csv", index=False)
    cols = ["controls", "feature_set", "brier_skill", "gain_ci_low", "gain_ci_high", "auc"]
    print(ab[cols].round(3).to_string(index=False))
    print(pl.round(3).to_string(index=False))
