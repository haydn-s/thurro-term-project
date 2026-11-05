"""The neural networks, and the non-network models they are judged against.

Why scikit-learn's MLP and not torch
------------------------------------
Every target in this project is small tabular data -- the largest is ~2.5k rows
with 11 features. A multi-layer perceptron is the right network for that shape,
and `MLPClassifier` / `MLPRegressor` are genuine ones: dense layers, ReLU,
backprop, Adam, L2 via `alpha`, early stopping. torch would add a ~200 MB
dependency and a second training loop to maintain and would fit the same
function class. It is also not currently installable in the pinned environment
(Python 3.14.7), so adding it would fork the environment as well.

If a later phase needs sequence models (an LSTM / temporal CNN over the monthly
panel) that argument flips, because scikit-learn cannot express them. The
volume task below is the one that would justify it.

Capacity ladder
---------------
Each task gets three sizes, deliberately. On data this small the interesting
result is not "what does the network score" but "what happens as capacity
grows" -- if the smallest network wins and bigger ones get worse, that is
overfitting shown rather than asserted.
"""
import numpy as np
from sklearn.dummy import DummyClassifier, DummyRegressor
from sklearn.linear_model import Ridge
from sklearn.neural_network import MLPClassifier, MLPRegressor
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from nn_config import RANDOM_STATE


# =====================================================================
# Classification networks (announcement tasks)
# =====================================================================
def _mlp_clf(hidden, alpha, seed=RANDOM_STATE, max_iter=4000):
    """Standardise, then an MLP.

    The scaler lives inside the pipeline so its mean and variance are learned
    from the training rows only -- on a walk-forward test, fitting the scaler on
    the whole series would leak the future into every fold.

    No early stopping: it holds out a random 10% of an already tiny training set
    and, worse, holds out *random* months, which breaks the time ordering the
    whole design rests on. L2 (`alpha`) does the regularising instead.
    """
    return make_pipeline(
        StandardScaler(),
        MLPClassifier(hidden_layer_sizes=hidden, alpha=alpha, activation="relu",
                      solver="adam", learning_rate_init=0.01, max_iter=max_iter,
                      shuffle=True, random_state=seed),
    )


def mlp_tiny(seed=RANDOM_STATE):
    """4 hidden units, strong L2. About the largest network 16-30 rows can carry."""
    return _mlp_clf((4,), alpha=1.0, seed=seed)


def mlp_small(seed=RANDOM_STATE):
    """8 hidden units."""
    return _mlp_clf((8,), alpha=1.0, seed=seed)


def mlp_deep(seed=RANDOM_STATE):
    """Two layers, weak L2 -- included to show the overfitting edge, not to win."""
    return _mlp_clf((32, 16), alpha=0.0001, seed=seed)


def baseline_clf():
    return DummyClassifier(strategy="prior")


# Specs use the same three-key shape as the exploration package's models.py, so
# its `fit_predict` and `walk_forward` can run them unmodified.
def national_nn_models():
    return {
        "MLP (4), core":        {"kind": "prob", "features": "core", "make": mlp_tiny},
        "MLP (8), core":        {"kind": "prob", "features": "core", "make": mlp_small},
        "MLP (8), all":         {"kind": "prob", "features": "all",  "make": mlp_small},
        "MLP (32,16), all":     {"kind": "prob", "features": "all",  "make": mlp_deep},
    }


# =====================================================================
# Regression networks (volume task)
# =====================================================================
def _mlp_reg(hidden, alpha, seed=RANDOM_STATE, max_iter=2000):
    return make_pipeline(
        StandardScaler(),
        MLPRegressor(hidden_layer_sizes=hidden, alpha=alpha, activation="relu",
                     solver="adam", learning_rate_init=0.005, max_iter=max_iter,
                     early_stopping=False, shuffle=True, random_state=seed),
    )


def reg_mlp_small(seed=RANDOM_STATE):
    return _mlp_reg((16,), alpha=0.1, seed=seed)


def reg_mlp_mid(seed=RANDOM_STATE):
    return _mlp_reg((64, 32), alpha=0.01, seed=seed)


def reg_mlp_wide(seed=RANDOM_STATE):
    return _mlp_reg((128, 64), alpha=0.001, seed=seed)


def ridge():
    return make_pipeline(StandardScaler(), Ridge(alpha=1.0))


def volume_models():
    """name -> (maker, needs_seed).

    The naive baselines are not fitted at all; they are computed in nn_volume.py
    straight from the lag columns, because a 'model' that returns last month's
    value has nothing to learn.
    """
    return {
        "Ridge":            (ridge, False),
        "MLP (16)":         (reg_mlp_small, True),
        "MLP (64,32)":      (reg_mlp_mid, True),
        "MLP (128,64)":     (reg_mlp_wide, True),
    }


def mean_baseline_reg():
    return DummyRegressor(strategy="mean")


# =====================================================================
# Multi-seed helper
# =====================================================================
def seed_list(n, base=RANDOM_STATE):
    """The seeds a network is refit under. Deterministic, so a rerun reproduces."""
    return [base + i for i in range(n)]


def summarise_seeds(values):
    """mean / sd / min / max across seeds, for reporting a network honestly."""
    v = np.asarray(values, dtype=float)
    return {"mean": float(v.mean()), "sd": float(v.std(ddof=1)) if len(v) > 1 else 0.0,
            "min": float(v.min()), "max": float(v.max()), "n_seeds": len(v)}
