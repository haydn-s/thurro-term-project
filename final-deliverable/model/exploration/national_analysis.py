"""Primary question: does national EV production growth lead investment announcements?

Five analyses, each writes a CSV to results/national/:

    1. lead_lag_scan       Poisson: announcements in t+k  ~  production growth at t   (k = 1..6)
    2. cross_correlation   does production lead announcements, or the other way round?
    3. granger             Granger causality tests in both directions
    4. model_comparison    7 models x 3 target definitions x 2 horizons, walk-forward
    5. ablation            which feature groups actually help, on top of trend + seasonality
    6. placebo             does the real production timing beat randomly shifted timing?
    7. interpretation      full-sample coefficients and feature importances
"""
import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy.stats import spearmanr
from statsmodels.tsa.stattools import grangercausalitytests

import feature_engineering as fe
from config import (FIRST_TEST, HORIZONS, MAIN_HORIZON, MAIN_TARGET, N_PLACEBO, RESULTS,
                    TARGETS)
from evaluation import bootstrap_vs, placebo_test, score, walk_forward
from models import NATIONAL_MODELS, logit_l1, logit_l2, random_forest

OUT = RESULTS / "national"


def resolve_features(name, target):
    """Turn a feature-list name used in models.py into actual column names."""
    if name == "controls":
        return fe.CONTROLS
    if name == "core":
        return fe.CORE_FEATURES
    if name == "all":
        return fe.feature_sets(target)["all"]
    raise ValueError(name)


def y_cols(target, horizon):
    return f"y_any_{target}_h{horizon}", f"y_count_{target}_h{horizon}"


# ---------------------------------------------------------------------------
# 1-3. In-sample tests of the lead itself
# ---------------------------------------------------------------------------
def lead_lag_scan(df, target=MAIN_TARGET):
    """Poisson GLM, one regression per lead k:
        announcements in month t+k  ~  growth signal at t  +  time trend
    A leading signal shows up as a positive, significant coefficient at some k.
    IRR (incidence-rate ratio) = exp(coef): the multiplier on the expected number
    of announcements for +1 log-point of growth.
    """
    rows = []
    for signal in ["prod_growth_1m", "prod_growth_3m", "prod_growth_6m"]:  # one at a time, so no collinearity
        for k in range(1, 7):
            y_col = f"events_next_{target}" if k == 1 else f"events_t{k}_{target}"
            d = df.dropna(subset=[y_col, signal])
            X = sm.add_constant(d[[signal, "time_trend"]])
            fit = sm.GLM(d[y_col], X, family=sm.families.Poisson()).fit()
            rows.append({"signal": signal, "lead_months": k, "coef": fit.params[signal],
                         "std_err": fit.bse[signal], "p_value": fit.pvalues[signal],
                         "irr": np.exp(fit.params[signal]), "p_trend": fit.pvalues["time_trend"],
                         "n": int(fit.nobs)})
    return pd.DataFrame(rows)


def cross_correlation(df, target=MAIN_TARGET):
    """Spearman correlation between production growth at t and announcements at t+k.

    k > 0: production first, announcements later (the hypothesis).
    k < 0: announcements first, production later (new plants raising output).
    """
    counts = df[f"events_now_{target}"]
    rows = []
    for k in range(-6, 7):
        future = counts.shift(-k)
        d = pd.DataFrame({"x": df["prod_growth_1m"], "y": future}).dropna()
        rho, p = spearmanr(d["x"], d["y"])
        rows.append({"k_months": k, "spearman_rho": rho, "p_value": p, "n": len(d)})
    return pd.DataFrame(rows)


def granger(df, target=MAIN_TARGET, max_lag=4):
    """Granger causality: do past values of X improve the forecast of Y beyond Y's own past?

    Tested both ways. Reported p-value is the F-test for each lag length.
    """
    data = df[[f"events_now_{target}", "prod_growth_1m"]].dropna()
    rows = []
    for direction, cols in [("production -> announcements", [f"events_now_{target}", "prod_growth_1m"]),
                            ("announcements -> production", ["prod_growth_1m", f"events_now_{target}"])]:
        res = grangercausalitytests(data[cols], maxlag=max_lag)
        for lag, out in res.items():
            f_stat, p, _, _ = out[0]["ssr_ftest"]
            rows.append({"direction": direction, "lags": lag, "f_stat": f_stat, "p_value": p})
    return pd.DataFrame(rows)


def dispersion_check(df, target=MAIN_TARGET):
    """Is a Poisson model enough, or are counts over-dispersed (need negative binomial)?

    Pearson chi2 / df near 1 -> Poisson is fine; well above 1 -> use negative binomial.
    """
    y = df[f"events_next_{target}"]
    d = df.dropna(subset=[f"events_next_{target}"])
    X = sm.add_constant(d[fe.CORE_FEATURES])
    pois = sm.GLM(d[f"events_next_{target}"], X, family=sm.families.Poisson()).fit()
    ratio = pois.pearson_chi2 / pois.df_resid
    try:
        nb = sm.NegativeBinomial(d[f"events_next_{target}"],
                                 sm.add_constant(d[["prod_growth_3m", "time_trend"]])).fit(disp=0)
        nb_alpha, nb_p = nb.params["alpha"], nb.pvalues["prod_growth_3m"]
    except Exception:
        nb_alpha, nb_p = np.nan, np.nan
    return pd.DataFrame([{"mean_count": y.mean(), "var_count": y.var(),
                          "poisson_pearson_chi2_per_df": ratio,
                          "negbin_alpha": nb_alpha, "negbin_p_prod_growth_3m": nb_p}])


# ---------------------------------------------------------------------------
# 4. Model comparison
# ---------------------------------------------------------------------------
def model_comparison(df):
    """Every model, for every target definition and horizon, scored out of sample."""
    rows, main_preds = [], None
    for target in TARGETS:
        for h in HORIZONS:
            y_any, y_count = y_cols(target, h)
            preds = {}
            for name, spec in NATIONAL_MODELS.items():
                feats = resolve_features(spec["features"], target)
                preds[name] = walk_forward(df, feats, y_any, y_count, spec, FIRST_TEST, h)
            base = preds["Baseline (base rate)"]
            for name, p in preds.items():
                row = {"target": target, "horizon": h, "model": name, **score(p["y"], p["p"])}
                row.update(bootstrap_vs(p["y"], p["p"], base["p"]))
                rows.append(row)
            if target == MAIN_TARGET and h == MAIN_HORIZON:
                main_preds = base[["month", "y"]].copy()
                for name, p in preds.items():
                    main_preds[name] = p["p"].values

    table = pd.DataFrame(rows)
    base_brier = table[table["model"] == "Baseline (base rate)"].set_index(["target", "horizon"])["brier"]
    table["brier_skill"] = 1 - table["brier"] / table.set_index(["target", "horizon"]).index.map(base_brier)
    return table, main_preds


# ---------------------------------------------------------------------------
# 5. Ablation: which feature groups help?
# ---------------------------------------------------------------------------
def ablation(df, target=MAIN_TARGET, horizon=MAIN_HORIZON):
    y_any, y_count = y_cols(target, horizon)
    specs = {"Logit L2": {"kind": "prob", "make": logit_l2},
             "Random forest": {"kind": "prob", "make": random_forest}}
    base = walk_forward(df, fe.CONTROLS, y_any, y_count, NATIONAL_MODELS["Baseline (base rate)"],
                        FIRST_TEST, horizon)
    rows = []
    for set_name, feats in fe.feature_sets(target).items():
        for model_name, spec in specs.items():
            p = walk_forward(df, feats, y_any, y_count, spec, FIRST_TEST, horizon)
            row = {"feature_set": set_name, "n_features": len(feats), "model": model_name,
                   **score(p["y"], p["p"])}
            row.update(bootstrap_vs(p["y"], p["p"], base["p"]))
            row["brier_skill"] = 1 - row["brier"] / score(base["y"], base["p"])["brier"]
            rows.append(row)
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# 6. Placebo
# ---------------------------------------------------------------------------
def placebo(df, target=MAIN_TARGET, horizon=MAIN_HORIZON):
    y_any, y_count = y_cols(target, horizon)
    core_prod = [c for c in fe.CORE_FEATURES if c.startswith("prod_")]
    mix_set = fe.feature_sets(target)["controls+production+mix"]
    mix_prod = fe.PRODUCTION + fe.SEGMENT_MIX
    # (label, model spec, features, columns whose timing gets shifted)
    runs = [("Logit L2, core", NATIONAL_MODELS["Logit L2, core"], fe.CORE_FEATURES, core_prod),
            ("Poisson, core", NATIONAL_MODELS["Poisson, core"], fe.CORE_FEATURES, core_prod),
            ("Logit L2, controls+production+mix (best ablation set)",
             {"kind": "prob", "make": logit_l2}, mix_set, mix_prod)]
    rows, dists = [], {}
    for name, spec, feats, shuffle_cols in runs:
        res = placebo_test(df, feats, shuffle_cols, y_any, y_count, spec,
                           FIRST_TEST, horizon, N_PLACEBO)
        dists[name] = res.pop("placebo_briers")
        rows.append({"model": name, "n_placebo_runs": N_PLACEBO, **res})
    return pd.DataFrame(rows), dists


# ---------------------------------------------------------------------------
# 7. Interpretation: what do the fitted models lean on? (full sample, in-sample)
# ---------------------------------------------------------------------------
def interpretation(df, target=MAIN_TARGET, horizon=MAIN_HORIZON):
    y_any, y_count = y_cols(target, horizon)
    d = df.dropna(subset=[y_any])
    all_feats = fe.feature_sets(target)["all"]

    # Poisson GLM on the core features with p-values (classical inference)
    X = sm.add_constant(d[fe.CORE_FEATURES])
    glm = sm.GLM(d[y_count], X, family=sm.families.Poisson()).fit()
    glm_table = pd.DataFrame({"coef": glm.params, "std_err": glm.bse, "p_value": glm.pvalues,
                              "irr": np.exp(glm.params)}).drop(index="const")

    # lasso: which features survive the penalty? (standardised coefficients)
    lasso = logit_l1().fit(d[all_feats], d[y_any])
    lasso_coef = pd.Series(lasso[-1].coef_[0], index=all_feats, name="lasso_coef")

    # random forest importance
    rf = random_forest().fit(d[all_feats], d[y_any])
    rf_imp = pd.Series(rf.feature_importances_, index=all_feats, name="rf_importance")

    importance = pd.concat([lasso_coef, rf_imp], axis=1).sort_values("rf_importance", ascending=False)
    importance["group"] = importance.index.map(feature_group)
    return glm_table, importance


def feature_group(col):
    for name, cols in [("controls", fe.CONTROLS), ("production", fe.PRODUCTION),
                       ("segment mix", fe.SEGMENT_MIX), ("industry", fe.INDUSTRY),
                       ("demand", fe.DEMAND)]:
        if col in cols:
            return name
    return "history" if col.startswith("events_") else "other"


# ---------------------------------------------------------------------------
def run():
    OUT.mkdir(parents=True, exist_ok=True)
    df = fe.national_features()
    df.to_csv(OUT / "national_features.csv", index=False)
    y_any, _ = y_cols(MAIN_TARGET, MAIN_HORIZON)
    print(f"National sample: {len(df)} months, {df['month'].min():%Y-%m} -> {df['month'].max():%Y-%m}; "
          f"{int(df[y_any].sum())} months with an announcement next month "
          f"(target={MAIN_TARGET}, h={MAIN_HORIZON})")

    results = {}
    results["lead_lag"] = lead_lag_scan(df)
    results["ccf"] = cross_correlation(df)
    results["granger"] = granger(df)
    results["dispersion"] = dispersion_check(df)
    results["comparison"], results["main_preds"] = model_comparison(df)
    results["ablation"] = ablation(df)
    results["placebo"], results["placebo_dists"] = placebo(df)
    results["glm"], results["importance"] = interpretation(df)

    results["lead_lag"].to_csv(OUT / "1_lead_lag_scan.csv", index=False)
    results["ccf"].to_csv(OUT / "2_cross_correlation.csv", index=False)
    results["granger"].to_csv(OUT / "3_granger.csv", index=False)
    results["dispersion"].to_csv(OUT / "3b_dispersion.csv", index=False)
    results["comparison"].to_csv(OUT / "4_model_comparison.csv", index=False)
    results["main_preds"].to_csv(OUT / "4b_walk_forward_predictions.csv", index=False)
    results["ablation"].to_csv(OUT / "5_ablation.csv", index=False)
    results["placebo"].to_csv(OUT / "6_placebo.csv", index=False)
    results["glm"].to_csv(OUT / "7a_poisson_glm_core.csv")
    results["importance"].to_csv(OUT / "7b_feature_importance.csv")
    return df, results
