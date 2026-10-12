"""Build the company-financials CSVs from the raw extracts in data/raw/.

Run from the repo root:

    python3 scripts/build_financials.py

These files carry the *backward-looking* dependent variable: what the target
companies actually spent on plant, as opposed to what they announced. The SQL
behind every extract is recorded in data/raw/QUERIES.md, and the target list
itself is data/manual/target_companies.csv.

Three cleaning rules matter and none of them are cosmetic:

1. Capex is split across two metric names. `Purchase of Fixed Assets` and
   `Capital Expenditure` are separate, additive line items in the same investing
   section -- Ola, Bajaj and Syrma report both in the same year -- while Hero,
   Tata Power, Tube Investments and Belrise use only the second. So capex is the
   sum of the two, not a coalesce. Getting this wrong drops Hero's entire capex
   series to zero.
2. Cash-flow outflows arrive signed negative. They are flipped to positive here
   so "bigger number means more spending" holds.
3. The interim (September) balance sheet classifies tangible against intangible
   differently from the year-end (March) one. Ola parks ~1,000 Cr in intangibles
   every September and ~9 Cr every March; M&M and Sona BLW swing the same way.
   A first difference on `Fixed Assets` alone therefore reads as a huge
   disinvestment every other period. Their sum is stable, so it is the sum that
   is exported as `productive_assets_cr`, with a flag on the rows where the split
   moves far more than the total does.
"""
import csv
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "processed"
TARGETS = ROOT / "data" / "manual" / "target_companies.csv"


def read_toon(path):
    """Read a saved connector result, bare TOON or JSON-wrapped {type,text}."""
    text = path.read_text()
    if text.lstrip().startswith("["):
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            pass  # bare TOON starts with "[N]{...}", which is not valid JSON
        else:
            text = "\n".join(
                p["text"] for p in payload if isinstance(p, dict) and "text" in p
            )

    header = re.search(r"^\[(\d+)\]\{(.+?)\}:$", text, re.M)
    if not header:
        raise SystemExit(f"{path.name}: no TOON header found")
    declared = int(header.group(1))
    columns = next(csv.reader([header.group(2)]))

    rows = []
    for line in text[header.end():].splitlines():
        if not line.strip():
            continue
        if not line.startswith("  "):
            break  # trailing COLUMNS/feedback footer
        rows.append(next(csv.reader([line[2:]])))

    if len(rows) != declared:
        raise SystemExit(f"{path.name}: declared {declared} rows, parsed {len(rows)}")
    bad = [r for r in rows if len(r) != len(columns)]
    if bad:
        raise SystemExit(f"{path.name}: {len(bad)} rows have the wrong width")
    return [dict(zip(columns, r)) for r in rows]


def num(value):
    return float(value) if value not in ("", None) else None


def load_targets():
    if not TARGETS.exists():
        raise SystemExit(f"missing {TARGETS.relative_to(ROOT)}")
    return {r["company"]: r for r in csv.DictReader(open(TARGETS))}


def write(path, columns, rows):
    with open(path, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(columns)
        w.writerows(rows)
    print(f"  {path.relative_to(ROOT)}: {len(rows)} rows")


def dedupe(records, key, label):
    """Keep one record per key. The source repeats a company-period whenever it
    carries two Industry_Name spellings (JBM Auto, Vedanta); the financial values
    are identical on those rows, so the first wins and a differing duplicate is
    an error worth surfacing."""
    seen, out, dropped = {}, [], 0
    for r in records:
        k = key(r)
        if k in seen:
            dropped += 1
            if seen[k] != r:
                print(f"  WARNING {label}: conflicting duplicate for {k}")
            continue
        seen[k] = r
        out.append(r)
    if dropped:
        print(f"  {label}: dropped {dropped} duplicate rows (repeated industry label)")
    return out


def build_capex(targets):
    print("annual capex")
    src = RAW / "financials_capex_annual.toon"
    if not src.exists():
        print("  SKIP (not present)")
        return set()
    rows = read_toon(src)

    # The industry label is what duplicates a company-period, so it is dropped
    # before de-duplicating rather than carried into the output.
    keyed = [{k: v for k, v in r.items() if k != "industry"} for r in rows]
    keyed = dedupe(keyed, lambda r: (r["company"], r["period_end"]), "annual capex")

    out = []
    for r in keyed:
        t = targets.get(r["company"], {})
        purchase = abs(num(r["purchase_fixed_assets_cr"]) or 0.0)
        capex_line = abs(num(r["capital_expenditure_cr"]) or 0.0)
        cwip = abs(num(r["cwip_cr"]) or 0.0)
        sales = num(r["sale_fixed_assets_cr"]) or 0.0
        capex = purchase + capex_line          # rule 1: additive, not a coalesce
        out.append([
            r["company"], r["nse_symbol"], r["isin"],
            t.get("tier", ""), t.get("primary_panel", ""),
            r["fiscal_period"], r["period_end"], int(r["period_end"][5:7]),
            round(capex, 4), round(purchase, 4), round(capex_line, 4),
            round(cwip, 4), round(sales, 4), round(capex - sales, 4),
            num(r["depreciation_cr"]), num(r["net_operating_cr"]),
            num(r["net_investing_cr"]),
        ])
    out.sort(key=lambda r: (r[0], r[6]))

    zero = [r[0] for r in out if r[8] == 0]
    if zero:
        print(f"  NOTE {len(zero)} rows report no capex at all: {sorted(set(zero))}")
    write(OUT / "company_capex_annual.csv",
          ["company", "nse_symbol", "isin", "tier", "primary_panel",
           "fiscal_period", "period_end", "fy_end_month", "capex_cr",
           "purchase_fixed_assets_cr", "capital_expenditure_cr", "cwip_cr",
           "asset_sales_cr", "net_capex_cr", "depreciation_cr", "cfo_cr",
           "net_investing_cr"], out)
    return {r[0] for r in out}


def build_assets(targets):
    print("half-yearly productive assets")
    src = RAW / "financials_fixed_assets_halfyearly.toon"
    if not src.exists():
        print("  SKIP (not present)")
        return set()
    rows = dedupe(read_toon(src), lambda r: (r["company"], r["period_end"]),
                  "half-yearly assets")

    by_company = {}
    for r in rows:
        by_company.setdefault(r["company"], []).append(r)

    out, flagged = [], 0
    for company, recs in by_company.items():
        recs.sort(key=lambda r: r["period_end"])
        t = targets.get(company, {})
        prev = None
        for r in recs:
            fixed = num(r["fixed_assets_cr"]) or 0.0
            intang = num(r["intangible_assets_cr"]) or 0.0
            productive = fixed + intang

            # Rule 3: if the tangible/intangible split moves by more than a
            # tenth of the base while the combined total barely moves, the
            # movement is a reclassification and not investment.
            flag = ""
            if prev is not None:
                d_fixed = abs(fixed - prev[0])
                d_prod = abs(productive - prev[2])
                if prev[0] and d_fixed > 0.10 * prev[0] and d_fixed > 3 * max(d_prod, 1e-9):
                    flag = "reclassified"
                    flagged += 1
            out.append([
                company, r["nse_symbol"], t.get("tier", ""),
                t.get("primary_panel", ""), r["fiscal_period"], r["period_end"],
                int(r["period_end"][5:7]), round(fixed, 4), round(intang, 4),
                round(productive, 4), num(r["total_assets_cr"]), flag,
            ])
            prev = (fixed, intang, productive)
    out.sort(key=lambda r: (r[0], r[5]))
    print(f"  {flagged} period(s) flagged as a tangible/intangible reclassification")
    write(OUT / "company_assets_halfyearly.csv",
          ["company", "nse_symbol", "tier", "primary_panel", "fiscal_period",
           "period_end", "fy_end_month", "fixed_assets_cr",
           "intangible_assets_cr", "productive_assets_cr", "total_assets_cr",
           "split_flag"], out)
    return {r[0] for r in out}


def check_coverage(targets, with_capex, with_assets):
    print("\ncoverage against data/manual/target_companies.csv")
    named = set(targets)
    for label, found in (("capex", with_capex), ("assets", with_assets)):
        extra = found - named
        if extra:
            print(f"  WARNING in {label} extract but not on the target list: "
                  f"{sorted(extra)}")

    expected_no_data = {c for c, r in targets.items()
                        if "no rows in the cash-flow feed" in r["rationale"]
                        or "no FY23-FY26 cash-flow history" in r["rationale"]}
    missing = named - with_capex
    unexplained = missing - expected_no_data
    print(f"  {len(with_capex)}/{len(named)} target companies have annual capex")
    print(f"  {len(missing)} without capex, of which {len(expected_no_data & missing)} "
          f"are documented as absent from the feed")
    if unexplained:
        print(f"  WARNING undocumented gap: {sorted(unexplained)}")

    panel = {c for c, r in targets.items() if r["primary_panel"] == "yes"}
    print(f"  primary panel: {len(panel & with_capex)} companies with capex, "
          f"{len(panel & with_assets)} with half-yearly assets")


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    targets = load_targets()
    capex = build_capex(targets)
    assets = build_assets(targets)
    check_coverage(targets, capex, assets)
    print("\nNot built here: data/manual/target_companies.csv (hand-classified "
          "from the roster -- see data/README.md).")
