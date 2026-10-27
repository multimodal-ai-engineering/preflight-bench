"""Full study analysis: question table, H1-H3, replay tables, cost model. Reads logged answers only.

  python -m harness.full_results escalate_tune      # C5/C6 on dev (Tier 1) under the 1% re-find cap -> frozen_full.json
  python -m harness.full_results all               # tables -> results/full/tables/, prints headlines

Answer sources: results/full/raw/pixel_{split}_decisions.csv (harness/full_checks.py), results/full/gpu_out/full.jsonl
(colab/vlm_runner.py), results/full/hosted/{split}_{model}_{kind}.jsonl (models/batch_full.py), results/full/live/loop.jsonl.
"""
import difflib, itertools, json, re, sys
from pathlib import Path

import numpy as np
import pandas as pd

from anchored import check as A
from harness import metrics as M
from harness.full_checks import FA, FROZEN, ROOT, Scorer, features, load, objective, threshold
from models.common import parse_json

RES = ROOT / "results/full"
TAB = RES / "tables"
SMALL = ["pixel", "qwen3-vl-2b", "qwen3-vl-4b", "smolvlm2-2.2b", "florence-2"]
MODEL_NAMES = {"Qwen/Qwen3-VL-2B-Instruct": "qwen3-vl-2b", "Qwen/Qwen3-VL-4B-Instruct": "qwen3-vl-4b",
               "HuggingFaceTB/SmolVLM2-2.2B-Instruct": "smolvlm2-2.2b", "florence-community/Florence-2-large": "florence-2"}
HOSTED = {"claude-haiku-5-5": "haiku-5.5", "claude-opus-5-5": "opus-5.5"}
CONTINUOUS = {"pixel", "florence-2"}  # checks with a graded score; every other check answers yes/no
ESC = dict(tau_low=[0.5, 0.6, 0.7, 0.8, 0.85, 0.9, 0.95, 1.01], cover_band=[0.0, 0.1, 0.25, 0.5, 0.75])


def gpu_answers():
    """All GPU answer files (full.jsonl plus parallel workers' full_*.jsonl); per job, an answer without an error wins
    over an errored attempt (errored jobs were retried)."""
    out = {}
    for p in sorted((RES / "gpu_out").glob("full*.jsonl")):
        for l in p.read_text().splitlines():
            if not l.strip():
                continue
            try:
                j = json.loads(l)
            except json.JSONDecodeError:
                continue
            if j["job_id"] not in out or (out[j["job_id"]].get("error") and not j.get("error")):
                out[j["job_id"]] = j
    return out


def hosted_answers(split, model, kind):
    p = RES / f"hosted/{split}_{model}_{kind}.jsonl"
    return {j["pair_id"]: j for j in map(json.loads, p.read_text().splitlines()) if j} if p.exists() else {}


def norm(s):
    return re.sub(r"[^a-z0-9 ]+", " ", s.lower()).split()


def ocr_match(expected, text):
    """Share of the expected effect's quoted words found in order in the OCR text (best window)."""
    q = re.findall(r"'([^']+)'", expected)
    want = norm(q[-1] if q else expected)
    got = norm(text)
    if not want:
        return 0.0
    best = 0.0
    for i in range(max(1, len(got) - len(want) + 1)):
        best = max(best, difflib.SequenceMatcher(None, want, got[i:i + len(want) + 1]).ratio())
    return best


# ---------- per-question scores, one row per (pair, question, check) ----------

def question_rows(split):
    rows = []
    pix = pd.read_csv(RES / f"raw/pixel_{split}_decisions.csv")
    acts = {r["pair_id"]: r for r in load(split, "action")}
    work = {r["pair_id"]: r for r in load(split, "worked")}
    base = lambda r: dict(pair_id=r["pair_id"], tier=r["tier"], kind=r["kind"], variant=r["variant"], seed=r["seed"])
    fz0 = json.loads(FROZEN.read_text())
    for _, d in pix[pix.cond.isin(["C1", "C2", "C4", "C7"])].iterrows():
        r = acts[d.pair_id]
        name = {"C1": "pusv-published", "C2": "pusv-tuned", "C4": "pixel", "C7": "pusv+anchored"}[d.cond]
        # decision = what the check actually does: settled -> it did not go; dialog -> its dialog flag
        dlg_dec = (float(d.s_dialog) >= fz0["question_thresholds"][f"dialog_t{r['tier']}"]) if d.cond == "C4" else bool(float(d.s_dialog) >= 0.5)
        rows.append(dict(base(r), question="settled", check=name, y=bool(r["settled"]), score=float(d.s_settled), ms=float(d.delta_s * 1000),
                         decision=bool(d.action != "go"), bg=r["bg"], event=r.get("event")))
        rows.append(dict(base(r), question="dialog", check=name, y=bool(r["dialog"]), score=float(d.s_dialog), ms=float(d.delta_s * 1000),
                         decision=dlg_dec, bg=r["bg"], event=r.get("event")))
    # pixel worked: effect-region changed fraction (failure score = 1 - changed share)
    fz = json.loads(FROZEN.read_text())
    for r in work.values():
        s = _pixel_worked(dict(r, action_box=r["effect_box"]), fz["mask"])  # region = where the expected effect appears
        rows.append(dict(base(r), question="worked", check="pixel", y=bool(r["worked"]), score=s, ms=np.nan, effect_kind=r["effect_kind"], outcome=r.get("outcome")))
    g = gpu_answers()
    for jid, o in g.items():
        kind, m, sp, pid = jid.split("|")
        if sp != split or kind not in ("action", "worked"):
            continue
        name = MODEL_NAMES.get(o["model"], o["model"])
        if kind == "action":
            r = acts[pid]; j = parse_json(o["raw"])
            same = j.get("same_place") if isinstance(j, dict) else None
            dl = j.get("dialog") if isinstance(j, dict) else None
            rows.append(dict(base(r), question="settled", check=name, y=bool(r["settled"]), score=0.5 if not isinstance(same, bool) else float(not same),
                             parse_fail=not isinstance(same, bool), ms=o["ms"], bg=r["bg"], event=r.get("event")))
            rows.append(dict(base(r), question="dialog", check=name, y=bool(r["dialog"]), score=0.5 if not isinstance(dl, bool) else float(dl),
                             parse_fail=not isinstance(dl, bool), ms=o["ms"], bg=r["bg"], event=r.get("event")))
        else:
            r = work[pid]
            if name == "florence-2":
                sc, pf = 1.0 - ocr_match(r["expected_effect"], o["raw"]), not o["raw"]
            else:
                j = parse_json(o["raw"]); h = j.get("happened") if isinstance(j, dict) else None
                sc, pf = (0.5, True) if not isinstance(h, bool) else (float(h is False), False)
            rows.append(dict(base(r), question="worked", check=name, y=bool(r["worked"]), score=sc, parse_fail=pf, ms=o["ms"],
                             effect_kind=r["effect_kind"], outcome=r.get("outcome")))
    for model, name in HOSTED.items():
        for kind in ("action", "worked"):
            for pid, o in hosted_answers(split, model, kind).items():
                j = parse_json(o.get("raw", ""))
                if kind == "action":
                    r = acts.get(pid)
                    if r is None:
                        continue
                    same = j.get("same_place") if isinstance(j, dict) else None
                    dl = j.get("dialog") if isinstance(j, dict) else None
                    rows.append(dict(base(r), question="settled", check=name, y=bool(r["settled"]), score=0.5 if not isinstance(same, bool) else float(not same),
                                     parse_fail=not isinstance(same, bool), usd=o.get("usd", 0.0), bg=r["bg"], event=r.get("event")))
                    rows.append(dict(base(r), question="dialog", check=name, y=bool(r["dialog"]), score=0.5 if not isinstance(dl, bool) else float(dl),
                                     parse_fail=not isinstance(dl, bool), usd=o.get("usd", 0.0), bg=r["bg"], event=r.get("event")))
                else:
                    r = work.get(pid)
                    if r is None:
                        continue
                    h = j.get("happened") if isinstance(j, dict) else None
                    rows.append(dict(base(r), question="worked", check=name, y=bool(r["worked"]), score=0.5 if not isinstance(h, bool) else float(h is False),
                                     parse_fail=not isinstance(h, bool), usd=o.get("usd", 0.0), effect_kind=r["effect_kind"], outcome=r.get("outcome")))
    df = pd.DataFrame(rows)
    df["parse_fail"] = df.get("parse_fail", False)
    df["parse_fail"] = df["parse_fail"].fillna(False).astype(bool)
    return df


def _pixel_worked(r, mask):
    from harness.q3 import pixel_score
    return pixel_score(r, mask[0], mask[1])[0]


# ---------- tables ----------

def thresholds(dev):
    th = {}
    for (q, c, t), g in dev.groupby(["question", "check", "tier"]):
        th[(q, c, t)] = threshold(g.score.values, g.y.values, FA)
    return th


def boot(g, stat, n=2000, seed=0):
    keys = g[["kind", "variant"]].drop_duplicates().values.tolist()
    groups = {tuple(k): g[(g.kind == k[0]) & (g.variant == k[1])] for k in keys}
    rng = np.random.default_rng(seed)
    vals = []
    for _ in range(n):
        pick = [groups[tuple(keys[i])] for i in rng.integers(0, len(keys), len(keys))]
        vals.append(stat(pd.concat(pick)))
    return np.nanpercentile(vals, [2.5, 97.5])


def question_table(test, th):
    out = []
    for (q, c, t), g in test.groupby(["question", "check", "tier"]):
        theta = th.get((q, c, t), np.inf)
        rec = lambda x: float((x[x.y].score >= theta).mean()) if x.y.any() else np.nan
        fa = lambda x: float((x[~x.y].score >= theta).mean()) if (~x.y).any() else np.nan
        lo, hi = boot(g, rec, n=500)
        bgneg = g[(~g.y) & (g.get("bg", pd.Series("none", index=g.index)) != "none")] if q == "settled" else g.iloc[0:0]
        nat = theta if c in CONTINUOUS else 0.5  # a yes/no check's own decision; a scored check at its dev threshold
        dec = g.decision.astype("boolean") if "decision" in g and g.decision.notna().all() else (g.score >= nat)  # logged decision wins
        out.append(dict(question=q, check=c, tier=t, n=len(g), positives=int(g.y.sum()), theta=theta, recall=rec(g), recall_lo=lo, recall_hi=hi,
                        recall_native=float(dec[g.y].mean()) if g.y.any() else np.nan,
                        fa_native=float(dec[~g.y].mean()) if (~g.y).any() else np.nan,
                        no_2pct_point=bool(not np.isfinite(theta) or theta > 1.0),
                        false_alarm=fa(g), bg_motion_false_alarm=float((bgneg.score >= theta).mean()) if len(bgneg) else np.nan,
                        parse_fail=float(g.parse_fail.mean()), ms_median=float(g.ms.median()) if "ms" in g and g.ms.notna().any() else np.nan,
                        usd_per_1000=float(g.usd.mean() * 1000) if "usd" in g and g.usd.notna().any() else 0.0))
    return pd.DataFrame(out)


def h1(dev, test, th, margin=0.02, n=2000):
    """Per question x tier: best small check by dev recall vs Opus on the same test pairs; paired bootstrap; Holm."""
    rows = []
    for q, t in itertools.product(["settled", "dialog", "worked"], [0, 1, 2]):
        dq = dev[(dev.question == q) & (dev.tier == t)]
        dev_rec = {c: float((g[g.y].score >= th.get((q, c, t), np.inf)).mean()) for c, g in dq.groupby("check") if c in SMALL and g.y.any()}
        if not dev_rec:
            continue
        best = max(dev_rec, key=dev_rec.get)
        tq = test[(test.question == q) & (test.tier == t)]
        s = tq[tq.check == best].set_index("pair_id"); f = tq[tq.check == "opus-5.5"].set_index("pair_id")
        common = s.index.intersection(f.index)
        s, f = s.loc[common], f.loc[common]
        y = s.y.values
        hs = (s.score.values >= th.get((q, best, t), np.inf)); hf = (f.score.values >= th.get((q, "opus-5.5", t), np.inf))
        clusters = list(zip(s.kind, s.variant))
        keys = sorted(set(clusters)); idx = {k: np.where([c == k for c in clusters])[0] for k in keys}
        rng = np.random.default_rng(1)
        diffs = []
        for _ in range(n):
            ii = np.concatenate([idx[keys[i]] for i in rng.integers(0, len(keys), len(keys))])
            yy = y[ii]
            if yy.any():
                diffs.append(hs[ii][yy].mean() - hf[ii][yy].mean())
        diffs = np.array(diffs)
        obs = hs[y].mean() - hf[y].mean() if y.any() else np.nan
        p = float((diffs <= -margin).mean()) if len(diffs) else np.nan
        th_f = th.get((q, "opus-5.5", t), np.inf)
        nat = lambda c: th.get((q, c, t), np.inf) if c in CONTINUOUS else 0.5
        ns = s.decision.astype(bool).values if "decision" in s and s.decision.notna().all() else s.score.values >= nat(best)
        nf = f.score.values >= 0.5
        rows.append(dict(question=q, tier=t, small_check=best, dev_recall=dev_rec[best], n_pairs=len(common), positives=int(y.sum()),
                         frontier_has_2pct_point=bool(np.isfinite(th_f) and th_f <= 1.0),
                         small_recall_native=float(ns[y].mean()) if y.any() else np.nan, small_fa_native=float(ns[~y].mean()) if (~y).any() else np.nan,
                         frontier_recall_native=float(nf[y].mean()) if y.any() else np.nan, frontier_fa_native=float(nf[~y].mean()) if (~y).any() else np.nan,
                         small_recall=float(hs[y].mean()) if y.any() else np.nan, frontier_recall=float(hf[y].mean()) if y.any() else np.nan,
                         diff=obs, diff_lo95_onesided=float(np.percentile(diffs, 5)) if len(diffs) else np.nan, p=p))
    d = pd.DataFrame(rows).sort_values("p").reset_index(drop=True)
    m = len(d)
    holm = []
    for i, p in enumerate(d.p):  # Holm step-down
        holm.append(min(1.0, max([(m - k) * d.p[k] for k in range(i + 1)])))
    d["p_holm"] = holm
    d["non_inferior"] = d.p_holm < 0.05
    # a cell where Opus has no operating point at <= 2% false alarms on dev is uninformative, not a pass
    d["h1_cell"] = np.where(~d.frontier_has_2pct_point, "uninformative (Opus has no 2% FA point)",
                            np.where(d.non_inferior, "non-inferior", "not shown"))
    return d


def escalate_tune():
    from harness.run_models import run_escalate
    fz = json.loads(FROZEN.read_text())
    recs = [r for r in load("dev") if r["tier"] == 1]
    g = gpu_answers()
    feats = features("dev")
    feats1 = {k: (v["F"], v["fms"]) for k, v in feats.items()}
    sc = Scorer(recs)
    best, log = {}, []
    for cond, m in (("C5", "qwen2b"), ("C6", "qwen4b")):
        outs = {f"{j.split('|')[0]}|{m[-2:]}|{j.split('|')[3]}": o for j, o in g.items() if j.split("|")[1] == m and j.split("|")[2] == "dev"}
        sub = [r for r in recs if any(k.endswith("|" + r["pair_id"]) for k in outs)] or recs
        for tl, cb in itertools.product(*ESC.values()):
            cfg = {**A.DEFAULTS, **fz["C4"], "tau_low": tl, "cover_band": cb, "cand_min": 0.5}
            d = pd.DataFrame(run_escalate(sub, feats1, cfg, m[-2:], outs, sc, cond))
            o = objective(d)
            log.append(dict(cond=cond, tau_low=tl, cover_band=cb, objective=o, escalated=float(d.escalated.mean()), missing=int(d.missing.sum())))
            if np.isfinite(o) and d.escalated.any() and (cond not in best or o < best[cond][0]):
                best[cond] = (o, dict(tau_low=tl, cover_band=cb, cand_min=0.5))
    TAB.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(log).to_csv(TAB / "escalation_tuning_dev.csv", index=False)
    fz.update({c: v[1] for c, v in best.items()})
    fz["escalation_dev_objective"] = {c: v[0] for c, v in best.items()}
    FROZEN.write_text(json.dumps(fz, indent=2))
    print(json.dumps({c: fz.get(c) for c in ("C5", "C6")}), fz.get("escalation_dev_objective"))


def replay_table(split="test"):
    from harness.run_models import run_escalate
    fz = json.loads(FROZEN.read_text())
    pix = pd.read_csv(RES / f"raw/pixel_{split}_decisions.csv")
    recs = load(split)
    sc = Scorer(recs)
    g = gpu_answers()
    feats = {k: (v["F"], v["fms"]) for k, v in features(split).items()}
    esc = []
    for cond, m in (("C5", "qwen2b"), ("C6", "qwen4b"), ("C5r", "qwen2b"), ("C6r", "qwen4b")):  # *r = exploratory
        if cond not in fz:
            continue
        outs = {f"{j.split('|')[0]}|{m[-2:]}|{j.split('|')[3]}": o for j, o in g.items() if j.split("|")[1] == m and j.split("|")[2] == split}
        sub = [r for r in recs if any(k.endswith("|" + r["pair_id"]) for k in outs)]
        esc += run_escalate(sub, feats, {**A.DEFAULTS, **fz["C4"], **fz[cond]}, m[-2:], outs, sc, cond)
    df = pd.concat([pix, pd.DataFrame(esc)], ignore_index=True)
    rows = []
    for (c, t), d in df.groupby(["cond", "tier"]):
        moved = d[d.correct0 == "reaim"]; re = d[d.action == "reaim"]
        w = M.wilson(int((re.outcome == "wrong_reaim").sum()), len(re))
        r = dict(cond=c, tier=t, n=len(d), stale_per_1000=M.per_1000(d, d.outcome == "stale"),
                 stale_during_check_per_1000=M.per_1000(d, d.stale_during_check), false_replans_per_1000=M.per_1000(d, d.outcome == "false_replan"),
                 reaim_recovery=float((moved.outcome == "recovered").mean()) if len(moved) else np.nan, n_reaims=len(re),
                 wrong_reaims=int((re.outcome == "wrong_reaim").sum()), wrong_share=w[0], wrong_hi=w[2],
                 ms_median=float(d.delta_s.median() * 1000), escalated=float(d.escalated.fillna(False).astype(bool).mean()) if "escalated" in d else 0.0)
        for p in (0.01, 0.05, 0.20):
            r[f"sec_p{p:g}"] = M.expected_seconds(d, p)
        c0 = df[(df.cond == "C0") & (df.tier == t) & df.pair_id.isin(d.pair_id)]
        f = lambda x, p: M.expected_seconds(x, p)
        a, b = f(d, 0), f(d, 1) - f(d, 0); a0, b0 = f(c0, 0), f(c0, 1) - f(c0, 0)
        r["break_even_observed"] = (a - a0) / (b0 - b) if b0 != b and 0 <= (a - a0) / (b0 - b) <= 1 else np.nan
        rows.append(r)
    return pd.DataFrame(rows), df


def h2(name="loop", c_plan=None):
    """Live loop. Stale actions among steps whose plan hit the named element (planner misses are reported apart),
    by gap; added time per step = (check time + re-plans x C_plan) / (mean planning time + gap) of the no-check cell;
    wrong re-aims as a share of re-aims with the Wilson upper bound. 95% Wilson CIs."""
    p = RES / f"live/{name}.jsonl"
    d = pd.DataFrame([json.loads(l) for l in p.read_text().splitlines() if l.strip()])
    c_plan = c_plan or M.C_PLAN
    rows = []
    for g_s, gg in d.groupby("gap_s"):
        base = gg[gg.cond == "none"]
        step_s = base.plan_ms.mean() / 1000 + g_s
        for cond, x in gg.groupby("cond"):
            hit = x[~x.outcome.isin(["planner_miss", "parse_fail"])]  # parse failures: planner gave no box; reported apart
            k = int((hit.outcome == "stale").sum()); n = len(hit)
            st = M.wilson(k, n)
            re = hit[hit.action == "reaim"]; w = M.wilson(int((re.outcome == "wrong_reaim").sum()), len(re))
            added = (x.check_ms.fillna(0).mean() / 1000 + (hit.action == "replan").sum() / max(len(x), 1) * c_plan) / step_s
            rows.append(dict(gap_s=g_s, cond=cond, steps=len(x), planner_miss=float((x.outcome == "planner_miss").mean()),
                             parse_fail=int((x.outcome == "parse_fail").sum()),
                             planned_hits=n, stale=k, stale_rate=st[0], stale_lo=st[1], stale_hi=st[2],
                             replans=int((hit.action == "replan").sum()), replan_needed=int((hit.outcome == "replan_needed").sum()),
                             replan_false=int((hit.outcome == "replan_false").sum()), reaims=len(re), wrong_reaims=int((re.outcome == "wrong_reaim").sum()),
                             wrong_hi=w[2], check_ms_median=float(x.check_ms.median()), added_time_share=added))
    r = pd.DataFrame(rows)
    out = []
    for g_s, gg in r.groupby("gap_s"):
        a, b = gg[gg.cond == "none"], gg[gg.cond == "preflight"]
        if len(a) and len(b):
            a, b = a.iloc[0], b.iloc[0]
            cut = 1 - b.stale_rate / a.stale_rate if a.stale_rate else np.nan
            out.append(dict(gap_s=g_s, stale_cut=cut, added_time=b.added_time_share, wrong_hi=b.wrong_hi,
                            h2_holds=bool(cut >= 0.5 and b.added_time_share <= 0.10 and (b.reaims == 0 or b.wrong_hi < 0.10))))
    return r, pd.DataFrame(out)


def main():
    TAB.mkdir(parents=True, exist_ok=True)
    if (RES / "live/loop.jsonl").exists():
        lr, lh = h2(); lr.to_csv(TAB / "h2_live_cells.csv", index=False); lh.to_csv(TAB / "h2.csv", index=False)
        print(lr.to_string(index=False, float_format=lambda v: f"{v:.3f}")); print(lh.to_string(index=False))
    dev, test = question_rows("dev"), question_rows("test")
    th = thresholds(dev)
    qt = question_table(test, th); qt.to_csv(TAB / "table1_questions.csv", index=False)
    hh = h1(dev, test, th); hh.to_csv(TAB / "h1.csv", index=False)
    rt, df = replay_table("test"); rt.to_csv(TAB / "table2_replay.csv", index=False)
    rd, _ = replay_table("dev"); rd.to_csv(TAB / "table2_replay_dev.csv", index=False)
    # extended cost model: predicted break-even from dev rates, observed from test
    be = rt[["cond", "tier", "break_even_observed"]].merge(rd[["cond", "tier", "break_even_observed"]].rename(columns={"break_even_observed": "break_even_predicted"}), on=["cond", "tier"])
    be.to_csv(TAB / "table3_break_even.csv", index=False)
    # H3: combined vs published PUSV on Tier 1 and 2
    h3 = []
    for t in (1, 2):
        g = qt[(qt.tier == t)]
        dl = g[g.question == "dialog"].set_index("check"); st = df[(df.tier == t)]
        bgm = lambda c: float((st[(st.cond == c) & ~st.relevant].action == "replan").mean())
        pd_rec = lambda c: float(dev[(dev.question == "dialog") & (dev.tier == t) & (dev.check == c)].pipe(lambda x: (x[x.y].score >= 0.5).mean()))
        tq = test[(test.question == "dialog") & (test.tier == t)]
        rec_raw = lambda c: float((tq[(tq.check == c) & tq.y].score >= 0.5).mean())
        h3.append(dict(tier=t, dialog_recall_pusv=rec_raw("pusv-published"), dialog_recall_combined=rec_raw("pusv+anchored"),
                       bg_replans_pusv=bgm("C1"), bg_replans_combined=bgm("C7")))
    h3 = pd.DataFrame(h3)
    h3["keeps_flags"] = h3.dialog_recall_combined >= h3.dialog_recall_pusv - 0.02
    h3["cuts_replans_50pct"] = h3.bg_replans_combined <= 0.5 * h3.bg_replans_pusv
    h3.to_csv(TAB / "h3.csv", index=False)
    print(qt.pivot_table(index=["question", "check"], columns="tier", values="recall").round(3).to_string())
    print(hh.to_string(index=False, float_format=lambda v: f"{v:.3f}"))
    print(h3.to_string(index=False, float_format=lambda v: f"{v:.3f}"))
    print(rt[["cond", "tier", "stale_per_1000", "reaim_recovery", "wrong_reaims", "n_reaims", "sec_p0.05", "break_even_observed"]].to_string(index=False, float_format=lambda v: f"{v:.3f}"))


if __name__ == "__main__":
    {"escalate_tune": escalate_tune, "all": main, "h2": lambda: [print(t.to_string(index=False)) for t in h2()]}[sys.argv[1]]()
