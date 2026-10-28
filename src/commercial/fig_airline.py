"""Figure 1 of the paper: one airline's home page as recorded by the HTTP Archive desktop crawl (2026-10-01).
Requests in flight and layout shifts over time, with the screenshot of a network-idle wait capped at 3 s and the
6.5 s an agent would then spend planning. Reads results/pages_desktop.csv and results/requests_desktop.csv
(the public repo ships them gzipped in data/commercial/).

  python commercial/fig_airline.py [host]      # -> paper/fig_airline.pdf, commercial/results/fig_airline.png
"""
import csv, sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import analyze as A  # noqa: E402

BLUE, ORANGE, AQUA, INK, MUTED, GRID = "#2a78d6", "#eb6834", "#1baf7a", "#0b0b0b", "#52514e", "#e6e4df"
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 8, "axes.edgecolor": MUTED, "axes.labelcolor": INK,
                     "xtick.color": MUTED, "ytick.color": MUTED, "axes.spines.top": False, "axes.spines.right": False,
                     "pdf.fonttype": 42, "ps.fonttype": 42})
csv.field_size_limit(10 ** 9)


def load(host):
    page = next(r for r in csv.DictReader(open(HERE / "results/pages_desktop.csv")) if r["host"] == host and truthy(r["is_book"]))
    req = next(r for r in csv.DictReader(open(HERE / "results/requests_desktop.csv")) if r["page"] == page["page"])
    iv = A.parse_intervals(req["intervals"])
    r = dict(intervals=iv, n_parsed=len(iv), n_requests=int(req["n_requests"]), n_open=int(req["n_open"]),
             main_status=int(req["main_status"]) if req["main_status"] else None)
    return page, r, A.page_record(page, r)


def truthy(x):
    return str(x).strip().lower() in ("true", "1")


def main(host="www.alaskaair.com", xmax=22.0):
    page, req, rec = load(host)
    s = lambda ms: ms / 1000.0
    t0, T, W = s(rec["t0"]), s(rec["T_S5"]), A.WINDOW_MS / 1000.0
    quiet = s(rec["idle_start"]) if rec["idle_start"] is not None else None
    load_ev = s(rec["load"]) if rec["load"] else None
    grid = np.arange(0, xmax * 1000, 10.0)
    infl = np.zeros_like(grid)
    for a, b in req["intervals"]:
        infl += (grid >= a) & (grid < (b if b is not None else np.inf))
    shifts = [(s(t), sc) for t, sc in A.parse_shifts(page["shifts"])]

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(6.6, 2.2), sharex=True, gridspec_kw=dict(height_ratios=[1, 1.5], hspace=0.12))
    for ax in (ax1, ax2):
        ax.axvspan(T, T + W, color=GRID, alpha=0.75, lw=0)
        ax.axvline(t0, color=MUTED, lw=0.8, ls=":")
        ax.axvline(T, color=ORANGE, lw=1.4)
        if load_ev:
            ax.axvline(load_ev, color=MUTED, lw=0.8, ls=":")
        if quiet:
            ax.axvline(quiet, color=MUTED, lw=0.8, ls=":")
    ax1.fill_between(grid / 1000.0, infl, step="post", color=BLUE, alpha=0.35, lw=0)
    ax1.step(grid / 1000.0, infl, where="post", color=BLUE, lw=0.6)
    ax1.set_ylabel("requests\nin flight", fontsize=7.5)
    ax1.set_ylim(0, max(infl.max() * 1.15, 5))
    ymax = 0.55
    for t, sc in shifts:
        inside = T < t <= T + W
        ax2.vlines(t, 0, sc, color=ORANGE if inside else MUTED, lw=2.0 if inside else 1.4)
        ax2.plot(t, sc, "o", color=ORANGE if inside else MUTED, ms=3.2)
    big = [(t, sc) for t, sc in shifts if T < t <= T + W and sc >= 0.2]
    for t, sc in big:
        ax2.text(t + 0.12, sc, f"{sc:.2f}", fontsize=7.5, color=ORANGE, va="center")
    ax2.set_ylim(0, ymax); ax2.set_ylabel("layout-shift\nscore", fontsize=7.5)
    ax2.set_xlim(0, xmax); ax2.set_xticks(range(0, int(xmax) + 1, 2)); ax2.set_xlabel("seconds after the page was requested")
    ax2.grid(axis="y", color=GRID, lw=0.5)
    lab = dict(fontsize=7, color=INK, va="top")
    ax1.text(t0 - 0.12, ax1.get_ylim()[1] * 0.98, "HTML\nparsed", ha="right", **lab)
    ax1.text(T + 0.12, ax1.get_ylim()[1] * 0.98, "screenshot after a network-idle\nwait (3 s cap)", ha="left", color=ORANGE, fontsize=7, va="top")
    ax2.text(T + W / 2, ymax * 0.97, f"agent plans ({W:g} s)", ha="center", **lab)
    if load_ev:
        ax2.text(load_ev - 0.12, ymax * 0.97, "load\nevent", ha="right", **lab)
    if quiet:
        ax2.text(quiet - 0.12, ymax * 0.97, "network\nquiet", ha="right", **lab)
    fig.subplots_adjust(left=0.1, right=0.985, top=0.97, bottom=0.19)
    fig.savefig(HERE.parent / "paper/fig_airline.pdf")
    fig.savefig(HERE / "results/fig_airline.png", dpi=220)
    inside = [(round(t, 3), round(sc, 4)) for t, sc in shifts if T < t <= T + W]
    print(dict(host=host, t0=t0, screenshot=T, quiet=quiet, load=load_ev, shifts_in_window=inside, n_in_window=len(inside),
               in_flight_at_screenshot=int(infl[int(rec["T_S5"] // 10)])))


if __name__ == "__main__":
    main(*sys.argv[1:2])
