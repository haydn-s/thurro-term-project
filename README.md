# EV production and ancillary investment

**Does national growth in EV production predict new automotive-sector
manufacturing-investment announcements?**

Term project for AIPI 590 (Alternative Data), Duke Pratt School of Engineering.
All data is pulled from the Thurro connector and covers India.

In plain terms: when more electric vehicles roll off assembly lines nationally,
is that a leading signal that automakers are about to announce new factories or
expansion investments — and does the same pattern predict *which states* land
the money?

## Deliverables

| | Question | Weight |
|---|---|---|
| **Primary** | National EV production growth leads investment announcements | ~80% |
| **Stretch** | State-level EV demand concentration explains where investment gets sited | ~20% |

The primary question is national and stands alone. The siting question is an
extension, not a requirement.

## Status

Data ingestion is complete for all four dataset families named in the project
brief. Modelling has not started.

Three of the four are in good shape. The fourth — industrial investment
tracking, which was meant to supply the **dependent variable** — turned out to
contain no EV content at all.

Following industry-partner feedback, the dependent variable has been rebuilt from
**company financials** rather than from announcement events: a named target set of
52 companies, and what they actually spent on plant each year, read from their
filed cash-flow statements. That takes the dependent variable from 16 usable
events to 182 company-years. Announcements are what a company said; capex is what
it spent, which is the backward-looking confirmation the feedback asked for.

One caveat travels with that fix: more companies buys precision, not time. The
independent variable is a single national series and capex is filed annually, so a
pooled regression still turns on four distinct values of X. The route that
identifies a lead is the six companies that have *their own* monthly EV volume
series, where X varies by company and by month.

**That route has now been built and tested, and the answer is null.** The
within-company relationship between a company's own EV volume growth and its own
asset growth is r = -0.003, and the one-period lead is r = -0.37 — wrong sign, and
on 19 observations. The national design has only 2–3 usable period pairs, so it
cannot be estimated at all. The well-powered cross-sectional test finds no
difference in capex intensity between EV-exposed firms and the rest (2.06 vs 2.08,
t = -0.06, n = 35), and an ICE-only negative control moves with the EV names.

The reading that survives is that **FY23–FY26 automotive capex was driven by a
sector-wide cycle, not by EV volumes specifically.** That is a real answer to the
project's question rather than a data failure, and it is what model evaluation
should be scoped around. The full working is in
[`notebook-590/03_capex_panel_eda.ipynb`](notebook-590/03_capex_panel_eda.ipynb).

See [`data/README.md`](data/README.md) for the full accounting and
[`presentations/`](presentations/) for the current status deck (which still
describes the pre-feedback state of the dependent variable).

## What's in the data

| Dataset | Grain | Coverage |
|---|---|---|
| EV production (SIAM) | month × OEM × model | 2023-04 → 2026-07 usable (40 months) |
| EV registrations (VAHAN) | month × state, × segment, × maker | 2018-01 → 2026-08 usable (104 months) |
| EV pricing & specs | model variant × price | 2025-11 → 2026-09 |
| Industrial investment projects | project | single snapshot — **no usable EV content** |
| Investment announcements | event | 2021-12 → 2026-09, hand-coded, 34 events |
| Target companies | company | 52 named, 36 in the modelling panel |
| Company capex | company × fiscal year | FY23 → FY26, 47 companies, 182 rows |
| Company asset stocks | company × half year | 2023-03 → 2026-03, 33 companies |
| Modelling panels | company × period | financials joined to national and own-company X |

Selected findings from first-pass exploration:

- National EV registrations grew from 9,008/month (2018-01) to a peak of
  332,544 (2026-07).
- The market is two- and three-wheelers: 62% 2W, 27% 3W, 10% 4W by 2026 volume.
- Demand is geographically concentrated but not extreme — the top five states
  take 49% of registrations (HHI 0.071), led by Uttar Pradesh at 14%.
- Production coverage of registrations *rose* from 18% to 60% over the clean
  40-month window, so the production feed captures a growing share of the market
  — but month-on-month growth in the two series correlates at only +0.24, and a
  lead test on the pair alternates sign (+0.24 at k=0, −0.20 at k=1, +0.40 at
  k=2), which reads as noise at n≈37 rather than structure.
- **16 dated announcement events** (exact or month precision) fall inside the
  usable production window (2023-04 → 2026-07), across 11 distinct months, up
  from 9 events in the first seed. Still thin for a lead test; see
  [`data/README.md`](data/README.md).
- Capex across the 36-company panel ran **29,808 → 42,510 → 52,841 → 52,760 Cr**
  over FY23–FY26: a 77% rise over three years that flattens in the last one. That
  is a dependent variable with real movement in it, unlike the announcement count.
- Only **7 of 52** target companies have their own monthly EV volume series to
  pair against their own capex. That overlap, not the 182-row total, is what
  determines whether a lead is detectable.

## Repository layout

```
data/
  raw/        connector extracts, unmodified + QUERIES.md (the query behind each)
  processed/  built from raw/ by scripts/, cleaned and validated
  manual/     hand-coded from source documents; no script can regenerate these
  README.md   grain, provenance and caveats for every file — read before modelling
scripts/
  build_processed.py          rebuilds processed/ from raw/
  build_financials.py         rebuilds the company capex and asset files
  build_panel.py              joins the financials to the EV volume series
  parse_production_extract.py rebuilds the production file
  toon_to_csv.py              shared reader for saved connector results
presentations/
```

## Reproducing the data

The CSVs are committed, so nothing needs re-running to use them.

```bash
python3 scripts/build_processed.py
```

That rebuilds everything in `processed/` from the extracts in `raw/`, applying
the cleaning rules and re-running the validation checks (segment columns sum to
totals; state-month keys unique; state totals reconcile against the national
file).

The company financials rebuild separately:

```bash
python3 scripts/build_financials.py
```

That one also re-checks both financial extracts against
`data/manual/target_companies.csv` in both directions, so a company that silently
drops out of the feed fails the build instead of quietly shrinking the panel.

Then the modelling panels, which join those to the EV volume series:

```bash
python3 scripts/build_panel.py
```

Two files are outside that pipeline and the script says so when it runs: the
two-wheeler price file (the connector returned it inline, so no extract was
saved) and the hand-coded announcements file. `data/raw/QUERIES.md` records the
exact query behind every extract, so anything can be re-pulled.

**Read `data/raw/QUERIES.md` before re-pulling.** It documents two connector
behaviours that cause silent data loss: the row cap scales with row width, and
small results are returned inline rather than written to disk.

## Presentations

`presentations/ev-investment-update.pptx` — 8-slide status deck (5–7 min):
problem statement, target datasets, initial EDA, success criteria and
evaluation, roadmap, plus a backup slide covering the data problems found and
the open questions for stakeholders. Speaker notes are on every slide.
