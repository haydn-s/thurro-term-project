# Exploratory model analysis

Does national EV production growth lead automotive manufacturing-investment
announcements, and does state-level EV demand explain where they land?

This folder compares **7 national models** and **9 state models** on the same
data with the same out-of-sample test. Findings and numbers are in
[`../exploratory-models-card.md`](../exploratory-models-card.md); the latest run's
headline table is regenerated at [`../results/summary.md`](../results/summary.md).

## Run it

```bash
pip install -r requirements.txt                      # repo-root notebook environment
python scripts/build_panel.py                        # refresh data/clean and data/model
python final-deliverable/model/exploration/run_all.py   # ~8 minutes
pytest final-deliverable/model/exploration -q        # 14 checks, incl. no-leakage
```

## Files

| file | what it does |
|---|---|
| `config.py` | every setting: paths, targets, horizons, test split, placebo runs |
| `data.py` | reads the four files in `data/clean/` |
| `feature_engineering.py` | builds ~30 features from `data/clean/` (national monthly, state x month, state x fiscal year) |
| `models.py` | the candidate models, each a small dict |
| `evaluation.py` | walk-forward test, metrics, bootstrap CI, placebo test |
| `national_analysis.py` | primary question: lead-lag scan, cross-correlation, Granger, model comparison, ablation, placebo, interpretation |
| `state_analysis.py` | stretch question: time-split model comparison, logit inference, fiscal-year model |
| `plots.py` | the 11 charts in `results/figures/` |
| `run_all.py` | runs everything and writes `results/summary.md` |
| `test_exploration.py` | target alignment, look-back, leakage, state shares, fiscal-year mapping |

## Data used (all from `data/clean/`)

| file | used for |
|---|---|
| `production_model_monthly.csv` | production level / growth / momentum, 2W-3W-PV mix, exports, unsold units, OEM concentration |
| `registrations_segment_monthly.csv` | national EV demand growth (total and 4W) |
| `registrations_state_monthly.csv` | state demand share, 4W/2W share, share change, growth, size, rank |
| `announcements_clean.csv` | the dependent variable (3 definitions), announcement history, fiscal-year dating |

## Features

| group | features | idea |
|---|---|---|
| controls | `time_trend`, `month_sin`, `month_cos`, `results_season` | the sector-wide cycle and calendar; the null every EV feature must beat |
| history | `events_last_6m` | announcements cluster |
| production | `prod_growth_1m`, `prod_growth_3m`, `prod_accel`, `prod_vs_6m_max`, `prod_record_high` | the variable the question names: growth, momentum, capacity pressure |
| segment mix | `prod_2w/3w_growth_3m`, `pv_share`, `three_w_share`, `export_share`, `inventory_build_3m` | which segment is growing, and whether output outruns sales |
| industry | `oem_hhi`, `top_oem_share`, `n_active_oems`, `oem_hhi_change_3m` | concentration across OEMs |
| demand | `reg_growth_3m`, `reg_4w_growth_3m`, `supply_minus_demand_3m` | registrations, and production running ahead of them |
| state | `share_total`, `share_4w`, `share_2w`, `share_change_6m`, `state_growth_6m`, `log_size_12m`, `top5_state`, `national_hhi`, `past_announcements`, `months_since_last`, `ever_announced` | demand concentration vs. a state's own track record |

Every feature at month t uses only data up to month t; targets are months t+1..t+h.
`prod_growth_6m` is computed but not modelled, because `prod_accel = 2*growth_3m - growth_6m`
exactly.

## How models are compared

* **Walk-forward test.** Train on every month whose outcome is already known, predict the
  next month, roll forward one month. 18 test months (national, h=1).
* **Metrics.** Brier score (main), log loss, AUC, average precision. Brier skill =
  1 - Brier_model / Brier_baseline, so > 0 means better than the base rate.
* **Bootstrap.** 90% interval of the Brier gain over the baseline, resampling test months.
* **Ablation.** The same model with feature groups added one at a time on top of the
  controls - this is the direct test of whether EV production adds anything.
* **Placebo.** Slide the production columns along the calendar by a random offset (200 runs)
  and refit. A real lead should beat nearly all shifted copies.
* **State models** train on state-months up to 2025-06 and test after, and also report
  how often the announcing state was in the model's top-5 that month.

## Bug found in the shared panel

`data/model/national_panel.csv:production_4w` is 0 in every month: `scripts/features.py`
filters production on `segment == "4W"`, but the production file keeps 2W / 3W /
Passenger Vehicles in `category`. This package reads `category` directly.
