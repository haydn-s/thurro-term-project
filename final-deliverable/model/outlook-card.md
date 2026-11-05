# Outlook models — model card

The two models the deliverable serves on `/outlook/national` and
`/outlook/states`. Artifact: [`outlook.json`](outlook.json) · built by
[`build_outlook.py`](build_outlook.py) · checked by
[`test_outlook_build.py`](test_outlook_build.py) · served by
[`../app/outlook.py`](../app/outlook.py).

Both specifications come from the exploration study
([`exploratory-models-card.md`](exploratory-models-card.md)), including its
2026-10-22 re-test with an ICE-production control. Nothing here is a new model:
the build imports the study's feature code (`exploration/feature_engineering.py`)
and model factory (`exploration/models.py`), fits, and exports.

## Provenance

| | |
|---|---|
| Built | 2026-11-01, `build_outlook.py`, repo-root `.VENV` (Python 3.14.7, scikit-learn 1.9.1, pandas 3.0.6) |
| Inputs | the five `data/clean/` files `exploration/data.py` reads; sha256 of each in `outlook.json` → `inputs` |
| Data through | 2026-09 for both models (production complete through 2026-09 after the PR #13 refresh) |
| Forecast month | 2026-10 |
| Versions | `national-announcement-logit` and `state-siting-logit`, both `1.0.0+data.202609` |

`1.0.0` is the specification; the suffix is the data month it was refit on and
changes on every rebuild.

## National: will there be an announcement next month?

| | |
|---|---|
| Model | Logit L2 (`StandardScaler` + `LogisticRegression(C=1)`), the study's `logit_l2()` |
| Features (15) | `CONTROLS_ICE` + `PRODUCTION` + `SEGMENT_MIX`: ICE-production growth, month seasonality, results season; five EV production-growth measures; six segment-mix and trade measures (2W/3W growth, PV and 3W share, export share, inventory build) |
| Target | `y_any_all_h1`: at least one announcement (any kind) in month t+1 |
| Served fit | every month with a known outcome: 2023-10 to 2026-08, 35 months, 12 with an announcement (base rate 0.34) |
| Scores | the 2026-09 row → P(announcement in 2026-10) |

**Out of sample** (walk-forward, expanding window, re-run by the build on the
same data; it reproduces `results/national/8_ice_control_ablation.csv`):

| test months | events | Brier | base-rate Brier | Brier skill | 90% CI of gain | AUC |
|---|---|---|---|---|---|---|
| 19 (2025-02 → 2026-08) | 8 | 0.177 | 0.266 | **+33.6%** | [0.020, 0.164] | 0.84 |

Beats all 200 calendar-shifted placebo copies of the production columns
(`results/national/8b_ice_control_placebo.csv`). An MLP picked the same
production + mix set independently, with the trend controls, and also beat
every placebo ([`nn-models-card.md`](nn-models-card.md)). Two model
families converging on one set, and its interval clearing zero, is why it was
selected over the study's earlier pick, the lasso on all features (+10.6% on
the pre-refresh data, interval including zero).

**Why ICE growth rather than the time trend.** Both give the same skill (+33.6%
vs +33.1%), but ICE growth beats every placebo where the trend version lets 4.5%
through, and it tests the question directly: does EV production say anything
beyond the sector cycle? It is also the right control to *serve*.
`time_trend` is rescaled to [0, 1] over whatever sample it is built on, so the
latest month is always 1.0 and its meaning shifts with every refit.

**What it says now.** P(announcement in October 2026) = **0.85** against a base
rate of 0.34. The largest contributions are export share (+2.05 log-odds; at
2.6% of production it is 2.3 standard deviations above its training mean, the
third-highest month on record) and a record EV production month (+1.22).

### Limits — these travel with the number as `model.notes`

- **Selection.** The feature set is the best of 14 runs (7 sets × 2 model
  families); its interval carries no correction for that choice. The placebo is
  the part of the evidence selection does not explain.
- **Concentration.** 83% of the walk-forward gain comes from 3 of 19 test
  months (2026-05, 2026-06, 2026-08), all in the 2026 run of announcements.
- **Production growth alone adds nothing** once ICE growth replaces the trend
  (−0.2% skill). The signal is in the composition of production — export share
  and inventory build — not its headline growth.
- **Announcements are hand-coded,** and recent ones are easier to find, so the
  2026 cluster may be partly a collection effect that any 2026-trending feature
  would fit.
- **ICE growth is a weak control on its own** (−12.8% skill, AUC 0.50). Beating
  it rules out "the mix features just proxy a trend"; it does not show they beat
  a good model of the sector cycle.

The test that would retire most of these is time: score months after 2026-09,
which no one selected a model on, once their announcements are coded.

## State: where will it be sited?

| | |
|---|---|
| Model | Logit L2, the study's `logit_l2()` |
| Features (6) | `STATE_SETS["share+history"]`: share of national EV registrations, share of 4W registrations, six-month share change (all 3-month rolling); past announcements, months since the last, ever announced |
| Target | the state is named in at least one announcement in month t+1 |
| Served fit | every state-month with a known outcome and complete features: 2018-07 to 2026-08, 2,967 rows, 18 with an announcement |
| Scores | the 2026-09 row for each of 34 states → a ranking for 2026-10 |

**Out of sample** (train to 2025-06, test after; the study's
`state_analysis.model_comparison`, re-run on the refreshed data):

| test rows | events | AUC | avg precision (base 0.023) | top-5 hit rate |
|---|---|---|---|---|
| 488 | 11 | **0.85** | 0.124 | **0.64** |

These match the study's pre-refresh table to two decimals.

**What it says now.** Top five for October 2026: Maharashtra (0.12), Telangana,
Tamil Nadu, Karnataka, Gujarat. Maharashtra's rank comes mostly from its record
(it has had announcements; +1.70 and +0.68 log-odds) and then its 4W share
(+0.61).

### Limits

- **Read the rank, not the level.** 18 positive state-months is too few to
  calibrate a probability; the top-5 hit rate is the evidence.
- **Demand share and state size are hard to separate.** A logit on 12-month
  EV registrations alone scores test AUC 0.77 against this model's 0.85, and
  the same 0.77 as share alone in the study. A high rank means "large EV market
  with a record of announcements"; it does not show demand caused the siting.
- **The state features shift by row, not month.** `state_features` rolls and
  lags a sparse panel positionally (see [`nn-models-card.md`, "For the
  modelling track"](nn-models-card.md#for-the-modelling-track)). Since 2025
  that touches only Ladakh, Lakshadweep, Nagaland and Sikkim (20
  state-months), none of which has had an announcement, so it is unlikely to
  move this ranking; it has not been re-checked with a reindexed panel.

## Rebuilding

```bash
.VENV/bin/python final-deliverable/model/build_outlook.py
.VENV/bin/python -m pytest final-deliverable/model/test_outlook_build.py -q
```

Re-run after any change to `data/clean/`. The build takes about two seconds;
`test_outlook_build.py` fails until the committed artifact matches the data,
checks the national evaluation against the study's own ablation code, and
checks that the scored month is never a training month.

To change a specification, edit `NATIONAL_FEATURES` or `STATE_SET` in
`build_outlook.py` and rebuild. The service needs no change: it reads the
feature list from the artifact.
