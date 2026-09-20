# EV data for India — ingestion notes

Data pulled via the Thurro connector for the term project. Everything here covers
India only, and every figure is a unit count unless stated otherwise.

Pulled on 2026-09-20.

## What's here

| File | Grain | Coverage | Rows |
|---|---|---|---|
| `processed/ev_production_model_monthly.csv` | month × category × segment × sub-segment × OEM × model | 2023-04 → 2026-08 | 1,363 |
| `processed/ev_registrations_segment_monthly.csv` | month × vehicle segment | 2018-01 → 2026-09 | 799 |
| `processed/ev_registrations_maker_monthly.csv` | month × maker | 2023-01 → 2026-09 | 891 |
| `processed/ev_maker_reference.csv` | maker | — | 20 |
| `raw/*.toon` | unparsed connector extracts backing the production file | — | — |

All month values are the first day of the month.

### `ev_production_model_monthly.csv`

Manufacturer-reported (SIAM) monthly **production**, domestic sales and exports
by model. This is the only genuine production series in the set — the other two
are registrations.

`month, category, segment, sub_segment, oem, model, production_units,
domestic_sales_units, export_units`

A blank metric means the model reported nothing that month, which is distinct
from a reported `0`.

### `ev_registrations_segment_monthly.csv`

VAHAN monthly EV **registrations** by vehicle segment (2W, 3W, 4W, buses, LCV,
M&HCV, tractors, construction equipment).

`month, vehicle_segment, ev_registrations`

### `ev_registrations_maker_monthly.csv` + `ev_maker_reference.csv`

The same registrations source cut by maker, limited to the 20 makers with the
highest EV volume since 2023-01. Ticker and ISIN live in the reference file
rather than being repeated on every row; join on `maker`. Seven of the twenty
are NSE-listed — the rest are unlisted (Ampere, BGauss, YC Electric, the
e-rickshaw makers).

`month, maker, ev_registrations` / `maker, nse_symbol, isin`

## Caveats worth knowing before you model on this

**Registrations are not production.** They lag manufacture, they are recorded at
the RTO where the vehicle is registered rather than where it was built, and they
exclude exports entirely. Use the production file when you mean production.

**Passenger-car EV production is under-covered.** The production source tags
electric two- and three-wheelers with an explicit electric sub-segment, but
classifies passenger vehicles by length and price instead. Four-wheeler EVs are
therefore only caught when the model name itself carries an EV marker (`XEV`,
`Comet EV`, `ZS EV`). Nameplates like Nexon or Punch, which are sold in both ICE
and electric variants under one name, are **not** separable in this feed and are
absent from the production file. For 4W EV volumes, use the registrations files,
where the fuel type is recorded explicitly.

**The last month is partial.** The registrations files run to 2026-09-15, so
2026-09 is roughly half a month and will read as a sharp drop. Drop it or
annualise it.

**Fiscal years.** The production source is organised on India's April–March
fiscal year, which is why it starts at 2023-04.

**One source was checked and rejected.** A project-level infrastructure
investment dataset was evaluated for EV manufacturing capex and dropped: its
"Energy Storage" sector is oil, gas and LNG storage rather than batteries, its
automotive rows were placeholders, and keyword matching on "battery" returned
coke-oven batteries at steel plants. No usable EV capacity data came out of it.

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
