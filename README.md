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
contain no EV content at all, and the substitute built from exchange filings is
currently too small to regress on. That is the open risk on the project, and it
is a design problem rather than a data-availability one. See
[`data/README.md`](data/README.md) for the full accounting and
[`presentations/`](presentations/) for the current status deck.

## What's in the data

| Dataset | Grain | Coverage |
|---|---|---|
| EV production (SIAM) | month × OEM × model | 2023-04 → 2026-07 usable (40 months) |
| EV registrations (VAHAN) | month × state, × segment, × maker | 2018-01 → 2026-08 usable (104 months) |
| EV pricing & specs | model variant × price | 2025-11 → 2026-09 |
| Industrial investment projects | project | single snapshot — **no usable EV content** |
| Investment announcements | event | 2021-12 → 2026-09, hand-coded, 34 events |

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

## Repository layout

```
data/
  raw/        connector extracts, unmodified + QUERIES.md (the query behind each)
  processed/  built from raw/ by scripts/, cleaned and validated
  manual/     hand-coded from source documents; no script can regenerate these
  README.md   grain, provenance and caveats for every file — read before modelling
scripts/
  build_processed.py          rebuilds processed/ from raw/
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
