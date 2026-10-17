"""Stretch question: does state-level EV demand concentration explain where investment is sited?

Three analyses, each writes a CSV to results/state/:

    1. model_comparison   state x month models, trained before STATE_TRAIN_END and tested after.
                          Scored on Brier / AUC / average precision AND on a plain-language
                          metric: when an announcement happened, was that state in the
                          model's top-5 that month?
    2. inference          full-sample logit with p-values: does demand share still matter
                          once a state's own announcement history is controlled for?
    3. fiscal_year        annual version using every announcement with a state, including the
                          12 dated only to a fiscal year
"""
import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy.stats import spearmanr

import feature_engineering as fe
from config import RESULTS, STATE_TRAIN_END, TOP_K
from evaluation import bootstrap_vs, score
from models import baseline, logit_l2, random_forest

OUT = RESULTS / "state"

# State events are rare (base rate ~0.3%-2%), so clip far less hard than the
# national 0.01, otherwise every low prediction collapses to the same value.
EPS = 1e-4


def state_models():
    """name -> (feature list, model maker). 'Demand-share rank' needs no fitting."""
    models = {"Baseline (base rate)": (["share_total"], baseline),
              "Demand-share rank (no fit)": (["share_total"], None)}
    for set_name, cols in fe.STATE_SETS.items():
        models[f"Logit L2, {set_name}"] = (cols, logit_l2)
    models["Random forest, all"] = (fe.STATE_SETS["all"], random_forest)
    return models


def top_k_hit_rate(test, p, k=TOP_K):
    """Share of (state, month) announcement cells where that state was ranked in the
    model's top-k states for that month."""
    t = test[["state", "month", "y_any"]].copy()
    t["p"] = p
    if np.ptp(p) == 0:
        # a constant prediction cannot rank states: the fair score is a random pick
        return k / t.groupby("month")["state"].nunique().mean()
    t["rank"] = t.groupby("month")["p"].rank(ascending=False, method="first")
    hits = t[t["y_any"] == 1]
    return float((hits["rank"] <= k).mean()) if len(hits) else np.nan


def model_comparison(sp):
    sp = sp.dropna(subset=["y_any"] + fe.STATE_SETS["all"])
    train = sp[sp["month"] <= STATE_TRAIN_END]
    test = sp[sp["month"] > STATE_TRAIN_END]

    preds, rows = {}, []
    for name, (cols, make) in state_models().items():
        if make is None:
            # rank states by last month's demand share; rescale to a probability-like score
            raw = test["share_total"].to_numpy()
            p = raw / raw.max()
        else:
            model = make().fit(train[cols], train["y_any"])
            p = model.predict_proba(test[cols])[:, 1]
        preds[name] = np.clip(p, EPS, 1 - EPS)

    base = preds["Baseline (base rate)"]
    for name, p in preds.items():
        row = {"model": name, **score(test["y_any"], p),
               f"top{TOP_K}_hit_rate": top_k_hit_rate(test, p)}
        row.update(bootstrap_vs(test["y_any"], p, base))
        if name.startswith("Demand-share rank"):
            # an unfitted ranking is not a probability: only rank metrics apply
            for k in ["brier", "log_loss", "brier_gain", "gain_ci_low", "gain_ci_high", "p_gain_le_0"]:
                row[k] = np.nan
        rows.append(row)
    table = pd.DataFrame(rows)
    table["brier_skill"] = 1 - table["brier"] / table.loc[0, "brier"]
    info = {"train_rows": len(train), "train_events": int(train["y_any"].sum()),
            "test_rows": len(test), "test_events": int(test["y_any"].sum())}
    return table, info


def inference(sp):
    """Full-sample logit, coefficients and p-values, from 2023 onward (the window
    where announcements are collected)."""
    d = sp[sp["month"] >= "2023-01-01"].dropna(subset=["y_any"] + fe.STATE_SETS["all"])
    rows = []
    specs = {"share only": ["share_total"],
             "history only": ["past_announcements"],
             "share + history": ["share_total", "past_announcements"],
             "share + 4W share + history": ["share_total", "share_4w", "past_announcements"],
             "share change + history": ["share_change_6m", "past_announcements"]}
    for name, cols in specs.items():
        X = sm.add_constant(d[cols])
        fit = sm.Logit(d["y_any"], X).fit(disp=0)
        for c in cols:
            rows.append({"spec": name, "variable": c, "coef": fit.params[c],
                         "std_err": fit.bse[c], "p_value": fit.pvalues[c],
                         # shares are 0-1, so report the odds ratio per +1 percentage point
                         "odds_ratio": np.exp(fit.params[c] * (0.01 if "share" in c else 1)),
                         "odds_ratio_unit": "per +1pp share" if "share" in c else "per +1 unit",
                         "pseudo_r2": fit.prsquared, "aic": fit.aic, "n": int(fit.nobs),
                         "events": int(d["y_any"].sum())})
    return pd.DataFrame(rows)


def fiscal_year():
    """Annual: announcements per state per FY against previous-FY demand share."""
    fy = fe.state_fiscal_year()
    corr_rows = []
    for year, g in fy.groupby("fy"):
        rho, p = spearmanr(g["prev_share_total"], g["announcements"])
        corr_rows.append({"fy": int(year), "announcements": int(g["announcements"].sum()),
                          "states_with_announcement": int((g["announcements"] > 0).sum()),
                          "spearman_rho_share_vs_count": rho, "p_value": p})
    X = sm.add_constant(pd.concat([fy[["prev_share_total"]],
                                   pd.get_dummies(fy["fy"], prefix="fy", drop_first=True, dtype=float)],
                                  axis=1))
    glm = sm.GLM(fy["announcements"], X, family=sm.families.Poisson()).fit()
    glm_row = pd.DataFrame([{"variable": "prev_share_total", "coef": glm.params["prev_share_total"],
                             "std_err": glm.bse["prev_share_total"],
                             "p_value": glm.pvalues["prev_share_total"],
                             "irr_per_10pp_share": np.exp(glm.params["prev_share_total"] * 0.10),
                             "n": int(glm.nobs)}])
    return fy, pd.DataFrame(corr_rows), glm_row


def run():
    OUT.mkdir(parents=True, exist_ok=True)
    results = {}
    sp1 = fe.state_features(horizon=1)
    sp3 = fe.state_features(horizon=3)
    results["comparison_h1"], results["info_h1"] = model_comparison(sp1)
    results["comparison_h3"], results["info_h3"] = model_comparison(sp3)
    results["inference"] = inference(sp1)
    results["fy_table"], results["fy_corr"], results["fy_glm"] = fiscal_year()

    results["comparison_h1"].to_csv(OUT / "1_state_model_comparison_h1.csv", index=False)
    results["comparison_h3"].to_csv(OUT / "1b_state_model_comparison_h3.csv", index=False)
    results["inference"].to_csv(OUT / "2_state_logit_inference.csv", index=False)
    results["fy_table"].to_csv(OUT / "3_state_fiscal_year_table.csv", index=False)
    results["fy_corr"].to_csv(OUT / "3b_fiscal_year_rank_correlation.csv", index=False)
    results["fy_glm"].to_csv(OUT / "3c_fiscal_year_poisson.csv", index=False)
    print(f"State sample (h=1): {results['info_h1']}")
    return sp1, results
