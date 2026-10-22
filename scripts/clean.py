"""Clean the raw EV and announcement files into `data/clean/`. Some wording in the file notes was polished with help from Claude.
"""
from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
IN_PROC = ROOT / "data" / "processed"
IN_MANUAL = ROOT / "data" / "manual"
OUT = ROOT / "data" / "clean"

# Nothing is partial in production any more: the 2026-08 pull that reported 5 of
# 11 EV OEMs was re-pulled on 2026-10-22 and now matches July and September.
INCOMPLETE_PRODUCTION_MONTHS = set()
# Registrations were re-pulled 2026-10-22: September is complete, October is
# month-to-date.
INCOMPLETE_REGISTRATION_MONTHS = {"2026-10-01"}

EV_KEYWORDS = [
    r"\bEV\b", r"\belectric\b", r"\be[- ]mobility\b", r"\be[- ]vehicle\b",
    r"\bbattery\b", r"\bLi[- ]ion\b", r"\blithium\b", r"\bLFP\b",
    r"\bcell manufactur", r"\bcells\b", r"\bcathode\b", r"\banode\b",
    r"\bGWh\b", r"\bgigafactory\b", r"\bgiga complex\b", r"\bgiga corridor\b",
    r"\bVIDA\b", r"\btraction motor\b", r"\bcharging\b",
    r"\brecycl", r"\bbattery pack\b", r"\bbattery foil\b",
]
EV_PATTERN = re.compile("|".join(EV_KEYWORDS), re.IGNORECASE)

EV_PURE_PLAY = {
    "Ather Energy", "Ola Electric Mobility", "Olectra Greentech",
    "Zelio E-Mobility", "Exicom Tele Systems",
}

NOT_EV_FACILITIES = {
    ("Eicher Motors", "Royal Enfield Cheyyar plant expansion"),
    ("Eicher Motors", "Royal Enfield greenfield Phase I"),
    ("Sansera Engineering", "Pantnagar crankshaft assembly plant (domestic two-wheelers)"),
    ("Maruti Suzuki India", "Kharkhoda second line"),
    ("Maruti Suzuki India", "Kharkhoda vehicle manufacturing facility"),
    ("Maruti Suzuki India", "Hansalpur Plant D"),
    ("Endurance Technologies", "Alloy wheel plant, AURIC Bidkin"),
    ("Uno Minda", "New greenfield casting plant, Hosur"),
    ("Uno Minda", "Uno Minda Kyoraku plant, Bengaluru"),
}


def tag_ev_related(row) -> str:
    """Return yes, no, or mixed."""
    if (row["company"], row["facility"]) in NOT_EV_FACILITIES:
        return "no"
    if row["company"] in EV_PURE_PLAY:
        return "yes"
    blob = f"{row.get('facility','')} {row.get('evidence','')}"
    ev_hit = bool(EV_PATTERN.search(blob))
    ice_hit = bool(re.search(r"\bICE\b", blob))
    if ev_hit and ice_hit:
        return "mixed"
    return "yes" if ev_hit else "no"


def clean_announcements() -> pd.DataFrame:
    a = pd.read_csv(IN_MANUAL / "investment_announcements.csv")
    a["ev_related"] = a.apply(tag_ev_related, axis=1)

    a["month"] = pd.NaT
    use = a["date_precision"].isin(["exact", "month"])
    a.loc[use, "month"] = pd.to_datetime(a.loc[use, "announcement_date"].str[:7] + "-01")

    a["capex_inr_cr"] = pd.to_numeric(a["capex_inr_cr"], errors="coerce")

    cols = ["announcement_date", "date_precision", "month", "company",
            "ev_related", "event_type", "facility", "state",
            "capex_inr_cr", "capacity", "source_url", "evidence"]
    return a[cols].sort_values(["month", "company"], na_position="last")


def clean_production() -> pd.DataFrame:
    p = pd.read_csv(IN_PROC / "ev_production_model_monthly.csv", parse_dates=["month"])
    before = len(p)
    p = p[~p["month"].isin(pd.to_datetime(list(INCOMPLETE_PRODUCTION_MONTHS)))]
    dropped = before - len(p)
    if dropped:
        print(f"  production: dropped {dropped} rows from incomplete months "
              f"({sorted(INCOMPLETE_PRODUCTION_MONTHS)})")
    return p


def clean_ice_production() -> pd.DataFrame:
    """ICE production = all-vehicle production minus the EV models, by month and category.

    The EV production file only holds electric models, so on its own it cannot say
    whether the sector as a whole is in an up- or down-cycle. This is that missing
    series.
    """
    tot = pd.read_csv(IN_PROC / "vehicle_production_total_monthly.csv", parse_dates=["month"])
    ev = pd.read_csv(IN_PROC / "ev_production_model_monthly.csv", parse_dates=["month"])
    ev = ev.groupby(["month", "category"], as_index=False)["production_units"].sum()
    m = tot.merge(ev, on=["month", "category"], how="left").fillna({"production_units": 0})
    m["ice_production"] = m["production_total"] - m["production_units"]
    return m[["month", "category", "ice_production"]].sort_values(["month", "category"])


def clean_registrations_state() -> pd.DataFrame:
    r = pd.read_csv(IN_PROC / "ev_registrations_state_monthly.csv", parse_dates=["month"])
    before = len(r)
    r = r[~r["month"].isin(pd.to_datetime(list(INCOMPLETE_REGISTRATION_MONTHS)))]
    dropped = before - len(r)
    if dropped:
        print(f"  state registrations: dropped {dropped} rows from incomplete months "
              f"({sorted(INCOMPLETE_REGISTRATION_MONTHS)})")
    return r


def clean_registrations_segment() -> pd.DataFrame:
    s = pd.read_csv(IN_PROC / "ev_registrations_segment_monthly.csv", parse_dates=["month"])
    s = s[~s["month"].isin(pd.to_datetime(list(INCOMPLETE_REGISTRATION_MONTHS)))]
    return s


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    print("Cleaning:")
    ann = clean_announcements()
    print(f"  announcements: {len(ann)} rows, "
          f"ev_related={dict(ann['ev_related'].value_counts())}")
    ann.to_csv(OUT / "announcements_clean.csv", index=False)

    prod = clean_production()
    prod.to_csv(OUT / "production_model_monthly.csv", index=False)

    ice = clean_ice_production()
    ice.to_csv(OUT / "ice_production_monthly.csv", index=False)

    seg = clean_registrations_segment()
    seg.to_csv(OUT / "registrations_segment_monthly.csv", index=False)

    state = clean_registrations_state()
    state.to_csv(OUT / "registrations_state_monthly.csv", index=False)

    print(f"\nWrote 5 files to {OUT.relative_to(ROOT)}/")


if __name__ == "__main__":
    main()
