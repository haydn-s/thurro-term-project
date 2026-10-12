# Connector queries behind the raw extracts

The `.json` files here are saved connector results. They are the inputs to
`scripts/build_processed.py`. This file records the query behind each one so any
extract can be re-pulled if it is lost or needs extending.

Two connector limits shape these queries:

- **The row cap scales with row width** — 1,000 rows for the narrow registration
  query, 370 for the wide investment query. Adding columns costs you rows, and
  the truncation is silent.
- **Results under roughly 60KB are returned inline** rather than written to a
  file. An inline result has to be transcribed by hand to reach disk, so the
  queries below select a discardable `_pad` column purely to push the result over
  that threshold. `toon_to_csv.py` drops any column whose name starts with `_`.
  Keep the padding small enough that the row cap stays above the row count you
  expect.

All queries run against the connector's structured alt-data store.

## `registrations_state_<year>.json` — nine files, 2018 through 2026

One call per calendar year, 307–415 rows each. Segments are pivoted into columns
so the row count stays at state × month rather than state × month × segment,
which would exceed the cap. `_pad` is 160 characters.

```sql
SELECT State_Clean AS state, toStartOfMonth(Relevant_Date) AS month,
       sumIf(Total, Vehicle_Segment='2W')  AS ev_2w,
       sumIf(Total, Vehicle_Segment='3W')  AS ev_3w,
       sumIf(Total, Vehicle_Segment='4W')  AS ev_4w,
       sumIf(Total, Vehicle_Segment='Buses') AS ev_buses,
       sumIf(Total, Vehicle_Segment='Small Buses') AS ev_small_buses,
       sumIf(Total, Vehicle_Segment='LCV') AS ev_lcv,
       sumIf(Total, Vehicle_Segment='M&HCV') AS ev_mhcv,
       sumIf(Total, Vehicle_Segment='Tractors') AS ev_tractors,
       sumIf(Total, Vehicle_Segment='Construction Equipment') AS ev_constr_eq,
       sum(Total) AS ev_total,
       repeat('.', 160) AS _pad
FROM <vahan maker x category x fuel, state level, monthly>
WHERE Fuel_Clean = 'ELECTRIC'
  AND Relevant_Date >= '<YYYY>-01-01' AND Relevant_Date < '<YYYY+1>-01-01'
GROUP BY state, month ORDER BY month, state
```

The 2026 file drops the upper bound. The builder checks that segment columns sum
to `ev_total` on every row and that state-month keys are unique; the totals also
reconcile exactly against `ev_registrations_segment_monthly.csv`.

## `prices_car_ev.json`

604 rows. Grouping on the price fields but taking `max` of rating and review
count keeps one row per variant per distinct price — those two columns move
weekly and would otherwise blow past the row cap (an earlier version grouping on
them returned 1,000 rows, truncated). EVs are identified by range unit, not by a
fuel flag. No padding needed; the result cleared the threshold on its own.

```sql
SELECT Brand_Company, Model, Model_Variant,
       Ex_Showroom_Price, Price_Unit, Battery_Capacity_kWh, Mileage, Mileage_Unit,
       Model_Seater_Count,
       max(Model_Rating) AS rating, max(No_Of_Reviews) AS reviews,
       min(Relevant_Date) AS first_seen, max(Relevant_Date) AS last_seen,
       count() AS obs
FROM <cardekho weekly prices>
WHERE Battery_Capacity_kWh IS NOT NULL OR Mileage_Unit = 'km'
GROUP BY Brand_Company, Model, Model_Variant, Ex_Showroom_Price, Price_Unit,
         Battery_Capacity_kWh, Mileage, Mileage_Unit, Model_Seater_Count
ORDER BY Brand_Company, Model, Model_Variant, first_seen
```

## `investment_projects.json`

117 rows — the whole automotive and energy-storage slice of the project registry.
`_pad` is 350 characters. The builder collapses this source's three null
spellings (`-`, `None`, empty) to empty.

```sql
SELECT Sector, Sub_Sector, Title, State, Address,
       Project_Start_Date, Project_Completion_Date,
       Promoter_Sponsor_Type, Project_Status,
       toFloat64OrNull(Total_Project_Cost_In_USD_MN) AS cost_usd_mn,
       Project_URL, repeat('.', 350) AS _pad
FROM <india investment grid project details>
WHERE Sector IN ('Automotive','Energy Storage')
ORDER BY Sector, Project_Start_Date
```

## No raw extract: `ev_prices_2w_variants.csv`

50 rows — too few to clear the inline threshold even with 1,000 characters of
padding, so this one was transcribed from the inline result and is not rebuilt by
`build_processed.py`. Re-running this query reproduces it exactly. The cleaning
is done in SQL rather than downstream: the `CASE` folds the two spellings of the
Flying Flea into one model, dropping the body-type column removes the duplicate
rows created by the Chetak being filed as both `Bike` and `Scooter`, and
`nullIf(..., 0)` turns the placeholder rating into a null.

```sql
SELECT Brand_Company AS brand,
       CASE WHEN Model = 'Flying Flea C6 (Royal Enfield)'
            THEN 'Royal Enfield Flying Flea C6' ELSE Model END AS model,
       Model_Variant AS variant,
       Ex_Showroom_Price AS ex_showroom_price_inr,
       Battery_Capacity_kWh AS battery_kwh,
       Mileage AS range_km,
       nullIf(max(Model_Rating), 0) AS rating,
       max(No_Of_Reviews) AS reviews,
       min(Relevant_Date) AS first_seen,
       max(Relevant_Date) AS last_seen,
       uniqExact(Relevant_Date) AS weeks_observed
FROM <bikedekho weekly prices>
WHERE Battery_Capacity_kWh IS NOT NULL OR Mileage_Unit = 'km/charge'
GROUP BY brand, model, variant, ex_showroom_price_inr, battery_kwh, range_km
ORDER BY brand, model, variant, first_seen
```

## No raw extract: `data/manual/investment_announcements.csv`

Hand-coded from filings prose, not from a structured query. Extending it means
another pass over the filings corpus, not re-running SQL. The search that
surfaced the underlying documents used capacity-expansion and capex themes
("battery plant capacity expansion", "EV manufacturing capex", "gigafactory")
to rank companies, then retrieved evidence per company from the exchange-filings
domain.

**Pass 4 (2026-09-28).** Theme roster for `electric vehicle manufacturing plant
investment`, `EV battery plant capex` and `gigafactory` (company domain) ranked
Ola Electric, Tata Motors, Amara Raja, Exide and Neogen Chemicals highest.
Then `retrieve` in focused/compare mode, company domain only, with capex/plant
wording (for example "board approves capital expenditure new manufacturing plant or
capacity expansion electric vehicle, investment crore, location"), over these
groups: Tata Motors; Hyundai; Ather; Hero MotoCorp; Sona BLW, Sansera, CIE
Automotive; Ashok Leyland, Eicher, Tata Power; Ola Electric, Bajaj, TVS; Exide,
Amara Raja, Tube Investments; Bharat Forge, M&M, JBM Auto. Chunks were read by hand
and coded per the inclusion rule in `data/README.md`.


---

# Company financials — the backward-looking dependent variable

Added 2026-09-30, following industry-partner feedback: name the companies the
study's result would actually land on, then read their financials as a
backward-looking indicator. Announcements are what a company *said*; capex is
what it *spent*. These extracts carry the spending.

Two things here are not SQL and are recorded anyway, because they are queries in
every sense that matters: a natural-language theme search and a company
resolution step. Both are reproducible.

## Step 1 — who is exposed, by mention count rather than by hunch

The target list starts from a corpus-wide theme search rather than from us
picking names. Ranked by how much each company actually discusses the theme:

```
theme_roster(
  theme_tokens = ["electric vehicle manufacturing capacity",
                  "EV plant capex",
                  "gigafactory"],
  domains      = ["company"]
)
```

Returned 50 companies ranked by mention count. The top of the list: Ola Electric
514, Tata Motors 135, Mahindra & Mahindra 110, Maruti Suzuki 107, Uno Minda 103,
Amara Raja 97, Olectra 80, Tata Power 77, Exide 71, Himadri 68. The counts are
kept in `data/manual/target_companies.csv` as `roster_mentions` so the ranking
that drove selection stays auditable.

The roster is a relevance ranking, not a scope decision. It surfaces companies
whose capex has nothing to do with vehicles (Indus Towers, Mahanagar Gas, Jindal
Worldwide, Hindustan Zinc, Vedanta, IREDA) because they discuss batteries or
storage in passing. Six names in the union were **added** from our own files
rather than the roster — TVS, Bajaj, Eicher, Bharat Forge, Ashok Leyland and
Gravita, which appear in `ev_maker_reference.csv` or
`investment_announcements.csv` but did not clear the roster's top 50. The scope
call is the `tier` and `primary_panel` columns of the target list, and it is
recorded per company with a reason.

Company names in the corpus are canonicalised (`Tvs Motor Company Limited`, not
`TVS Motor`). The roster returns them already canonical; anything typed by hand
goes through `resolve_company` first or the `WHERE ... IN (...)` silently matches
nothing.

## Step 2 — `financials_capex_annual.toon`

187 rows, 47 companies, FY23 through FY26. One row per company × fiscal year,
with the capex line items pivoted into columns.

**Read the three notes under the query before using this file.**

```sql
SELECT Company_Long_Name_Clean AS company, NSE_Symbol AS nse_symbol, ISIN AS isin,
       Industry_Name AS industry, Period_Date AS period_end, Relevant_Quarter AS fiscal_period,
       sumIf(Value, Metric='Purchase of Fixed Assets')   AS purchase_fixed_assets_cr,
       sumIf(Value, Metric='Capital Work in Progress')   AS cwip_cr,
       sumIf(Value, Metric='Capital Expenditure')        AS capital_expenditure_cr,
       sumIf(Value, Metric='Proceeds from Sale of Fixed Assets') AS sale_fixed_assets_cr,
       sumIf(Value, Metric='Payment for Acquiring Right of Use Assets') AS rou_assets_cr,
       sumIf(Value, Metric='Net Cash Provided by (Used in) Investing Activities') AS net_investing_cr,
       sumIf(Value, Metric='Depreciation and Amortization') AS depreciation_cr,
       sumIf(Value, Metric='Net Cash Used in Operating Activities') AS net_operating_cr
FROM <BSE consolidated cash flow, company-wise, yearly>
WHERE Company_Long_Name_Clean IN (<the 52 names in target_companies.csv>)
GROUP BY company, nse_symbol, isin, industry, period_end, fiscal_period
ORDER BY company, period_end
```

**Capex lives under two different metric names and they are additive, not
alternates.** Most filers report `Purchase of Fixed Assets`. Hero MotoCorp, Tata
Power, Tube Investments and Belrise report only `Capital Expenditure`. Ola, Bajaj
and Syrma report **both, in the same year, as separate lines** — confirmed by
pulling the full investing section for those three. So capex is the sum of the
two. Coalescing instead of summing zeroes out Hero's entire series and
understates Ola's FY23 by 403 Cr.

**`Industry_Name` duplicates rows.** JBM Auto carries two industry spellings
(`Auto Ancillaries - Sheet Metal` and `Auto Ancillaries - Others`) and Vedanta
gains a second in FY26, so those company-years appear twice with identical
financials. The builder drops the column and de-duplicates on company × period,
warning if a duplicate pair ever disagrees. 5 rows drop this way, 187 → 182.

**Not every filer is on a March year end.** CIE Automotive closes in December, so
its rows are stamped `Q3 FY23`…`Q3 FY26` and cover calendar years. Hyundai also
shows December and June periods. The builder exports `fy_end_month` so a
period-aligned join is possible; do not treat `FY25` as one window across filers.

Outflows arrive signed negative and are flipped to positive in `processed/`.

## Step 3 — `financials_fixed_assets_halfyearly.toon`

239 rows, 33 companies. Denser in time than the annual capex file, which is why
it is worth having: the balance sheet lands twice a year where the detailed
cash-flow statement lands once.

```sql
SELECT Company_Long_Name_Clean AS company, NSE_Symbol AS nse_symbol,
       Period_Date AS period_end, Relevant_Quarter AS fiscal_period,
       sumIf(Value, Metric='Fixed Assets')      AS fixed_assets_cr,
       sumIf(Value, Metric='Intangible Assets') AS intangible_assets_cr,
       sumIf(Value, Metric='Total Assets')      AS total_assets_cr
FROM <BSE results balance sheet, company-wise, "quarterly">
WHERE Company_Long_Name_Clean IN (<the 36 primary-panel names>)
  AND Metric IN ('Fixed Assets','Intangible Assets','Total Assets')
GROUP BY company, nse_symbol, period_end, fiscal_period
ORDER BY company, period_end
```

**The table named "quarterly" is half-yearly.** Its period dates are 31 March and
30 September only — seven periods from 2023-03 to 2026-03, not fourteen. Budget
observations accordingly. (The stray June and December dates belong to the
non-March filers.)

**The September balance sheet classifies tangible against intangible differently
from the March one.** Ola books ~1,000 Cr under intangibles every September and
~9 Cr every March; the total barely moves. M&M, Sona BLW, Motherson and Autoline
swing the same way. A first difference on `Fixed Assets` alone therefore shows a
large disinvestment every other period that did not happen. Their **sum** is
stable, so `processed/` exports `productive_assets_cr = fixed + intangible` and
flags the 11 periods where the split moves more than a tenth of the base while
the total holds still. Difference the sum, not the parts.

**Capex is not available quarterly anywhere in this feed.** The detailed
cash-flow line items (`Purchase of Fixed Assets`, `Capital Work in Progress`,
`Capital Expenditure`) exist only in the yearly table. The half-yearly cash-flow
table carries summary rows only — `Net Cash Used in Investing Activities` and
nothing beneath it — and covers 2023-09 to 2025-09. So true capex is annual, and
the half-yearly asset delta is the only sub-annual proxy. This is a hard ceiling
on time resolution, not a query that needs rewriting.

## Step 4 — the coverage check

Five companies on the target list return **no rows at all** from the yearly
cash-flow table. This was confirmed rather than inferred, with a deliberately
unfiltered count:

```sql
SELECT Company_Long_Name_Clean AS company, count() AS rows_any_metric,
       min(Period_Date) AS first_p, max(Period_Date) AS last_p
FROM <BSE consolidated cash flow, company-wise, yearly>
WHERE Company_Long_Name_Clean IN ('Ather Energy Limited','Rolex Rings Limited',
  'Divgi Torqtransfer Systems Limited','Motherson Sumi Wiring India Limited',
  'Sedemac Mechatronics Limited')
GROUP BY company ORDER BY company
```

Zero rows. **Ather Energy is the costly one** — a pure-play electric 2W maker
with its own registrations series, and exactly the company the study most wants.
It listed in 2025, so there is no FY23–FY26 filing history to read. It stays on
the target list with `primary_panel = no` so the gap is visible rather than
silently absent.

`build_financials.py` re-runs this check on every build, comparing the extracts
against the target list in both directions and failing loudly on an undocumented
gap.
