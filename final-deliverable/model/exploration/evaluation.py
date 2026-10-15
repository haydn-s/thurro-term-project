"""How models are tested and scored.

walk_forward()      out-of-sample predictions, one month at a time
score()             Brier, log loss, AUC, average precision, skill vs baseline
bootstrap_vs()      is a model's Brier gain over the baseline bigger than luck?
placebo_test()      would random production histories score as well?
"""
import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, brier_score_loss, log_loss, roc_auc_score

from config import N_BOOTSTRAP, RANDOM_STATE
from models import fit_predict

EPS = 0.01  # probabilities are clipped to [0.01, 0.99] so log loss stays finite


def walk_forward(df, features, y_any_col, y_count_col, spec, first_test, horizon):
    """Expanding-window, one-step-ahead test.

    At each forecast month t we may only use rows whose target is already known
    at t. A row j with horizon h has its target in months j+1..j+h, so it is
    known once j + h <= t. That is why training stops at t - horizon.
    """
    preds = []
    for t in range(first_test, len(df)):
        if pd.isna(df[y_any_col].iloc[t]):
            continue                                  # no outcome to score against
        train = df.iloc[: t - horizon + 1].dropna(subset=[y_any_col])
        test = df.iloc[[t]]
        p = fit_predict(spec, train[features], train[y_any_col], train[y_count_col], test[features])[0]
        preds.append({"month": df["month"].iloc[t], "y": int(df[y_any_col].iloc[t]),
                      "p": float(np.clip(p, EPS, 1 - EPS))})
    return pd.DataFrame(preds)


def score(y, p):
    """All the numbers we report for one set of predictions."""
    y, p = np.asarray(y), np.asarray(p)
    both = len(np.unique(y)) == 2
    return {
        "brier": brier_score_loss(y, p),                          # lower is better
        "log_loss": log_loss(y, p, labels=[0, 1]),                # lower is better
        "auc": roc_auc_score(y, p) if both else np.nan,           # 0.5 = coin flip
        "avg_precision": average_precision_score(y, p) if both else np.nan,  # base rate = no skill
        "n_test": len(y),
        "events_in_test": int(y.sum()),
    }


def bootstrap_vs(y, p_model, p_base, n=N_BOOTSTRAP, seed=RANDOM_STATE):
    """Paired bootstrap over test months of (Brier_baseline - Brier_model).

    Returns the mean gain and a 90% interval. If the interval includes 0, the
    model's advantage over the baseline could just be luck.
    """
    rng = np.random.default_rng(seed)
    y, p_model, p_base = map(np.asarray, (y, p_model, p_base))
    loss_m = (p_model - y) ** 2
    loss_b = (p_base - y) ** 2
    gains = []
    for _ in range(n):
        idx = rng.integers(0, len(y), len(y))
        gains.append(loss_b[idx].mean() - loss_m[idx].mean())
    gains = np.array(gains)
    return {"brier_gain": loss_b.mean() - loss_m.mean(),
            "gain_ci_low": np.percentile(gains, 5),
            "gain_ci_high": np.percentile(gains, 95),
            "p_gain_le_0": float((gains <= 0).mean())}


def placebo_test(df, features, shuffle_cols, y_any_col, y_count_col, spec, first_test,
                 horizon, n_runs, seed=RANDOM_STATE):
    """Circular-shift placebo.

    Slide the production columns along the calendar by a random number of months
    (wrapping round the end), refit, and score again. That keeps each series'
    own shape and autocorrelation but breaks its timing against announcements.
    If the real timing scores no better than most shifted copies, the model has
    not found a real lead.
    """
    rng = np.random.default_rng(seed)
    real = walk_forward(df, features, y_any_col, y_count_col, spec, first_test, horizon)
    real_brier = brier_score_loss(real["y"], real["p"])

    placebo = []
    for _ in range(n_runs):
        shift = int(rng.integers(6, len(df) - 6))     # at least 6 months away from the truth
        fake = df.copy()
        for c in shuffle_cols:
            fake[c] = np.roll(df[c].to_numpy(), shift)
        res = walk_forward(fake, features, y_any_col, y_count_col, spec, first_test, horizon)
        placebo.append(brier_score_loss(res["y"], res["p"]))
    placebo = np.array(placebo)
    return {"real_brier": real_brier,
            "placebo_brier_median": float(np.median(placebo)),
            "share_placebo_better_or_equal": float((placebo <= real_brier).mean()),
            "placebo_briers": placebo}
