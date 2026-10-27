"""Slide and paper figures, 1920x1080, minimal style: off-white background, near-black text, one accent, no gridlines.

  python -m harness.figures slides        # slide6_live_planned_vs_now.png, slide7_anchored_overlay.png (dev pair)
  python -m harness.figures tradeoff      # fig_reaim_tradeoff.png from tradeoff_c4_*.csv (and C6 when present)
"""
import json, sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.patches import Rectangle
from PIL import Image

from anchored import check as A

ROOT = Path(__file__).resolve().parents[1]
FIG = ROOT / "figures"
BG, INK, ACCENT, MUTED = "#FAFAF7", "#1A1A1A", "#D9480F", "#8A8A85"
plt.rcParams.update({"font.size": 26, "font.family": "sans-serif", "axes.edgecolor": INK, "axes.labelcolor": INK,
                     "xtick.color": INK, "ytick.color": INK, "figure.facecolor": BG, "axes.facecolor": BG,
                     "axes.spines.top": False, "axes.spines.right": False, "axes.grid": False})


def fig():
    return plt.figure(figsize=(19.2, 10.8), dpi=100)


def pick_pair():
    """A Tier 1 feed or dashboard dev pair where the target moved and C4 (frozen) re-aimed onto it."""
    from harness.run_checks import load, feature_table, Scorer
    fz = json.loads((ROOT / "results/pilot/frozen_w2.json").read_text())["C4"]
    recs = load("dev")
    feats = feature_table("dev", recs, fz["mask_thr"], fz["mask_dilate"])
    sc = Scorer(recs)
    cfg = {**A.DEFAULTS, **fz}
    best = None
    for r in recs:
        if r["tier"] != 1 or r["page"] not in ("live_feed", "live_dashboard") or r["truth"][0]["correct_action"] != "reaim":
            continue
        F, ms = feats[r["pair_id"]]
        action, click, _, _ = A.decide(F, r["planned_box"], cfg, "reaim")
        if action != "reaim" or sc(r["pair_id"], action, click, ms + A.FRAME_WAIT_MS)["outcome"] != "recovered":
            continue
        shift = abs(click[0] - r["click"][0]) + abs(click[1] - r["click"][1])
        g = {k: A.gray(ROOT / v) for k, v in r["frames"].items()}
        Mk = A.motion_mask(g["planned_a"], g["planned_b"], g["current_a"], g["current_b"], cfg["mask_thr"], cfg["mask_dilate"])
        bx, by, bw, bh = r["planned_box"]
        ys, ye = int(max(0, min(by, by + click[1] - r["click"][1]) - 150)), int(max(by, by + click[1] - r["click"][1]) + bh + 150)
        local = float(Mk[ys:ye, int(max(0, bx - 300)):int(bx + bw + 300)].mean())
        key = (40 <= shift <= 400, min(local, 0.08))  # a visible move, then visible masked motion near it
        if best is None or key > best[0]:
            best = (key, r, F, click, cfg)
    return best[1:]


def dot(ax, xy, color=INK, r=11):
    ax.add_patch(plt.Circle(xy, r, color=color, zorder=5))
    ax.add_patch(plt.Circle(xy, r + 5, fill=False, color=BG, lw=3, zorder=5))


def slides():
    r, F, click, cfg = pick_pair()
    pa = Image.open(ROOT / r["frames"]["planned_a"]).convert("RGB")
    cb = Image.open(ROOT / r["frames"]["current_b"]).convert("RGB")
    c0 = r["click"]

    f = fig()
    for i, (im, title) in enumerate([(pa, "Planned on"), (cb, "Now")]):
        ax = f.add_axes([0.03 + i * 0.49, 0.08, 0.455, 0.78])
        ax.imshow(im); ax.set_axis_off()
        dot(ax, c0)
        ax.set_title(title, loc="left", fontsize=40, color=INK, pad=18, fontweight="bold")
    f.text(0.03, 0.03, f"Pilot data. Same click point on both frames; {r['page'].replace('_', ' ')}, 6.7 s apart.",
           fontsize=20, color=MUTED)
    FIG.mkdir(exist_ok=True)
    f.savefig(FIG / "slide6_live_planned_vs_now.png", facecolor=BG); plt.close(f)

    g = {k: A.gray(ROOT / v) for k, v in r["frames"].items()}
    M = A.motion_mask(g["planned_a"], g["planned_b"], g["current_a"], g["current_b"], cfg["mask_thr"], cfg["mask_dilate"])
    x, y, w, h = r["planned_box"]
    nx, ny = x + (click[0] - c0[0]), y + (click[1] - c0[1])
    # Crop every panel to the same window around the planned and re-found boxes, 4:3.
    x0, x1 = min(x, nx) - 60, max(x, nx) + w + 60
    y0, y1 = min(y, ny) - 60, max(y, ny) + h + 60
    cw = max(x1 - x0, (y1 - y0) * 4 / 3, 480); chh = cw * 3 / 4
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    X0 = int(min(max(0, cx - cw / 2), 1280 - cw)); Y0 = int(min(max(0, cy - chh / 2), 800 - chh))
    win = (X0, X0 + cw, Y0 + chh, Y0)
    f = fig()
    titles = ["Ignore what moves", "Find the target", "Re-aim"]
    for i in range(3):
        ax = f.add_axes([0.02 + i * 0.327, 0.16, 0.31, 0.62])
        ax.imshow(cb); ax.set_axis_off()
        ax.set_xlim(win[0], win[1]); ax.set_ylim(win[2], win[3])
        ax.set_title(titles[i], loc="left", fontsize=36, color=INK, pad=16, fontweight="bold")
        if i == 0:
            ov = np.zeros((*M.shape, 4)); ov[M] = (0.85, 0.28, 0.06, 0.45)
            ax.imshow(ov)
        if i >= 1:
            ax.add_patch(Rectangle((x, y), w, h, fill=False, ec=MUTED, lw=2.5, ls="--"))
            ax.add_patch(Rectangle((nx - 4, ny - 4), w + 8, h + 8, fill=False, ec=ACCENT, lw=4))
        if i == 2:
            dot(ax, c0, MUTED, 9)
            ax.annotate("", xy=click, xytext=c0, arrowprops=dict(arrowstyle="-|>", color=ACCENT, lw=3.5, mutation_scale=30))
            dot(ax, click, ACCENT)
    f.text(0.02, 0.06, "Shaded: pixels that moved on their own (masked).  Dashed: planned box.  Orange: re-found target and new click.",
           fontsize=20, color=MUTED)
    f.text(0.02, 0.025, f"Pilot data, dev pair {r['pair_id']}.", fontsize=18, color=MUTED)
    f.savefig(FIG / "slide7_anchored_overlay.png", facecolor=BG); plt.close(f)
    print("slides from", r["pair_id"])


def tradeoff(split="test"):
    f = fig()
    ax = f.add_axes([0.1, 0.14, 0.82, 0.72])
    for name, color, label in (("c4", INK, "C4 pixels only"), ("c6", ACCENT, "C6 pixels + Qwen3-VL 4B")):
        p = ROOT / f"results/pilot/tradeoff_{name}_{split}.csv"
        if not p.exists():
            continue
        d = pd.read_csv(p)
        ax.plot(d.wrong_share * 100, d.reaim_recovery * 100, "-o", color=color, lw=3, ms=10, label=label)
        for _, row in d.iloc[[0, -1]].iterrows():
            ax.annotate(f"m={row.m_unique:g}", (row.wrong_share * 100, row.reaim_recovery * 100), xytext=(10, -28),
                        textcoords="offset points", fontsize=18, color=MUTED)
    ax.set_xlabel("Wrong re-aims, % of re-aims"); ax.set_ylabel("Moved targets re-aimed correctly, %")
    ax.legend(frameon=False, loc="lower right")
    f.text(0.1, 0.92, "Re-aim recovery against wrong re-aims", fontsize=32, color=INK, fontweight="bold")
    f.text(0.1, 0.03, f"Pilot data, Tier 1 {split} split. Each point is one uniqueness margin m (best minus second match score).", fontsize=18, color=MUTED)
    f.savefig(FIG / "fig_reaim_tradeoff.png", facecolor=BG); plt.close(f)


if __name__ == "__main__":
    {"slides": slides, "tradeoff": tradeoff}[sys.argv[1]]()
