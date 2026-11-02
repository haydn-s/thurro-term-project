"""Fit the two outlook models the service serves, and write model/outlook.json.

    .VENV/bin/python final-deliverable/model/build_outlook.py

Run it from the repo-root environment (pandas, scikit-learn, statsmodels), not
the deliverable's: this is the offline half of the outlook. The service only
reads what it writes.

The two models are the ones selected at the end of model development:

  national  Logit L2 on CONTROLS_ICE + PRODUCTION + SEGMENT_MIX, target "all",
            h = 1. P(at least one announcement next month).
  state     Logit L2 on STATE_SETS["share+history"], h = 1. P(a given state is
            named in an announcement next month), served as a ranking.

Both are the exploration study's own specifications, built with its feature
code and model factory, imported from exploration/ rather than copied. This
script fits and exports; it does not define a feature. Changing what the
service serves means changing NATIONAL_FEATURES or STATE_FEATURES below and
re-running.

What the artifact holds, per model: the fitted scaler and coefficients, the
training window, an out-of-sample evaluation re-run on the same data, and the
feature rows for the latest month with the probability scikit-learn gives them.
The service recomputes those probabilities from the coefficients and refuses to
start if it does not get the same numbers, so a hand-edited or truncated
artifact fails at deploy time rather than in the results.

Refit = re-run after data/clean/ changes. test_outlook_build.py fails until you
do, because a committed artifact that no longer matches the data is the one
failure here that nothing else would catch.
"""
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "exploration"))

import feature_engineering as fe  # noqa: E402
from config import CLEAN, FIRST_TEST, STATE_TRAIN_END, TOP_K  # noqa: E402
from evaluation import bootstrap_vs, score, walk_forward  # noqa: E402
from models import NATIONAL_MODELS, logit_l2  # noqa: E402
from state_analysis import model_comparison  # noqa: E402

OUT = HERE / "outlook.json"

#: Bumped when the artifact's layout changes; app/outlook.py refuses any other.
SCHEMA_VERSION = 1

TARGET = "all"
HORIZON = 1
NATIONAL_FEATURES = fe.CONTROLS_ICE + fe.PRODUCTION + fe.SEGMENT_MIX
NATIONAL_SPEC = {"kind": "prob", "make": logit_l2}
STATE_SET = "share+history"
STATE_FEATURES = fe.STATE_SETS[STATE_SET]

#: The files exploration/data.py reads. Hashed into the artifact so a served
#: probability can be traced to the exact inputs it came from.
INPUTS = ["announcements_clean.csv", "production_model_monthly.csv",
          "registrations_segment_monthly.csv", "registrations_state_monthly.csv",
          "ice_production_monthly.csv"]

#: Plain-language descriptions, served beside each feature's contribution so a
#: consumer can read a driver without the feature code.
DESCRIPTIONS = {
    "ice_growth_3m": "3-month log growth in combustion-engine (ICE) vehicle production: the sector cycle",
    "month_sin": "Calendar seasonality, sine of the month",
    "month_cos": "Calendar seasonality, cosine of the month",
    "results_season": "1 in a quarterly results month (Feb, May, Aug, Nov)",
    "prod_growth_1m": "1-month log growth in national EV production",
    "prod_growth_3m": "3-month log growth in national EV production",
    "prod_accel": "3-month EV production growth minus its value three months earlier",
    "prod_vs_6m_max": "EV production against the best of the previous six months",
    "prod_record_high": "1 if EV production set an all-time high this month",
    "prod_2w_growth_3m": "3-month log growth in electric two-wheeler production",
    "prod_3w_growth_3m": "3-month log growth in electric three-wheeler production",
    "pv_share": "Passenger vehicles' share of EV production",
    "three_w_share": "Three-wheelers' share of EV production",
    "export_share": "Exports as a share of EV production",
    "inventory_build_3m": "Units built but neither sold nor exported, as a share of production, 3-month mean",
    "share_total": "State's share of national EV registrations, 3-month rolling",
    "share_4w": "State's share of national electric four-wheeler registrations, 3-month rolling",
    "share_change_6m": "Change in the state's registration share over six months",
    "past_announcements": "Announcements sited in the state up to this month",
    "months_since_last": "Months since the state's last announcement (60 if it has had none)",
    "ever_announced": "1 if the state has had any announcement",
}


def _month(ts) -> str:
    return pd.Timestamp(ts).strftime("%Y-%m-%d")


def _r(x, digits=4):
    """Round a metric for the artifact. Coefficients and features are NOT
    rounded: the service recomputes probabilities from them exactly."""
    return None if x is None or pd.isna(x) else round(float(x), digits)


def _fitted(model, X, y, features):
    """Fit a Logit L2 pipeline and return it with its parameters as plain lists."""
    model.fit(X[features], y)
    scaler = model.named_steps["standardscaler"]
    logit = model.named_steps["logisticregression"]
    params = {
        "features": list(features),
        "descriptions": {f: DESCRIPTIONS[f] for f in features},
        "scaler_mean": [float(v) for v in scaler.mean_],
        "scaler_scale": [float(v) for v in scaler.scale_],
        "coefficients": [float(v) for v in logit.coef_[0]],
        "intercept": float(logit.intercept_[0]),
    }
    return model, params


def _scored_row(model, row, features, **key):
    return {**key, "month": _month(row["month"]),
            "features": {f: float(row[f]) for f in features},
            "probability": float(model.predict_proba(row[features].to_frame().T)[0, 1])}


def _training(rows, y):
    return {"first_month": _month(rows["month"].min()), "last_month": _month(rows["month"].max()),
            "rows": int(len(rows)), "events": int(rows[y].sum()), "base_rate": _r(rows[y].mean())}


def national():
    df = fe.national_features()
    y_any, y_count = f"y_any_{TARGET}_h{HORIZON}", f"y_count_{TARGET}_h{HORIZON}"

    # Out-of-sample evaluation: the same walk-forward, baseline and bootstrap as
    # exploration/ice_control_analysis.py::ablation(), for this one feature set.
    p = walk_forward(df, NATIONAL_FEATURES, y_any, y_count, NATIONAL_SPEC, FIRST_TEST, HORIZON)
    base = walk_forward(df, fe.CONTROLS, y_any, y_count, NATIONAL_MODELS["Baseline (base rate)"],
                        FIRST_TEST, HORIZON)
    s, b = score(p["y"], p["p"]), score(base["y"], base["p"])
    gain = bootstrap_vs(p["y"], p["p"], base["p"])
    per_month = (base["p"] - p["y"]) ** 2 - (p["p"] - p["y"]) ** 2
    top3 = per_month.nlargest(3).sum() / per_month.sum() if per_month.sum() > 0 else np.nan

    # The served fit: every month whose outcome is known, then the latest month.
    train = df.dropna(subset=[y_any])
    model, params = _fitted(logit_l2(), train, train[y_any], NATIONAL_FEATURES)
    latest = df.iloc[-1]

    return {
        "name": "national-announcement-logit",
        "version": f"1.0.0+data.{latest['month']:%Y%m}",
        "description": (
            "Probability that at least one automotive manufacturing-investment "
            "announcement is made in the forecast month, from national EV "
            "production, its segment mix, and ICE-production growth as the "
            "sector-cycle control. L2-regularised logistic regression on "
            "standardised features, refit on every month with a known outcome."),
        "target": TARGET,
        "horizon_months": HORIZON,
        **params,
        "training": _training(train, y_any),
        "evaluation": {
            "design": "walk-forward, expanding window, one month ahead",
            "first_test_month": _month(p["month"].min()),
            "test_months": s["n_test"], "test_events": s["events_in_test"],
            "brier": _r(s["brier"]), "baseline_brier": _r(b["brier"]),
            "brier_skill": _r(1 - s["brier"] / b["brier"]),
            "brier_gain_ci90_low": _r(gain["gain_ci_low"]),
            "brier_gain_ci90_high": _r(gain["gain_ci_high"]),
            "auc": _r(s["auc"]),
            "top3_months_share_of_gain": _r(top3),
        },
        "notes": [
            "Selected as the best of 14 feature-set runs; the walk-forward "
            "interval carries no correction for that choice.",
            "Headline EV production growth adds nothing on its own once ICE "
            "growth replaces the time trend; the signal is in the segment mix "
            "(export share, inventory build).",
            f"{top3:.0%} of the walk-forward Brier gain comes from 3 of "
            f"{s['n_test']} test months.",
            "A probability for the forecast month only: it says nothing about "
            "the size or location of an announcement.",
        ],
        "scored": [_scored_row(model, latest, NATIONAL_FEATURES)],
    }


def state():
    sp = fe.state_features(horizon=HORIZON)
    # The study trains and tests on rows complete in every state feature, not
    # just this set's; the served fit uses the same rows so it is the model
    # that was evaluated, refit on more months.
    complete = sp.dropna(subset=fe.STATE_SETS["all"])

    table, info = model_comparison(sp)
    row = table.set_index("model").loc[f"Logit L2, {STATE_SET}"]
    size = table.set_index("model").loc["Logit L2, size"]
    hit = f"top{TOP_K}_hit_rate"

    train = complete.dropna(subset=["y_any"])
    model, params = _fitted(logit_l2(), train, train["y_any"], STATE_FEATURES)
    latest = complete[complete["month"] == complete["month"].max()]
    scored = [_scored_row(model, r, STATE_FEATURES, state=r["state"])
              for _, r in latest.sort_values("state").iterrows()]

    return {
        "name": "state-siting-logit",
        "version": f"1.0.0+data.{latest['month'].max():%Y%m}",
        "description": (
            "Probability that a state is named in at least one automotive "
            "manufacturing-investment announcement in the forecast month, from "
            "its share of EV registrations and its own announcement history. "
            "Served as a ranking of states. L2-regularised logistic regression "
            "on standardised features, refit on every state-month with a known "
            "outcome."),
        "target": TARGET,
        "horizon_months": HORIZON,
        **params,
        "training": _training(train, "y_any"),
        "evaluation": {
            "design": f"train to {STATE_TRAIN_END[:7]}, test on later months",
            "test_rows": info["test_rows"], "test_events": info["test_events"],
            "auc": _r(row["auc"]), "avg_precision": _r(row["avg_precision"]),
            "baseline_avg_precision": _r(table.set_index("model").loc["Baseline (base rate)",
                                                                       "avg_precision"]),
            f"top{TOP_K}_hit_rate": _r(row[hit]),
            "size_only_auc": _r(size["auc"]),
            f"size_only_top{TOP_K}_hit_rate": _r(size[hit]),
        },
        "notes": [
            f"Trained on {int(train['y_any'].sum())} state-months with an "
            "announcement: read the rank, not the probability level.",
            f"A logit on state size alone (12-month EV registrations) scores test "
            f"AUC {size['auc']:.2f} against this model's {row['auc']:.2f}. Demand "
            "share and state size are hard to separate in this data, so a high "
            "rank means 'large EV market with a record of announcements', not "
            "that demand caused the siting.",
        ],
        "scored": scored,
    }


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build() -> dict:
    return {
        "artifact": "ev-investment-outlook",
        "schema_version": SCHEMA_VERSION,
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "inputs": {name: _sha256(CLEAN / name) for name in INPUTS},
        "national": national(),
        "state": state(),
    }


def main() -> None:
    artifact = build()
    OUT.write_text(json.dumps(artifact, indent=2) + "\n", encoding="utf-8")
    n, s = artifact["national"], artifact["state"]
    top = sorted(s["scored"], key=lambda r: -r["probability"])[:TOP_K]
    print(f"wrote {OUT}")
    print(f"national  {n['version']}: P(announcement in month after "
          f"{n['scored'][0]['month'][:7]}) = {n['scored'][0]['probability']:.3f}, "
          f"walk-forward skill {n['evaluation']['brier_skill']:+.1%}")
    print(f"state     {s['version']}: top {TOP_K} = "
          + ", ".join(f"{r['state']} {r['probability']:.3f}" for r in top))


if __name__ == "__main__":
    main()
