"""Supplementary illustration: a stale click on the benchmark's news-feed page (dev pair 3d0f761ce315bfcd)."""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
plt.rcParams.update({"pdf.fonttype": 42, "ps.fonttype": 42})
from matplotlib.patches import Circle, FancyArrowPatch, Rectangle
from PIL import Image

ORANGE, BLUE, INK = "#eb6834", "#2a78d6", "#1c1b19"
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 8})
X0, Y0, X1, Y1 = 0, 46, 840, 536            # crop in page pixels
click = (260.66, 188.48)                     # planned click point
x, y, w, h = (239, 484.08, 43.33, 24.80)     # planned target's box at the moment of the click

fig, axes = plt.subplots(1, 2, figsize=(6.9, 2.75), gridspec_kw={"wspace": 0.05})
panels = [("hero/planned.png", "Planned on  (t = 0 s)",
           "Plan: click Save on the top story,\n“Zinnia tansy quill vesper drift zinnia ferry.”"),
          ("hero/now.png", "Clicked  (t = 6.5 s)",
           "Two stories arrived on top. The same spot is now Save\non another story; the target (blue) is 308 px lower.")]
for ax, (f, title, note) in zip(axes, panels):
    ax.imshow(Image.open(f).crop((X0, Y0, X1, Y1)), extent=(X0, X1, Y1, Y0))
    ax.set_xlim(X0, X1); ax.set_ylim(Y1, Y0); ax.set_xticks([]); ax.set_yticks([])
    for s in ax.spines.values():
        s.set_color("#d6d3cc"); s.set_linewidth(0.8)
    ax.set_title(title, fontsize=8.2, color=INK, loc="left", pad=4, fontweight="bold")
    ax.set_xlabel(note, fontsize=7.0, color=INK, loc="left", labelpad=5, linespacing=1.3)
    ax.add_patch(Circle(click, 25, fill=False, ec=ORANGE, lw=2.0))
    ax.plot([click[0]], [click[1]], marker="o", color=ORANGE, ms=2.4)
axes[1].add_patch(Rectangle((x - 7, y - 7), w + 14, h + 14, fill=False, ec=BLUE, lw=1.6))
axes[1].add_patch(FancyArrowPatch((click[0] - 27, click[1] + 12), (x - 11, y + h / 2), connectionstyle="arc3,rad=0.35",
                                  arrowstyle="-|>", mutation_scale=9, color=BLUE, lw=1.4))
fig.savefig("fig_feed.pdf", bbox_inches="tight", pad_inches=0.02)
fig.savefig("fig_feed.png", dpi=220, bbox_inches="tight", pad_inches=0.02)
print("ok")
