"""Join the company financials to the EV volume series into modelling panels.

Run from the repo root (after build_financials.py):

    python3 scripts/build_panel.py

Produces two panels, both keyed on company x reporting period:

    processed/panel_company_annual.csv      capex        (FY23-FY26)
    processed/panel_company_halfyearly.csv  asset growth (6 half-year deltas)

Each row carries the independent variable at two levels:

  national  -- EV production and registrations, shared by every company in the
               period. This is the project's primary X, and because it is shared
               it contributes only as many distinct values as there are periods.
  own       -- that company's own EV registrations, available for the seven
               listed makers in ev_registrations_maker_monthly.csv. This varies
               across both company and time, so it is the only X here that
               identifies a within-company effect.

X is summed over the actual months in each company's reporting window rather
than by fiscal-year label. Two things make that necessary: CIE Automotive closes
in December and Hyundai files December and June periods, so an "FY25" label spans
different real months for different filers; and Ola's balance-sheet history skips
a period, leaving a 9-month gap that a label-based join would silently treat as
6 months. Windows are recorded on every row as window_start/window_end/
window_months, and a row whose window is not fully covered by the source is
flagged rather than quietly summed over a short window.
"""
import csv
from collections import defaultdict
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROC = ROOT / "data" / "processed"

# ev_registrations_maker_monthly.csv names makers as VAHAN spells them; the
# financials are keyed on NSE symbol. ev_maker_reference.csv carries the bridge
# for the seven listed makers -- the other thirteen are unlisted and have no
# financials to join to.
MAKER_TO_SYMBOL = {
    "ATHER ENERGY": "ATHERENERG",
    "BAJAJ AUTO": "BAJAJ-AUTO",
    "HERO MOTOCORP": "HEROMOTOCO",
    "MAHINDRA AND MAHINDRA": "M&M",
    "OLA": "OLAELEC",
    "TATA MOTORS": "TMCV",
    "TVS MOTOR": "TVSMOTOR",
}


def read(name):
    return list(csv.DictReader(open(PROC / name)))


def ym(s):
    """'2023-04-01' or '2023-04' -> (2023, 4)."""
    return int(s[:4]), int(s[5:7])


def months_between(start, end):
    """Inclusive list of (year, month) from start to end."""
    (y0, m0), (y1, m1) = start, end
    out = []
    while (y0, m0) <= (y1, m1):
        out.append((y0, m0))
        m0 += 1
        if m0 == 13:
            y0, m0 = y0 + 1, 1
    return out


def shift(period, n):
    """Move (year, month) by n months."""
    y, m = period
    total = y * 12 + (m - 1) + n
    return total // 12, total % 12 + 1


def load_series():
    """Monthly (year, month) -> value, for each independent variable."""
    national_prod = defaultdict(float)
    prod_months = set()
    for r in read("ev_production_model_monthly.csv"):
        units = r["production_units"]
        if units == "":
            continue  # blank means the model reported nothing, distinct from 0
        k = ym(r["month"])
        national_prod[k] += float(units)
        prod_months.add(k)

    national_reg = defaultdict(float)
    reg_months = set()
    for r in read("ev_registrations_segment_monthly.csv"):
        k = ym(r["month"])
        national_reg[k] += float(r["ev_registrations"])
        reg_months.add(k)

    own = defaultdict(float)
    own_months = defaultdict(set)
    for r in read("ev_registrations_maker_monthly.csv"):
        sym = MAKER_TO_SYMBOL.get(r["maker"])
        if not sym:
            continue
        k = ym(r["month"])
        own[(sym, k)] += float(r["ev_registrations"])
        own_months[sym].add(k)

    return (national_prod, prod_months, national_reg, reg_months, own, own_months)


# The last month of each source is partial and must never enter a window.
# Production: 2026-08 reports 5 of 11 OEMs, so the series ends 2026-07.
# Registrations: pulled 2026-09-15, so 2026-09 is roughly half a month.
PROD_LAST_GOOD = (2026, 7)
REG_LAST_GOOD = (2026, 8)


def window_sum(series, available, months, last_good):
    """Sum a monthly series over `months`. Returns (value, covered)."""
    usable = [m for m in months if m <= last_good]
    if len(usable) != len(months) or not all(m in available for m in usable):
        return None, False
    return sum(series.get(m, 0.0) for m in usable), True


def pct(curr, prev):
    if curr is None or prev is None or not prev:
        return None
    return round((curr - prev) / prev * 100, 4)


def build(rows, y_field, y_label, out_name, per_company_window):
    (nprod, pmonths, nreg, rmonths, own, own_months) = load_series()

    by_company = defaultdict(list)
    for r in rows:
        by_company[r["company"]].append(r)

    out = []
    for company, recs in by_company.items():
        recs.sort(key=lambda r: r["period_end"])
        sym = recs[0]["nse_symbol"]
        prev_y = prev_own = None
        prev_end = None
        for r in recs:
            end = ym(r["period_end"])
            start = per_company_window(end, prev_end)
            if start is None:
                prev_end = end
                prev_y = float(r[y_field]) if r[y_field] not in ("", None) else None
                continue
            months = months_between(start, end)

            prod, prod_ok = window_sum(nprod, pmonths, months, PROD_LAST_GOOD)
            reg, reg_ok = window_sum(nreg, rmonths, months, REG_LAST_GOOD)
            own_v, own_ok = (None, False)
            if sym in own_months:
                own_v, own_ok = window_sum(
                    {k[1]: v for k, v in own.items() if k[0] == sym},
                    own_months[sym], months, REG_LAST_GOOD)

            y = float(r[y_field]) if r[y_field] not in ("", None) else None
            out.append({
                "company": company, "nse_symbol": sym,
                "tier": r["tier"], "primary_panel": r["primary_panel"],
                "fiscal_period": r["fiscal_period"], "period_end": r["period_end"],
                "window_start": f"{start[0]:04d}-{start[1]:02d}",
                "window_end": f"{end[0]:04d}-{end[1]:02d}",
                "window_months": len(months),
                y_label: round(y, 4) if y is not None else "",
                f"{y_label}_growth_pct": pct(y, prev_y),
                "national_ev_production": round(prod) if prod_ok else "",
                "national_ev_registrations": round(reg) if reg_ok else "",
                "own_ev_registrations": round(own_v) if own_ok else "",
                "own_ev_reg_growth_pct": pct(own_v, prev_own) if own_ok else None,
                "x_coverage": ";".join(
                    n for n, ok in (("production", prod_ok), ("registrations", reg_ok),
                                    ("own", own_ok)) if not ok) or "complete",
            })
            prev_y, prev_own, prev_end = y, (own_v if own_ok else None), end

    out.sort(key=lambda r: (r["company"], r["period_end"]))
    cols = list(out[0].keys())
    with open(PROC / out_name, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for r in out:
            w.writerow({k: ("" if v is None else v) for k, v in r.items()})
    print(f"  {(PROC / out_name).relative_to(ROOT)}: {len(out)} rows")
    return out


def rewrite(rows, name):
    cols = list(rows[0].keys())
    with open(PROC / name, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow({k: ("" if v is None else v) for k, v in r.items()})
    print(f"  {(PROC / name).relative_to(ROOT)}: {len(rows)} rows, "
          f"{len(cols)} cols")


def annual_window(end, prev_end):
    """The 12 months ending at this period end."""
    return shift(end, -11)


def halfyear_window(end, prev_end):
    """The months since the previous balance-sheet date. None for the first
    period, which has no prior stock to difference against."""
    if prev_end is None:
        return None
    return shift(prev_end, 1)


def attach_asset_formation(annual, half, capex_rows):
    """Add a validated gross-capex proxy to the annual panel.

    A balance-sheet stock change is a *net* number: capex minus depreciation,
    plus anything acquired. Filed capex is *gross*. Differencing the asset stock
    and comparing it to capex directly therefore looks wrong even when both are
    right -- Maruti FY26 spent 10,123 Cr while its asset stock rose only 3,450,
    because depreciation consumed the difference.

    Adding depreciation back recovers the gross figure and lifts the correlation
    with filed capex from 0.696 to 0.900, median absolute error 17%. That makes
    the twice-yearly balance sheet usable as a capex measure where the annual
    cash-flow statement is the only alternative.

    The residual is informative in its own right. Where the proxy exceeds filed
    capex by more than 100%, the company grew its asset base by *buying* it
    rather than building it -- Bajaj's FY26 stock rose 9,745 Cr on 722 Cr of
    capex. For a question about new manufacturing investment that distinction
    matters, so those rows are flagged rather than smoothed away.
    """
    stock = {(r["nse_symbol"], r["period_end"]): float(r["productive_assets_cr"])
             for r in half}
    # Depreciation and operating cash flow are on the source capex file rather
    # than the panel rows, and both are worth carrying: depreciation to build the
    # proxy, CFO to scale capex across a panel spanning Reliance and PPAP.
    extra = {(r["nse_symbol"], r["period_end"]): (r["depreciation_cr"], r["cfo_cr"])
             for r in capex_rows}

    for r in annual:
        sym, pe = r["nse_symbol"], r["period_end"]
        prior = f"{int(pe[:4]) - 1}{pe[4:]}"
        dep, cfo = extra.get((sym, pe), ("", ""))
        r["depreciation_cr"], r["cfo_cr"] = dep, cfo
        formation = err = flag = ""
        if (sym, pe) in stock and (sym, prior) in stock and dep not in ("", None):
            delta = stock[(sym, pe)] - stock[(sym, prior)]
            formation = round(delta + float(dep), 4)
            filed = r["capex_cr"]
            if filed not in ("", None) and float(filed) > 0:
                err = round((formation - float(filed)) / float(filed) * 100, 2)
                if abs(err) > 100:
                    flag = "acquired" if err > 0 else "divested"
        r["asset_formation_cr"] = formation
        r["asset_formation_error_pct"] = err
        r["formation_flag"] = flag
    n = sum(1 for r in annual if r["formation_flag"])
    have = sum(1 for r in annual if r["asset_formation_cr"] != "")
    print(f"  asset-formation proxy on {have} rows; {n} flagged as growth by "
          f"acquisition or disposal rather than capex")
    return annual


def report(label, rows, x):
    usable = [r for r in rows if r["primary_panel"] == "yes" and r[x] != ""]
    periods = sorted({r["period_end"] for r in usable})
    firms = sorted({r["nse_symbol"] for r in usable})
    print(f"  {label:<34} {len(usable):>4} rows  {len(firms):>2} firms  "
          f"{len(periods)} distinct periods")


if __name__ == "__main__":
    print("annual panel (capex)")
    capex = [r for r in read("company_capex_annual.csv")]
    a = build(capex, "capex_cr", "capex_cr", "panel_company_annual.csv",
              annual_window)

    print("half-yearly panel (productive-asset growth)")
    assets = read("company_assets_halfyearly.csv")
    h = build(assets, "productive_assets_cr", "productive_assets_cr",
              "panel_company_halfyearly.csv", halfyear_window)

    print("gross-capex proxy on the annual panel")
    a = attach_asset_formation(a, assets, capex)
    rewrite(a, "panel_company_annual.csv")

    print("\nusable observations by design")
    report("annual, national production X", a, "national_ev_production")
    report("annual, national registrations X", a, "national_ev_registrations")
    report("annual, own registrations X", a, "own_ev_registrations")
    report("half-yearly, national production X", h, "national_ev_production")
    report("half-yearly, own registrations X", h, "own_ev_registrations")
