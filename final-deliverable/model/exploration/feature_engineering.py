"""Feature engineering for the model comparison, built straight from data/clean/.

Why a second feature file next to scripts/features.py?
    scripts/features.py builds the shared panels in data/model/. This file adds
    the extra features the model comparison needs (segment mix, OEM concentration,
    demand side, momentum, state history, ...). Every feature here is computed
    only from information available at the end of month t, so it can be used to
    predict month t+1 without leaking the future.

    If the team keeps any of these, move them into scripts/features.py so there
    is one source of truth.

Note on data/model/national_panel.csv:
    `production_4w` is 0 in every month there, because scripts/features.py filters
    production on segment == "4W" while the production file stores 2W / 3W /
    Passenger Vehicles in the `category` column. The features below use `category`.

Three tables come out of this file:
    national_features()   one row per month           (primary question)
    state_features()      one row per state x month   (stretch question)
    state_fiscal_year()   one row per state x fiscal year (stretch, uses undated rows too)
"""
import numpy as np
import pandas as pd

from config import MAX_LOOKBACK
from data import (load_announcements, load_ice_production, load_production,
                  load_registrations_segment, load_registrations_state)


# =====================================================================
# Small helpers
# =====================================================================
def log_growth(series, months):
    """log(x_t / x_(t-months)). +1 inside the log so a zero month does not break it."""
    return np.log((series + 1) / (series.shift(months) + 1))


def ev_filter(ann, target):
    """Keep the announcements that count for a given target definition."""
    if target == "all":
        return ann
    if target == "ev_or_mix":
        return ann[ann["ev_related"].isin(["yes", "mixed"])]
    if target == "ev":
        return ann[ann["ev_related"] == "yes"]
    raise ValueError(f"unknown target {target}")


def future_sum(series, h):
    """Sum of the next h values: x_(t+1) + ... + x_(t+h). NaN when the future is unknown."""
    total = 0
    for k in range(1, h + 1):
        total = total + series.shift(-k)
    return total


# =====================================================================
# 1. National monthly features
# =====================================================================
def production_block(prod):
    """Production level, growth, momentum, segment mix, trade and inventory."""
    g = prod.groupby("month")
    df = pd.DataFrame({
        "prod_total": g["production_units"].sum(),
        "domestic_sales": g["domestic_sales_units"].sum(),
        "exports": g["export_units"].sum(),
    })
    by_cat = prod.pivot_table(index="month", columns="category", values="production_units",
                              aggfunc="sum", fill_value=0)
    df["prod_2w"] = by_cat.get("2W", 0)
    df["prod_3w"] = by_cat.get("3W", 0)
    df["prod_pv"] = by_cat.get("Passenger Vehicles", 0)
    df = df.sort_index()

    out = pd.DataFrame(index=df.index)
    out["prod_total"] = df["prod_total"]

    # growth over 1, 3 and 6 months (log points, ~ percent / 100)
    out["prod_growth_1m"] = log_growth(df["prod_total"], 1)
    out["prod_growth_3m"] = log_growth(df["prod_total"], 3)
    out["prod_growth_6m"] = log_growth(df["prod_total"], 6)

    # momentum: is 3-month growth speeding up or slowing down?
    out["prod_accel"] = out["prod_growth_3m"] - out["prod_growth_3m"].shift(3)

    # capacity pressure: output against the best of the previous 6 months.
    # Above 1 means plants are running harder than they recently have.
    out["prod_vs_6m_max"] = df["prod_total"] / df["prod_total"].shift(1).rolling(6).max()

    # new all-time high this month (1/0)
    out["prod_record_high"] = (df["prod_total"] > df["prod_total"].shift(1).cummax()).astype(int)

    # segment growth and mix. Passenger vehicles are the most capex-heavy segment.
    out["prod_2w_growth_3m"] = log_growth(df["prod_2w"], 3)
    out["prod_3w_growth_3m"] = log_growth(df["prod_3w"], 3)
    out["prod_pv_growth_3m"] = log_growth(df["prod_pv"], 3)
    out["pv_share"] = df["prod_pv"] / df["prod_total"]
    out["three_w_share"] = df["prod_3w"] / df["prod_total"]

    # trade and stock: exports share, and units built but not sold (3-month mean)
    out["export_share"] = df["exports"] / df["prod_total"]
    unsold = (df["prod_total"] - df["domestic_sales"] - df["exports"]) / df["prod_total"]
    out["inventory_build_3m"] = unsold.rolling(3).mean()
    return out


def industry_structure_block(prod):
    """How concentrated production is across OEMs."""
    by_oem = prod.groupby(["month", "oem"])["production_units"].sum().reset_index()
    by_oem["share"] = by_oem["production_units"] / by_oem.groupby("month")["production_units"].transform("sum")
    g = by_oem.groupby("month")
    out = pd.DataFrame({
        "oem_hhi": g["share"].apply(lambda s: (s ** 2).sum()),    # 1 = one OEM makes everything
        "top_oem_share": g["share"].max(),
        "n_active_oems": by_oem[by_oem["production_units"] > 0].groupby("month")["oem"].nunique(),
    })
    out["oem_hhi_change_3m"] = out["oem_hhi"] - out["oem_hhi"].shift(3)
    return out


def demand_block(seg):
    """National EV registrations (demand side)."""
    total = seg.groupby("month")["ev_registrations"].sum()
    four_w = seg[seg["vehicle_segment"] == "4W"].groupby("month")["ev_registrations"].sum()
    df = pd.DataFrame({"reg_total": total, "reg_4w": four_w}).fillna(0).sort_index()
    out = pd.DataFrame(index=df.index)
    out["reg_growth_3m"] = log_growth(df["reg_total"], 3)
    out["reg_4w_growth_3m"] = log_growth(df["reg_4w"], 3)
    return out, df["reg_total"]


def ice_block(ice):
    """Sector-cycle control: growth in combustion-engine (ICE) production.

    Built from all-vehicle production minus the EV models, so it moves with the
    industry's capacity cycle but not with EV volumes. A feature set that beats
    the controls built on this has found something beyond "the whole sector is
    expanding".
    """
    total = ice.groupby("month")["ice_production"].sum().sort_index()
    out = pd.DataFrame(index=total.index)
    out["ice_growth_3m"] = log_growth(total, 3)
    return out


def announcement_counts(ann, target, months):
    """Monthly count of announcements for one target definition, on a fixed month index."""
    dated = ev_filter(ann, target).dropna(subset=["month"])
    counts = dated.groupby("month").size()
    return counts.reindex(months, fill_value=0)


def national_features():
    """One row per month t with every feature and every target.

    Targets are named y_count_<target>_h<h> (announcements in t+1..t+h) and
    y_any_<target>_h<h> (1 if that count > 0). They are NaN when t+h is past the
    last month the announcement data covers.
    """
    from config import HORIZONS, TARGETS

    prod = load_production()
    seg = load_registrations_segment()
    ann = load_announcements()

    df = production_block(prod)
    df = df.join(industry_structure_block(prod))
    demand, reg_total = demand_block(seg)
    df = df.join(demand)
    df = df.join(ice_block(load_ice_production()))

    # supply vs demand: production growing faster than registrations (> 0) or slower
    df["supply_minus_demand_3m"] = df["prod_growth_3m"] - df["reg_growth_3m"]

    # ---- controls: trend, seasonality, results season, recent announcement activity
    df = df.reset_index().rename(columns={"index": "month"})
    n = len(df)
    df["time_trend"] = np.arange(n) / (n - 1)                 # 0 at the start, 1 at the end
    df["month_sin"] = np.sin(2 * np.pi * df["month"].dt.month / 12)
    df["month_cos"] = np.cos(2 * np.pi * df["month"].dt.month / 12)
    # Indian listed companies report in Feb / May / Aug / Nov; many announcements
    # in this dataset come from those earnings calls.
    df["results_season"] = df["month"].dt.month.isin([2, 5, 8, 11]).astype(int)

    # announcement months run past the production data, so build them on a longer index
    last_ann_month = ann["month"].max()
    first_month = min(df["month"].min(), ann["month"].min())
    all_months = pd.date_range(first_month, last_ann_month, freq="MS")
    for target in TARGETS:
        counts = announcement_counts(ann, target, all_months)
        # recent activity: announcements in the last 6 months (known at t)
        recent = counts.rolling(6, min_periods=1).sum()
        df[f"events_last_6m_{target}"] = df["month"].map(recent)
        df[f"events_now_{target}"] = df["month"].map(counts)   # count in month t itself
        df[f"events_next_{target}"] = df["month"].map(counts.shift(-1))  # t+1, for lead/lag scans
        for k in range(2, 7):
            df[f"events_t{k}_{target}"] = df["month"].map(counts.shift(-k))
        for h in HORIZONS:
            y = future_sum(counts, h)
            df[f"y_count_{target}_h{h}"] = df["month"].map(y)
            df[f"y_any_{target}_h{h}"] = (df[f"y_count_{target}_h{h}"] > 0).astype(float)
            df.loc[df[f"y_count_{target}_h{h}"].isna(), f"y_any_{target}_h{h}"] = np.nan

    # drop the first months that lack a full look-back window
    df = df.iloc[MAX_LOOKBACK:].reset_index(drop=True)
    return df


# Feature groups. The ablation study adds them one at a time on top of CONTROLS,
# which is how we test whether EV production adds anything beyond the sector trend.
CONTROLS = ["time_trend", "month_sin", "month_cos", "results_season"]
# Same controls with the linear time trend replaced by an ICE-production cycle
# measure (model card, next step b). The trend can only say "later in the sample";
# this says "the combustion-engine side of the industry is expanding".
CONTROLS_ICE = ["ice_growth_3m", "month_sin", "month_cos", "results_season"]
# prod_growth_6m is NOT used as a feature: prod_accel = 2 * growth_3m - growth_6m
# exactly, so putting all three in one regression makes it singular.
PRODUCTION = ["prod_growth_1m", "prod_growth_3m", "prod_accel",
              "prod_vs_6m_max", "prod_record_high"]
SEGMENT_MIX = ["prod_2w_growth_3m", "prod_3w_growth_3m",
               "pv_share", "three_w_share", "export_share", "inventory_build_3m"]
INDUSTRY = ["oem_hhi", "top_oem_share", "n_active_oems", "oem_hhi_change_3m"]
DEMAND = ["reg_growth_3m", "reg_4w_growth_3m", "supply_minus_demand_3m"]


def history_feature(target):
    return [f"events_last_6m_{target}"]


def feature_sets(target, controls=None):
    """Named feature sets, from the null (controls only) to everything.

    `controls` defaults to CONTROLS (with the linear time trend); pass CONTROLS_ICE
    to run the same sets with the ICE-production cycle measure instead.
    """
    controls = CONTROLS if controls is None else controls
    hist = history_feature(target)
    return {
        "controls": controls,
        "controls+history": controls + hist,
        "controls+production": controls + PRODUCTION,
        "controls+production+mix": controls + PRODUCTION + SEGMENT_MIX,
        "controls+demand": controls + DEMAND,
        "controls+industry": controls + INDUSTRY,
        "all": controls + hist + PRODUCTION + SEGMENT_MIX + INDUSTRY + DEMAND,
    }


# A compact set used by the main model comparison: the controls, the history
# term, and the production-growth signals the research question is about.
CORE_FEATURES = CONTROLS + ["prod_growth_3m", "prod_accel", "prod_vs_6m_max"]


# =====================================================================
# 2. State x month features (stretch question)
# =====================================================================
def state_features(horizon=1):
    """One row per state x month.

    Shares are computed from 3-month rolling sums, which smooths the very noisy
    monthly counts in small states. Target `y_any` = 1 if the state gets at least
    one announcement in months t+1..t+horizon.
    """
    reg = load_registrations_state().sort_values(["state", "month"])
    ann = load_announcements().dropna(subset=["month", "state"])

    reg["roll_total"] = reg.groupby("state")["ev_total"].transform(lambda s: s.rolling(3, min_periods=1).sum())
    reg["roll_4w"] = reg.groupby("state")["ev_4w"].transform(lambda s: s.rolling(3, min_periods=1).sum())
    reg["roll_2w"] = reg.groupby("state")["ev_2w"].transform(lambda s: s.rolling(3, min_periods=1).sum())
    nat = reg.groupby("month")[["roll_total", "roll_4w", "roll_2w"]].transform("sum")

    reg["share_total"] = reg["roll_total"] / nat["roll_total"]
    reg["share_4w"] = reg["roll_4w"] / nat["roll_4w"].replace(0, np.nan)
    reg["share_2w"] = reg["roll_2w"] / nat["roll_2w"].replace(0, np.nan)
    reg["share_change_6m"] = reg["share_total"] - reg.groupby("state")["share_total"].shift(6)
    reg["state_growth_6m"] = reg.groupby("state")["roll_total"].transform(lambda s: log_growth(s, 6))
    reg["log_size_12m"] = np.log1p(reg.groupby("state")["ev_total"].transform(lambda s: s.rolling(12, min_periods=1).sum()))
    reg["share_rank"] = reg.groupby("month")["share_total"].rank(ascending=False)
    reg["top5_state"] = (reg["share_rank"] <= 5).astype(int)
    reg["national_hhi"] = reg.groupby("month")["share_total"].transform(lambda s: (s ** 2).sum())

    # announcement history and future target
    counts = ann.groupby(["state", "month"]).size().rename("ann").reset_index()
    reg = reg.merge(counts, on=["state", "month"], how="left")
    reg["ann"] = reg["ann"].fillna(0)
    reg["past_announcements"] = reg.groupby("state")["ann"].cumsum()   # up to and including t

    def months_since_last(group):
        out, last = [], None
        for i, (m, a) in enumerate(zip(group["month"], group["ann"])):
            if a > 0:
                last = i
            out.append(60 if last is None else i - last)
        return pd.Series(out, index=group.index)

    reg["months_since_last"] = reg.groupby("state", group_keys=False).apply(months_since_last)
    reg["ever_announced"] = (reg["past_announcements"] > 0).astype(int)

    # Build the target on a full state x month calendar that runs to the last
    # announcement month (announcements run past the registration data).
    last_ann_month = ann["month"].max()
    calendar = pd.date_range(reg["month"].min(), last_ann_month, freq="MS")
    y = (counts.pivot_table(index="month", columns="state", values="ann", aggfunc="sum")
         .reindex(index=calendar, columns=sorted(reg["state"].unique()), fill_value=0)
         .fillna(0))
    y.index.name, y.columns.name = "month", "state"
    fut = sum(y.shift(-k) for k in range(1, horizon + 1))
    fut.iloc[len(fut) - horizon:] = np.nan                   # future beyond the data is unknown
    fut = fut.stack(future_stack=True).rename("y_count").reset_index()
    reg = reg.merge(fut, on=["month", "state"], how="left")
    reg["y_any"] = (reg["y_count"] > 0).astype(float)
    reg.loc[reg["y_count"].isna(), "y_any"] = np.nan
    return reg.reset_index(drop=True)


STATE_SETS = {
    "size": ["log_size_12m"],
    "share": ["share_total"],
    "share+mix": ["share_total", "share_4w", "share_2w", "share_change_6m", "state_growth_6m"],
    "history": ["past_announcements", "months_since_last", "ever_announced"],
    "share+history": ["share_total", "share_4w", "share_change_6m",
                      "past_announcements", "months_since_last", "ever_announced"],
    "all": ["share_total", "share_4w", "share_2w", "share_change_6m", "state_growth_6m",
            "log_size_12m", "top5_state", "national_hhi",
            "past_announcements", "months_since_last", "ever_announced"],
}


# =====================================================================
# 3. State x fiscal-year table (stretch, annual robustness)
# =====================================================================
def fiscal_year(month):
    """Indian fiscal year: April 2025 - March 2026 is FY2026."""
    return month.dt.year + (month.dt.month >= 4).astype(int)


def state_fiscal_year():
    """Announcements per state per fiscal year, against the previous year's EV demand.

    This uses the 12 announcements dated only to a fiscal year as well, which the
    monthly tables have to drop.
    """
    reg = load_registrations_state()
    reg["fy"] = fiscal_year(reg["month"])
    yearly = reg.groupby(["state", "fy"])[["ev_total", "ev_4w"]].sum().reset_index()
    yearly["share_total"] = yearly["ev_total"] / yearly.groupby("fy")["ev_total"].transform("sum")
    yearly["share_4w"] = yearly["ev_4w"] / yearly.groupby("fy")["ev_4w"].transform("sum")

    ann = load_announcements().dropna(subset=["state"]).copy()
    dated = ann["month"].notna()
    ann.loc[dated, "fy"] = fiscal_year(ann.loc[dated, "month"])
    ann.loc[~dated, "fy"] = ann.loc[~dated, "announcement_date"].str.replace("FY", "").astype(int)
    counts = ann.groupby(["state", "fy"]).size().rename("announcements").reset_index()

    # features come from the PREVIOUS fiscal year
    prev = yearly.rename(columns={"share_total": "prev_share_total", "share_4w": "prev_share_4w",
                                  "ev_total": "prev_ev_total"})
    prev["fy"] = prev["fy"] + 1
    out = prev[["state", "fy", "prev_share_total", "prev_share_4w", "prev_ev_total"]]
    out = out.merge(counts, on=["state", "fy"], how="left").fillna({"announcements": 0})
    out = out[out["fy"].between(2023, 2027)]
    return out.reset_index(drop=True)
