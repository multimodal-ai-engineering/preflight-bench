"""Figure 1: a stale click on a race-registration page built for this illustration (race/race.html).
Run race/render_race.py first: it renders the page at DOM-ready and 4 s later, and reads the element under the click."""
import json
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Circle, FancyArrowPatch, Rectangle
from PIL import Image

ORANGE, BLUE, INK = "#eb6834", "#2a78d6", "#1c1b19"
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 8})
meta = json.load(open("race/race_meta.json"))
assert meta["element_at_click"] == "olympic"
X0, Y0, X1, Y1 = 0, 58, 930, 512
click = tuple(meta["click"])
sb = meta["sprint_box_at_click"]
x, y, w, h = sb["x"], sb["y"], sb["width"], sb["height"]
shift = round(sb["y"] - meta["planned_box"]["y"])

fig, axes = plt.subplots(1, 2, figsize=(6.9, 2.7), gridspec_kw={"wspace": 0.05})
panels = [("race/planned.png", "Planned on  (t = 0 s, page just opened)",
           "Plan: click Register for the Sprint."),
          ("race/clicked.png", "Clicked  (t = 4 s)",
           "A results banner loaded at 0.8 s, pushing the list down\na row. The spot is now Register for the Olympic.")]
for ax, (f, title, note) in zip(axes, panels):
    ax.imshow(Image.open(f).crop((X0, Y0, X1, Y1)), extent=(X0, X1, Y1, Y0))
    ax.set_xlim(X0, X1); ax.set_ylim(Y1, Y0); ax.set_xticks([]); ax.set_yticks([])
    for s in ax.spines.values():
        s.set_color("#d6d3cc"); s.set_linewidth(0.8)
    ax.set_title(title, fontsize=8.2, color=INK, loc="left", pad=4, fontweight="bold")
    ax.set_xlabel(note, fontsize=6.8, color=INK, loc="left", labelpad=5, linespacing=1.3)
    ax.add_patch(Circle(click, 36, fill=False, ec=ORANGE, lw=2.2))
    ax.plot([click[0]], [click[1]], marker="o", color=ORANGE, ms=2.4)
axes[1].add_patch(Rectangle((x - 7, y - 7), w + 14, h + 14, fill=False, ec=BLUE, lw=1.6))
fig.savefig("fig_hero.pdf", bbox_inches="tight", pad_inches=0.02)
fig.savefig("fig_hero.png", dpi=220, bbox_inches="tight", pad_inches=0.02)
fig.savefig("fig_hero_hi.png", dpi=400, bbox_inches="tight", pad_inches=0.02)
print("ok")
