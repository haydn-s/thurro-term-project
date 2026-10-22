"""Build the model panels from the cleaned files.

This writes one national panel and one state panel to `data/model/`.             Some wording in the file notes was polished with help from Claude.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
IN = ROOT / "data" / "clean"
OUT = ROOT / "data" / "model"

LAGS = range(1, 7)
WINSOR_SD = 2.0
# Production is keyed on SIAM's `category` (2W / 3W / Passenger Vehicles); there is
# no "4W" value in it. Registrations use VAHAN's `vehicle_segment`, which does.
FOUR_W_PRODUCTION_CATEGORIES = {"Passenger Vehicles"}
FOUR_W_SEGMENTS = {"4W"}


def production_national_monthly(prod: pd.DataFrame) -> pd.DataFrame:
    total = prod.groupby("month", as_index=False)["production_units"].sum()
    total = total.rename(columns={"production_units": "production_total"})
    four = (
        prod[prod["category"].isin(FOUR_W_PRODUCTION_CATEGORIES)]
        .groupby("month", as_index=False)["production_units"].sum()
        .rename(columns={"production_units": "production_4w"})
    )
    return total.merge(four, on="month", how="left").fillna({"production_4w": 0})


def registrations_national_monthly(seg: pd.DataFrame) -> pd.DataFrame:
    totals = seg.groupby("month", as_index=False)["ev_registrations"].sum()
    totals = totals.rename(columns={"ev_registrations": "registrations_total"})
    four = (
        seg[seg["vehicle_segment"].isin(FOUR_W_SEGMENTS)]
        .groupby("month", as_index=False)["ev_registrations"].sum()
        .rename(columns={"ev_registrations": "registrations_4w"})
    )
    return totals.merge(four, on="month", how="left").fillna({"registrations_4w": 0})


def add_growth(df: pd.DataFrame, col: str) -> pd.DataFrame:
    # a zero month followed by a non-zero one is inf, not a growth rate
    g = df[col].pct_change().replace([np.inf, -np.inf], np.nan)
    sd = g.std()
    mu = g.mean()
    winsor = g.clip(lower=mu - WINSOR_SD * sd, upper=mu + WINSOR_SD * sd)
    log_diff = np.log(df[col].replace(0, np.nan)).diff()
    df[f"{col}_growth"] = g
    df[f"{col}_growth_winsor"] = winsor
    df[f"{col}_log_growth"] = log_diff
    return df


def add_lags(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    for c in cols:
        for k in LAGS:
            df[f"{c}_lag{k}"] = df[c].shift(k)
    return df


def monthly_announcement_series(ann: pd.DataFrame, months: pd.DatetimeIndex) -> pd.DataFrame:
    dated = ann.dropna(subset=["month"]).copy()
    dated["month"] = pd.to_datetime(dated["month"])

    out = pd.DataFrame({"month": months})
    out["event_count"] = out["month"].map(dated.groupby("month").size()).fillna(0).astype(int)

    ev = dated[dated["ev_related"] == "yes"]
    out["event_count_ev"] = out["month"].map(ev.groupby("month").size()).fillna(0).astype(int)

    evm = dated[dated["ev_related"].isin(["yes", "mixed"])]
    out["event_count_ev_or_mix"] = out["month"].map(evm.groupby("month").size()).fillna(0).astype(int)

    capex = dated.assign(c=dated["capex_inr_cr"].fillna(0)).groupby("month")["c"].sum()
    out["capex_sum_cr"] = out["month"].map(capex).fillna(0.0)
    return out


def add_time_controls(df: pd.DataFrame) -> pd.DataFrame:
    n = len(df)
    t = np.arange(n)
    df["time_trend"] = (t - t.mean()) / n
    df["month_of_year"] = df["month"].dt.month
    df["quarter"] = df["month"].dt.quarter
    return df


def build_national_panel(prod_clean: pd.DataFrame,
                         seg_clean: pd.DataFrame,
                         ann_clean: pd.DataFrame) -> pd.DataFrame:
    prod = production_national_monthly(prod_clean)
    reg = registrations_national_monthly(seg_clean)

    panel = reg.merge(prod, on="month", how="left")
    panel = panel.sort_values("month").reset_index(drop=True)

    panel = add_growth(panel, "production_total")
    panel = add_growth(panel, "production_4w")
    panel = add_growth(panel, "registrations_total")

    panel["production_coverage"] = (
        panel["production_total"] / panel["registrations_total"]
    )

    lag_cols = [
        "production_total_growth", "production_total_growth_winsor",
        "production_4w_growth", "production_4w_growth_winsor",
    ]
    panel = add_lags(panel, lag_cols)

    y = monthly_announcement_series(ann_clean, panel["month"])
    panel = panel.merge(y, on="month", how="left")

    panel = add_time_controls(panel)

    first_growth = panel["production_total_growth"].first_valid_index()
    last_prod = panel["production_total"].last_valid_index()
    panel["in_window"] = False
    if first_growth is not None and last_prod is not None:
        panel.loc[first_growth:last_prod, "in_window"] = True

    return panel


def build_state_panel(state_clean: pd.DataFrame,
                      ann_clean: pd.DataFrame) -> pd.DataFrame:
    s = state_clean.copy()
    s["ev_total_national"] = s.groupby("month")["ev_total"].transform("sum")
    s["ev_4w_national"] = s.groupby("month")["ev_4w"].transform("sum")
    s["state_share_total"] = s["ev_total"] / s["ev_total_national"]
    s["state_share_4w"] = s["ev_4w"] / s["ev_4w_national"].replace(0, np.nan)

    hhi = (
        s.assign(sq=s["state_share_total"] ** 2)
        .groupby("month")["sq"].sum()
        .rename("hhi_total")
    )
    s = s.merge(hhi, on="month", how="left")

    dated = ann_clean.dropna(subset=["month", "state"]).copy()
    dated["month"] = pd.to_datetime(dated["month"])
    ann_cnt = dated.groupby(["state", "month"]).size().rename("announcements_in_state")
    s = s.merge(ann_cnt, on=["state", "month"], how="left")
    s["announcements_in_state"] = s["announcements_in_state"].fillna(0).astype(int)
    s["any_announcement"] = (s["announcements_in_state"] > 0).astype(int)

    s = s.sort_values(["state", "month"])
    s["cum_announcements"] = s.groupby("state")["announcements_in_state"].cumsum()

    return s.reset_index(drop=True)


def main():
    OUT.mkdir(parents=True, exist_ok=True)

    ann = pd.read_csv(IN / "announcements_clean.csv", parse_dates=["month"])
    prod = pd.read_csv(IN / "production_model_monthly.csv", parse_dates=["month"])
    seg = pd.read_csv(IN / "registrations_segment_monthly.csv", parse_dates=["month"])
    state = pd.read_csv(IN / "registrations_state_monthly.csv", parse_dates=["month"])

    print("Building national panel")
    nat = build_national_panel(prod, seg, ann)
    nat.to_csv(OUT / "national_panel.csv", index=False)
    in_win = nat[nat["in_window"]]
    print(f"  {len(nat)} rows total, {len(in_win)} in modelling window "
          f"({in_win['month'].min().date()} → {in_win['month'].max().date()})")
    print(f"  events in window: total={int(in_win['event_count'].sum())}, "
          f"ev-only={int(in_win['event_count_ev'].sum())}")

    print("Building state panel")
    sp = build_state_panel(state, ann)
    sp.to_csv(OUT / "state_panel.csv", index=False)
    print(f"  {len(sp)} rows ({sp['state'].nunique()} states × "
          f"{sp['month'].nunique()} months)")
    with_ann = sp[sp["any_announcement"] == 1]
    print(f"  state × month cells with an announcement: {len(with_ann)}, "
          f"across {with_ann['state'].nunique()} states")

    print(f"\nWrote 2 files to {OUT.relative_to(ROOT)}/")


if __name__ == "__main__":
    main()
