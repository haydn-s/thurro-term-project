# Neural-network experiments: model card

Companion to [`exploratory-models-card.md`](exploratory-models-card.md), which
covers the 7 national and 9 state models this is judged against. Code in
[`nn/`](nn/), generated tables in
[`results/nn/summary.md`](results/nn/summary.md).

**The question asked here:** can a neural network find something in this data
that the linear and tree models could not?

**The short answer:** on the national announcement-timing question, yes — a
network is the best model in the study on that target, and the advantage
survives the placebo test. On the state siting question it ties the logit and
should not be preferred to it. On EV volume forecasting, the one target with
enough data to train a network properly, a feedforward network on engineered
lags loses to a random walk (Track B) — but mostly because of how it was
trained. Sequence networks beat the random walk, largely by rediscovering
exponential smoothing; one of them, N-BEATS trained on the smoother's residual,
beats smoothing itself by ~4.5% one month ahead, and that held up in a 46-month
rolling backtest (Track C). Beyond one month nothing beats smoothing reliably.

---

## Provenance

| | |
|---|---|
| Branch | `nn-development`, off `review-final-deliverable`; Track C on `nn-sequence-models`, off `nn-development` |
| Run date | 2026-10-16 (Tracks A, B); 2026-10-23 (Track B re-run, Track C) |
| Environment | repo-root `requirements.txt`; Python 3.14.7, scikit-learn 1.9.1, pandas 3.0.6, numpy 2.5.3. Track C adds `nn/requirements-dl.txt` (torch 2.14.1, CPU) |
| Track A features | `exploration/feature_engineering.py`, unmodified |
| Track A data | `data/clean/` (production file mtime 2026-10-16 21:08) |
| Track B data | `data/clean/registrations_state_monthly.csv`, ends 2026-08 (re-run 2026-10-23; see the correction under Track B) |
| Networks | A, B: `sklearn.neural_network.MLPClassifier` / `MLPRegressor` — dense + ReLU + Adam, L2 via `alpha`. C: GRU, LSTM, TCN, Transformer, N-BEATS and their SES hybrids in torch (`nn/seq_models.py`) |
| Seeds | 5 per network (3 for placebo runs); every table reports the spread |
| Tests | `pytest final-deliverable/model/nn -q`, 68 checks (the 45 in `test_seq.py` skip without torch) |

No fitted artifact is committed. Nothing here is wired into the container; the
deliverable still serves its documented null baseline.

---

## Why scikit-learn for Tracks A and B, torch for Track C

Tracks A and B are small tabular problems — the largest is 2,455 rows and 21
features. An MLP is the right network for that shape, and scikit-learn's is a
real one.

Track C needs sequence models, which scikit-learn cannot express. torch 2.14.1
has a wheel for Python 3.14 (the round-one blocker is gone), so it is installed
as an optional layer, `nn/requirements-dl.txt`, rather than added to the
repo-root requirements: ~590 MB that nothing else in the project imports.
`test_seq.py` skips itself without it, and the Dockerfile's ignore list already
keeps `model/nn/` out of the image.

---

## Track A, national: does an announcement follow?

Same walk-forward test, target and split as the shared study: train on every
month whose outcome is known, predict the next, roll forward. 18 test months, 7
events in test, 11 in total. A training fold is 16 to 33 months.

| model | features | Brier (mean ± sd) | AUC | Brier skill | 90% CI of gain |
|---|---|---|---|---|---|
| **MLP (8), all** | 23 | **0.191 ± 0.006** | 0.679 | **+25.3%** | [−0.022, +0.154] |
| MLP (32,16), all | 23 | 0.191 ± 0.032 | 0.748 | +25.3% | [−0.039, +0.166] |
| MLP (8), core | 7 | 0.216 ± 0.018 | 0.705 | +15.6% | [−0.043, +0.123] |
| *Logit L1 (lasso), all* | 23 | *0.229* | 0.636 | *+10.6%* | [−0.020, +0.075] |
| *Random forest, all* | 23 | *0.236* | 0.714 | *+7.9%* | [−0.021, +0.057] |
| *Logit L2, core* | 7 | *0.236* | 0.695 | *+7.8%* | [−0.042, +0.078] |
| MLP (4), core | 7 | 0.241 ± 0.039 | 0.736 | +5.8% | [−0.051, +0.077] |
| Baseline (base rate) | 0 | 0.256 | 0.636 | +0.0% | — |

The networks take the top three places. **Every interval in that column
includes zero**, so on 18 test months the margin is not separable from luck —
which is equally true of the linear models it beats.

### The seed warning, which is the methodological point

`MLP (32,16), all` scores Brier **0.145 on seed 4 and 0.223 on seed 2**. A
single-seed run would have reported +43% skill, and that number would have been
noise. Everything here is 5 seeds with the spread shown, and the one-line
summary of this card is that nothing on 34 months should be reported from one
initialisation.

### Ablation: where the advantage comes from

Feature groups added one at a time on top of the controls — the direct test of
whether EV production contributes anything beyond trend and seasonality.

| feature set | features | Brier (mean ± sd) | AUC | Brier skill | 90% CI of gain |
|---|---|---|---|---|---|
| controls | 4 | 0.268 ± 0.012 | 0.561 | −4.8% | [−0.056, +0.031] |
| controls+history | 5 | 0.282 ± 0.019 | 0.478 | −10.4% | [−0.105, +0.053] |
| controls+production | 9 | 0.223 ± 0.016 | 0.703 | +12.8% | [−0.049, +0.116] |
| controls+demand | 7 | 0.270 ± 0.020 | 0.582 | −5.4% | [−0.085, +0.054] |
| controls+industry | 8 | 0.318 ± 0.009 | 0.600 | −24.4% | [−0.153, +0.013] |
| **controls+production+mix** | 15 | **0.168 ± 0.023** | **0.783** | **+34.1%** | **[+0.005, +0.172]** |
| all | 23 | 0.191 ± 0.006 | 0.679 | +25.3% | [−0.022, +0.154] |

Three things read off this:

1. **Controls alone are worse than the base rate** (−4.8%, AUC 0.56). The
   network's advantage is not a trend artifact — it has nothing until the
   production columns arrive.
2. **Production is where the gain appears** (+12.8%), and production plus
   segment mix is where it peaks (+34.1%, AUC 0.78).
3. `controls+production+mix` is **the only specification in this card whose 90%
   interval excludes zero**: [+0.005, +0.172].

`MLP (4)` reproduces the same shape (controls −0.3%, production+mix +25.0%), so
the pattern is not specific to one architecture.

### Placebo: the test that decides it

Slide the production columns along the calendar by a random offset, refit,
rescore, 200 times. Each series keeps its own shape and autocorrelation but
loses its timing against announcements. A model that has found a real lead
should beat nearly all the shifted copies.

| model | real Brier | median placebo Brier | share of placebos as good |
|---|---|---|---|
| **MLP (8), controls+production+mix** | **0.181** | 0.262 | **0.0%** |
| MLP (8), core | 0.214 | 0.299 | 0.0% |
| MLP (8), all | 0.195 | 0.236 | 7.0% |
| MLP (4), core | 0.224 | 0.295 | 8.0% |
| MLP (32,16), all | 0.201 | 0.272 | 9.5% |

Every network beats at least 90% of shifted copies, and the best ablation set
beats **all 200, on all three seeds** (sd 0.0). The actual calendar alignment of
production against announcements carries information that a shifted copy does
not.

### What this does and does not say

It **converges with the shared study**, which found the same winning feature set
by a different route: `Logit L2, controls+production+mix` scored real Brier
0.185 with 0% of placebos as good and +27.6%, CI [0.003, 0.142]. Two unrelated
model families, independently, pick `controls+production+mix` and pass the same
placebo. That convergence is the strongest thing in this card, and it is
stronger than either result alone.

Three limits travel with it:

- **18 test months, 7 events.** Every interval except one includes zero. The
  direction is better supported than the magnitude.
- **Selection.** `controls+production+mix` is the best of 7 feature sets × 2
  architectures = 14 runs, and its interval carries no correction for that
  choice. This is the same caveat the exploration card's best ablation carries.
  The placebo is the part of the evidence that selection does not explain, since
  it re-tests the chosen spec against 200 null calendars.
- **It is not the capex result.** The project README's headline null concerns
  **company capex** — a different dependent variable, annual, 182 rows. Nothing
  here revisits it. This is the announcement-timing question, and the two can
  both be true: sector capex was cycle-driven while announcement *timing* still
  tracked production.

---

## Track A, state: where does investment get sited?

Train on state-months to 2025-06, test after. 2,479 training rows — but **7
training events**, a 0.28% base rate. The row count is not the constraint.

| model | Brier | AUC | avg precision | top-5 hit rate |
|---|---|---|---|---|
| MLP (8), all | 0.0219 ± 0.0001 | 0.852 ± 0.001 | 0.120 | 0.545 |
| MLP (4), all | 0.0219 ± 0.0001 | 0.853 ± 0.002 | 0.119 | 0.545 |
| Baseline (base rate) | 0.0225 | 0.500 | 0.023 | 0.144 |
| MLP (32,16), all | 0.0231 ± 0.0012 | 0.625 ± 0.048 | 0.070 | 0.345 |

The network matches the study's best logit on AUC (0.852 vs 0.85) and average
precision (0.120 vs 0.124) and is **worse on the metric that matters
operationally** — top-5 hit rate 0.545 against the logit's 0.64, which is how
often the announcing state was in the model's top five that month.

`MLP (32,16)` collapses to AUC 0.625, below the two small networks and barely
above the base rate on Brier. With 7 positives, capacity is purely harmful.

**Conclusion: no gain.** Prefer `Logit L2, share+history` — it is simpler,
interpretable, and better at the ranking task. A network has nothing to add to 7
events.

---

## Track B: next-month state EV registrations

Track A is limited by events, which no model class can fix. This track changes
the target instead: forecast a state's EV registrations next month. Dense, 34
states × 92 months, 2,455 training rows, no missing outcomes. **This is the only
target in the project a network can genuinely be trained on.**

> **Correction, 2026-10-23.** The first run read
> `data/processed/ev_registrations_state_monthly.csv`, whose last month (2026-09)
> is a half month: the pull ends 2026-09-15, and `data/README.md` says so.
> `scripts/clean.py` drops it from `data/clean/`, which Track B now reads. The
> half month put a ~55% fall in every state into the final test month, so every
> score below moved: naive went from 0.267 to 0.234 and the networks lost ground
> against it. The conclusion did not change, but every number here is from the
> re-run, and `test_final_month_is_not_partial` now guards it. The re-run also
> fixed the seasonal-naive baseline, which forecast month t+1 from t−12 (a
> 13-month lag) instead of t−11, the same month a year earlier.

It is also useful rather than a detour: EV volume is the *independent* variable
in the research question, so a one-month-ahead forecast of it is what would turn
the deliverable's backward-looking panel into a forward-looking signal.

Scored on the reconstructed log level in both framings, so the two are
comparable. "Delta" predicts the log *change* and adds the current level back —
the fair framing for a network, since predicting the level forces it to
re-learn an identity map first.

| model | MAE (log) predicting level | MAE (log) predicting change | skill vs naive (better framing) |
|---|---|---|---|
| Mean of training growth | — | 0.232 | +0.7% |
| Drift (last + mean growth) | 0.233 | 0.233 | +0.7% |
| **Naive (last month)** | **0.234** | **0.234** | **0.0%** |
| Ridge | 0.244 | 0.244 | −4.2% |
| MLP (16) | 0.267 ± 0.021 | 0.278 ± 0.028 | −14.0% |
| MLP (64,32) | 0.313 ± 0.038 | 0.312 ± 0.021 | −33.1% |
| MLP (128,64) | 0.354 ± 0.098 | 0.324 ± 0.024 | −38.5% |
| Seasonal naive (12m) | 0.427 | 0.427 | −82.5% |

**No fitted model beats the random walk.** The only things that edge it are the
two constant-growth baselines, by 0.7% — "same as last month, plus the average
training growth rate". The series is close to a random walk with drift at
monthly frequency: the conditional mean of log growth given 21 features is
approximately the unconditional one.

> **Revised by Track C, 2026-10-23.** Exponential smoothing — one fitted
> parameter, not in this table — beats the random walk by 8.2% on these rows, so
> "close to a random walk" overstates it: the series is a level plus noise that
> partly reverses. And the same MLP (16), trained with a median loss and early
> stopping, gets most of the way there. See Track C.

### The diagnostic that separates the two failure modes

| model | MAE train | MAE test | gap |
|---|---|---|---|
| Naive (last month) | 0.432 | 0.234 | −0.197 |
| Ridge | 0.408 | 0.244 | −0.164 |
| MLP (16) | 0.349 | 0.278 | −0.071 |
| MLP (64,32) | 0.195 | 0.312 | +0.117 |
| MLP (128,64) | 0.158 | 0.324 | +0.166 |

Two different failures, and the distinction matters:

- The **large** networks overfit outright (train 0.158 against test 0.324).
- **`MLP (16)` does not overfit at all** — its test error is *better* than its
  training error — and it still loses to naive.

That second row is the finding. If only the big networks had failed, the answer
would be "regularise more". A well-behaved small network losing too means the
conditional structure is not there to fit, and tuning will not produce it.

> **Revised by Track C.** That last inference was wrong. The structure is there
> — SES finds it — and a non-overfitting network can still miss it if it is
> trained on squared error over volatile small states. The Track C control
> (this network, this data, pinball loss and early stopping) moves from −18.8%
> to −2.7% per seed and +6.8% as an ensemble.

(The baselines' negative gaps are not a bug: the test window is calmer than the
2018–2021 history, where small states had volatile low counts.)

### Learning curve — would more data help?

`MLP (64,32)`, trained on the most recent fraction of the window:

| train months | train rows | MAE test (log) |
|---|---|---|
| 19 | 646 | 0.490 |
| 38 | 1,292 | 0.360 |
| 56 | 1,898 | 0.299 |
| 75 | 2,455 | 0.312 |

Falls steeply, then **flat over the last quarter** (0.299 → 0.312). It has
saturated well short of naive's 0.234, so more history would not close the gap.

### Per state

The network beats naive in **7 of 34** states; median skill −0.251. The failure
is general, not an artifact of a few large states.

---

## Track C: sequence models on the volume target

Track B left one hypothesis open. A feedforward network on 21 engineered lags
lost to the random walk, but the lags might have been the wrong summary rather
than the signal being absent. Track C gives five sequence architectures the raw
monthly window instead — **GRU, LSTM, a temporal CNN (TCN), a Transformer
encoder and N-BEATS** — on the same 34 states, split and rows (the one-month
rows are asserted identical to Track B's in `test_seq.py`).

Each model reads 13 or 24 months (chosen per architecture on validation) of
nine channels: log level relative to the origin month, monthly log change,
2W/3W/4W share, national log change, calendar, and a padding mask. The
recurrent, convolutional and attention models also get a state embedding and
the origin's level; N-BEATS reads the univariate window only. Every model
predicts the 10th, 50th and 90th percentile of the log change 1–6 months ahead,
trained on pinball loss; the median is the point forecast.

**Protocol, fixed before any test month was scored:** early stopping and window
choice on the last 12 training months; refit on the whole training window for
the chosen epoch count; 5 seeds plus their median as an ensemble; nothing
chosen on test months. Intervals resample whole months, because 34 states
share each month's shocks.

Two baselines are new here, and both turn out to matter: **simple exponential
smoothing (SES)** of the log level, with one smoothing weight fitted on
training rows (α = 0.65), and, for every simple baseline, an 80% interval built
from its own recent training errors.

### One month ahead, main split (544 rows, 16 months)

| model | MAE (log) | vs naive | 90% CI of gain vs SES |
|---|---|---|---|
| **N-BEATS on SES, 5-seed ensemble** | **0.204** | **+13.0%** | **[+0.002, +0.021]** |
| N-BEATS on SES, per seed | 0.205 ± 0.002 | +12.3% | [−0.001, +0.021] |
| N-BEATS, 5-seed ensemble | 0.209 | +10.7% | [−0.002, +0.014] |
| N-BEATS, per seed | 0.214 ± 0.004 | +8.7% | [−0.009, +0.012] |
| *SES (one parameter)* | *0.215* | *+8.2%* | — |
| Transformer, per seed | 0.220 ± 0.004 | +6.2% | [−0.018, +0.008] |
| TCN, per seed | 0.220 ± 0.008 | +6.0% | [−0.017, +0.007] |
| LSTM, per seed | 0.224 ± 0.006 | +4.4% | [−0.020, +0.002] |
| GRU, per seed | 0.225 ± 0.006 | +4.0% | [−0.021, +0.001] |
| MLP (16) on Track B's features, trained the Track C way | 0.240 ± 0.032 | −2.7% | [−0.041, −0.011] |
| *Naive (last month)* | *0.234* | *0.0%* | |
| MLP (16), Track B (squared loss, no early stopping) | 0.278 ± 0.028 | −18.8% | |

All 11 networks, their ensembles, the 3- and 6-month tables and the
major-state subset are in [`results/nn/summary.md`](results/nn/summary.md).

Four findings, in the order they were reached:

**1. Every sequence network beats the random walk,** all five on all 5 seeds —
the first fitted networks in the project to do so on this target.

**2. But mostly by rediscovering exponential smoothing.** SES, with one
parameter, scores +8.2%. No plain network's interval against it clears zero,
and their forecasts correlate 0.71–0.81 with SES's. This also corrects Track B:
the monthly series is not a random walk but a level plus month-to-month noise
that partly reverses, and a smoother is the right summary of it.

**3. Track B's MLP lost mostly because of how it was trained, not what it was
shown.** The control is Track B's MLP (16) on its own 21 features, trained the
Track C way (pinball loss, early stopping, a head that starts at "no change").
Per seed it goes from −18.8% to −2.7%; reading the raw window instead adds
another 7–11 points, to +4.0%–+8.7%, and cuts the seed spread from 0.032 to
0.008 or less. As 5-seed ensembles the control reaches +6.8% against +10.7% for
the best plain sequence model.

**4. A network trained on top of the smoother does beat it.** This is the
ES-RNN idea that won the M4 competition: predict the residual over the SES
forecast, so that an untrained network *is* SES and training has to earn every
departure from it. All five hybrids improve on their plain versions. N-BEATS on
SES has the lowest validation loss of all 11 networks and is the only model
whose interval against SES clears zero.

### The forking path, and the backtest that answers it

The hybrids were added **after** the first run showed the plain networks
roughly tying SES on the test months. Validation picked N-BEATS on SES, but the
decision to try hybrids at all was informed by the test window. So the deciding
comparison was re-run as a rolling-origin backtest: refit every 6 months from
2022-09, each origin with its own validation, early stopping, SES weight, drift
and scaling, scoring the next 6 months. The first 30 forecast months come
before the main test window and had not been looked at.

| one month ahead | MAE, 46 months | vs SES [90% CI] | MAE, 30 earlier months | vs SES [90% CI] |
|---|---|---|---|---|
| **N-BEATS on SES, ensemble** | **0.245** | **+4.5% [+0.004, +0.018]** | **0.266** | **+4.5% [+0.003, +0.022]** |
| N-BEATS, ensemble | 0.250 | +2.4% [−0.001, +0.013] | 0.273 | +1.9% [−0.005, +0.015] |
| SES | 0.256 | — | 0.278 | — |
| Naive (last month) | 0.281 | −9.6% | 0.305 | −9.8% |

The hybrid's error is below SES's in 7 of the 8 six-month blocks (two of them by
under 0.001) and within 0.0001 in the eighth, and the margin in the 30 earlier
months is the same as in the main window. **This is
the result in Track C that replicates.** It is a modest one: about 4.5% on
top of SES, which is itself 8.7% better than naive. On the 18 major states the
backtest margin is +5.2% [+0.002, +0.018], though over the earlier 30 months
alone its interval includes zero.

### Longer horizons do not survive the backtest

- **3 months.** In the main split the hybrid beats SES clearly (+8.0%,
  [+0.008, +0.037]). Across the backtest it leads by +4.0% with an interval that
  includes zero, and by +2.6% in the earlier months.
- **6 months.** In the main split, constant drift wins (MAE 0.322, +16.7%) and
  the networks beat naive by 10–16%. In the backtest's earlier months drift is
  the *worst* model (−5.6% against naive), and across all 41 months the hybrid
  and SES tie (0.359). The test window's growth happened to match the training
  average; that is luck in the window, not structure.

### Intervals

The networks' 80% intervals cover 87–91% one month out (slightly wide) and
73–85% six months out. The best mean pinball loss at one month belongs to the
hybrid ensemble (0.070), barely ahead of SES plus its own empirical errors
(0.071); plain networks do not beat that baseline at 1–3 months. A network buys
no better uncertainty than a smoother with honest error bands.

### What this means for the deliverable

If the service ever forecasts state volume, start with **SES**: one parameter,
no training loop, and about two-thirds of the best one-month gain (8.7% of 12.8%
in the backtest). N-BEATS on SES adds a further ~4.5% one month ahead,
consistently, at the cost of torch, five networks and a refit schedule. That is
worth it only if one-month accuracy matters at that margin. Beyond one month,
nothing here reliably beats smoothing.

### Limits

- **Months, not rows, are the sample.** 46 in the backtest, 16 in the main
  split; every interval resamples months.
- **Selection.** 11 networks × ensembles × 3 horizons × 2 subsets is a lot of
  rows. The defence is that the winner was picked on validation loss and then
  held up on 30 months nobody had examined. Its margin over SES is small: the
  lower bound is +0.003.
- **Same information.** The sequence models see the state's own history, the
  national total and the calendar — nothing Track B lacked except the raw
  window. Prices, subsidies and supply are outside every model here.
- The major-state subset is fixed by training-window volume to 2025-03 and is
  reused unchanged in the backtest.

---

## Reproducing

```bash
.VENV/bin/pip install -r final-deliverable/model/nn/requirements-dl.txt   # Track C only
.VENV/bin/python final-deliverable/model/nn/nn_volume.py          # ~20s
.VENV/bin/python final-deliverable/model/nn/nn_announcements.py   # ~12min, placebo dominates
.VENV/bin/python final-deliverable/model/nn/seq_volume.py         # ~2.5min on 6 cores
.VENV/bin/python final-deliverable/model/nn/make_summary.py       # rebuild tables
.VENV/bin/python -m pytest final-deliverable/model/nn -q          # 68 checks
```

The ablation and its placebo are `national_ablation()` and `placebo_for_set()`
in `nn_announcements.py`; they are not in `run()` because together they add
~4 minutes on top of it.

---

## For the modelling track

Things found while doing this, not acted on, belonging to whoever owns the
modelling code:

**1. The state panel is sparse-encoded, and lagging it positionally is wrong.**
`ev_registrations_state_monthly.csv` has no row for a state-month with zero
registrations. 21 of 36 states have internal calendar gaps — including Gujarat,
Kerala and Andhra Pradesh, each missing a 2020 lockdown month. So
`groupby("state").shift(1)` moves one **row**, not one **month**, and silently
reaches back 2, 3 or 31 months for some rows.

Track B calls `complete_panel()` first and
`test_lags_are_backward_looking` keeps it honest. The same positional pattern is
in `exploration/feature_engineering.py::state_features`, which rolls and shifts
the same sparse panel — **untouched here**, because it is not this track's code.
Worth checking what it does to the state features and to the state results that
rest on them.

**2. Exponential smoothing is a strong, cheap baseline for anything that uses
monthly volume.** One parameter, fitted on training rows, beats the random walk
by 8–9% on next-month state registrations. If the shared study ever forecasts
or lags a volume series, smoothing it first is worth trying before anything
learned. (Round one's item 2 — a sequence model — is now Track C.)
