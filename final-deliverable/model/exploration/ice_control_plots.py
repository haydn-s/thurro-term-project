"""Two charts for the ICE-control re-test (reads the CSVs ice_control_analysis.py writes).

    python final-deliverable/model/exploration/ice_control_plots.py

12_ice_control_comparison.png   Brier skill (and 90% interval) per feature set and control set
13_ice_control_placebo.png      real timing vs 200 shifted-timing placebos, per control set
"""
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

import plots                      # shared style, colours and save()
from config import RESULTS
from plots import BLUE, GREY, INK2, ORANGE, save

NAT = RESULTS / "national"
# fixed order, same colour for the same control set in both charts
VARIANTS = [("time_trend", "time trend (original)", BLUE),
            ("ice_growth", "ICE growth instead of trend", ORANGE)]
SETS = [("controls", "controls only"),
        ("controls+production", "+ production growth"),
        ("controls+production+mix", "+ production growth + segment mix")]


def comparison():
    ab = pd.read_csv(NAT / "8_ice_control_ablation.csv")
    ab = ab.copy()
    # the CI is on the Brier gain; skill = gain / baseline Brier, and baseline = brier / (1 - skill)
    base = ab["brier"] / (1 - ab["brier_skill"])
    ab["lo"], ab["hi"] = ab["gain_ci_low"] / base, ab["gain_ci_high"] / base

    fig, ax = plt.subplots(figsize=(8.5, 4.6))
    offsets = [0.15, -0.15]
    for (key, label, color), off in zip(VARIANTS, offsets):
        for i, (set_key, _) in enumerate(SETS):
            r = ab[(ab["controls"] == key) & (ab["feature_set"] == set_key)].iloc[0]
            y = i + off
            ax.plot([r["lo"] * 100, r["hi"] * 100], [y, y], color=color, lw=2, solid_capstyle="round")
            ax.plot(r["brier_skill"] * 100, y, "o", ms=7, color=color, mec="#fcfcfb", mew=1.5,
                    label=label if i == 0 else None)
            if set_key == "controls+production+mix":      # selective direct labels, in text ink
                ax.text(r["hi"] * 100 + 1.2, y, f"{r['brier_skill']:+.1%}", va="center", fontsize=8, color=INK2)
    ax.axvline(0, color=INK2, lw=0.8)
    ax.set_yticks(range(len(SETS)))
    ax.set_yticklabels([s[1] for s in SETS])
    ax.invert_yaxis()
    ax.set_xlabel("Brier skill vs base rate, % (dot) with 90% interval of the gain (line); right of 0 beats the base rate")
    ax.set_title("The segment-mix gain survives the control swap; the weaker feature sets do not")
    ax.legend(loc="upper right", fontsize=8, title="controls", title_fontsize=8)
    ax.grid(axis="y", visible=False)
    ax.set_xlim(None, ax.get_xlim()[1] + 6)
    save(fig, "12_ice_control_comparison.png")


def placebo():
    pl = pd.read_csv(NAT / "8b_ice_control_placebo.csv").set_index("controls")
    draws = pd.read_csv(NAT / "8c_ice_control_placebo_draws.csv")
    lo, hi = draws.min().min(), max(draws.max().max(), pl["real_brier"].max())
    bins = np.linspace(lo, hi, 26)
    fig, axes = plt.subplots(1, 2, figsize=(8, 3.6), sharey=True, sharex=True)
    for ax, (key, label, color) in zip(axes, VARIANTS):
        ax.hist(draws[key], bins=bins, color=GREY, alpha=0.8)
        real = pl.loc[key, "real_brier"]
        ax.axvline(real, color=color, lw=2.5)
        ax.set_title(label, fontsize=9)
        ax.set_xlabel(f"Brier of 200 shifted histories (lower is better)\n"
                      f"real timing {real:.3f}; {pl.loc[key, 'share_placebo_better_or_equal']:.1%} "
                      f"of shifts score as well", fontsize=8)
    axes[0].set_ylabel("placebo runs")
    fig.suptitle("Shifting the production timing almost never reproduces the real score "
                 "(grey = shifted, line = real)", x=0.01, ha="left", fontsize=10, fontweight="bold")
    save(fig, "13_ice_control_placebo.png")


if __name__ == "__main__":
    comparison()
    placebo()
    print("wrote", plots.FIG / "12_ice_control_comparison.png", "and 13_ice_control_placebo.png")
