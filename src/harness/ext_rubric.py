"""Extension Part B: the checker rubric (docs/PREREG_EXTENSION.md, B.1, B.3, B.4). Existing answers only.

  python -m harness.ext_rubric            # -> results/extension/tables/rubric_*.csv

Per question and tier, every ordered pair of checks (A cheaper by delta, B costlier): the escalation threshold
M* = [(dB - dA) + (1 - q)(fB - fA) C] / [q (rB - rA)] from dev rates on the pairs both were run on, validated on test:
E_X = d_X + q (1 - r_X) M + (1 - q) f_X C. B.4 picks cost-optimal thresholds for the scored checks.
"""
import itertools, json, time

import numpy as np
import pandas as pd

from harness.ext_inequality import EXT, LAT_FILE, TAB
from harness.full_checks import FROZEN, ROOT, load
from harness.full_results import CONTINUOUS, question_rows, thresholds

QS = (0.01, 0.02, 0.05, 0.10, 0.20)
MS = (10, 30, 60, 120, 300, 600, 1800)
CS = (1.24, 6.51)
GAP = 6.5
CHECKS = {
    "settled": ["pusv-published", "pusv-tuned", "pixel", "pusv+anchored", "qwen3-vl-2b", "qwen3-vl-4b", "smolvlm2-2.2b", "haiku-5.5", "opus-5.5"],
    "dialog": ["pixel", "pusv-tuned", "qwen3-vl-2b", "qwen3-vl-4b", "smolvlm2-2.2b", "haiku-5.5", "opus-5.5"],
    "worked": ["pixel", "qwen3-vl-2b", "qwen3-vl-4b", "smolvlm2-2.2b", "florence-2", "haiku-5.5", "opus-5.5"],
}
# provisional model latencies (s) until B.2's clean T4 medians exist: Qwen 2B on a T4, the rest on a shared A100
LAT = {"haiku-5.5": 1.276, "opus-5.5": 2.366, "qwen3-vl-2b": 1.683, "qwen3-vl-4b": 1.135, "smolvlm2-2.2b": 1.542, "florence-2": 6.847}
PIX_COND = {"pusv-published": "C1", "pusv-tuned": "C2", "pixel": "C4", "pusv+anchored": "C7"}


def pixel_worked_ms(n=200):
    """Laptop time of the pixel effect-region score on dev worked pairs (cached)."""
    p = TAB / "rubric_pixel_worked_ms.json"
    if p.exists():
        return json.loads(p.read_text())["median_s"]
    from harness.full_results import _pixel_worked
    fz = json.loads(FROZEN.read_text())
    rs = load("dev", "worked")[:n]
    ts = []
    for r in rs:
        t0 = time.perf_counter()
        _pixel_worked(dict(r, action_box=r["effect_box"]), fz["mask"])
        ts.append(time.perf_counter() - t0)
    out = dict(n=len(ts), median_s=float(np.median(ts)), p90_s=float(np.percentile(ts, 90)), note="laptop, compute only (frames already taken)")
    p.write_text(json.dumps(out, indent=2))
    return out["median_s"]


def deltas():
    lat = dict(LAT)
    src = "provisional (full study)"
    if LAT_FILE.exists():
        b2 = pd.read_csv(LAT_FILE)
        for _, r in b2.iterrows():
            lat[(r.check, r.job_kind)] = r.median_ms / 1000
        src = "b2"
    pix = pd.read_csv(ROOT / "results/full/raw/pixel_dev_decisions.csv")
    med = pix.groupby("cond").delta_s.median().to_dict()
    pw = pixel_worked_ms()

    def d(q, c):
        if c in PIX_COND:
            return med[PIX_COND[c]] if q != "worked" else pw
        if q == "worked" and c == "pixel":
            return pw
        kind = "worked" if q == "worked" else "action"
        return lat.get((c, kind), lat[c])
    return d, src


def decide(rows, th):
    """Native decision: pixel settled/dialog = logged decision; scored checks = dev threshold at <= 2% FA; yes/no = 0.5."""
    out = []
    for (q, c, t), g in rows.groupby(["question", "check", "tier"]):
        if "decision" in g and g.decision.notna().all() and q != "worked":
            dec = g.decision.astype(bool)
        elif c in CONTINUOUS:
            dec = g.score >= th.get((q, c, t), np.inf)
        else:
            dec = g.score >= 0.5
        out.append(g.assign(dec=dec.values))
    return pd.concat(out)


def rf(g):
    y = g.y.values.astype(bool); d = g.dec.values.astype(bool)
    return (float(d[y].mean()) if y.any() else np.nan, float(d[~y].mean()) if (~y).any() else np.nan, int(y.sum()))


def mstar(dA, dB, rA, rB, fA, fB, q, C):
    if rB <= rA:
        return np.inf  # never escalate
    return ((dB - dA) + (1 - q) * (fB - fA) * C) / (q * (rB - rA))


def pick_b(dA, dB, rA, rB, fA, fB, q, M, C):
    return q * M * (rB - rA) > (dB - dA) + (1 - q) * (fB - fA) * C


def E(d, r, f, q, M, C):
    return d + q * (1 - r) * M + (1 - q) * f * C


def pairs_table(dev, test, dfun):
    thr, val = [], []
    for q, checks in CHECKS.items():
        for t in (0, 1, 2):
            dv = dev[(dev.question == q) & (dev.tier == t)]
            ts = test[(test.question == q) & (test.tier == t)]
            avail = [c for c in checks if (dv.check == c).any() and (ts.check == c).any()]
            order = sorted(avail, key=lambda c: (dfun(q, c), c))
            for A, B in itertools.combinations(order, 2):
                ia = set(dv[dv.check == A].pair_id) & set(dv[dv.check == B].pair_id)
                it = set(ts[ts.check == A].pair_id) & set(ts[ts.check == B].pair_id)
                ga, gb = dv[(dv.check == A) & dv.pair_id.isin(ia)], dv[(dv.check == B) & dv.pair_id.isin(ia)]
                ta, tb = ts[(ts.check == A) & ts.pair_id.isin(it)], ts[(ts.check == B) & ts.pair_id.isin(it)]
                (rA, fA, pos), (rB, fB, _) = rf(ga), rf(gb)
                (rAt, fAt, post), (rBt, fBt, _) = rf(ta), rf(tb)
                dA, dB = dfun(q, A), dfun(q, B)
                base = dict(question=q, tier=t, A=A, B=B, dA=dA, dB=dB, n_dev=len(ia), pos_dev=pos, n_test=len(it), pos_test=post,
                            rA=rA, rB=rB, fA=fA, fB=fB, rA_test=rAt, rB_test=rBt, fA_test=fAt, fB_test=fBt)
                if pos < 10 or not np.isfinite(rA + rB + fA + fB) or not np.isfinite(rAt + rBt + fAt + fBt):
                    thr.append(dict(base, note="left out: fewer than 10 dev positives or missing rates"))
                    continue
                for qq in QS:
                    for C in CS:
                        ms = mstar(dA, dB, rA, rB, fA, fB, qq, C)
                        mt = mstar(dA, dB, rAt, rBt, fAt, fBt, qq, C)
                        row = dict(base, q=qq, C=C, M_star=ms, M_star_test=mt,
                                   verdict="never escalate" if not np.isfinite(ms) else ("always escalate" if ms <= 0 else "threshold"))
                        if q in ("settled", "dialog"):
                            ea, eb = max(0, 1 - dA / GAP), max(0, 1 - dB / GAP)
                            row["M_star_reff"] = mstar(dA, dB, rA * ea, rB * eb, fA, fB, qq, C)
                        thr.append(row)
                        for M in MS:
                            choose_b = pick_b(dA, dB, rA, rB, fA, fB, qq, M, C)
                            ea_t, eb_t = E(dA, rAt, fAt, qq, M, C), E(dB, rBt, fBt, qq, M, C)
                            cheaper_b = eb_t < ea_t
                            excluded = bool(rB > rA and np.isfinite(ms) and ms > 0 and 0.8 * ms <= M <= 1.2 * ms)
                            val.append(dict(question=q, tier=t, A=A, B=B, q=qq, M=M, C=C, M_star=ms, rule_picks="B" if choose_b else "A",
                                            test_cheaper="B" if cheaper_b else "A", tie=bool(abs(eb_t - ea_t) < 1e-12),
                                            agree=bool(choose_b == cheaper_b), excluded=excluded, E_A_test=ea_t, E_B_test=eb_t))
    return pd.DataFrame(thr), pd.DataFrame(val)


def cost_optimal(dev, test, dfun):
    """B.4: for scored checks, threshold minimizing dev E at each (q, M, C); evaluated on test (supplementary)."""
    rows = []
    for q, c in (("settled", "pixel"), ("dialog", "pixel"), ("worked", "pixel"), ("worked", "florence-2")):
        for t in (0, 1, 2):
            dv = dev[(dev.question == q) & (dev.check == c) & (dev.tier == t)]
            ts = test[(test.question == q) & (test.check == c) & (test.tier == t)]
            if not len(dv) or not len(ts):
                continue
            cands = np.unique(np.concatenate([dv.score.values, [-np.inf, np.inf]]))
            yd, sd = dv.y.values.astype(bool), dv.score.values
            yt, st = ts.y.values.astype(bool), ts.score.values
            R = np.array([(sd[yd] >= th).mean() for th in cands]); F = np.array([(sd[~yd] >= th).mean() for th in cands])
            d = dfun(q, c)
            for qq in QS:
                for M in MS:
                    for C in CS:
                        e = E(d, R, F, qq, M, C)
                        th = cands[int(np.argmin(e))]
                        rt, ft = float((st[yt] >= th).mean()), float((st[~yt] >= th).mean())
                        rows.append(dict(question=q, check=c, tier=t, q=qq, M=M, C=C, theta=th, r_dev=R[np.argmin(e)], f_dev=F[np.argmin(e)],
                                         E_dev=float(e.min()), r_test=rt, f_test=ft, E_test=E(d, rt, ft, qq, M, C), delta=d))
    return pd.DataFrame(rows)


def rubric(dev, test, co, dfun):
    """Per question, tier, (q, M) at each C: the checker with the lowest dev E (each on its own pairs) and whether it
    is lowest on test. Scored checks enter at their cost-optimal threshold."""
    rows = []
    for q, checks in CHECKS.items():
        for t in (0, 1, 2):
            for qq in QS:
                for M in MS:
                    for C in CS:
                        ed, et = {}, {}
                        for c in checks:
                            g = dev[(dev.question == q) & (dev.check == c) & (dev.tier == t)]
                            h = test[(test.question == q) & (test.check == c) & (test.tier == t)]
                            if not len(g) or not len(h):
                                continue
                            sel = co[(co.question == q) & (co.check == c) & (co.tier == t) & (co.q == qq) & (co.M == M) & (co.C == C)]
                            if q in ("settled", "dialog") and c == "pixel" and len(sel) or (q == "worked" and c in ("pixel", "florence-2") and len(sel)):
                                ed[c], et[c] = float(sel.E_dev.iloc[0]), float(sel.E_test.iloc[0])
                            else:
                                (r, f, _), (r2, f2, _) = rf(g), rf(h)
                                ed[c], et[c] = E(dfun(q, c), r, f, qq, M, C), E(dfun(q, c), r2, f2, qq, M, C)
                        if not ed:
                            continue
                        bd, bt = min(ed, key=ed.get), min(et, key=et.get)
                        rows.append(dict(question=q, tier=t, q=qq, M=M, C=C, cheapest_dev=bd, cheapest_test=bt, agree=bd == bt,
                                         E_dev=ed[bd], E_test_of_pick=et[bd], E_test_best=et[bt]))
    return pd.DataFrame(rows)


def main():
    TAB.mkdir(parents=True, exist_ok=True)
    dfun, src = deltas()
    dev, test = question_rows("dev"), question_rows("test")
    th = thresholds(dev)
    dev, test = decide(dev, th), decide(test, th)
    thr, val = pairs_table(dev, test, dfun)
    thr.to_csv(TAB / "rubric_mstar.csv", index=False)
    val.to_csv(TAB / "rubric_validation.csv", index=False)
    v = val[~val.excluded]
    summ = pd.DataFrame([dict(scope="all questions", cells=len(v), excluded=int(val.excluded.sum()), agreement=float(v.agree.mean()))] +
                        [dict(scope=q, cells=len(g), excluded=int(val[val.question == q].excluded.sum()), agreement=float(g.agree.mean()))
                         for q, g in v.groupby("question")])
    summ["E2_holds"] = summ.agreement >= 0.9
    summ["latency_source"] = src
    summ.to_csv(TAB / "rubric_summary.csv", index=False)
    co = cost_optimal(dev, test, dfun)
    co.to_csv(TAB / "rubric_cost_optimal.csv", index=False)
    rb = rubric(dev, test, co, dfun)
    rb.to_csv(TAB / "rubric_table.csv", index=False)
    print(summ.round(3).to_string(index=False))
    print("rubric agreement (dev pick = test cheapest):", round(rb.agree.mean(), 3))
    t1 = rb[(rb.tier == 1) & (rb.C == 6.51)]
    for q in CHECKS:
        print(q); print(t1[t1.question == q].pivot(index="q", columns="M", values="cheapest_dev").to_string())


if __name__ == "__main__":
    main()
