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
| `manual/investment_announcements.csv` | announcement event | 2021-12 → 2026-09 | 34 |
| `manual/target_companies.csv` | company | — | 52 |
| `processed/company_capex_annual.csv` | company × fiscal year | FY23 → FY26 | 182 |
| `processed/company_assets_halfyearly.csv` | company × half year | 2023-03 → 2026-03 | 239 |

All month values are the first day of the month.

The four datasets named on the project slide map to these as: national production
& sales → the production file; state-level registrations → the state file;
EV pricing & specs → the two price files; industrial investment tracking →
`investment_projects_auto_energy.csv`, **which does not contain usable data** —
see below.

Two files stand in for that fourth dataset, and they measure different things.
`investment_announcements.csv` holds what companies *said* they would build.
`company_capex_annual.csv` holds what they actually *spent*, read from their
filed cash-flow statements. The capex file is the better dependent variable and
should be treated as the primary one: it is regular, quantified, uniformly
defined across companies, and has 182 observations against the announcement
file's 16 usable events. The announcements remain useful as event markers — a
capex series says when money landed but not what it was for.

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

`date_precision` is `exact`, `month` or `fiscal_period` — 16 of 34 rows carry an
exact date, and those come from press notes and board-meeting filings, which are
the only sources that date an announcement to the day. `capex_inr_cr` is blank
where the filing gave a range or no figure rather than a single number.

### `manual/target_companies.csv`

The 52 companies the study's result would land on, and the reason each one is
there. Built from the union of three sources: a natural-language theme search of
the filings corpus ranked by mention count, the listed makers in
`ev_maker_reference.csv`, and every company named in
`investment_announcements.csv`. The exact theme query is in
[`raw/QUERIES.md`](raw/QUERIES.md).

`company, nse_symbol, tier, ev_volume_series, in_announcements, roster_mentions,
primary_panel, rationale`

`tier` is the scope judgement and the column that does the work:

| tier | n | what it means |
|---|---|---|
| `oem_ev_pure` | 3 | Vehicle maker whose capex is essentially all EV |
| `oem_ev_led` | 5 | Vehicle maker with a real EV line inside a larger book |
| `oem_ice_led` | 4 | Vehicle maker where EV is a small share of capex |
| `battery_cell` | 2 | Cell or battery maker |
| `ev_component` | 26 | Component supplier selling into EV programmes |
| `charging` | 1 | Charging hardware; tracks the fleet, not production |
| `upstream_material` | 9 | Metals and chemicals; capex driven by other end markets |
| `out_of_scope` | 2 | Cleared the theme search but does not make vehicles or parts |

`primary_panel` (36 of 52) is the modelling set: the first six tiers, minus the
five companies with no filing history. `upstream_material` and `out_of_scope` are
excluded but committed, because a reader should be able to see what was dropped
and why. Reliance alone would contribute capex two orders of magnitude larger
than the median panel company and would dominate any pooled regression.

`ev_volume_series = yes` marks the **seven** companies that also have their own
monthly EV registrations series in `ev_registrations_maker_monthly.csv`: Ola,
Ather, Bajaj, Hero, M&M, Tata Motors and TVS. That overlap matters more than its
size suggests — see the identification caveat below.

`roster_mentions` is the corpus-wide mention count that drove the ranking. It is
blank for the six companies added from our own files rather than from the roster.

### `processed/company_capex_annual.csv`

Annual capital expenditure per company, from filed consolidated cash-flow
statements. 47 companies, FY23 through FY26. This is the backward-looking
dependent variable.

`company, nse_symbol, isin, tier, primary_panel, fiscal_period, period_end,
fy_end_month, capex_cr, purchase_fixed_assets_cr, capital_expenditure_cr,
cwip_cr, asset_sales_cr, net_capex_cr, depreciation_cr, cfo_cr, net_investing_cr`

`capex_cr` is the headline figure: `purchase_fixed_assets_cr +
capital_expenditure_cr`. Those are two separate, additive line items in the
source, not two spellings of one — Ola, Bajaj and Syrma report both in the same
year, while Hero, Tata Power, Tube Investments and Belrise report only the
second. `net_capex_cr` nets off disposals. All values are INR crore, positive for
spending; the source signs outflows negative.

`cfo_cr` (operating cash flow) and `depreciation_cr` are carried for scaling —
capex in rupees is not comparable across a panel spanning Reliance and PPAP, so
model capex over one of these or over lagged assets rather than raw.

Aggregate panel capex runs 29,808 → 42,510 → 52,841 → 52,760 Cr across FY23–FY26:
a 77% rise over three years that flattens in the final year.

### `processed/company_assets_halfyearly.csv`

Balance-sheet asset stocks at each half year, 2023-03 to 2026-03. 33 companies,
seven periods. Its reason for existing is time resolution: capex is annual, this
is twice-annual, so a first difference here is the only sub-annual capex proxy
the feed supports.

`company, nse_symbol, tier, primary_panel, fiscal_period, period_end,
fy_end_month, fixed_assets_cr, intangible_assets_cr, productive_assets_cr,
total_assets_cr, split_flag`

**Difference `productive_assets_cr`, not `fixed_assets_cr`.** The September
balance sheet splits tangible from intangible differently than the March one, so
the tangible line alone lurches every other period without any investment
happening. `productive_assets_cr` is the sum of the two and is stable across the
boundary. `split_flag = reclassified` marks the 11 periods where the split moved
by more than a tenth of the base while the total held still — Ola three times,
Sona BLW four, M&M twice, Motherson and Autoline once each.

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

**Capex fixes the sample size but not the identification problem, and the
difference matters.** Moving the dependent variable from 16 announcement events
to 182 company-years is a real gain in precision on the *company* side. It buys
nothing on the *time* side. The independent variable is one national EV
production series, so in any regression of company capex on national production
every company in a given year sees the identical X. Annual capex gives **four**
distinct values of X (FY23–FY26); adding companies shrinks the standard error on
the noise but cannot manufacture time-series variation that is not there. A
pooled panel of 139 observations with company fixed effects and a national
regressor is still, for the purpose of detecting a lead, an n=4 test.

Three ways out, in descending order of how much they salvage:

1. **Company-specific X.** For the seven companies with their own monthly series
   in `ev_registrations_maker_monthly.csv`, regress a company's capex on *its own*
   EV volume growth. X then varies across both company and time, and the panel
   identifies off N×T rather than T. Seven companies × 4 years = 28 observations
   with genuine variation, and a within estimator becomes meaningful. This is the
   only design here that is a real panel rather than a short time series wearing
   a panel's clothes, and it is why `ev_volume_series` is a column on the target
   list. Note that Tata Motors contributes only FY25–FY26 and Ather contributes
   nothing, so the usable count is nearer 22.
2. **Half-yearly Y.** Differencing `productive_assets_cr` doubles the time points
   from 4 to 6 or 7. Cheap, and worth doing, but 7 is not 40.
3. **Cross-sectional intensity.** Drop the lead question and ask whether
   *cumulative* EV exposure predicts *cumulative* capex intensity across 36
   companies. This is well-powered and answerable, but it is a different and
   weaker claim than "production growth leads investment".

The registrations files reaching back to 2018 do not help here: capex simply is
not filed more often than annually, whatever the independent variable does. State
the constraint in the writeup rather than letting a large-looking n imply power
the design does not have.

**Capex is not EV capex.** Every figure is company-wide. M&M's capex covers
tractors and SUVs, Tube Investments' covers bicycles and steel tubes, Bharat
Forge's covers defence. No filing in this corpus decomposes capex by powertrain,
so an EV-only cut is not available at any price. The `tier` column is the honest
substitute: it says how much of a company's capex could *plausibly* be EV-driven,
and the tiering should be used as an interaction or a sample restriction rather
than being quietly ignored. `oem_ev_pure` (Ola, Ather, Olectra) is the only tier
where capex is close to EV-attributable, and one of the three has no data.

**Ather Energy is missing and it is the most expensive gap in the set.** A
pure-play electric 2W maker, its own registrations series, 47 mentions in the
theme roster — and no cash-flow history, because it listed in 2025. It is the
cleanest possible test case for the whole hypothesis and it cannot be tested.
Four more companies are absent for the same reason (Motherson Sumi Wiring, Rolex
Rings, Divgi Torqtransfer, Sedemac). Tata Motors is partially absent: the
demerger means only FY25 and FY26 exist under the `TMCV` ISIN, so India's largest
4W EV maker contributes two observations.

**Precision Camshafts is in the panel deliberately as a negative control.**
Camshafts are an ICE-only part. If national EV production growth "predicts" its
capex as strongly as it predicts Uno Minda's, the model is picking up the
automotive cycle rather than anything electric. Several other `ev_component`
names are ICE-heavy in practice, so consider a broader placebo set.

**Fiscal year ends differ, so `FY25` is not one window.** CIE Automotive closes
in December and Hyundai shows December and June periods alongside March. Join on
`fy_end_month` or restrict to March filers (135 of 139 panel rows) rather than
assuming the label lines up.

**Tata Power reports no capex at all in FY26** — both capex metrics are zero
where earlier years carry 7,656 to 17,273 Cr. That is a source gap, not a spending
halt. It sits outside the primary panel so it does not contaminate the modelling
set, but do not read the zero as real.

**The financials tables carry a staleness warning.** The connector flags the
yearly cash-flow and balance-sheet tables as stale, meaning their newest rows
predate the current reporting quarter. Both in fact reach 2026-03-31, the latest
completed fiscal year end, which is what this project needs. The warning is about
recency and not about the FY23–FY26 window being incomplete.

**The announcements file is a seed, not a census.** It is what four passes over
the filings corpus surfaced, covering 24 companies. The fourth pass (2026-09-28)
added 13 events across Sona BLW, Eicher (2), Hero MotoCorp (2), Ather, Hyundai, Zelio,
Sansera, Amara Raja, TVS, Exide and M&M. It ran focused
retrieval per company on the exchange-filings domain and kept only dated primary
documents (board outcomes, Regulation 30 intimations, press notes, earnings-call
transcripts) or annual-report statements. Ratings rationales, DRHP boilerplate and
industry-overview text were discarded. 16 events with exact or month dates fall in
the usable production window (2023-04 → 2026-07), across 11 months. Two rows
(Exide 2021-12, TVS 2023-01) pre-date the production series and are usable only
against the registrations files.

*Inclusion rule used:* India manufacturing capacity for automotive, EV, battery-cell
or auto-component production, from a listed company, as a board approval, new-plant
announcement, capacity expansion, commissioning, or an explicit capex figure or
guidance. Excluded: overseas plants (e.g. Sona Comstar Mexico, April 2024), solar
and other non-auto manufacturing (Tata Power), parts-logistics centres (Hero GPC 2.0,
Tirupati), charging-network deployments, and equity infusions into subsidiaries
(Ashok Leyland–Switch/Optare). Rows are not flagged as EV versus ICE; several new
rows (Eicher, Hyundai, Sansera) are ICE-led, so add an `ev_related` column before
modelling if the EV-only cut matters. Building a complete series is still open:
Ola Electric, Bajaj, Tata Motors, Bharat Forge and JBM Auto returned no dated,
quantified plant announcements in this pass, which reflects the retrieval limit and
not necessarily the absence of events.

**Announcement dates are often imprecise.** 12 of 34 rows are dated only to a
fiscal period, because annual reports describe a facility without saying when it
was announced. A lead-lag test needs the `exact` and `month` rows, or a rule for
placing fiscal-period events. Two rows carry extra date caveats, stated in their
`evidence`: Ather (6 June 2024) is the board-resolution date, with first public
disclosure in the September 2024 DRHP, and Eicher's Andhra Pradesh approval is
coded to FY2027 because the results-day date was not visible in the retrieved text.

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

The company financials are rebuilt separately, because they come from a different
source family and a different set of connector calls:

```bash
python3 scripts/build_financials.py
```

That applies the capex cleaning rules (the two additive metric names, the sign
flip, the duplicate industry labels), computes `productive_assets_cr` and the
reclassification flag, and re-checks both extracts against
`data/manual/target_companies.csv` in each direction so an undocumented coverage
gap fails loudly. `data/manual/target_companies.csv` is hand-classified and is
not rebuilt by it.

Two files are not rebuilt by `build_processed.py`, both noted in the script's output:
`ev_prices_2w_variants.csv`, because at 50 rows the connector returned it inline
and no extract was saved, and `manual/investment_announcements.csv`, because it
is hand-coded. `data/raw/QUERIES.md` holds the exact query for both, so the
two-wheeler file can be reproduced on demand.

**Read `data/raw/QUERIES.md` before re-pulling anything.** It documents two
connector behaviours that will otherwise bite you: the row cap scales with row
width, so adding columns silently costs you rows, and small results are returned
inline instead of being written to disk.
