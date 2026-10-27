"""Extension Part A: the preflight inequality, validated on the full study's replay (docs/PREREG_EXTENSION.md, A.1-A.5).
Existing data only; no API, no GPU. Every output is labelled extension.

  python -m harness.ext_inequality        # -> results/extension/tables/ineq_*.csv, budgets, h2 supplementary

Predicted p* from dev rates (first order: r, f, delta; second order: exposure during the check and re-aims at the
preregistered costs); observed p* from the test replay with costs generalized to stale k*C, re-plan C, wrong re-aim 3*C.
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd

from harness import metrics as M
from harness.full_checks import ROOT, load
from harness.full_results import question_rows, replay_table

EXT = ROOT / "results/extension"
TAB = EXT / "tables"
GAP = 6.5  # benchmark gap (s)
WRONG = 3.0
KS = (2, 3, 5, 10, 20)
LOOP = ROOT / "results/full/live/loop.jsonl"
# measured median latencies (s); Qwen 4B is replaced by B.2's clean T4 median once it exists
LAT = {"opus-5.5": 2.366, "haiku-5.5": 1.276, "qwen3-vl-4b": 1.135}
LAT_FILE = EXT / "tables/b2_latency.csv"
MODEL_CHECKS = ("opus-5.5", "haiku-5.5", "qwen3-vl-4b")


def latencies():
    lat = dict(LAT)
    if LAT_FILE.exists():  # clean T4 numbers (B.2) replace the provisional shared-A100 ones
        b2 = pd.read_csv(LAT_FILE)
        for _, r in b2[b2.job_kind == "action"].iterrows():
            lat[r.check] = r.median_ms / 1000
    return lat


def plan_median():
    d = pd.read_json(LOOP, lines=True)
    return float(d.plan_ms.median() / 1000)


def model_decisions(split, lat):
    """Models alone as `settled` checkers: re-plan when the answer is "moved" (parse failure = re-plan, the native
    decision score >= 0.5), scored at action time with the full study's rule."""
    q = question_rows(split)
    q = q[(q.question == "settled") & q.check.isin(MODEL_CHECKS)]
    recs = {r["pair_id"]: r for r in load(split)}
    rows = []
    for _, x in q.iterrows():
        r = recs[x.pair_id]
        dec = dict(action="replan" if x.score >= 0.5 else "go", ms=lat[x.check] * 1000)
        o = M.score(dec, r)
        rows.append(dict(o, cond=x.check, tier=r["tier"]))
    return pd.DataFrame(rows)


def decisions(split, lat):
    cache = EXT / f"cache/replay_{split}.pkl"  # pixel and escalation decisions do not depend on model latencies
    if cache.exists():
        df = pd.read_pickle(cache)
    else:
        _, df = replay_table(split)
        cache.parent.mkdir(parents=True, exist_ok=True)
        df.to_pickle(cache)
    df = df[df.cond.isin(["C0", "C1", "C2", "C4", "C7", "C4r", "C5r", "C6r"])]
    return pd.concat([df, model_decisions(split, lat)], ignore_index=True)


def rates(d):
    """Dev inputs: r, f, delta (median), and the outcome shares used by the second-order form."""
    rel, un = d[d.relevant], d[~d.relevant]
    n1, n0 = max(len(rel), 1), max(len(un), 1)
    s_go = float((rel.action == "go").mean()) if len(rel) else np.nan
    s_rp = float((rel.action == "replan").sum() / n1)
    s_ok = float(((rel.action == "reaim") & (rel.outcome == "recovered")).sum() / n1)
    s_wr = float(((rel.action == "reaim") & (rel.outcome == "wrong_reaim")).sum() / n1)
    f_rp = float((un.action == "replan").sum() / n0)
    f_wr = float(((un.action == "reaim") & (un.outcome == "wrong_reaim")).sum() / n0)
    h = float(((un.action == "go") & (un.outcome == "stale")).sum() / n0)  # unchanged at t0, stale by action time
    return dict(n=len(d), positives=len(rel), r=1 - s_go, h=h, f=float((un.action != "go").mean()) if len(un) else np.nan,
                delta=float(d.delta_s.median()), s_go=s_go, s_rp=s_rp, s_ok=s_ok, s_wr=s_wr, f_rp=f_rp, f_wr=f_wr)


def p_first(x, C, k):
    tau = x["delta"] / C
    return (tau + x["f"]) / (x["r"] * (k - 1) + x["f"])


def p_second(x, C, k, gap=GAP):
    tau = x["delta"] / C
    e = max(0.0, 1 - x["delta"] / gap)
    rp, ok, wr = x["s_rp"] * e, x["s_ok"] * e, x["s_wr"] * e
    go = 1 - rp - ok - wr
    m1 = go * k + rp + WRONG * wr
    phi = x["f_rp"] + WRONG * x["f_wr"]
    den = k - m1 + phi
    return (tau + phi) / den if den > 0 else np.inf


def p_exposure(x, C, k):
    """Exploratory (not preregistered): first order plus the exposure the replay actually charges, on the unchanged
    branch: a share h of unchanged steps (dev) goes stale while the check runs and costs k*C."""
    tau = x["delta"] / C
    hk = x["h"] * k
    return (tau + x["f"] + hk) / (x["r"] * (k - 1) + x["f"] + hk)


def cost(d, C, k):
    c = pd.Series(0.0, index=d.index)
    c[d.outcome == "stale"] = k * C
    c[d.outcome == "wrong_reaim"] = WRONG * C
    c[d.outcome.isin(["replan", "false_replan"])] = C
    return c


def line(d, C, k):
    """E(p) = a + b*p (expected seconds per step)."""
    c = cost(d, C, k)
    m0 = c[~d.relevant].mean() if (~d.relevant).any() else 0.0
    m1 = c[d.relevant].mean() if d.relevant.any() else 0.0
    a = d.delta_s.mean() + m0
    return a, m1 - m0


def p_observed(d, c0, C, k):
    a, b = line(d, C, k)
    a0, b0 = line(c0, C, k)
    if b0 > b:
        return (a - a0) / (b0 - b)
    return 0.0 if a < a0 else np.inf


clip = lambda v: float(min(max(v, 0.0), 1.0)) if np.isfinite(v) else 1.0


def validate(dev, test, cs):
    rows = []
    for (c, t), dd in dev[dev.cond != "C0"].groupby(["cond", "tier"]):
        tt = test[(test.cond == c) & (test.tier == t)]
        if not len(tt) or not dd.relevant.any():
            continue
        x = rates(dd)
        xt = rates(tt)
        c0 = test[(test.cond == "C0") & (test.tier == t) & test.pair_id.isin(tt.pair_id)]
        for C in cs:
            for k in KS:
                pf, ps, po = p_first(x, C, k), p_second(x, C, k), p_observed(tt, c0, C, k)
                px = p_exposure(x, C, k)
                rows.append(dict(check=c, tier=t, C=C, k=k, r_dev=x["r"], f_dev=x["f"], delta_dev=x["delta"], n_dev=x["n"],
                                 pos_dev=x["positives"], r_test=xt["r"], f_test=xt["f"], n_test=xt["n"],
                                 h_dev=x["h"], p_first=pf, p_second=ps, p_exposure_exploratory=px, p_obs=po,
                                 err_exposure_exploratory=abs(clip(px) - clip(po)), err_first=abs(clip(pf) - clip(po)), err_second=abs(clip(ps) - clip(po)),
                                 obs_interior=bool(np.isfinite(po) and 0 < po < 1)))
    return pd.DataFrame(rows)


def summarize(v):
    out = []
    for name, g in (("all cells", v), ("observed p* in (0, 1)", v[v.obs_interior])):
        out.append(dict(subset=name, cells=len(g), first_within_003=float((g.err_first <= 0.03).mean()),
                        second_within_002=float((g.err_second <= 0.02).mean()),
                        exploratory_exposure_within_003=float((g.err_exposure_exploratory <= 0.03).mean()),
                        exploratory_exposure_within_002=float((g.err_exposure_exploratory <= 0.02).mean()),
                        first_median=g.err_first.median(), first_p90=g.err_first.quantile(0.9), first_max=g.err_first.max(),
                        second_median=g.err_second.median(), second_p90=g.err_second.quantile(0.9), second_max=g.err_second.max()))
    s = pd.DataFrame(out)
    s["E1a_holds"] = s.first_within_003 >= 0.8
    s["E1b_holds"] = s.second_within_002 >= 0.8
    return s


def budgets(test):
    rows = []
    for c in ("C4", "opus-5.5"):
        x = rates(test[(test.cond == c) & (test.tier == 1)])
        for C in (1.24, 6.51, 20.0):
            for k in (2, 5, 10, 20):
                for p in (0.01, 0.02, 0.05, 0.1, 0.2, 0.5):
                    tau = x["delta"] / C
                    rows.append(dict(check=c, C=C, k=k, p=p, r=x["r"], f=x["f"], delta=x["delta"],
                                     f_max=(p * x["r"] * (k - 1) - tau) / (1 - p),
                                     delta_max=C * (p * x["r"] * (k - 1) - (1 - p) * x["f"]),
                                     pays=bool(x["f"] <= (p * x["r"] * (k - 1) - tau) / (1 - p))))
    return pd.DataFrame(rows)


def h2_supplementary(c_meas, k=2):
    d = pd.read_json(LOOP, lines=True)
    rows = []
    for g_s, gg in d.groupby("gap_s"):
        base = gg[gg.cond == "none"]
        step_s = base.plan_ms.mean() / 1000 + g_s
        net = {}
        for cond, x in gg.groupby("cond"):
            hit = x[~x.outcome.isin(["planner_miss", "parse_fail"])]
            n = max(len(x), 1)
            replans = float((hit.action == "replan").sum() / n)
            stale = float((x.outcome == "stale").sum() / n)
            check = x.check_ms.fillna(0).mean() / 1000
            net[cond] = check + replans * c_meas + stale * k * c_meas
            rows.append(dict(gap_s=g_s, cond=cond, steps=len(x), replans_per_step=replans, stale_per_step=stale, check_s=check,
                             added_time_at_c_meas=(check + replans * c_meas) / step_s, net_s_per_step=net[cond]))
        for r in rows:
            if r["gap_s"] == g_s:
                r["net_vs_none_s"] = r["net_s_per_step"] - net.get("none", np.nan)
                r["net_vs_none_share_of_step"] = r["net_vs_none_s"] / step_s
    return pd.DataFrame(rows)


def main():
    TAB.mkdir(parents=True, exist_ok=True)
    lat = latencies()
    c_meas = plan_median()
    cs = (round(c_meas, 3), 3.0, 6.51, 12.0, 20.0)
    dev, test = decisions("dev", lat), decisions("test", lat)
    v = validate(dev, test, cs)
    v.to_csv(TAB / "ineq_validation.csv", index=False)
    s = summarize(v)
    s.to_csv(TAB / "ineq_summary.csv", index=False)
    per = v.groupby("check").agg(cells=("err_first", "size"), first_within=("err_first", lambda e: (e <= 0.03).mean()),
                                 second_within=("err_second", lambda e: (e <= 0.02).mean()),
                                 exploratory_exposure_within_003=("err_exposure_exploratory", lambda e: (e <= 0.03).mean())).reset_index()
    per.to_csv(TAB / "ineq_by_check.csv", index=False)
    budgets(test).to_csv(TAB / "ineq_budgets.csv", index=False)
    h2s = h2_supplementary(c_meas)
    h2s.to_csv(TAB / "h2_supplementary.csv", index=False)
    rt = pd.DataFrame([dict(check=c, tier=t, **rates(g)) for (c, t), g in test.groupby(["cond", "tier"]) if c != "C0"])
    rt.to_csv(TAB / "ineq_test_rates.csv", index=False)
    json.dump(dict(c_meas=c_meas, latencies=lat, latency_source="b2" if LAT_FILE.exists() else "provisional (full study)"),
              open(TAB / "ineq_inputs.json", "w"), indent=2)
    print("C_meas", c_meas, "latencies", lat)
    print(s.round(3).to_string(index=False))
    print(per.round(3).to_string(index=False))
    print(h2s.round(3).to_string(index=False))


if __name__ == "__main__":
    main()
