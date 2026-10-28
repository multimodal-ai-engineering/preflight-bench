"""Figure for the commercial study, in the style of paper/figs.py: share of pages with a layout shift in the 6.5 s after
the screenshot, per wait rule, for BOOK, SHOP and GOV (95% intervals). Reads results/analysis_desktop/.

  python commercial/fig_commercial.py   # -> commercial/results/fig_commercial.png, paper/fig_commercial.pdf
"""
import csv
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent
BLUE, ORANGE, AQUA, INK, MUTED, GRID = "#2a78d6", "#eb6834", "#1baf7a", "#0b0b0b", "#52514e", "#e6e4df"
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 9, "axes.edgecolor": MUTED, "axes.labelcolor": INK,
                     "xtick.color": MUTED, "ytick.color": MUTED, "axes.spines.top": False, "axes.spines.right": False,
                     "pdf.fonttype": 42, "ps.fonttype": 42})

RULES = ["S0", "S1", "S2", "S4", "S5", "S5u"]
LABELS = ["DOM\nready", "+0.5 s", "+1 s", "load\nevent", "network\nidle, 3 s cap", "network idle,\nno cap*"]
GROUPS = [("BOOK", "booking and buying", ORANGE), ("SHOP", "e-commerce sample", AQUA), ("GOV", ".gov", BLUE)]


def main():
    rows = {(r["group"], r["rule"]): r for r in csv.DictReader(open(HERE / "results/analysis_desktop/shift_and_stale_by_group_rule.csv"))}
    fig, ax = plt.subplots(figsize=(6.6, 2.05))
    ax.axvspan(RULES.index("S5") - 0.42, RULES.index("S5") + 0.42, color=GRID, alpha=0.7, lw=0)
    ax.text(RULES.index("S5"), 97, "rule 1", ha="center", va="top", fontsize=8, color=INK)
    for j, (g, lab, c) in enumerate(GROUPS):
        xs, ys, lo, hi = [], [], [], []
        for i, r in enumerate(RULES):
            row = rows[(g, r)]
            s = 100 * float(row["shift_share"])
            xs.append(i + (j - 1) * 0.22); ys.append(s)
            lo.append(s - 100 * float(row["shift_lo"])); hi.append(100 * float(row["shift_hi"]) - s)
        n = rows[(g, "S5")]["n_pages"]
        ax.errorbar(xs, ys, yerr=[lo, hi], fmt="o", color=c, ecolor=c, elinewidth=1, capsize=2, ms=4.5, label=f"{lab} (n = {int(n):,})")
    ax.set_xticks(range(len(RULES))); ax.set_xticklabels(LABELS, fontsize=8)
    ax.set_ylim(0, 100); ax.set_xlim(-0.5, len(RULES) - 0.5)
    ax.set_ylabel("pages that shift within\n6.5 s of the screenshot (%)")
    ax.grid(axis="y", color=GRID, lw=0.6)
    ax.legend(frameon=False, fontsize=8, loc="lower center", bbox_to_anchor=(0.5, 1.0), ncol=3, handletextpad=0.3, columnspacing=1.2)
    fig.tight_layout()
    fig.savefig(HERE / "results/fig_commercial.png", dpi=220)
    fig.savefig(HERE.parent / "paper/fig_commercial.pdf")
    print("ok")


if __name__ == "__main__":
    main()
