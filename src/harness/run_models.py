"""Wave 3 model conditions, PILOT. Replays logged model answers; no model is called here.

  python -m harness.run_models tune      # C5/C6 tau_low and cover band on Tier 1 dev -> results/pilot/frozen_w3.json
  python -m harness.run_models dev|test  # C4 (frozen W2) + C5-C9 tables

Model answers come from: Qwen on Colab (results/pilot/qwen_out/{split}_{escalate,locate}.jsonl, colab/qwen_runner.py)
and hosted Claude (results/pilot/hosted_out/, models/hosted_locate.py). Check time delta per pair:
  C5/C6: pixel feature + decide ms (laptop) + 200 ms frame wait + every escalation call's generate ms (Colab GPU)
  C7:    Qwen3-VL 4B generate ms (Colab GPU)
  C8/C9: API wall time (laptop to Anthropic API)
"""
import argparse, itertools, json, subprocess, sys, time
from pathlib import Path

import numpy as np
import pandas as pd

from anchored import check as A
from harness import metrics as M
from harness.run_checks import FROZEN, RES, ROOT, Scorer, feature_table, git_hash, hardware, load, objective, run_anchored, run_refs, summarize
from models import hosted_locate as H
from models.common import locate_decision, parse_json
from models.qwen_jobs import TAU_LOW_MIN, results

FROZEN3 = RES / "frozen_w3.json"
SIZES = {"C5": "2b", "C6": "4b"}
GRID = dict(tau_low=[0.5, 0.6, 0.7, 0.8, 0.85, 0.9, 0.95], cover_band=[0.0, 0.1, 0.25, 0.5, 0.75])
C8_N = {"dev": 50, "test": 300}


def replay_asker(F, pid, size, outs, calls):
    """Answers escalation questions from logged Qwen outputs. A missing answer counts as a parse failure."""
    def ask(kind, arg):
        if kind == "cover":
            name = "in" if arg is F["at_in"] else f"p{F['peaks'].index(arg)}"
            jid = f"cover_{name}|{size}|{pid}"
        else:
            jid = f"tiebreak|{size}|{pid}"
        o = outs.get(jid)
        j = parse_json(o["raw"]) if o else None
        calls.append(dict(kind=kind, job_id=jid, ms=o["ms"] if o else 0.0, parsed=j, missing=o is None))
        return j
    return ask


def run_escalate(recs, feats, cfg, size, outs, scorer, cond):
    rows = []
    for r in recs:
        F, fms = feats[r["pair_id"]]
        calls = []
        ask = replay_asker(F, r["pair_id"], size, outs, calls)
        t0 = time.perf_counter()
        action, click, reason, esc = A.decide(F, r["planned_box"], cfg, "escalate", ask)
        ms = fms + (time.perf_counter() - t0) * 1000 + A.FRAME_WAIT_MS + sum(c["ms"] for c in calls)
        rows.append(scorer(r["pair_id"], action, click, ms, cond=cond, reason=reason, escalated=esc,
                           n_calls=len(calls), model_ms=sum(c["ms"] for c in calls),
                           missing=sum(c["missing"] for c in calls),
                           parse_fail=sum(c["parsed"] is None for c in calls)))
    return rows


def run_c7(recs, outs, scorer, cond="C7"):
    rows = []
    for r in recs:
        o = outs.get(f"locate|4b|{r['pair_id']}")
        parsed = parse_json(o["raw"]) if o else None
        if isinstance(parsed, dict) and "box" not in parsed and "bbox_2d" in parsed:
            parsed["box"] = parsed["bbox_2d"]
        action, click = locate_decision(parsed, r["planned_box"], (1280 / 1000, 800 / 1000))  # Qwen3-VL: 0-1000 relative
        rows.append(scorer(r["pair_id"], action, click if action == "reaim" else r["click"], o["ms"] if o else 0.0,
                           cond=cond, reason="parse_fail" if parsed is None else action, missing=o is None,
                           parse_fail=int(parsed is None), model_ms=o["ms"] if o else 0.0))
    return rows


def run_hosted(recs, model, split, scorer, cond, n=None):
    sub = {r["pair_id"] for r in H.subset(recs, n)}
    out = H.done(model, split, "locate")
    rows = []
    for r in recs:
        if r["pair_id"] not in sub:
            continue
        o = out.get(r["pair_id"])
        parsed = parse_json(o["raw"]) if o else None
        action, click = locate_decision(parsed, r["planned_box"], (1.0, 1.0))
        rows.append(scorer(r["pair_id"], action, click if action == "reaim" else r["click"], o["ms"] if o else 0.0,
                           cond=cond, reason="parse_fail" if parsed is None else action, missing=o is None,
                           parse_fail=int(parsed is None), usd=o["usd"] if o else 0.0, model_ms=o["ms"] if o else 0.0))
    return rows


def tune():
    fz = json.loads(FROZEN.read_text())["C4"]
    recs = [r for r in load("dev") if r["tier"] == 1]
    feats = feature_table("dev", recs, fz["mask_thr"], fz["mask_dilate"])
    outs = results("dev_escalate")
    scorer = Scorer(recs)
    best, log = {}, []
    for cond, size in SIZES.items():
        for tl, cb in itertools.product(GRID["tau_low"], GRID["cover_band"]):
            cfg = {**A.DEFAULTS, **fz, "tau_low": tl, "cover_band": cb, "cand_min": TAU_LOW_MIN}
            df = pd.DataFrame(run_escalate(recs, feats, cfg, size, outs, scorer, cond))
            # The prompt's C5/C6 rule: minimize expected seconds per step at p = 0.05, model time included. Wrong
            # re-aims are already charged at C_wrong. The Wave 2 re-find-error cap is reported (cap_ok), not applied:
            # on dev no escalation setting meets it (look-alikes on gone/covered pairs get picked).
            obj = M.expected_seconds(df, 0.05)
            cap_ok = objective(df) != float("inf")
            s = summarize(df)
            log.append(dict(cond=cond, tau_low=tl, cover_band=cb, objective=obj, escalated=df.escalated.mean(),
                            mean_model_ms=df.model_ms.mean(), missing=int(df.missing.sum()), cap_ok=cap_ok, **s))
            if cond not in best or obj < best[cond][0]:
                best[cond] = (obj, dict(tau_low=tl, cover_band=cb, cand_min=TAU_LOW_MIN))
    pd.DataFrame(log).to_csv(RES / "tuning_w3_escalate.csv", index=False)
    out = {c: v[1] for c, v in best.items()}
    out["dev_objective"] = {c: v[0] for c, v in best.items()}
    out.update(tuned_on="Tier 1 dev", commit=git_hash(), date=time.strftime("%Y-%m-%d"),
               model_hardware="Colab Tesla T4 (fp16)", pixel_hardware=hardware(),
               grid=GRID, note="Wave 2 C4 thresholds fixed; tie-break candidates = top 3 peaks >= cand_min; objective = expected s/step at p=0.05 incl. model time, no re-find cap (reported as cap_ok)",
               c4_dev_objective=M.expected_seconds(pd.DataFrame(run_anchored(recs, feats, {**A.DEFAULTS, **fz}, "reaim", scorer, "C4")), 0.05))
    FROZEN3.write_text(json.dumps(out, indent=2))
    print(pd.DataFrame(log).sort_values(["cond", "objective"]).groupby("cond").head(5)[
        ["cond", "tau_low", "cover_band", "objective", "cap_ok", "escalated", "mean_model_ms", "reaim_recovery", "wrong_reaims", "n_reaims", "stale_per_1000", "missing"]].to_string(index=False))
    print(json.dumps(out, indent=2))


def evaluate(split):
    if split == "test":
        tags = subprocess.run(["git", "tag", "--merged", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.split()
        if "pilot-prereg-w3" not in tags:
            sys.exit("test split needs the pilot-prereg-w3 tag in HEAD's history")
    fz2 = json.loads(FROZEN.read_text())
    fz3 = json.loads(FROZEN3.read_text())
    recs = load(split)
    scorer = Scorer(recs)
    c4 = fz2["C4"]
    feats = feature_table(split, recs, c4["mask_thr"], c4["mask_dilate"], refresh=(split == "test"))
    rows = run_refs(recs, scorer)
    rows += run_anchored(recs, feats, {**A.DEFAULTS, **c4}, "reaim", scorer, "C4")
    esc = results(f"{split}_escalate")
    for cond, size in SIZES.items():
        rows += run_escalate(recs, feats, {**A.DEFAULTS, **c4, **fz3[cond]}, size, esc, scorer, cond)
    rows += run_c7(recs, results(f"{split}_locate"), scorer)
    rows += run_hosted(recs, H.Fr.OPUS, split, scorer, "C8", C8_N[split])
    rows += run_hosted(recs, H.Fr.SMALL_HOSTED, split, scorer, "C9")
    df = pd.DataFrame(rows)
    meta = dict(split=split, commit=git_hash(), date=time.strftime("%Y-%m-%d %H:%M"), pixel_hardware=hardware(),
                qwen_hardware="Colab Tesla T4 (fp16, transformers + CUDA)", hosted=[H.Fr.OPUS, H.Fr.SMALL_HOSTED],
                n_pairs=len(recs), c8_subset=C8_N[split])
    raw = RES / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    df.to_csv(raw / f"w3_{split}_decisions.csv", index=False)
    (raw / f"w3_{split}_meta.json").write_text(json.dumps(meta, indent=2))
    tables(df, split, meta)
    return df


def tables(df, split, meta):
    order = ["C0", "C4", "C5", "C6", "C7", "C8", "C9", "oracle", "always_replan"]
    out = []
    for tier in (0, 1):
        for cond in order:
            d = df[(df.cond == cond) & (df.tier == tier)]
            if not len(d):
                continue
            s = summarize(d)
            lo, hi = M.cluster_bootstrap(d, lambda x: M.expected_seconds(x, 0.05))
            extra = dict(escalated=float(d.escalated.mean()) if "escalated" in d and d.escalated.notna().any() else np.nan,
                         mean_model_ms=float(d.model_ms.mean()) if d.model_ms.notna().any() else np.nan,
                         parse_fail_rate=float((d.parse_fail.fillna(0) > 0).mean()), missing=int(d.missing.fillna(0).sum()),
                         usd_per_step=float(d.usd.mean()) if "usd" in d and d.usd.notna().any() else np.nan)
            out.append(dict(tier=tier, cond=cond, **s, **extra, sec_p05_lo=lo, sec_p05_hi=hi))
    t = pd.DataFrame(out)
    t.to_csv(RES / f"w3_{split}_summary.csv", index=False)
    bins = [dict(cond=c, motion_bin=b, **summarize(d)) for c in order for b in ["static", "low", "med", "high"]
            if len(d := df[(df.cond == c) & (df.tier == 1) & (df.motion_bin == b)])]
    pd.DataFrame(bins).to_csv(RES / f"w3_{split}_by_motion.csv", index=False)
    lk = []
    for c in ["C4", "C5", "C6"]:
        d = df[(df.cond == c) & (df.event == "moved_lookalike") & (df.tier == 1)]
        all1 = df[(df.cond == c) & (df.tier == 1)]
        lk.append(dict(cond=c, **summarize(d), added_ms_all_tier1=float((all1.delta_s.mean() -
                       df[(df.cond == "C4") & (df.tier == 1)].delta_s.mean()) * 1000)))
    pd.DataFrame(lk).to_csv(RES / f"w3_{split}_lookalike.csv", index=False)
    cols = ["tier", "cond", "n", "false_alarm", "stale_per_1000", "stale_during_check_per_1000", "reaim_recovery",
            "n_reaims", "wrong_reaims", "wrong_hi", "ms_median", "escalated", "parse_fail_rate", "missing", "sec_p05", "sec_p05_lo", "sec_p05_hi"]
    print(json.dumps(meta))
    print(t[cols].to_string(index=False, float_format=lambda v: f"{v:.3f}"))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("what", choices=["tune", "dev", "test"])
    a = ap.parse_args()
    tune() if a.what == "tune" else evaluate(a.what)
