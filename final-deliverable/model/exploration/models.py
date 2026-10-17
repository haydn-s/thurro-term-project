"""The candidate models.

Every model is a small dictionary with three things:
    "kind"      "prob"  -> predicts P(at least one announcement) directly
                "count" -> predicts the expected NUMBER of announcements (mu);
                           we turn it into a probability with P = 1 - exp(-mu)
    "features"  which feature list it uses ("core", "all", "controls", ...)
    "make"      a function that returns a fresh, unfitted scikit-learn model

All linear models standardise their inputs inside a Pipeline, so the scaling is
learned from the training months only (no peeking at the test month).

Why these models?
    Baseline            the number every model has to beat
    Logit (controls)    the "sector cycle" null: trend + seasonality, no EV data
    Poisson (core)      the natural model for a small monthly count
    Logit L2 (core)     same signals, framed as yes / no, with shrinkage
    Logit L1 (all)      lasso: gets every feature and has to pick a few
    Random forest       non-linear, threshold effects, interactions
    Gradient boosting   a second non-linear learner, built tree by tree
"""
import numpy as np
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression, PoissonRegressor
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from config import RANDOM_STATE


def baseline():
    # always predicts the share of training months that had an announcement
    return DummyClassifier(strategy="prior")


def logit_l2(C=1.0):
    return make_pipeline(StandardScaler(), LogisticRegression(C=C, max_iter=2000))


def logit_l1(C=0.5):
    return make_pipeline(StandardScaler(),
                         LogisticRegression(penalty="l1", C=C, solver="liblinear", max_iter=2000))


def poisson(alpha=1.0):
    # alpha is a ridge penalty; it keeps the fit stable on ~20-30 months
    return make_pipeline(StandardScaler(), PoissonRegressor(alpha=alpha, max_iter=1000))


def random_forest():
    return RandomForestClassifier(n_estimators=300, max_depth=3, min_samples_leaf=3,
                                  random_state=RANDOM_STATE)


def gradient_boosting():
    return GradientBoostingClassifier(n_estimators=150, max_depth=2, learning_rate=0.05,
                                      subsample=0.8, random_state=RANDOM_STATE)


NATIONAL_MODELS = {
    "Baseline (base rate)":      {"kind": "prob",  "features": "controls", "make": baseline},
    "Logit, controls only":      {"kind": "prob",  "features": "controls", "make": logit_l2},
    "Poisson, core":             {"kind": "count", "features": "core",     "make": poisson},
    "Logit L2, core":            {"kind": "prob",  "features": "core",     "make": logit_l2},
    "Logit L1 (lasso), all":     {"kind": "prob",  "features": "all",      "make": logit_l1},
    "Random forest, all":        {"kind": "prob",  "features": "all",      "make": random_forest},
    "Gradient boosting, all":    {"kind": "prob",  "features": "all",      "make": gradient_boosting},
}


def fit_predict(spec, X_train, y_any_train, y_count_train, X_test):
    """Fit one model on the training rows and return P(event) for each test row.

    Falls back to the training base rate when the training rows contain only one
    class (a classifier cannot be fitted then).
    """
    base_rate = float(np.mean(y_any_train))
    model = spec["make"]()
    if spec["kind"] == "count":
        if y_count_train.sum() == 0:
            return np.full(len(X_test), base_rate)
        model.fit(X_train, y_count_train)
        mu = np.clip(model.predict(X_test), 0, None)
        return 1 - np.exp(-mu)
    if len(np.unique(y_any_train)) < 2:
        return np.full(len(X_test), base_rate)
    model.fit(X_train, y_any_train)
    return model.predict_proba(X_test)[:, 1]
