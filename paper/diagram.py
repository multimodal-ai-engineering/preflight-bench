"""Figure 1: one agent step today, and with a preflight. Drawn with matplotlib patches."""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
plt.rcParams.update({"pdf.fonttype": 42, "ps.fonttype": 42})
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

BLUE, ORANGE, AQUA, INK, MUTED, PALE = "#2a78d6", "#eb6834", "#1baf7a", "#0b0b0b", "#52514e", "#f1f0ec"
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 8.5})

fig, ax = plt.subplots(figsize=(6.6, 2.9))
ax.set_xlim(-0.6, 100.8); ax.set_ylim(-2, 46); ax.axis("off")

def box(x, y, w, h, text, fc="white", ec=MUTED, lw=1.0, fs=8.5, color=INK, bold=False, ls="-"):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0,rounding_size=1.2", fc=fc, ec=ec, lw=lw, ls=ls))
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=fs, color=color, fontweight="bold" if bold else "normal", linespacing=1.15)

def arrow(x0, y0, x1, y1, color=MUTED, lw=1.2, style="-|>"):
    ax.add_patch(FancyArrowPatch((x0, y0), (x1, y1), arrowstyle=style, mutation_scale=9, color=color, lw=lw, shrinkA=0, shrinkB=0))

# ---- Row A: today
ya = 31
ax.text(0, ya + 11, "Today", fontsize=9.5, fontweight="bold", color=INK, va="center")
box(0, ya, 15, 8, "screenshot\ncaptured as the\npage opens", fc=PALE, fs=7.2)
arrow(15, ya + 4, 19, ya + 4)
box(19, ya, 34, 8, "plan with a large AI model\n(1–13 s)", fc=PALE, fs=8)
ax.text(36, ya - 2.6, "the page continues loading: 17% of planned targets move", fontsize=7.5, color=ORANGE, ha="center", va="center")
arrow(53, ya + 4, 57, ya + 4)
box(57, ya, 17, 8, "click at the\nplanned position", fc=PALE, fs=7.3)
arrow(74, ya + 4, 78, ya + 4)
box(78, ya, 22, 8, "click lands on a\ndifferent element", fs=7.5, fc="#fdebe4", ec=ORANGE, color=ORANGE, bold=True)

# ---- Row B: with a preflight
yb = 11
ax.text(0, yb + 12, "With the three rules", fontsize=9.5, fontweight="bold", color=INK, va="center")
box(0, yb, 15, 8, "wait for\nnetwork activity\nto stop (~1 s)", fc="#e3f6ee", ec=AQUA, fs=7.0)
arrow(15, yb + 4, 17, yb + 4)
box(17, yb, 13, 8, "screenshot", fc=PALE, fs=8)
arrow(30, yb + 4, 33, yb + 4)
box(33, yb, 20, 8, "plan with a\nlarge AI model", fc=PALE, fs=8)
arrow(53, yb + 4, 56, yb + 4)
box(56, yb - 1, 26, 10, "pixel check at the target\n(0.3 s, no model):\nstill there? covered?", fc="#e4eefb", ec=BLUE, fs=7.2)
arrow(82, yb + 4, 85.5, yb + 4)
box(85.5, yb + 2, 14.5, 5, "proceed", fc="#e3f6ee", ec=AQUA, color=AQUA, bold=True)
# re-plan loop
arrow(69, yb - 1, 69, yb - 4.5, color=BLUE, style="-")
arrow(69, yb - 4.5, 43, yb - 4.5, color=BLUE, style="-")
arrow(43, yb - 4.5, 43, yb - 0.2, color=BLUE)
ax.text(52, yb - 6.6, "target moved or covered: re-plan from a new screenshot", fontsize=7.3, color=BLUE, ha="center", va="center")
# after the action: the "what" check
box(85.5, yb - 8, 14.5, 7.5, "after a commit:\nverify outcome\n(small model)", fc="#fff4e3", ec="#eda100", fs=6.6)

# two kinds of seeing legend
ax.text(0, -0.8, "Two forms of perception:  pixels verify where the target is;  a small model or OCR verifies what happened.",
        fontsize=7.8, color=MUTED, va="center")

fig.tight_layout(pad=0.3)
fig.savefig("fig_diagram.pdf"); fig.savefig("fig_diagram.png", dpi=220)
print("ok")
