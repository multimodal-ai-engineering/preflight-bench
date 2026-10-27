"""Paper figures, drawn from the numbers in results/full, results/extension and results/additions."""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

BLUE, ORANGE, AQUA, INK, MUTED, GRID = "#2a78d6", "#eb6834", "#1baf7a", "#0b0b0b", "#52514e", "#e6e4df"
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 9, "axes.edgecolor": MUTED, "axes.labelcolor": INK,
                     "xtick.color": MUTED, "ytick.color": MUTED, "axes.spines.top": False, "axes.spines.right": False})


def survival():
    t = [0.5, 1, 2, 6.5, 12, 30]
    settled = [0.997, 0.997, 0.996, 0.997, 0.997, 0.996]
    nav = [0.855, 0.828, 0.826, 0.829, 0.830, 0.829]
    scroll = [0.996, 0.996, 0.990, 0.990, 0.990, 0.990]
    fig, ax = plt.subplots(figsize=(3.4, 2.5))
    for y, c, lab in [(settled, BLUE, "fully loaded"), (scroll, AQUA, "after a scroll"), (nav, ORANGE, "newly opened")]:
        ax.plot(t, [100 * v for v in y], color=c, lw=2, marker="o", ms=4, label=lab)
    ax.set_xscale("log"); ax.set_xticks([0.5, 1, 2, 6.5, 12, 30]); ax.set_xticklabels(["0.5", "1", "2", "6.5", "12", "30"])
    ax.set_ylim(78.5, 101); ax.set_xlim(0.42, 40); ax.set_xlabel("seconds after the screenshot"); ax.set_ylabel("planned clicks still valid (%)")
    ax.grid(axis="y", color=GRID, lw=0.6); ax.legend(frameon=False, loc="center left", fontsize=8, bbox_to_anchor=(0.0, 0.55))
    ax.text(1.05, 96.8, "fully loaded: 0.4% stale at 30 s", fontsize=8, color=INK)
    ax.text(1.05, 80.6, "newly opened: 17% stale by 1 s", fontsize=8, color=INK)
    fig.tight_layout(); fig.savefig("fig_survival.pdf"); fig.savefig("fig_survival.png", dpi=220)


def settle():
    rules = ["no wait", "0.5 s delay", "load event", "layout stable 0.5 s", "1 s delay", "network idle"]
    wait = [0, 0.50, 0.43, 0.65, 1.00, 1.24]
    inval = [14.4, 2.5, 3.0, 2.8, 3.1, 0.46]
    lo = [12.6, 1.7, 2.2, 2.0, 2.3, 0.21]
    hi = [16.5, 3.5, 4.2, 3.8, 4.2, 1.0]
    fig, ax = plt.subplots(figsize=(3.4, 2.5))
    ax.errorbar(wait, inval, yerr=[np.subtract(inval, lo), np.subtract(hi, inval)], fmt="o", color=BLUE, ecolor=MUTED,
                elinewidth=0.8, capsize=2, ms=5)
    labels = {"no wait": (0.05, 14.4), "load event": (0.06, 4.3), "0.5 s delay": (0.42, 1.55), "layout stable": (0.53, 4.3),
              "1 s delay": (1.03, 4.0), "network idle": (0.88, 0.62)}
    for r, (x, y) in labels.items():
        ax.text(x, y, r if r != "network idle" else "network\nidle", fontsize=7.5, color=INK, va="top" if r == "network idle" else "baseline")
    ax.axhline(1, color=MUTED, lw=0.8, ls="--"); ax.text(0.02, 1.12, "1% bar", fontsize=7.5, color=MUTED)
    ax.set_yscale("log"); ax.set_yticks([0.3, 1, 3, 10, 20]); ax.set_yticklabels(["0.3", "1", "3", "10", "20"]); ax.set_ylim(0.15, 24)
    ax.set_xlim(-0.08, 1.6); ax.set_xlabel("median wait after the page opens (s)"); ax.set_ylabel("clicks stale within 6.5 s (%)")
    ax.grid(axis="y", color=GRID, lw=0.6)
    fig.tight_layout(); fig.savefig("fig_settle.pdf"); fig.savefig("fig_settle.png", dpi=220)


if __name__ == "__main__":
    survival(); settle()
    print("ok")
