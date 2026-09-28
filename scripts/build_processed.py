"""Build the processed CSVs from the raw connector extracts in data/raw/.

Run from the repo root:

    python3 scripts/build_processed.py

Each builder is independent; a missing raw input is reported and skipped rather
than failing the run. The SQL behind every extract is recorded in
data/raw/QUERIES.md.
"""
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from toon_to_csv import extract  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "processed"

# The project source writes three different things for "no value": a literal
# dash, the string "None", and an empty cell. Collapse them to empty so callers
# have one null to test for.
NULLS = {"-", "None"}


def write(path, columns, rows):
    with open(path, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(columns)
        w.writerows(rows)
    print(f"  {path.relative_to(ROOT)}: {len(rows)} rows")


def load(name):
    path = RAW / name
    if not path.exists():
        print(f"  SKIP {name} (not present)")
        return None
    return extract(path)


def build_state_registrations():
    print("state registrations")
    parts = sorted(RAW.glob("registrations_state_*.json"))
    if not parts:
        print("  SKIP (no extracts present)")
        return
    columns, rows = None, []
    for part in parts:
        raw_cols, part_rows = extract(part)
        keep = [i for i, c in enumerate(raw_cols) if not c.startswith("_")]
        cols = [raw_cols[i] for i in keep]
        if columns is None:
            columns = cols
        elif cols != columns:
            raise SystemExit(f"{part.name}: column mismatch")
        rows.extend([[r[i] for i in keep] for r in part_rows])

    # Every row must satisfy: the nine segment columns sum to the total.
    seg = [columns.index(c) for c in columns if c.startswith("ev_") and c != "ev_total"]
    tot = columns.index("ev_total")
    bad = [r for r in rows if sum(float(r[i]) for i in seg) != float(r[tot])]
    if bad:
        raise SystemExit(f"{len(bad)} rows where segments do not sum to ev_total")

    keys = {(r[0], r[1]) for r in rows}
    if len(keys) != len(rows):
        raise SystemExit("duplicate state-month keys")

    write(OUT / "ev_registrations_state_monthly.csv", columns, rows)


def build_car_prices():
    print("car prices")
    loaded = load("prices_car_ev.json")
    if loaded is None:
        return
    cols, rows = loaded
    idx = {c: i for i, c in enumerate(cols)}
    unit = {"Lakh": 100_000, "Cr": 10_000_000}

    out = []
    for r in rows:
        price, price_unit = r[idx["Ex_Showroom_Price"]], r[idx["Price_Unit"]]
        out.append([
            r[idx["Brand_Company"]], r[idx["Model"]], r[idx["Model_Variant"]],
            int(round(float(price) * unit[price_unit])) if price else "",
            r[idx["Battery_Capacity_kWh"]], r[idx["Mileage"]],
            r[idx["Model_Seater_Count"]], r[idx["rating"]], r[idx["reviews"]],
            r[idx["first_seen"]], r[idx["last_seen"]], r[idx["obs"]],
        ])
    write(OUT / "ev_prices_car_variants.csv",
          ["brand", "model", "variant", "ex_showroom_price_inr", "battery_kwh",
           "range_km", "seats", "rating", "reviews", "first_seen", "last_seen",
           "weeks_observed"], out)


def build_investment_projects():
    print("investment projects")
    loaded = load("investment_projects.json")
    if loaded is None:
        return
    cols, rows = loaded
    idx = {c: i for i, c in enumerate(cols)}
    order = ["Sector", "Sub_Sector", "Title", "State", "Address",
             "Project_Start_Date", "Project_Completion_Date",
             "Promoter_Sponsor_Type", "Project_Status", "cost_usd_mn",
             "Project_URL"]
    out = [["" if r[idx[c]] in NULLS else r[idx[c]] for c in order] for r in rows]
    write(OUT / "investment_projects_auto_energy.csv",
          ["sector", "sub_sector", "title", "state", "district",
           "project_start_date", "project_completion_date", "promoter_type",
           "project_status", "cost_usd_mn", "project_url"], out)


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    build_state_registrations()
    build_car_prices()
    build_investment_projects()
    print("\nNot built here: ev_prices_2w_variants.csv (connector returned it "
          "inline, so there is no raw extract -- see data/raw/QUERIES.md) and "
          "data/manual/investment_announcements.csv (hand-coded).")
