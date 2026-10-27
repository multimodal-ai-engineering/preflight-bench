"""Full-study figures, 1920x1080, minimal style (off-white, near-black text, one accent, no gridlines).

  python -m harness.full_figures   # results/figures/full_fig_A_stale.png, full_fig_B_grid.png, full_fig_C_example.png
"""
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.patches import Rectangle
from PIL import Image

from anchored import check as A

ROOT = Path(__file__).resolve().parents[2]
TAB = ROOT / "results/full/tables"
FIG = ROOT / "results" / "figures"
BG, INK, ACCENT, MUTED = "#FAFAF7", "#1A1A1A", "#D9480F", "#8A8A85"
plt.rcParams.update({"font.size": 24, "font.family": "sans-serif", "axes.edgecolor": INK, "axes.labelcolor": INK, "xtick.color": INK,
                     "ytick.color": INK, "figure.facecolor": BG, "axes.facecolor": BG, "axes.spines.top": False,
                     "axes.spines.right": False, "axes.grid": False})
NAMES = {"C0": "No check", "C1": "PUSV as published", "C2": "PUSV-style, tuned", "C4": "Anchored, pixels (re-plan only)", "C5": "Anchored + Qwen 2B",
         "C6": "Anchored + Qwen 4B", "C7": "PUSV + anchored"}


def fig_a():
    t = pd.read_csv(TAB / "table2_replay.csv")
    t = t[t.tier == 1].set_index("cond").reindex([c for c in NAMES if c in set(t.cond)])
    f = plt.figure(figsize=(19.2, 10.8), dpi=100); ax = f.add_axes([0.30, 0.14, 0.50, 0.72])
    y = np.arange(len(t))[::-1]
    cols = [ACCENT if c == "C4" else INK for c in t.index]
    ax.barh(y, t.stale_per_1000, color=cols, height=0.6)
    raw = pd.read_csv(ROOT / "results/full/raw/pixel_test_decisions.csv")
    rp = raw[raw.tier == 1].groupby("cond").apply(lambda d: (d.action == "replan").mean())
    for yi, v, c in zip(y, t.stale_per_1000, t.index):
        ax.text(v + 8, yi, f"{v:.0f}   (re-plans {rp.get(c, 0):.0%} of steps)", va="center", fontsize=20)
    ax.set_yticks(y, [NAMES[c] for c in t.index]); ax.set_xlabel("Stale actions per 1,000 steps (Tier 1 test)")
    f.text(0.03, 0.92, "Stale actions that slip through, by check", fontsize=32, fontweight="bold")
    f.text(0.03, 0.03, "PreflightBench-Live, Tier 1 test templates (unseen layouts). 6.5 s gap. Lower is better; a re-plan avoids a stale action but costs 6.5 s.",
           fontsize=17, color=MUTED)
    f.savefig(FIG / "full_fig_A_stale.png", facecolor=BG); plt.close(f)


def fig_b():
    """Each question x check size at the check's own decision point (supplementary: recall at 2% false alarms is
    undefined for yes/no checks whose false alarms exceed 2%). Best check per cell = highest recall among checks
    whose false-alarm rate is no higher than Opus's; orange when that recall is within 2 points of Opus's."""
    q = pd.read_csv(TAB / "table1_questions.csv")
    size = {"pixel": "pixel", "pusv-tuned": "pixel", "qwen3-vl-2b": "small", "qwen3-vl-4b": "small", "smolvlm2-2.2b": "small",
            "florence-2": "small", "haiku-5.5": "large", "opus-5.5": "large"}
    q = q[q.check.isin(size) & (q.tier == 1)].copy(); q["size"] = q.check.map(size)
    f = plt.figure(figsize=(19.2, 10.8), dpi=100); ax = f.add_axes([0.16, 0.1, 0.62, 0.74])
    qs, ss = ["settled", "dialog", "worked"], ["pixel", "small", "large"]
    for i, qq in enumerate(qs):
        op = q[(q.question == qq) & (q.check == "opus-5.5")].iloc[0]
        for j, s_ in enumerate(ss):
            g = q[(q.question == qq) & (q["size"] == s_) & (q.fa_native <= op.fa_native + 1e-9)]
            if not len(g):
                ax.text(j, i, "none at Opus's\nfalse-alarm rate", ha="center", va="center", color=MUTED, fontsize=16); continue
            b = g.sort_values("recall_native", ascending=False).iloc[0]
            ok = b.recall_native >= op.recall_native - 0.02
            ax.add_patch(Rectangle((j - .45, i - .4), .9, .8, color=ACCENT if ok else "#E8E6DF"))
            ax.text(j, i + .02, f"{b.recall_native:.0%}", ha="center", va="center", fontsize=34, color="white" if ok else INK, fontweight="bold")
            ax.text(j, i - .24, b.check, ha="center", va="center", fontsize=16, color="white" if ok else MUTED)
            ax.text(j, i + .27, f"{b.fa_native:.1%} false alarms", ha="center", va="center", fontsize=15, color="white" if ok else MUTED)
    ax.set_xlim(-.5, 2.5); ax.set_ylim(2.5, -.5)
    ax.set_xticks(range(3), ["Pixels", "Small model (≤ 4B)", "Large hosted model"]); ax.set_yticks(range(3), ["Target settled?", "Dialog in the way?", "Did it fail?"])
    ax.tick_params(length=0); [s_.set_visible(False) for s_ in ax.spines.values()]
    f.text(0.03, 0.92, "Which check each question needs", fontsize=32, fontweight="bold")
    f.text(0.80, 0.5, "Recall at each check's\nown decision point,\nTier 1 test.\n\nOnly checks with no more\nfalse alarms than Opus 5.5.\nOrange: within 2 points\nof Opus's recall.", fontsize=18, color=MUTED, va="center")
    f.text(0.03, 0.03, "PreflightBench-Live. Supplementary view (not the preregistered metric). Small models on a stratified test subset.", fontsize=17, color=MUTED)
    f.savefig(FIG / "full_fig_B_grid.png", facecolor=BG); plt.close(f)


def fig_c():
    from harness.full_checks import Scorer, features, load
    fz = json.loads((ROOT / "results/full/frozen_full.json").read_text())
    cfg = {**A.DEFAULTS, **fz.get("deviation", {}).get("exploratory_C4r", fz["C4"])}
    recs = [r for r in load("dev") if r["tier"] == 1 and r["kind"] in ("live_newsfeed", "live_market", "live_map") and r["correct_action"] == "reaim"]
    feats = features("dev"); sc = Scorer(recs)
    best = None
    for r in recs:
        F = feats[r["pair_id"]]["F"]
        a, click, _, _ = A.decide(F, r["planned_box"], cfg, "reaim")
        if a != "reaim" or sc(r["pair_id"], a, click, 240)["outcome"] != "recovered":
            continue
        shift = abs(click[0] - r["click"][0]) + abs(click[1] - r["click"][1])
        key = (40 <= shift <= 300, -abs(shift - 120))
        if best is None or key > best[0]:
            best = (key, r, click)
    if best is None:
        print("no example found"); return
    _, r, click = best
    g = {k: A.gray(ROOT / v) for k, v in r["frames"].items()}
    M_ = A.motion_mask(g["planned_a"], g["planned_b"], g["current_a"], g["current_b"], cfg["mask_thr"], cfg["mask_dilate"])
    cb = Image.open(ROOT / r["frames"]["current_b"]).convert("RGB")
    x, y, w, h = r["planned_box"]; c0 = r["click"]; nx, ny = x + click[0] - c0[0], y + click[1] - c0[1]
    x0, x1 = min(x, nx) - 80, max(x, nx) + w + 80; y0, y1 = min(y, ny) - 80, max(y, ny) + h + 80
    cw = max(x1 - x0, (y1 - y0) * 4 / 3, 480); ch = cw * 3 / 4
    X0 = min(max(0, (x0 + x1) / 2 - cw / 2), 1280 - cw); Y0 = min(max(0, (y0 + y1) / 2 - ch / 2), 800 - ch)
    f = plt.figure(figsize=(19.2, 10.8), dpi=100)
    for i, title in enumerate(["Ignore what moves", "Find the target", "Re-aim"]):
        ax = f.add_axes([0.02 + i * 0.327, 0.16, 0.31, 0.62]); ax.imshow(cb); ax.set_axis_off()
        ax.set_xlim(X0, X0 + cw); ax.set_ylim(Y0 + ch, Y0); ax.set_title(title, loc="left", fontsize=36, fontweight="bold", pad=16)
        if i == 0:
            ov = np.zeros((*M_.shape, 4)); ov[M_] = (0.85, 0.28, 0.06, 0.45); ax.imshow(ov)
        if i >= 1:
            ax.add_patch(Rectangle((x, y), w, h, fill=False, ec=MUTED, lw=2.5, ls="--"))
            ax.add_patch(Rectangle((nx - 4, ny - 4), w + 8, h + 8, fill=False, ec=ACCENT, lw=4))
        if i == 2:
            ax.annotate("", xy=click, xytext=c0, arrowprops=dict(arrowstyle="-|>", color=ACCENT, lw=3.5, mutation_scale=30))
            ax.add_patch(plt.Circle(click, 10, color=ACCENT, zorder=5))
    f.text(0.02, 0.06, "Shaded: pixels that moved on their own (masked). Dashed: planned box. Orange: re-found target and new click.", fontsize=20, color=MUTED)
    f.text(0.02, 0.025, f"PreflightBench-Live dev pair, {r['kind'].replace('_', ' ')}. Re-aim shown with the exploratory setting (C4r); "
           "the frozen check re-plans instead, because no re-aim setting met the 1% wrong re-aim cap.", fontsize=16, color=MUTED)
    f.savefig(FIG / "full_fig_C_example.png", facecolor=BG); plt.close(f)


if __name__ == "__main__":
    for fn in (fig_a, fig_b, fig_c):
        try:
            fn(); print("ok", fn.__name__)
        except Exception as e:
            print("skip", fn.__name__, repr(e)[:200])
