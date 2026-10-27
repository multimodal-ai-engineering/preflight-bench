"""Wave 4 tables and figures from logged decisions. PILOT. No model is called.

  python -m harness.results SPLIT          # tables -> results/pilot/tables_{split}/*.csv, figures -> results/figures/
  python -m harness.results lopo          # leave-one-page-out threshold check for C4 and C6

Inputs: results/pilot/raw/w2_{split}_decisions.csv (C1-C3) and raw/w3_{split}_decisions.csv (C0, C4-C9, references),
results/pilot/q3_{split}_summary.csv. Tier 1 unless noted. Costs: C_plan 6.51 s, C_stale 2x, C_wrong 3x.
"""
import itertools, json, sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from harness import metrics as M

ROOT = Path(__file__).resolve().parents[2]
RES = ROOT / "results/pilot"
FIG = ROOT / "results" / "figures"
ORDER = ["C0", "C1", "C2", "C3", "C4", "C5", "C6", "C7", "C8", "C9", "oracle", "always_replan"]
LABEL = {"C0": "C0 no check", "C1": "C1 whole-screen (published)", "C2": "C2 whole-screen (tuned)",
         "C3": "C3 anchored, re-plan only", "C4": "C4 anchored + re-aim", "C5": "C5 anchored + Qwen 2B",
         "C6": "C6 anchored + Qwen 4B", "C7": "C7 Qwen 4B alone", "C8": "C8 Opus 5.5 alone",
         "C9": "C9 Haiku 5.5 alone", "oracle": "oracle", "always_replan": "always re-plan"}
BINS = ["static", "low", "med", "high"]
BG, INK, ACCENT, MUTED = "#FAFAF7", "#1A1A1A", "#D9480F", "#8A8A85"


def decisions(split):
    w2 = pd.read_csv(RES / f"raw/w2_{split}_decisions.csv")
    w3 = pd.read_csv(RES / f"raw/w3_{split}_decisions.csv")
    df = pd.concat([w2[w2.cond.isin(["C1", "C2", "C3"])], w3], ignore_index=True)
    for c in ("escalated", "usd", "model_ms"):
        if c not in df:
            df[c] = np.nan
    df["escalated"] = df.escalated.fillna(False).astype(bool)
    df["usd"] = df.usd.fillna(0.0)
    for c in ("missing", "parse_fail"):  # booleans (C7-C9) and counts (C5/C6) in one column
        df[c] = pd.to_numeric(df[c].replace({True: 1, False: 0, "True": 1, "False": 0}), errors="coerce").fillna(0)
    return df


def ci(d, stat):
    lo, hi = M.cluster_bootstrap(d, stat)
    return lo, hi


def row_q1(d):
    fr = lambda x: M.per_1000(x, x.outcome == "false_replan")
    st = lambda x: M.per_1000(x, x.outcome == "stale")
    sd = lambda x: M.per_1000(x, x.stale_during_check)
    sec = lambda x: M.expected_seconds(x, 0.05)
    out = dict(n=len(d))
    for name, f in (("false_replan_per_1000", fr), ("stale_per_1000", st), ("stale_during_check_per_1000", sd), ("sec_p05", sec)):
        lo, hi = ci(d, f)
        out.update({name: f(d), f"{name}_lo": lo, f"{name}_hi": hi})
    out.update(ms_median=float(d.delta_s.median() * 1000), ms_p95=float(d.delta_s.quantile(0.95) * 1000),
               escalation_rate=float(d.escalated.mean()), usd_per_step=float(d.usd.mean()),
               usd_per_1000=float(d.usd.mean() * 1000))
    return out


def table1(df):
    rows = []
    t1 = df[df.tier == 1]
    for c in ORDER:
        d = t1[t1.cond == c]
        if not len(d):
            continue
        rows.append(dict(cond=c, motion_bin="all", **row_q1(d)))
        for b in BINS:
            db = d[d.motion_bin == b]
            if len(db):
                rows.append(dict(cond=c, motion_bin=b, **row_q1(db)))
    return pd.DataFrame(rows)


def table2(df):
    t1 = df[df.tier == 1]
    rows = []
    for c in ORDER:
        d = t1[t1.cond == c]
        if not len(d) or c == "C3":
            continue
        base = t1[(t1.cond == "C3") & t1.pair_id.isin(d.pair_id)]  # same pairs (C8 runs on a subset)
        moved = d[d.correct0 == "reaim"]
        re = d[d.action == "reaim"]
        lk = d[d.event == "moved_lookalike"]
        lkre = lk[lk.action == "reaim"]
        w = M.wilson(int((re.outcome == "wrong_reaim").sum()), len(re))
        wl = M.wilson(int((lkre.outcome == "wrong_reaim").sum()), len(lkre))
        rec = lambda x: float((x[x.correct0 == "reaim"].outcome == "recovered").mean())
        lo, hi = ci(d, rec)
        replans = lambda x: (x.action == "replan").mean() * 1000
        rows.append(dict(cond=c, n=len(d), n_moved=len(moved), reaim_recovery=rec(d), reaim_recovery_lo=lo, reaim_recovery_hi=hi,
                         n_reaims=len(re), wrong_reaims=int((re.outcome == "wrong_reaim").sum()), wrong_share=w[0], wrong_lo=w[1], wrong_hi=w[2],
                         lookalike_n=len(lk), lookalike_reaims=len(lkre), lookalike_wrong=int((lkre.outcome == "wrong_reaim").sum()),
                         lookalike_wrong_share=wl[0], lookalike_wrong_hi=wl[2],
                         lookalike_stale_per_1000=M.per_1000(lk, lk.outcome == "stale"),
                         replans_avoided_per_1000_vs_C3=replans(base) - replans(d),
                         sec_saved_per_step_vs_C3=M.expected_seconds(base, 0.05) - M.expected_seconds(d, 0.05)))
    return pd.DataFrame(rows)


def break_even(d, c0):
    """Event rate p at which the condition's expected seconds equal C0's (both linear in p); NaN if none in [0, 1]."""
    f = lambda x, p: M.expected_seconds(x, p)
    a, b = f(d, 0.0), f(d, 1.0) - f(d, 0.0)
    a0, b0 = f(c0, 0.0), f(c0, 1.0) - f(c0, 0.0)
    if b0 == b:
        return np.nan
    p = (a - a0) / (b0 - b)
    return p if 0 <= p <= 1 else np.nan


def table4(df):
    t1 = df[df.tier == 1]
    rows = []
    for c in ORDER:
        d = t1[t1.cond == c]
        if not len(d):
            continue
        c0 = t1[(t1.cond == "C0") & t1.pair_id.isin(d.pair_id)]
        r = dict(cond=c, n=len(d), break_even_p_vs_C0=break_even(d, c0) if c != "C0" else np.nan)
        for p in M.P_VALUES:
            r[f"sec_p{p:g}"] = M.expected_seconds(d, p)
        for k in (1, 2, 5):
            r[f"sec_p0.05_stale{k}x"] = M.expected_seconds(d, 0.05, stale=k)
            r[f"sec_p0.05_wrong{k}x"] = M.expected_seconds(d, 0.05, wrong=k)
        rows.append(r)
    return pd.DataFrame(rows)


def parse_rates(df):
    out = []
    for c in ["C5", "C6", "C7", "C8", "C9"]:
        d = df[df.cond == c]
        if len(d):
            out.append(dict(cond=c, n=len(d), pairs_with_parse_failure=int((d.parse_fail.fillna(0) > 0).sum()),
                             missing_answers=int(d.missing.fillna(0).sum())))
    return pd.DataFrame(out)


# ---------- figures ----------

def _style():
    plt.rcParams.update({"font.size": 24, "font.family": "sans-serif", "axes.edgecolor": INK, "axes.labelcolor": INK,
                         "xtick.color": INK, "ytick.color": INK, "figure.facecolor": BG, "axes.facecolor": BG,
                         "axes.spines.top": False, "axes.spines.right": False, "axes.grid": False})


def fig_cost_ladder(df, split):
    _style()
    t1 = df[df.tier == 1]
    conds = ["C1", "C4", "C6", "C7", "C8", "C9"]
    p = 0.05
    parts = []
    for c in conds:
        d = t1[t1.cond == c]
        cost = M.costs(d)
        w = np.where(d.relevant, p / max(d.relevant.sum(), 1), (1 - p) / max((~d.relevant).sum(), 1))
        part = lambda m: float((cost[m] * w[m.values]).sum())
        parts.append(dict(cond=c, check=float(d.delta_s.mean()),
                          false_replans=part(d.outcome == "false_replan"), needed_replans=part(d.outcome == "replan"),
                          stale=part(d.outcome == "stale"), wrong=part(d.outcome == "wrong_reaim")))
    P = pd.DataFrame(parts)
    fig = plt.figure(figsize=(19.2, 10.8), dpi=100)
    ax = fig.add_axes([0.27, 0.14, 0.5, 0.72])
    segs = [("check", "Check time", INK), ("false_replans", "False re-plans", ACCENT), ("stale", "Stale actions", "#E8A07A"),
            ("wrong", "Wrong re-aims", "#7A2E0B"), ("needed_replans", "Needed re-plans", "#CFCFC8")]
    left = np.zeros(len(P))
    y = np.arange(len(P))[::-1]
    for k, lab, col in segs:
        ax.barh(y, P[k], left=left, color=col, label=lab, height=0.62)
        left += P[k].values
    for yi, tot in zip(y, left):
        ax.text(tot + 0.08, yi, f"{tot:.1f} s", va="center", fontsize=22, color=INK)
    ax.set_yticks(y, [LABEL[c] for c in P.cond])
    ax.set_xlabel("Seconds added per step at p = 0.05")
    ax.legend(frameon=False, loc="upper left", bbox_to_anchor=(1.0, 1.0), fontsize=20)
    fig.text(0.03, 0.92, "What each check adds per step on a moving page", fontsize=32, fontweight="bold", color=INK)
    fig.text(0.03, 0.03, f"Pilot data, Tier 1 {split} split. C8 on a stratified subset. C_plan 6.51 s, stale 2x, wrong 3x.",
             fontsize=18, color=MUTED)
    FIG.mkdir(exist_ok=True)
    fig.savefig(FIG / "fig_cost_ladder.png", facecolor=BG)
    plt.close(fig)
    return P


def fig_cost_by_motion(t1tab, split):
    _style()
    fig = plt.figure(figsize=(19.2, 10.8), dpi=100)
    ax = fig.add_axes([0.08, 0.14, 0.6, 0.72])
    conds = [c for c in ORDER if c not in ("oracle", "always_replan")]
    cmap = {"C4": ACCENT}
    for c in conds:
        d = t1tab[(t1tab.cond == c) & (t1tab.motion_bin != "all")].set_index("motion_bin").reindex(BINS)
        if d.sec_p05.isna().all():
            continue
        col = cmap.get(c, MUTED if c not in ("C0", "C1", "C8") else INK)
        ls = "-" if c in ("C0", "C1", "C4", "C8") else "--"
        ax.plot(BINS, d.sec_p05, ls, marker="o", color=col, lw=3 if c == "C4" else 2, ms=8)
        last = d.sec_p05.dropna()
        if c not in ("C3", "C5", "C6"):  # these sit on top of C4 at the right edge; named in the side note
            ax.text(len(BINS) - 1 + 0.08, last.iloc[-1], c if c != "C4" else "C4*", color=col, fontsize=18, va="center")
    ax.set_yscale("log")
    ax.set_xlabel("Measured motion (pixels changing within 200 ms)")
    ax.set_ylabel("Seconds added per step, p = 0.05 (log)")
    fig.text(0.08, 0.92, "Cost of each check as the page moves more", fontsize=32, fontweight="bold", color=INK)
    fig.text(0.78, 0.5, "\n".join(f"{c}: {LABEL[c][len(c) + 1:]}" for c in conds), fontsize=16, color=MUTED, va="center")
    n = t1tab[(t1tab.cond == "C4") & (t1tab.motion_bin != "all")].set_index("motion_bin").reindex(BINS).n
    fig.text(0.08, 0.03, f"Pilot data, Tier 1 {split} split. Pairs per bin: " + ", ".join(f"{b} {int(v)}" for b, v in n.items()) +
             ". C8 runs on a subset. *C3, C5 and C6 lie close to C4.", fontsize=18, color=MUTED)
    fig.savefig(FIG / "fig_cost_by_motion.png", facecolor=BG)
    plt.close(fig)


def tradeoff_c6(split="dev"):
    """C6 recovery against wrong re-aims as m_unique varies (other thresholds frozen). Dev only: the test split
    holds answers for the frozen rule's questions alone."""
    from anchored import check as A
    from harness.run_checks import Scorer, feature_table, load, summarize
    from harness.run_models import run_escalate
    from models.qwen_jobs import results
    fz2 = json.loads((RES / "frozen_w2.json").read_text())["C4"]
    fz3 = json.loads((RES / "frozen_w3.json").read_text())["C6"]
    recs = [r for r in load(split) if r["tier"] == 1]
    feats = feature_table(split, recs, fz2["mask_thr"], fz2["mask_dilate"])
    outs, sc = results(f"{split}_escalate"), Scorer(recs)
    rows = []
    for mu in [0.0, 0.01, 0.02, 0.03, 0.05, 0.075, 0.10, 0.15, 0.20, 0.30]:
        d = pd.DataFrame(run_escalate(recs, feats, {**A.DEFAULTS, **fz2, **fz3, "m_unique": mu}, "4b", outs, sc, "C6"))
        s = summarize(d)
        rows.append(dict(m_unique=mu, reaim_recovery=s["reaim_recovery"], wrong_share=s["wrong_share"],
                         wrong_reaims=s["wrong_reaims"], n_reaims=s["n_reaims"], missing=int(d.missing.sum())))
    out = pd.DataFrame(rows)
    out.to_csv(RES / f"tradeoff_c6_{split}.csv", index=False)
    return out


# ---------- leave one page out ----------

def lopo():
    """Re-tune C4 (Wave 2 rule, ext2 grid around the frozen point) and C6 (Wave 3 rule) on dev without one page,
    then score that page on test with the re-tuned and the frozen thresholds."""
    from anchored import check as A
    from harness.run_checks import Scorer, feature_table, load, objective, run_anchored
    from harness.run_models import GRID as G3, run_escalate
    from models.qwen_jobs import TAU_LOW_MIN, results
    fz2 = json.loads((RES / "frozen_w2.json").read_text())["C4"]
    fz3 = json.loads((RES / "frozen_w3.json").read_text())["C6"]
    g = pd.read_csv(RES / "tuning_w2_anchored_ext2.csv")
    g = g[g.cond == "C4"]
    keys = ["mask_thr", "mask_dilate", "tau_in", "tau_match", "m_unique", "tau_target", "b", "d"]
    grid = g[keys].drop_duplicates().to_dict("records")
    dev = [r for r in load("dev") if r["tier"] == 1]
    test = [r for r in load("test") if r["tier"] == 1]
    sdev, stest = Scorer(dev), Scorer(test)
    pages = sorted({r["page"] for r in dev})
    fdev = {k: feature_table("dev", dev, *k) for k in {(c["mask_thr"], c["mask_dilate"]) for c in grid}}
    ftest = {k: feature_table("test", test, *k) for k in {(c["mask_thr"], c["mask_dilate"]) for c in grid}}
    # C4: one dev run per config, objective per held-out page
    per = {p: (float("inf"), None) for p in pages}
    for c in grid:
        c = {k: (int(v) if k in ("mask_thr", "mask_dilate") else float(v)) for k, v in c.items()}
        d = pd.DataFrame(run_anchored(dev, fdev[(c["mask_thr"], c["mask_dilate"])], {**A.DEFAULTS, **c}, "reaim", sdev, "C4"))
        for p in pages:
            o = objective(d[d.page != p])
            if o < per[p][0]:
                per[p] = (o, c)
    rows = []
    for p in pages:
        tp = [r for r in test if r["page"] == p]
        for name, c in (("frozen", fz2), ("lopo", per[p][1])):
            d = pd.DataFrame(run_anchored(tp, ftest[(c["mask_thr"], c["mask_dilate"])] if (c["mask_thr"], c["mask_dilate"]) in ftest
                                          else feature_table("test", test, c["mask_thr"], c["mask_dilate"]), {**A.DEFAULTS, **c}, "reaim", stest, "C4"))
            rows.append(dict(cond="C4", held_out=p, thresholds=name, sec_p05=M.expected_seconds(d, 0.05),
                             false_alarm=float((d[~d.relevant].action == "replan").mean()), **{f"cfg_{k}": c[k] for k in keys}))
    # C6: escalation grid on dev minus page, then test page
    edev, etest = results("dev_escalate"), results("test_escalate")
    f2d, f2t = fdev.get((fz2["mask_thr"], fz2["mask_dilate"])) or feature_table("dev", dev, fz2["mask_thr"], fz2["mask_dilate"]), \
        ftest.get((fz2["mask_thr"], fz2["mask_dilate"])) or feature_table("test", test, fz2["mask_thr"], fz2["mask_dilate"])
    runs = {}
    for tl, cb in itertools.product(G3["tau_low"], G3["cover_band"]):
        cfg = {**A.DEFAULTS, **fz2, "tau_low": tl, "cover_band": cb, "cand_min": TAU_LOW_MIN}
        runs[(tl, cb)] = pd.DataFrame(run_escalate(dev, f2d, cfg, "4b", edev, sdev, "C6"))
    for p in pages:
        best = min(runs, key=lambda k: M.expected_seconds(runs[k][runs[k].page != p], 0.05))
        tp = [r for r in test if r["page"] == p]
        for name, (tl, cb) in (("frozen", (fz3["tau_low"], fz3["cover_band"])), ("lopo", best)):
            cfg = {**A.DEFAULTS, **fz2, "tau_low": tl, "cover_band": cb, "cand_min": TAU_LOW_MIN}
            d = pd.DataFrame(run_escalate(tp, f2t, cfg, "4b", etest, stest, "C6"))
            rows.append(dict(cond="C6", held_out=p, thresholds=name, sec_p05=M.expected_seconds(d, 0.05),
                             false_alarm=float((d[~d.relevant].action == "replan").mean()), cfg_tau_low=tl, cfg_cover_band=cb,
                             missing_answers=int(d.missing.sum())))
    out = pd.DataFrame(rows)
    out.to_csv(RES / "lopo_test.csv", index=False)
    print(out.to_string(index=False, float_format=lambda v: f"{v:.3f}"))


def main(split):
    out = RES / f"tables_{split}"
    out.mkdir(exist_ok=True)
    df = decisions(split)
    t1 = table1(df)
    t1.to_csv(out / "table1_q1.csv", index=False)
    table2(df).to_csv(out / "table2_q2.csv", index=False)
    t4 = table4(df)
    t4.to_csv(out / "table4_sensitivity.csv", index=False)
    parse_rates(df).to_csv(out / "parse_rates.csv", index=False)
    t0 = pd.DataFrame([dict(cond=c, false_alarm=float((d[~d.relevant].action == "replan").mean()), **row_q1(d))
                       for c in ORDER if len(d := df[(df.tier == 0) & (df.cond == c)])])
    t0.to_csv(out / "tier0.csv", index=False)
    q3 = RES / f"q3_{split}_summary.csv"
    if q3.exists():
        pd.read_csv(q3).to_csv(out / "table3_q3.csv", index=False)
    P = fig_cost_ladder(df, split)
    P.to_csv(out / "cost_ladder_parts.csv", index=False)
    fig_cost_by_motion(t1, split)
    print(t1[t1.motion_bin == "all"][["cond", "n", "false_replan_per_1000", "stale_per_1000", "stale_during_check_per_1000",
                                      "ms_median", "escalation_rate", "sec_p05", "sec_p05_lo", "sec_p05_hi", "usd_per_1000"]]
          .to_string(index=False, float_format=lambda v: f"{v:.3f}"))
    print(t4[["cond", "break_even_p_vs_C0", "sec_p0.01", "sec_p0.05", "sec_p0.2"]].to_string(index=False, float_format=lambda v: f"{v:.3f}"))


if __name__ == "__main__":
    lopo() if sys.argv[1] == "lopo" else main(sys.argv[1])
