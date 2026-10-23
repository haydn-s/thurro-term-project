# Exploratory model analysis — model card

Code: [`exploration/`](exploration/README.md) · results: [`results/`](results/) ·
run: `python final-deliverable/model/exploration/run_all.py`

## Question

**Primary (~80%).** Does national EV production growth lead automotive-sector
manufacturing-investment announcements?
**Stretch (~20%).** Does state-level EV demand concentration explain where the
investment is sited?

## Data and window

| | |
|---|---|
| Inputs | all four files in `data/clean/` (production, segment registrations, state registrations, announcements) |
| National sample | 2023-10 to 2026-07, **34 months** (production starts 2023-04; first 6 months used as look-back) |
| Dependent variable | announcements in month t+1 (h=1) or t+1..t+3 (h=3); three definitions: all / EV or mixed / EV only |
| Events | 11 of 34 months are followed by an announcement (target = all, h=1) |
| Out-of-sample test | walk-forward, expanding window, 18 test months with 7 events |
| State sample | 36 states x month; train to 2025-06 (7 events), test 2025-07 to 2026-08 (11 events) |

## Models compared

| national model | features | why it is here |
|---|---|---|
| Baseline | none | the base rate every model must beat |
| Logit, controls only | trend, seasonality, results season | the "sector cycle" null, no EV information |
| Poisson, core | controls + production growth, acceleration, capacity pressure | natural model for a small count |
| Logit L2, core | same | yes/no framing with shrinkage |
| Logit L1 (lasso), all | all 23 features | lets the data pick a few |
| Random forest, all | all 23 | non-linear, thresholds |
| Gradient boosting, all | all 23 | second non-linear learner |

State models: base rate, an unfitted demand-share ranking, L2 logits on six feature sets
(size / share / share+mix / history / share+history / all), and a random forest.

## Results — primary question

**1. The lead itself (in-sample).** No lead from 1 to 6 months is significant for 1-, 3-
or 6-month production growth (all p > 0.18; signs flip between leads). Granger tests
reject in neither direction (production → announcements p = 0.40–0.94). The time trend is
significant in every lead regression (p ≤ 0.015). Counts are mildly over-dispersed
(Pearson χ²/df = 1.8) but a negative binomial gives the same answer (p = 0.35).

**2. Model comparison (out-of-sample, target = all, h = 1).**

| model | Brier ↓ | log loss ↓ | AUC ↑ | Brier skill | 90% CI of gain |
|---|---|---|---|---|---|
| Baseline | 0.256 | 0.715 | 0.64 | — | — |
| Logit, controls only | 0.255 | 0.777 | 0.66 | +0.5% | [−0.041, 0.041] |
| Poisson, core | 0.238 | 0.698 | 0.71 | +6.8% | [−0.010, 0.043] |
| Logit L2, core | 0.236 | 0.780 | 0.69 | +7.8% | [−0.042, 0.078] |
| **Logit L1 (lasso), all** | **0.229** | **0.671** | 0.64 | **+10.6%** | [−0.020, 0.075] |
| Random forest, all | 0.236 | 0.738 | 0.71 | +7.9% | [−0.021, 0.057] |
| Gradient boosting, all | 0.272 | 1.017 | 0.73 | −6.5% | [−0.115, 0.077] |

Lasso is the best model on Brier and log loss; it and the Poisson model are the only
ones better than the baseline on both. No model's interval excludes zero. For the EV-only target, random
forest (+10.5%) and gradient boosting (+14.8%, but log loss 0.82) lead; again no interval
excludes zero. At h = 3 every model is worse than the baseline.

**3. Ablation (Logit L2 / random forest, h = 1).** Production growth adds +11% over the
controls in the logit. Adding the segment-mix block (exports, unsold units, 2W/3W growth)
gives the best result in the study: **Brier skill +27.6%, 90% CI [0.003, 0.142]**, AUC 0.81,
and it holds for the EV-only target (+21%). Demand and industry-concentration blocks do
not help. A random forest on the controls alone already reaches +15.6%, so part of what
any model gains is a non-linear version of the trend.

**4. Placebo (200 random time shifts of the production columns).**

| model | real Brier | median placebo | placebos as good |
|---|---|---|---|
| Logit L2, core | 0.236 | 0.282 | 4% |
| Poisson, core | 0.238 | 0.238 | 50% |
| Logit L2, controls+production+mix | 0.185 | 0.264 | 0% |

**5. What the models lean on.** Random-forest importance and lasso agree on
`inventory_build_3m` (−), `export_share` (+), the trend, recent announcement activity and
`top_oem_share` (−). Headline production growth gets zero lasso weight.

## Results — stretch question

| state model (test, h=1) | AUC | avg precision | top-5 hit rate |
|---|---|---|---|
| Baseline | 0.50 | 0.023 | 0.14 (random) |
| Demand-share rank, no fit | 0.77 | 0.064 | 0.45 |
| Logit L2, history only | 0.75 | 0.087 | 0.64 |
| **Logit L2, share + history** | **0.85** | **0.124** | **0.64** |
| Random forest, all | 0.85 | 0.102 | 0.45 |

* Demand share alone ranks states well (AUC 0.77): the announcing state was in the
  top-5 EV markets 45% of the time. Adding each state's announcement history lifts this to
  64% and AUC 0.85 — the best state model. The same order holds at h = 3 (AUC 0.86).
* In-sample logit: share stays significant with history controlled (+1 pp share → odds ×1.13,
  p = 0.009). Once 4W share is added it takes over (p = 0.007) and total share drops out —
  passenger-car demand, not total EV demand, is what lines up with siting.
* Annual (uses all 34 announcements incl. fiscal-year-dated ones): previous-year share
  correlates with announcements in FY24–FY27 (Spearman 0.33–0.40, p ≤ 0.05); +10 pp share
  → ×3.7 announcements (Poisson, p < 0.001).

## Reading

1. **Headline EV production growth does not lead announcements.** Lead-lag, Granger and
   the core models all say so; it gets no lasso weight.
2. **The best national model is the lasso (all features)**, and the most promising
   direction is the **segment-mix block** — export share and unsold-inventory build. It
   is the only result whose interval clears zero and that beats every placebo shift.
3. **Treat (2) as a lead for future work, not a finding.** It was the best of 14 ablation
   runs on 18 test months with 7 events; and a single trending series (export share
   alone) also passes the circular placebo (3% of shifts as good), so the placebo cannot
   fully separate "timing" from "shares the 2026 upward surge".
4. **Stretch: yes, with a caveat.** Where investment lands follows state EV demand
   (especially 4W), but a state's own track record carries as much signal.

## Recommended for future development

| use | model | why |
|---|---|---|
| National reporting model | **Logit L1 (lasso), all features** | best Brier and log loss, interpretable, picks its own features |
| National candidate to validate | Logit L2, controls + production + mix | best ablation result; needs data after 2026-07 to confirm |
| State siting | **Logit L2, share + history** | best AUC / precision / top-5 hit rate, simple coefficients |

Next steps: (a) re-test the segment-mix signal on months after 2026-07 before it is
served — **first pass done, see the re-test below; one new scored month only**;
(b) replace `time_trend` with an ICE-production control — **done, see below**;
(c) fix `production_4w` in `scripts/features.py` — **done**; the move of the useful
exploration features into `scripts/features.py` is still open.

## Re-test after the 2026-10-22 data refresh

Production now runs complete through 2026-09 (the 5-of-11-OEM August gap is
filled), so the national sample is 36 months, 2023-10 to 2026-09, with 35 known
targets and 12 events. Walk-forward test: **19 months, 8 events** (was 18 and 7).
Only **one** month is genuinely new to the test (t = 2026-08, outcome 2026-09: an
announcement happened; the model said 0.77 against a base rate of 0.32). The
2026-09 row has no outcome yet. Code: `exploration/ice_control_analysis.py`;
results: `results/national/8_ice_control_ablation.csv`, `8b_ice_control_placebo.csv`, `8d_mix_model_by_month.csv`;
figures: `results/figures/12_ice_control_comparison.png`, `13_ice_control_placebo.png`.

Controls: the original (linear `time_trend`) and ICE growth instead of the trend.
ICE = all-vehicle SIAM production minus the EV models.

| Logit L2, h = 1 | Brier skill | 90% CI of gain | AUC | placebos as good |
|---|---|---|---|---|
| controls + production + mix, original controls | +33.1% | [0.020, 0.162] | 0.84 | 4.5% |
| same, ICE growth replaces trend | +33.6% | [0.020, 0.164] | 0.84 | 0.0% |

(On the pre-refresh data the same code gives the card's +27.6%, [0.003, 0.142].)

* **The segment-mix result survives the control swap.** It is the same size with
  ICE growth in place of the trend. Its interval
  still clears zero, and it still beats nearly all shifted copies.
* **ICE growth is a weak control, not a stronger null.** On its own it scores worse
  than the base rate (Brier skill −12.8%, AUC 0.50): three-month ICE growth is a
  noisy, seasonal series, and the trend was doing real work. The test shows the mix
  features are not just proxying the trend; it does not show they beat a good
  model of the sector cycle.
* **Production growth alone adds nothing once the trend is gone** (+15.8% with the
  trend, −0.2% with ICE growth instead). That fits the capex finding that the
  cycle, not EV volume, is what moves.
* **The gain is concentrated.** Three months (2026-05, 2026-06, 2026-08, all
  events, all in the 2026 upswing) supply 84% of the total Brier gain. The
  new month is the third of them. That is why this is still a lead, not a finding:
  one extra event month cannot confirm it. More months, especially quiet ones, are
  what is needed; the Q3 results season (November) is the next chance.
* Not refreshed: the in-sample Poisson / Granger / lead-lag tables and the state
  models (they need `statsmodels`, which could not be installed where this was
  run), `results/summary.md` and the figures. Rerun `run_all.py` to update them.
