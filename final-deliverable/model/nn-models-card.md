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
enough data to train a network properly, it loses to a random walk and no
amount of capacity fixes that.

---

## Provenance

| | |
|---|---|
| Branch | `nn-development`, off `review-final-deliverable` |
| Run date | 2026-10-16 |
| Environment | repo-root `requirements.txt`; Python 3.14.7, scikit-learn 1.9.1, pandas 3.0.6, numpy 2.5.3 |
| Track A features | `exploration/feature_engineering.py`, unmodified |
| Track A data | `data/clean/` (production file mtime 2026-10-16 21:08) |
| Track B data | `data/processed/ev_registrations_state_monthly.csv` (mtime 2026-09-30 15:48) |
| Networks | `sklearn.neural_network.MLPClassifier` / `MLPRegressor` — dense + ReLU + Adam, L2 via `alpha` |
| Seeds | 5 per network (3 for placebo runs); every table reports the spread |
| Tests | `pytest final-deliverable/model/nn -q`, 21 checks |

No fitted artifact is committed. Nothing here is wired into the container; the
deliverable still serves its documented null baseline.

---

## Why an MLP and not torch

Every target in this project is small tabular data — the largest is 2,455 rows
and 21 features. An MLP is the right network for that shape, and scikit-learn's
is a real one. torch would add ~200 MB and a second training loop to fit the
same function class, and it has no wheel for the pinned environment's Python
3.14.7, so adding it would fork the environment as well.

That argument flips for a sequence model (an LSTM or temporal CNN over the
monthly panel), which scikit-learn cannot express. Track B is the target that
would justify one.

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

It is also useful rather than a detour: EV volume is the *independent* variable
in the research question, so a one-month-ahead forecast of it is what would turn
the deliverable's backward-looking panel into a forward-looking signal.

Scored on the reconstructed log level in both framings, so the two are
comparable. "Delta" predicts the log *change* and adds the current level back —
the fair framing for a network, since predicting the level forces it to
re-learn an identity map first.

| model | MAE (log) predicting level | MAE (log) predicting change | skill vs naive (better framing) |
|---|---|---|---|
| **Naive (last month)** | **0.267** | **0.267** | **0.0%** |
| Mean of training growth | — | 0.267 | −0.2% |
| Drift (last + mean growth) | 0.267 | 0.267 | −0.3% |
| Ridge | 0.290 | 0.290 | −8.7% |
| MLP (16) | 0.298 ± 0.021 | 0.306 ± 0.020 | −11.9% |
| MLP (64,32) | 0.347 ± 0.035 | 0.337 ± 0.017 | −26.4% |
| MLP (128,64) | 0.384 ± 0.100 | 0.353 ± 0.020 | −32.3% |
| Seasonal naive (12m) | 0.473 | 0.473 | −77.3% |

**Nothing beats the random walk.** The series is close to a martingale at
monthly frequency: predicting "same as last month" is better than any fitted
model, and predicting the average training growth rate is no better than
predicting zero growth, which says the conditional mean of log growth given 21
features is approximately constant.

### The diagnostic that separates the two failure modes

| model | MAE train | MAE test | gap |
|---|---|---|---|
| Naive (last month) | 0.432 | 0.267 | −0.165 |
| Ridge | 0.408 | 0.290 | −0.119 |
| MLP (16) | 0.349 | 0.306 | −0.044 |
| MLP (64,32) | 0.195 | 0.337 | +0.142 |
| MLP (128,64) | 0.158 | 0.353 | +0.195 |

Two different failures, and the distinction matters:

- The **large** networks overfit outright (train 0.158 against test 0.353).
- **`MLP (16)` does not overfit at all** — its test error is *better* than its
  training error — and it still loses to naive.

That second row is the finding. If only the big networks had failed, the answer
would be "regularise more". A well-behaved small network losing too means the
conditional structure is not there to fit, and tuning will not produce it.

(The baselines' negative gaps are not a bug: the test window is calmer than the
2018–2021 history, where small states had volatile low counts.)

### Learning curve — would more data help?

`MLP (64,32)`, trained on the most recent fraction of the window:

| train months | train rows | MAE test (log) |
|---|---|---|
| 19 | 646 | 0.552 |
| 38 | 1,292 | 0.410 |
| 56 | 1,898 | 0.333 |
| 75 | 2,455 | 0.338 |

Falls steeply, then **flat over the last quarter** (0.333 → 0.338). It has
saturated well short of naive's 0.267, so more history would not close the gap.

### Per state

The network beats naive in **6 of 34** states; median skill −0.246. The failure
is general, not an artifact of a few large states.

---

## Reproducing

```bash
.VENV/bin/python final-deliverable/model/nn/nn_volume.py          # ~20s
.VENV/bin/python final-deliverable/model/nn/nn_announcements.py   # ~12min, placebo dominates
.VENV/bin/python final-deliverable/model/nn/make_summary.py       # rebuild tables
.VENV/bin/python -m pytest final-deliverable/model/nn -q          # 21 checks
```

The ablation and its placebo are `national_ablation()` and `placebo_for_set()`
in `nn_announcements.py`; they are not in `run()` because together they add
~4 minutes on top of it.

---

## For the modelling track

Two things found while doing this, neither acted on, both belonging to whoever
owns the modelling code:

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

**2. A sequence model is the one architecture this data has not been given.**
Track B rules out a feedforward network on engineered lags. It does not rule out
an LSTM or temporal CNN reading the raw monthly sequence, which is a different
hypothesis (the lags may be the wrong summary rather than the signal being
absent). That needs torch, so it is a real decision rather than an afternoon —
and given that naive wins by 12% on the best network here, the prior should be
low.
