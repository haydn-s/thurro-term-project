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

# ---------------------------------------------------------------- sequence models
# Track C: recurrent, convolutional, attention and N-BEATS networks reading the
# raw monthly sequence rather than engineered lags. Same panel, states and split
# as Track B, so its one-month-ahead numbers land in the same table.

# Forecast 1..SEQ_HORIZON months ahead from each origin. h=1 is Track B's target;
# the longer horizons are where a random walk degrades and structure, if any,
# should show.
SEQ_HORIZON = 6
SEQ_REPORT_HORIZONS = [1, 3, 6]

# Window lengths tried. Picked per architecture on the inner validation block
# below, never on the test months. 13 is the history every Track B row already
# has (lag12 + the current month); 24 reaches back further, zero-padded and
# masked where a state's history is shorter.
SEQ_WINDOWS = [13, 24]

# Inner validation: the last this-many months of training origins. Used for
# early stopping and the window choice; the model is then refitted on the whole
# training window for the chosen number of epochs.
SEQ_VAL_MONTHS = 12

# Quantiles every sequence model predicts. The median is the point forecast;
# 0.1 and 0.9 give an 80% interval, scored for coverage.
SEQ_QUANTILES = [0.1, 0.5, 0.9]

# Training budget: Adam, early-stopped on the validation pinball loss.
SEQ_MAX_EPOCHS = 300
SEQ_PATIENCE = 30
SEQ_BATCH = 64

# A second scoring subset, fixed before any sequence model was run: states whose
# mean monthly registrations over the training window are at least this. The
# smallest kept states average 2-15 a month, where log1p is dominated by count
# noise; the headline metric keeps them so it stays comparable with Track B.
SEQ_MAJOR_STATE_MIN_MONTHLY = 1000

# Rolling-origin backtest of the deciding comparison: refit at each origin and
# forecast the next SEQ_ROLLING_BLOCK months of origins, so every block is out of
# sample for the model that scores it. The first five blocks end before the main
# test window and had not been looked at when the hybrid was added.
SEQ_ROLLING_ORIGINS = ["2022-09-01", "2023-03-01", "2023-09-01", "2024-03-01",
                       "2024-09-01", "2025-03-01", "2025-09-01", "2026-03-01"]
SEQ_ROLLING_BLOCK = 6
SEQ_ROLLING_ARCHS = ["N-BEATS", "N-BEATS on SES"]
SEQ_ROLLING_WINDOW = 13          # what validation chose for both in the main split

# Parallel training jobs. Each job pins torch to one thread; these networks are
# too small for intra-op threading to help.
SEQ_N_JOBS = 6

RANDOM_STATE = 0

# How many seeds each network is refit under. A single seed on data this small
# reports the luck of an initialisation, not the architecture.
N_SEEDS = 5
