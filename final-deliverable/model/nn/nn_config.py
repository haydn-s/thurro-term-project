"""Settings for the neural-network experiments.

Separate from the exploration package's `config.py` on purpose: that file is the
shared study's settings and is not mine to edit. Anything here that must match
the study (test splits, targets, horizons) is *imported* from it rather than
restated, so the two cannot drift.
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
MODEL_DIR = HERE.parent                      # final-deliverable/model/
ROOT = HERE.parents[2]                       # repo root

# The exploration package uses bare imports (`from config import ...`), so it has
# to be on sys.path before anything in it can be imported.
EXPLORATION = MODEL_DIR / "exploration"
if str(EXPLORATION) not in sys.path:
    sys.path.insert(0, str(EXPLORATION))

RESULTS = MODEL_DIR / "results" / "nn"

# ---------------------------------------------------------------- volume task
# Forecasting next-month EV registrations per state. This is the only target in
# the project with enough dense observations to train a network on; see
# nn-models-card.md for the counts that led here.
#
# data/clean/, not data/processed/. The registrations pull ends 2026-09-15, so
# the processed file's last month is half a month and reads as a ~55% collapse in
# every state at once. scripts/clean.py drops it; reading the processed file
# skipped that and put a target no model can predict into every test score.
VOLUME_PANEL = ROOT / "data" / "clean" / "registrations_state_monthly.csv"

# Train on months up to and including this, test after. Chosen to leave ~18
# months of test, matching the national study's test length.
VOLUME_TRAIN_END = "2025-03-01"

# A state must have this many non-zero months to enter the panel. Tiny union
# territories are mostly structural zeros and only teach the network to predict 0.
VOLUME_MIN_NONZERO_MONTHS = 24

# Longest look-back used by a volume feature; rows without a full window are dropped.
VOLUME_MAX_LOOKBACK = 12

RANDOM_STATE = 0

# How many seeds each network is refit under. A single seed on data this small
# reports the luck of an initialisation, not the architecture.
N_SEEDS = 5
