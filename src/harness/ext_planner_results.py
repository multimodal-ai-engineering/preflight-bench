"""Extension Part D analysis (docs/PREREG_EXTENSION.md, D.1 and D.2).

  python -m harness.ext_planner_results     # -> results/extension/tables/d1_*.csv, d2_*.csv
"""
import difflib, json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import binomtest

from harness.metrics import wilson
from live.ext_planner import parse_reground

ROOT = Path(__file__).resolve().parents[2]
LIVE = ROOT / "results/extension/live"
TAB = ROOT / "results/extension/tables"
PRIV = ROOT / "private/ext_d2"
GPU = ROOT / "results/extension/gpu_out"
NAMES = {"a": "motion on, last three", "b": "motion frozen, last three", "c": "motion on, latest only"}


def inbox(pt, b):
    return bool(b) and b[0] <= pt[0] < b[0] + b[2] and b[1] <= pt[1] < b[1] + b[3]


def classify(r, cond):
    x = r[cond]
    pt = x.get("click")
    if not pt:
        return "other (no click)"
    info = x.get("info200") or {}
    cur = x.get("target_box200")
    prev = r["prev_boxes"]["B" if cond == "b" else "A"]
    if any(inbox(pt, b) for b in prev if b) and not inbox(pt, cur):
        return "earlier screenshot"
    if info.get("same_container") or any(v != r["target_id"] for v in info.get("virt_hits") or []):
        return "neighbour"
    ht, tt = (info.get("hit_text") or "").strip(), (info.get("target_text") or "").strip()
    if ht and tt and ((info.get("hit_tag") == info.get("target_tag") and ht == tt) or difflib.SequenceMatcher(None, ht, tt).ratio() >= 0.8):
        return "lookalike"
    if info.get("root") or info.get("empty"):
        return "no element"
    return "other"


def mcnemar(x, y):
    """Exact McNemar on paired misses: x, y boolean arrays (True = miss)."""
    n01, n10 = int((~x & y).sum()), int((x & ~y).sum())
    p = binomtest(n10, n01 + n10, 0.5).pvalue if n01 + n10 else 1.0
    return n10, n01, float(p)


def d1():
    rs = [json.loads(l) for l in (LIVE / "d1.jsonl").read_text().splitlines() if l.strip()]
    skipped = sum(1 for r in rs if "skipped" in r)
    rs = [r for r in rs if "skipped" not in r]
    miss = {c: np.array([r[c]["miss"] for r in rs]) for c in "abc"}
    miss0 = {c: np.array([not r[c].get("hit0", False) for r in rs]) for c in "abc"}
    rows = []
    for c in "abc":
        k, n = int(miss[c].sum()), len(rs)
        m, lo, hi = wilson(k, n)
        ms = np.array([r[c]["plan_ms"] for r in rs])
        rows.append(dict(cond=c, name=NAMES[c], steps=n, misses=k, miss_rate=m, lo=lo, hi=hi, miss_rate_0ms=float(miss0[c].mean()),
                         plan_ms_median=float(np.median(ms)), plan_ms_p90=float(np.percentile(ms, 90)), skipped_steps=skipped))
    rates = pd.DataFrame(rows)
    tests = []
    for other in "bc":
        n10, n01, p = mcnemar(miss["a"], miss[other])  # n10: a missed, other hit
        tests.append(dict(comparison=f"a vs {other}", a_only_miss=n10, other_only_miss=n01, p=p,
                          predicted_direction=bool(n10 > n01)))
    t = pd.DataFrame(tests).sort_values("p").reset_index(drop=True)
    t["p_holm"] = [min(1.0, max((2 - j) * t.p[j] for j in range(i + 1))) for i in range(len(t))]
    t["significant"] = t.p_holm < 0.05
    t["holds"] = t.significant & t.predicted_direction
    cls = []
    for r in rs:
        for c in "abc":
            if r[c]["miss"]:
                cls.append(dict(cond=c, kind=r["kind"], cls=classify(r, c), episode=r["episode"], step=r["step"], task=r["task"]))
    cls = pd.DataFrame(cls)
    br = cls.groupby(["cond", "cls"]).size().unstack(fill_value=0) if len(cls) else pd.DataFrame()
    by_kind = pd.DataFrame([dict(kind=k, cond=c, steps=len(g), miss_rate=float(np.mean([r[c]["miss"] for r in g])))
                            for k in sorted({r["kind"] for r in rs}) for c in "abc" for g in [[r for r in rs if r["kind"] == k]]])
    return rates, t, cls, br, by_kind


def qwen_answers():
    out = {}
    for p in sorted(GPU.glob("*.jsonl")) if GPU.exists() else []:
        for l in p.read_text().splitlines():
            if l.strip():
                j = json.loads(l)
                if j.get("kind") == "reground" and not j.get("error"):
                    out[j["job_id"].split("|")[3]] = j
    return out


def parse_qwen(txt, scale):
    """Qwen3-VL answered in its native 0-1000 relative coordinates (y up to 978 on a 640-px-high image), not the
    requested pixels. scale "rel1000" (primary, chosen after seeing the outputs; a deviation) or "pixels" (as asked)."""
    kd, pt = parse_reground(txt)  # pt is in 1280x800 if the box was 1024x640 pixels
    if kd != "box":
        return kd, None
    if scale == "rel1000":
        pt = [pt[0] / 1.25 * 1280 / 1000, pt[1] / 1.25 * 800 / 1000]
    return kd, pt


def score_grid(pt, stem):
    g = json.loads((PRIV / f"{stem}_grid.json").read_text())
    if any(abs(x - pt[0]) <= 2 and abs(y - pt[1]) <= 2 for x, y in g["hit_mask"] or []):
        return dict(correct=True, other_element=False)
    gy, gx = int(pt[1] // 8), int(pt[0] // 8)
    v = int(g["grid"][gy][gx]) if 0 <= gy < len(g["grid"]) and 0 <= gx < len(g["grid"][0]) else 0
    return dict(correct=v == 2, other_element=v == 1)


def outcome(rec, gone):
    if rec["kind"] in ("gone", "none") or not rec.get("click"):
        if rec["kind"] == "none":
            return "no answer"
        return "gone-correct" if gone else "gone-wrong"
    return "correct" if rec["score"]["correct"] else "wrong"


def d2(c_meas):
    rs = [json.loads(l) for l in (LIVE / "d2.jsonl").read_text().splitlines() if l.strip()]
    qa = qwen_answers()
    fired = [r for r in rs if "recoveries" in r]
    recs = []
    for r in fired:
        rv = dict(r["recoveries"])
        q = rv.pop("qwen_job")
        if q["stem"] in qa:
            for scale, name in (("rel1000", "reground_qwen4b"), ("pixels", "reground_qwen4b_as_pixels")):
                kd, pt = parse_qwen(qa[q["stem"]]["raw"], scale)
                inside = pt is not None and 0 <= pt[0] < 1280 and 0 <= pt[1] < 800
                rv[name] = dict(kind=kd, click=pt if inside or pt is None else pt, ms=qa[q["stem"]]["ms"], usd=0.0,
                                score=(score_grid(pt, q["stem"]) if inside else dict(correct=False, other_element=False)) if pt else None)
        for name, x in rv.items():
            o = outcome(x, r["gone"])
            recs.append(dict(episode=r["episode"], step=r["step"], kind_page=r["kind"], recovery=name, gone=r["gone"], outcome=o,
                             other_element=bool(o == "wrong" and x["score"] and x["score"]["other_element"]), ms=x["ms"], usd=x.get("usd", 0.0)))
    d = pd.DataFrame(recs)
    rows = []
    for name, g in d.groupby("recovery"):
        n = len(g)
        row = dict(recovery=name, fired_steps=n, ms_median=float(g.ms.median()), ms_p90=float(g.ms.quantile(0.9)),
                   usd_per_call=float(g.usd.mean()))
        for o in ("correct", "wrong", "gone-correct", "gone-wrong", "no answer"):
            k = int((g.outcome == o).sum())
            s, lo, hi = wilson(k, n)
            row.update({o: k, f"{o}_rate": s, f"{o}_lo": lo, f"{o}_hi": hi})
        row["wrong_on_other_element"] = int(g.other_element.sum())
        rows.append(row)
    tab = pd.DataFrame(rows)
    rp = tab[tab.recovery == "replan"].iloc[0]
    hk = tab[tab.recovery == "reground_haiku"].iloc[0]
    e5 = dict(wrong=int(hk.wrong), fired=int(hk.fired_steps), wrong_rate=hk.wrong_rate, wrong_hi=hk.wrong_hi,
              reground_ms_median=hk.ms_median, replan_ms_median=rp.ms_median, latency_ratio=hk.ms_median / rp.ms_median)
    e5["holds"] = bool(e5["wrong_hi"] <= 0.03 and e5["latency_ratio"] <= 0.5)
    # time per step with executed recoveries (C = the planner's measured median planning time)
    steps = [r for r in rs if r.get("outcome") != "parse_fail"]
    base = np.mean([r["plan_ms"] / 1000 + 6.5 + r.get("check_ms", 0) / 1000 for r in steps])
    stale = np.mean([r.get("outcome") == "stale" for r in steps])
    tps = [dict(recovery="re-plan counted, not executed (full study accounting)", s_per_step=base + len(fired) / len(steps) * c_meas)]
    for name, g in d.groupby("recovery"):
        extra = (g.ms / 1000 + np.where(g.outcome == "wrong", 3 * c_meas, 0) + np.where(g.outcome.isin(["gone-correct", "gone-wrong", "no answer"]), c_meas, 0)).sum()
        tps.append(dict(recovery=name, s_per_step=base + extra / len(steps)))
    tps = pd.DataFrame(tps)
    tps["steps"], tps["fired"], tps["c_meas"], tps["stale_per_step"] = len(steps), len(fired), c_meas, stale
    oc = pd.Series([r.get("outcome") for r in rs]).value_counts().rename_axis("outcome").reset_index(name="steps")
    return tab, pd.DataFrame([e5]), tps, oc, d


def main():
    TAB.mkdir(parents=True, exist_ok=True)
    c_meas = json.loads((TAB / "ineq_inputs.json").read_text())["c_meas"]
    if (LIVE / "d1.jsonl").exists():
        rates, t, cls, br, bk = d1()
        rates.to_csv(TAB / "d1_rates.csv", index=False); t.to_csv(TAB / "d1_e4.csv", index=False)
        cls.to_csv(TAB / "d1_miss_classes_all.csv", index=False); br.to_csv(TAB / "d1_miss_breakdown.csv"); bk.to_csv(TAB / "d1_by_kind.csv", index=False)
        print(rates.round(3).to_string(index=False)); print(t.round(4).to_string(index=False)); print(br.to_string()); print(bk.round(3).to_string(index=False))
    if (LIVE / "d2.jsonl").exists():
        tab, e5, tps, oc, _ = d2(c_meas)
        tab.to_csv(TAB / "d2_recoveries.csv", index=False); e5.to_csv(TAB / "d2_e5.csv", index=False)
        # supplementary: split by whether the target was still hittable when the recovery was asked
        split = _.groupby(["recovery", "gone"]).outcome.value_counts().unstack(fill_value=0).reset_index()
        split.to_csv(TAB / "d2_recoveries_by_target.csv", index=False); print(split.to_string(index=False))
        tps.to_csv(TAB / "d2_time_per_step.csv", index=False); oc.to_csv(TAB / "d2_outcomes.csv", index=False)
        print(tab.round(3).to_string(index=False)); print(e5.round(3).to_string(index=False)); print(tps.round(3).to_string(index=False)); print(oc.to_string(index=False))


if __name__ == "__main__":
    main()
