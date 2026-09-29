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

