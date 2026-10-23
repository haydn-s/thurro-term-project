# Neural-network experiments

Can a neural network find something in this data that the linear and tree models
in [`../exploration/`](../exploration/) could not?

Three tracks, because the project's own research question and the question
"where can a network be trained at all" have different answers, and because the
second question has two model families worth asking it of.

| track | file | target | rows the network sees |
|---|---|---|---|
| **A** | `nn_announcements.py` | the project's question: does an announcement follow? | 16–33 months, 11 events (national); 2,479 rows, **7 events** (state) |
| **B** | `nn_volume.py` | next month's EV registrations per state | 2,455 training rows (34 states x 92 months), dense continuous target |
| **C** | `seq_volume.py` | the same, 1-6 months ahead, from the raw monthly window | the same 2,455 rows as windows; GRU, LSTM, TCN, Transformer, N-BEATS, and each on top of exponential smoothing |

Findings and the numbers behind them are in
[`../nn-models-card.md`](../nn-models-card.md).

## Run it

```bash
.VENV/bin/pip install -r final-deliverable/model/nn/requirements-dl.txt   # torch, Track C only
.VENV/bin/python final-deliverable/model/nn/nn_volume.py          # ~20s
.VENV/bin/python final-deliverable/model/nn/nn_announcements.py   # ~12min (the placebo dominates)
.VENV/bin/python final-deliverable/model/nn/seq_volume.py         # ~2.5min on 6 cores
.VENV/bin/python final-deliverable/model/nn/make_summary.py       # rebuild results/nn/summary.md
.VENV/bin/python -m pytest final-deliverable/model/nn -q          # 68 checks; 45 skip without torch
```

Results are written to `../results/nn/`. Nothing here writes to
`../results/`'s other subdirectories, so it cannot overwrite the shared study.

## Files

| file | what it does |
|---|---|
| `nn_config.py` | paths, splits and seed count; imports anything shared from `../exploration/config.py` rather than restating it |
| `nn_models.py` | the networks (a capacity ladder per task) and the non-network models they are judged against |
| `nn_announcements.py` | Track A: the study's walk-forward and state split, with networks added |
| `nn_volume.py` | Track B: the volume panel, both target framings, and the fit diagnostics |
| `seq_models.py` | Track C's networks (torch), the quantile head they share, and the training loop |
| `seq_volume.py` | Track C: windows, splits, baselines (incl. exponential smoothing), validate-then-refit, scoring, rolling-origin backtest |
| `make_summary.py` | rebuilds `../results/nn/summary.md` from the CSVs without refitting |
| `requirements-dl.txt` | the optional torch layer, pinned |
| `test_nn.py` | 23 checks on Tracks A and B, mostly leakage |
| `test_seq.py` | 45 checks on Track C, mostly leakage; skipped without torch |

## Why scikit-learn for A and B, torch for C

Tracks A and B are small tabular data — the largest is 2,455 rows and 21
features. An MLP is the right network for that shape, and `MLPClassifier` /
`MLPRegressor` are real ones: dense layers, ReLU, Adam, backprop, L2.

Track C needs recurrent, convolutional and attention models, which
scikit-learn cannot express. torch 2.14.1 now ships a wheel for Python 3.14, so
it is an optional layer (`requirements-dl.txt`) rather than a change to the
repo-root requirements: nothing else imports it, and it is ~590 MB. The
Dockerfile's ignore list already keeps this directory out of the image.

## Three things to know before reading the results

**Every network is run under 5 seeds.** On data this small a single seed reports
the luck of an initialisation. `MLP (32,16)` on the national task scores Brier
0.145 on one seed and 0.223 on another — the first number alone would have been
a finding, and it is not one. Tables report the mean and the spread.

**Track C picks nothing on the test months.** Window length and epoch count
come from an inner validation block; the architecture used for the per-state
breakdown is the one with the lowest validation loss. The hybrids were added
after the first run, so their result was re-checked on a rolling-origin
backtest whose first 30 months had not been looked at. See the card.

**No new shared features.** Track A consumes the exploration package's
`feature_engineering.py` exactly as it stands; Tracks B and C build lag, window and calendar
columns locally, for their own target, and deliberately does not add them to
`scripts/features.py`. The shared feature layer belongs to the modelling track,
and a second implementation of it would drift from the first.

## A data bug this turned up

`data/processed/ev_registrations_state_monthly.csv` is **sparse-encoded**: a
state-month with no registrations has no row. 21 of 36 states have internal
calendar gaps, including Gujarat, Kerala and Andhra Pradesh, each missing a 2020
lockdown month.

That matters to anything that lags the panel, because
`groupby("state").shift(1)` moves one **row**, not one **month** — on a sparse
panel it silently reaches back 2, 3 or 31 months for some rows. `nn_volume.py`
calls `complete_panel()` first, which puts every state on an unbroken monthly
grid from its own first sighting and fills absent months with zero.
`test_lags_are_backward_looking` is what caught it, and is what keeps it caught.

The same positional-shift pattern appears in the shared study's state features
(`../exploration/feature_engineering.py::state_features`, which rolls and shifts
a sparse panel the same way). That is the modelling track's code and has not
been touched here — see the card's "For the modelling track" note.
