# EV data for India — ingestion notes

Data pulled via the Thurro connector for the term project. Everything here covers
India only, and every figure is a unit count unless stated otherwise.

Production and national registrations pulled 2026-09-20. State registrations,
pricing, investment projects and investment announcements pulled 2026-09-28.

## Layout

- `raw/` — saved connector extracts, unmodified. `QUERIES.md` records the query
  behind each one.
- `processed/` — built from `raw/` by `scripts/build_processed.py` and
  `scripts/parse_production_extract.py`. Cleaned and validated; safe to model on.
- `manual/` — hand-coded from source documents rather than derived from an
  extract. Extending these means reading, not re-running a script.

## What's here

| File | Grain | Coverage | Rows |
|---|---|---|---|
| `processed/ev_production_model_monthly.csv` | month × category × segment × sub-segment × OEM × model | 2023-04 → 2026-08 | 1,363 |
| `processed/ev_registrations_segment_monthly.csv` | month × vehicle segment | 2018-01 → 2026-09 | 799 |
| `processed/ev_registrations_maker_monthly.csv` | month × maker | 2023-01 → 2026-09 | 891 |
| `processed/ev_registrations_state_monthly.csv` | month × state (segments as columns) | 2018-01 → 2026-09 | 3,216 |
| `processed/ev_maker_reference.csv` | maker | — | 20 |
| `processed/ev_prices_car_variants.csv` | model variant × distinct price | 2025-11 → 2026-09 | 604 |
| `processed/ev_prices_2w_variants.csv` | model variant × distinct price | 2025-11 → 2026-09 | 50 |
| `processed/investment_projects_auto_energy.csv` | project | snapshot dated 2026-07-04 | 117 |
| `manual/investment_announcements.csv` | announcement event | 2023-12 → 2026-09 | 21 |

All month values are the first day of the month.

The four datasets named on the project slide map to these as: national production
& sales → the production file; state-level registrations → the state file;
EV pricing & specs → the two price files; industrial investment tracking →
`investment_projects_auto_energy.csv`, **which does not contain usable data** —
see below. `investment_announcements.csv` is the substitute dependent variable.

### `ev_production_model_monthly.csv`

Manufacturer-reported (SIAM) monthly **production**, domestic sales and exports
by model. This is the only genuine production series in the set — the others
are registrations.

`month, category, segment, sub_segment, oem, model, production_units,
domestic_sales_units, export_units`

A blank metric means the model reported nothing that month, which is distinct
from a reported `0`.

### `ev_registrations_segment_monthly.csv`

VAHAN monthly EV **registrations** by vehicle segment (2W, 3W, 4W, buses, LCV,
M&HCV, tractors, construction equipment).

`month, vehicle_segment, ev_registrations`

### `ev_registrations_state_monthly.csv`

The same VAHAN source cut by state, with the nine vehicle segments pivoted into
columns so each row is one state-month. 36 states and union territories.

`state, month, ev_2w, ev_3w, ev_4w, ev_buses, ev_small_buses, ev_lcv, ev_mhcv,
ev_tractors, ev_constr_eq, ev_total`

The segment columns sum to `ev_total` on every row, and the state totals
reconcile **exactly** against `ev_registrations_segment_monthly.csv` — 10,126,919
registrations across all 105 overlapping months, zero discrepancy. This is the
file the state-siting (stretch) question needs; the maker and segment files
carry no geography.

### `ev_registrations_maker_monthly.csv` + `ev_maker_reference.csv`

The same registrations source cut by maker, limited to the 20 makers with the
highest EV volume since 2023-01. Ticker and ISIN live in the reference file
rather than being repeated on every row; join on `maker`. Seven of the twenty
are NSE-listed — the rest are unlisted (Ampere, BGauss, YC Electric, the
e-rickshaw makers).

`month, maker, ev_registrations` / `maker, nse_symbol, isin`

### `ev_prices_car_variants.csv` + `ev_prices_2w_variants.csv`

Weekly scraped listing prices and specs, deduplicated to one row per variant per
distinct price, with the window over which that price held. `weeks_observed`
counts the weekly snapshots backing the row, so a price change appears as
consecutive rows for the same variant.

Cars: `brand, model, variant, ex_showroom_price_inr, battery_kwh, range_km,
seats, rating, reviews, first_seen, last_seen, weeks_observed`

Two-wheelers: same, minus `seats`, and with no battery capacity for most rows.

Source prices arrive in Lakh or Crore for cars and rupees for two-wheelers;
all are normalised to rupees here (1 Lakh = 100,000, 1 Cr = 10,000,000).

The two-wheeler file is cleaned in the query rather than downstream: the two
spellings of the Royal Enfield Flying Flea are folded into one model, the
unreliable body-type column is dropped (which also removes the duplicate rows
created by the Bajaj Chetak being filed as both `Bike` and `Scooter`), and the
placeholder `rating` of 0 becomes a null. That is why it holds 50 rows rather
than the 55 the raw source returns.

### `manual/investment_announcements.csv`

Dated capacity and capex announcements by listed auto, battery and ancillary
firms, hand-coded from exchange filings, press notes, board-meeting outcomes and
earnings-call transcripts in the connector's filings corpus.

`announcement_date, date_precision, company, event_type, facility, state,
capex_inr_cr, capacity, source_url, evidence`

`date_precision` is `exact`, `month` or `fiscal_period` — 8 of 21 rows carry an
exact date, and those come from press notes and board-meeting filings, which are
the only sources that date an announcement to the day. `capex_inr_cr` is blank
where the filing gave a range or no figure rather than a single number.

## Caveats worth knowing before you model on this

**The industrial-investment dataset is empty of EV content.** The build step
collapses this source's three null spellings (`-`, `None`, empty) to empty, but
that is the only change made to it. This was checked
twice and the file is committed only as evidence of the gap. The whole automotive
sector in that source is **two rows**, titled `Infra` and `Non NIP worklist
rejection` (the latter sited "Offshore"). Of the 115 Energy Storage rows, 113 are
`Oil/Gas/LNG Storage` — refineries, LPG bottling plants, crude pipelines — and
the remaining two are a solar PV project and a strategic petroleum reserve. **No
title in the file matches any of** `batter`, `lithium`, `cell manufact`,
`electric vehicle`, `ev`, `gigafactor`. Separately, every row shares a single
snapshot date, so the source could not yield an announcement time series even if
the rows were on-topic. Keyword matching on "battery" returns coke-oven batteries
at steel plants.

**The announcements file is a seed, not a census.** It is what three passes over
the filings corpus surfaced, covering 16 companies. Building the full event
series — and deciding the inclusion rule for what counts as an "announcement" —
is the remaining work on the dependent variable. Treat the current row count as
too small to regress on.

**Announcement dates are mostly imprecise.** Half the rows are dated only to a
fiscal period, because annual reports describe a facility without saying when it
was announced. A lead-lag test needs the `exact` and `month` rows, or a rule for
placing fiscal-period events.

**Registrations are not production.** They lag manufacture, they are recorded at
the RTO where the vehicle is registered rather than where it was built, and they
exclude exports entirely. Use the production file when you mean production. This
matters doubly for the siting question: a state's registrations measure where
vehicles are *bought*, not where they are *made*.

**Passenger-car EV production is under-covered.** The production source tags
electric two- and three-wheelers with an explicit electric sub-segment, but
classifies passenger vehicles by length and price instead. Four-wheeler EVs are
therefore only caught when the model name itself carries an EV marker (`XEV`,
`Comet EV`, `ZS EV`). Nameplates like Nexon or Punch, which are sold in both ICE
and electric variants under one name, are **not** separable in this feed and are
absent from the production file. For 4W EV volumes, use the registrations files,
where the fuel type is recorded explicitly.

**The production series is short.** It starts 2023-04, giving 41 monthly
observations — thin for testing leads of several months. The registrations files
reach back to 2018 (segment, state) and are worth considering as an extended or
alternate independent variable.

**The last month is partial in both sources, for different reasons.** The
registrations files run to 2026-09-15, so 2026-09 is roughly half a month and
will read as a sharp drop. Separately, **2026-08 production is incomplete**: only
5 of the 11 OEMs reporting in 2026-07 appear in 2026-08 (Ather, Hero, Honda,
Suzuki, Yamaha and Okinawa are all missing), which reads as an 88% month-on-month
collapse and is a reporting artefact, not a real one. The usable production
series therefore ends **2026-07**, giving 40 months, not 41. Drop both tail
months or annualise them.

**Pricing covers ten months, not a history.** Both price files start 2025-11 and
are weekly scrapes, so they support cross-sectional comparison and short-run
price moves, not a multi-year price series.

**Two-wheeler pricing is thin.** The source carries only seven legacy brands, so
Ather and Ola — two of the largest electric 2W makers by registrations — are
absent entirely. Battery capacity is populated only for the TVS iQube family.
The source's duplicate-model and placeholder-rating defects are fixed in the
query; see the pricing section above.

**EV identification differs by file.** Cars and two-wheelers are identified as
electric by their range unit (`km` / `km per charge`) rather than by a fuel flag;
filtering on battery capacity alone finds only 6 two-wheeler rows instead of 55.

**Fiscal years.** The production source is organised on India's April–March
fiscal year, which is why it starts at 2023-04.

## Regenerating

The CSVs are committed, so nothing needs to be re-run to use them. The
production file is rebuilt from the raw extracts with:

```bash
python3 scripts/parse_production_extract.py data/raw/production_*.toon -o data/processed/ev_production_model_monthly.csv
```

The extracts in `raw/` were split across calls because the connector caps a
single result at 1,000 rows. `production_03` is a targeted re-pull of 2025-04,
the month the first extract truncated mid-way; the parser sorts inputs by
filename and lets later files win on key collisions, so it must keep sorting
last. The parser also drops substring false positives — an unanchored match on
"ev" pulls in Bonneville.

Everything else in `processed/` is rebuilt from the extracts in `raw/` with:

```bash
python3 scripts/build_processed.py
```

That script applies the cleaning rules and re-runs the validation checks (segment
columns sum to `ev_total`, state-month keys unique). `scripts/toon_to_csv.py` is
the shared reader underneath it.

Two files are not rebuilt by it, both noted in the script's output:
`ev_prices_2w_variants.csv`, because at 50 rows the connector returned it inline
and no extract was saved, and `manual/investment_announcements.csv`, because it
is hand-coded. `data/raw/QUERIES.md` holds the exact query for both, so the
two-wheeler file can be reproduced on demand.

**Read `data/raw/QUERIES.md` before re-pulling anything.** It documents two
connector behaviours that will otherwise bite you: the row cap scales with row
width, so adding columns silently costs you rows, and small results are returned
inline instead of being written to disk.
