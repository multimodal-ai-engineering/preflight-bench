"""Extension figures -> figures/ext_{bar,budget,hazard,rubric,planner}.png (all labelled extension).

  python -m harness.ext_figures
"""
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
TAB = ROOT / "results/extension/tables"
FIG = ROOT / "figures"
plt.rcParams.update({"font.size": 13, "axes.spines.top": False, "axes.spines.right": False})
COL = {"C2": "#7a7a7a", "C4": "#1f6fd1", "opus-5.5": "#c2410c", "haiku-5.5": "#16a34a"}
LAB = {"C2": "PUSV-style tuned (C2)", "C4": "anchored pixels (C4)", "opus-5.5": "Opus 5.5 as checker", "haiku-5.5": "Haiku 5.5 as checker"}


def fig_bar():
    rt = pd.read_csv(TAB / "ineq_test_rates.csv")
    C = np.exp(np.linspace(np.log(0.3), np.log(60), 300))
    fig, ax = plt.subplots(figsize=(10, 7))
    for chk in ("C2", "C4", "opus-5.5", "haiku-5.5"):
        x = rt[(rt.check == chk) & (rt.tier == 1)].iloc[0]
        for k, ls in ((2, "-"), (10, "--")):
            p = (x.delta / C + x.f) / (x.r * (k - 1) + x.f)
            ax.plot(C, np.clip(p, 0, 1.05), ls, color=COL[chk], lw=2.6, label=f"{LAB[chk]}" if k == 2 else None)
    marks = []
    h2 = pd.read_csv(ROOT / "results/full/tables/h2_live_cells.csv")
    marks.append(("benchmark Tier 1 (live loop, 6.5 s gap)", float(h2[(h2.cond == "none") & (h2.gap_s == 6.5)].stale_rate.iloc[0]), "#111"))
    sv = TAB / "rs_survival.csv"
    if sv.exists():
        s = pd.read_csv(sv)
        s = s[(s.kind == "all") & (s.type == "all") & (s.offset == 6.5)]
        for cond, name, col in (("settled", "real pages, settled", "#8b5cf6"), ("nav", "real pages, just navigated", "#db2777"), ("scroll", "real pages, just scrolled", "#f59e0b")):
            if (s.cond == cond).any():
                marks.append((name + " (6.5 s)", 1 - float(s[s.cond == cond].S.iloc[0]), col))
    for name, v, col in marks:
        ax.axhline(v, color=col, lw=1.4, ls=":")
        ax.text(0.31, v * 1.08 if v > 0.002 else 0.0025, f"{name}: {v:.3f}", color=col, fontsize=11, bbox=dict(facecolor="white", alpha=0.85, edgecolor="none", pad=1))
    ax.set_xscale("log"); ax.set_yscale("log")
    ax.set_ylim(0.002, 1.05); ax.set_xlim(0.3, 60)
    ax.set_xlabel("planning time per plan, C (s)")
    ax.set_ylabel("break-even change rate p*  (check pays above the line)")
    ax.set_title("When a preflight check pays (solid k = 2, dashed k = 10; Tier 1 test rates)", fontsize=13)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.12), ncol=2, fontsize=11, frameon=False)
    fig.text(0.99, 0.005, "extension; p* = (δ/C + f) / (r(k−1) + f)", ha="right", fontsize=9, color="#555")
    fig.tight_layout(); fig.savefig(FIG / "ext_bar.png", dpi=160); plt.close(fig)


def fig_budget():
    b = pd.read_csv(TAB / "ineq_budgets.csv")
    b = b[(b.check == "C4") & (b.C == 6.51)]
    piv = b.pivot(index="k", columns="p", values="f_max")
    fig, ax = plt.subplots(figsize=(8.5, 4.8))
    im = ax.imshow(np.clip(piv.values, -0.2, 1), cmap="RdYlGn", vmin=-0.2, vmax=1, aspect="auto")
    for i in range(piv.shape[0]):
        for j in range(piv.shape[1]):
            v = piv.values[i, j]
            ax.text(j, i, "none" if v < 0 else f"{min(v, 1):.2f}", ha="center", va="center", fontsize=11)
    ax.set_xticks(range(piv.shape[1]), [f"{p:g}" for p in piv.columns]); ax.set_yticks(range(piv.shape[0]), piv.index)
    ax.set_xlabel("change rate p"); ax.set_ylabel("stale cost k (plans)")
    f = b.f.iloc[0]
    ax.set_title(f"False-alarm budget f_max for C4 at C = 6.51 s (C4's own f = {f:.3f})", fontsize=12)
    fig.colorbar(im, ax=ax, shrink=0.8)
    fig.text(0.99, 0.01, "extension; Tier 1 test r and δ", ha="right", fontsize=9, color="#555")
    fig.tight_layout(); fig.savefig(FIG / "ext_budget.png", dpi=160); plt.close(fig)


def fig_hazard():
    p = TAB / "rs_survival.csv"
    if not p.exists():
        return
    s = pd.read_csv(p)
    s = s[s.type == "all"]
    kinds = [k for k in ["all", "front_page", "listing", "status", "dashboard", "map", "reference"] if (s.kind == k).any()]
    n = len(kinds); cols = min(4, n); rows = int(np.ceil(n / cols))
    fig, axs = plt.subplots(rows, cols, figsize=(4.2 * cols, 3.4 * rows), squeeze=False, sharey=True)
    for ax, k in zip(axs.flat, kinds):
        for cond, col in (("settled", "#8b5cf6"), ("nav", "#db2777"), ("scroll", "#f59e0b")):
            g = s[(s.kind == k) & (s.cond == cond)].sort_values("offset")
            if len(g):
                ax.errorbar(g.offset, g.S, yerr=[(g.S - g.S_lo).clip(lower=0), (g.S_hi - g.S).clip(lower=0)], marker="o", color=col, label=cond, capsize=2, lw=1.8)
        ax.set_xscale("log"); ax.set_title(k.replace("_", " "), fontsize=12); ax.set_xlabel("seconds after t0")
    for ax in axs[:, 0]:
        ax.set_ylabel("planned clicks still valid, S(t)")
    for ax in list(axs.flat)[n:]:
        ax.axis("off")
    axs[0, 0].legend(fontsize=10, frameon=False)
    fig.suptitle("Real pages: survival of a planned click, settled vs just acted (extension, Wilson 95% CI)", fontsize=13)
    fig.tight_layout(); fig.savefig(FIG / "ext_hazard.png", dpi=150); plt.close(fig)


def fig_rubric():
    m = pd.read_csv(TAB / "rubric_mstar.csv")
    m = m[(m.tier == 1) & (m.C == 6.51) & m.M_star.notna()]
    pairs = {"settled": [("pusv-tuned", "pixel"), ("pixel", "opus-5.5"), ("pixel", "haiku-5.5")],
             "dialog": [("pixel", "qwen3-vl-4b"), ("pixel", "opus-5.5"), ("qwen3-vl-4b", "opus-5.5")],
             "worked": [("pixel", "qwen3-vl-4b"), ("qwen3-vl-4b", "opus-5.5"), ("pixel", "opus-5.5")]}
    fig, axs = plt.subplots(1, 3, figsize=(15, 4.8), sharey=True)
    for ax, (q, prs) in zip(axs, pairs.items()):
        for a, b in prs:
            g = m[(m.question == q) & (((m.A == a) & (m.B == b)) | ((m.A == b) & (m.B == a)))].sort_values("q")
            if not len(g):
                continue
            y = g.M_star.where(np.isfinite(g.M_star) & (g.M_star > 0))
            lab = f"{g.A.iloc[0]} → {g.B.iloc[0]}" + ("" if y.notna().any() else f" ({g.verdict.iloc[0]})")
            ax.plot(g.q, y, marker="o", lw=2, label=lab)
        ax.set_xscale("log"); ax.set_yscale("log"); ax.set_title(q, fontsize=13); ax.set_xlabel("problem rate q at this step")
        ax.legend(fontsize=9, frameon=False)
    axs[0].set_ylabel("escalate when miss cost M exceeds M* (s)")
    fig.suptitle("Checker rubric, Tier 1 dev rates, C = 6.51 s (extension)", fontsize=13)
    fig.tight_layout(); fig.savefig(FIG / "ext_rubric.png", dpi=150); plt.close(fig)


def fig_planner():
    p = TAB / "d1_rates.csv"
    if not p.exists():
        return
    r = pd.read_csv(p)
    br = pd.read_csv(TAB / "d1_miss_breakdown.csv", index_col=0)
    fig, axs = plt.subplots(1, 2, figsize=(13, 4.8))
    ax = axs[0]
    ax.bar(range(len(r)), r.miss_rate, yerr=[r.miss_rate - r.lo, r.hi - r.miss_rate], color=["#1f6fd1", "#16a34a", "#f59e0b"], capsize=4)
    ax.set_xticks(range(len(r)), [n.replace(", ", ",\n") for n in r.name]); ax.set_ylabel("planner misses the named element")
    for i, v in enumerate(r.miss_rate):
        ax.text(i, v + 0.005, f"{v:.3f}", ha="center")
    ax.set_title("Planner misses by condition (Wilson 95% CI)", fontsize=12)
    ax = axs[1]
    bottom = np.zeros(len(br))
    for c in br.columns:
        ax.bar(range(len(br)), br[c], bottom=bottom, label=c); bottom += br[c].values
    ax.set_xticks(range(len(br)), [{"a": "motion on,\nlast three", "b": "frozen,\nlast three", "c": "motion on,\nlatest only"}[i] for i in br.index])
    ax.set_ylabel("misses"); ax.legend(fontsize=10, frameon=False); ax.set_title("What the missed click landed on", fontsize=12)
    fig.text(0.99, 0.01, "extension D.1; Haiku 5.5 planner, Tier 1 test pages", ha="right", fontsize=9, color="#555")
    fig.tight_layout(); fig.savefig(FIG / "ext_planner.png", dpi=150); plt.close(fig)


def main():
    FIG.mkdir(exist_ok=True)
    for f in (fig_bar, fig_budget, fig_hazard, fig_rubric, fig_planner):
        f()
    print("figures written")


if __name__ == "__main__":
    main()
