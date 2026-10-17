"""Charts for the model comparison. Every chart is saved as a PNG in results/figures/.

Style rules: one y-axis per panel (two measures -> two panels), thin marks,
light grid, three fixed series colours, grey for the baseline.
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from config import MAIN_HORIZON, MAIN_TARGET, RESULTS, TOP_K

FIG = RESULTS / "figures"

BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
GREY, INK, INK2, GRID = "#8a8984", "#0b0b0b", "#52514e", "#e4e3df"
SERIES = [BLUE, ORANGE, AQUA]

plt.rcParams.update({
    "font.size": 9, "axes.edgecolor": GRID, "axes.labelcolor": INK2, "axes.titlecolor": INK,
    "axes.titlesize": 10, "axes.titleweight": "bold", "axes.titlelocation": "left",
    "xtick.color": INK2, "ytick.color": INK2, "axes.grid": True, "grid.color": GRID,
    "grid.linewidth": 0.6, "axes.axisbelow": True, "axes.spines.top": False,
    "axes.spines.right": False, "legend.frameon": False, "figure.dpi": 150,
})


def save(fig, name):
    FIG.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(FIG / name, dpi=150)
    plt.close(fig)


# ---------------------------------------------------------------- national
def national_series(df):
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(10, 5.5), sharex=True,
                                 gridspec_kw={"height_ratios": [2, 1]})
    a1.plot(df["month"], df["prod_total"] / 1000, color=BLUE, lw=2)
    a1.set_ylabel("EV production ('000 units)")
    a1.set_title("National EV production (top) and investment announcements (bottom)")
    a2.bar(df["month"], df[f"events_now_{MAIN_TARGET}"], width=20, color=ORANGE)
    a2.set_ylabel("announcements")
    a2.set_yticks(range(0, int(df[f"events_now_{MAIN_TARGET}"].max()) + 1))
    save(fig, "01_national_series.png")


def lead_lag(scan):
    fig, ax = plt.subplots(figsize=(7, 4))
    for i, (signal, g) in enumerate(scan.groupby("signal", sort=False)):
        x = g["lead_months"] + (i - 1) * 0.15
        ax.errorbar(x, g["coef"], yerr=1.96 * g["std_err"], fmt="o", ms=5, capsize=3,
                    lw=1.2, color=SERIES[i], label=signal)
    ax.axhline(0, color=INK2, lw=0.8)
    ax.set_xlabel("announcements measured k months after production growth")
    ax.set_ylabel("Poisson coefficient (95% CI)")
    ax.set_title("Lead-lag scan: no lead is distinguishable from zero")
    ax.legend(loc="upper left", fontsize=8)
    save(fig, "02_lead_lag_scan.png")


def cross_correlation(ccf):
    fig, ax = plt.subplots(figsize=(7, 3.6))
    colors = [ORANGE if k < 0 else BLUE for k in ccf["k_months"]]
    ax.bar(ccf["k_months"], ccf["spearman_rho"], color=colors, width=0.6)
    band = 2 / np.sqrt(ccf["n"].mean())
    ax.axhspan(-band, band, color=GRID, alpha=0.6, lw=0)
    ax.axhline(0, color=INK2, lw=0.8)
    ax.set_xlabel("k (months).  k > 0: production leads   |   k < 0: announcements lead")
    ax.set_ylabel("Spearman correlation")
    ax.set_title("Cross-correlation of production growth and announcements (grey = noise band)")
    save(fig, "03_cross_correlation.png")


def model_comparison(table):
    t = table[(table["horizon"] == MAIN_HORIZON) & (table["model"] != "Baseline (base rate)")]
    models = list(dict.fromkeys(t["model"]))
    fig, ax = plt.subplots(figsize=(8, 4.8))
    y = np.arange(len(models))
    for i, target in enumerate(["all", "ev_or_mix", "ev"]):
        g = t[t["target"] == target].set_index("model").loc[models]
        base = g["brier"] / (1 - g["brier_skill"])          # baseline Brier for this target
        lo, hi = g["gain_ci_low"] / base, g["gain_ci_high"] / base
        yy = y + (i - 1) * 0.25
        ax.errorbar(g["brier_skill"], yy, xerr=[g["brier_skill"] - lo, hi - g["brier_skill"]],
                    fmt="o", ms=5, capsize=2, lw=1, color=SERIES[i], label=f"target = {target}")
    ax.axvline(0, color=INK2, lw=0.8)
    ax.set_yticks(y, models)
    ax.invert_yaxis()
    ax.set_xlabel("Brier skill vs baseline (90% bootstrap CI).  > 0 = better than base rate")
    ax.set_title(f"Model comparison, walk-forward, horizon = {MAIN_HORIZON} month")
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.13), ncol=3, fontsize=8)
    save(fig, "04_model_comparison.png")


def walk_forward(preds):
    show = ["Baseline (base rate)", "Poisson, core", "Logit L1 (lasso), all", "Random forest, all"]
    colors = [GREY, BLUE, ORANGE, AQUA]
    fig, ax = plt.subplots(figsize=(10, 4))
    for name, c in zip(show, colors):
        ax.plot(preds["month"], preds[name], marker="o", ms=4, lw=1.5, color=c, label=name)
    hits = preds[preds["y"] == 1]
    ax.scatter(hits["month"], np.ones(len(hits)) * 1.02, marker="v", s=40, color=INK,
               label="announcement next month")
    ax.set_ylim(0, 1.08)
    ax.set_ylabel("predicted P(announcement next month)")
    ax.set_title("Walk-forward predictions (target = all, horizon = 1)")
    ax.legend(fontsize=7, loc="upper left", ncol=2)
    save(fig, "05_walk_forward.png")


def ablation(abl):
    sets = list(dict.fromkeys(abl["feature_set"]))
    fig, ax = plt.subplots(figsize=(8, 4.2))
    y = np.arange(len(sets))
    for i, model in enumerate(["Logit L2", "Random forest"]):
        g = abl[abl["model"] == model].set_index("feature_set").loc[sets]
        ax.barh(y + (i - 0.5) * 0.38, g["brier_skill"], height=0.34, color=SERIES[i], label=model)
    ax.axvline(0, color=INK2, lw=0.8)
    ax.set_yticks(y, sets)
    ax.invert_yaxis()
    ax.set_xlabel("Brier skill vs baseline (walk-forward)")
    ax.set_title("Ablation: which feature groups add skill on top of trend + seasonality?")
    ax.legend(fontsize=8, loc="lower right")
    save(fig, "06_ablation.png")


def placebo(placebo_table, dists):
    n = len(dists)
    fig, axes = plt.subplots(1, n, figsize=(4.2 * n, 3.4), sharey=True)
    for ax, (_, row) in zip(np.atleast_1d(axes), placebo_table.iterrows()):
        d = dists[row["model"]]
        ax.hist(d, bins=25, color=GREY, alpha=0.8)
        ax.axvline(row["real_brier"], color=ORANGE, lw=2)
        ax.set_title(row["model"].replace(" (best ablation set)", "\n(best ablation set)"), fontsize=8)
        ax.set_xlabel(f"Brier of shifted histories\n{row['share_placebo_better_or_equal']:.0%} "
                      f"score as well as the real one")
    np.atleast_1d(axes)[0].set_ylabel("placebo runs")
    save(fig, "07_placebo.png")


def importance(imp):
    top = imp.head(15).iloc[::-1]
    fig, ax = plt.subplots(figsize=(7, 4.8))
    ax.barh(top.index, top["rf_importance"], color=BLUE, height=0.6)
    for i, (name, row) in enumerate(top.iterrows()):
        ax.text(row["rf_importance"] + 0.002, i, row["group"], va="center", fontsize=7, color=INK2)
    ax.set_xlabel("random-forest importance (full sample)")
    ax.set_title("What the forest leans on (group in grey)")
    save(fig, "08_feature_importance.png")


# ---------------------------------------------------------------- state
def state_comparison(table, horizon):
    t = table.copy()
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(10, 4), sharey=True)
    y = np.arange(len(t))
    colors = [GREY if m.startswith("Baseline") else BLUE for m in t["model"]]
    a1.barh(y, t["auc"], color=colors, height=0.6)
    a1.axvline(0.5, color=INK2, lw=0.8)
    a1.set_yticks(y, t["model"])
    a1.invert_yaxis()
    a1.set_xlim(0.4, 1)
    a1.set_xlabel("test AUC (0.5 = random)")
    a1.set_title(f"State siting models, test after train cut-off (h = {horizon})")
    a2.barh(y, t[f"top{TOP_K}_hit_rate"], color=colors, height=0.6)
    a2.set_xlim(0, 1)
    a2.set_xlabel(f"share of announcements in the model's top-{TOP_K} states that month")
    save(fig, f"09_state_comparison_h{horizon}.png")


def state_fiscal_year(fy):
    fig, ax = plt.subplots(figsize=(7, 4.2))
    rng = np.random.default_rng(0)
    jitter = rng.uniform(-0.12, 0.12, len(fy))
    ax.scatter(fy["prev_share_total"] * 100, fy["announcements"] + jitter, s=28,
               color=BLUE, alpha=0.6, edgecolor="white", lw=0.5)
    top = fy[fy["announcements"] >= 2]
    for _, r in top.iterrows():
        ax.annotate(f"{r['state']} FY{int(r['fy']) % 100}", (r["prev_share_total"] * 100, r["announcements"]),
                    fontsize=7, color=INK2, xytext=(4, 2), textcoords="offset points")
    ax.set_xlabel("state's share of national EV registrations in the previous fiscal year (%)")
    ax.set_ylabel("announcements in the fiscal year")
    ax.set_title("Annual view: bigger EV markets get more announcements")
    save(fig, "10_state_fiscal_year.png")
