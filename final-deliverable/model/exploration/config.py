"""Settings shared by every file in the exploration package.

Change things here, not inside the analysis code.
"""
from pathlib import Path

# ---------------------------------------------------------------- paths
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]                      # repo root
CLEAN = ROOT / "data" / "clean"             # written by scripts/clean.py
MODEL_PANELS = ROOT / "data" / "model"      # written by scripts/features.py
RESULTS = HERE.parent / "results"           # final-deliverable/model/results/

# ---------------------------------------------------------------- national question
# Which announcements count as the dependent variable.
#   "all"        every automotive manufacturing-investment announcement
#   "ev_or_mix"  ev_related in {yes, mixed}
#   "ev"         ev_related == yes
TARGETS = ["all", "ev_or_mix", "ev"]
MAIN_TARGET = "all"

# Forecast horizons in months: h=1 asks "will there be an announcement next
# month?", h=3 asks "will there be one in the next three months?".
HORIZONS = [1, 3]
MAIN_HORIZON = 1

# Walk-forward test: the first FIRST_TEST rows are only ever used for training.
FIRST_TEST = 16

# Longest look-back used by any feature. Rows without a full look-back are dropped,
# so every model sees exactly the same months.
MAX_LOOKBACK = 6

# How many shuffled-history runs for the placebo test, and bootstrap draws.
N_PLACEBO = 200
N_BOOTSTRAP = 2000

RANDOM_STATE = 0

# ---------------------------------------------------------------- state question
# Train on state-months up to and including this month, test on the rest.
STATE_TRAIN_END = "2025-06-01"
TOP_K = 5   # "was the announcing state in the model's top-5 that month?"
