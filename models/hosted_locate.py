"""C8/C9 hosted locate checks (and Q3 worked questions) through the metered Anthropic client. PILOT.

  PREFLIGHT_API_KEY=... python -m models.hosted_locate run   MODEL SPLIT [--n 50] [--pairs FILE] [--workers 4]
  PREFLIGHT_API_KEY=... python -m models.hosted_locate worked MODEL SPLIT [--workers 4]
  python -m models.hosted_locate score MODEL SPLIT [--n 50]

Raw responses go to results/pilot/hosted_out/{split}_{model}_{kind}.jsonl, one line per call, and finished pair ids
are skipped on a rerun. Check time is the measured API wall time. A parse failure counts as a re-plan.
"""
import argparse, json, os, random, subprocess, sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd
from PIL import Image

from models import frontier as Fr
from models.common import locate_decision, parse_json, plan_crop, prompt
from models.qwen_jobs import locate_kw

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results/pilot/hosted_out"
MAX_TOKENS = {Fr.SMALL_HOSTED: 100, Fr.OPUS: 1024}  # Opus thinks at effort low; its thinking counts inside max_tokens
PROMPT = {"locate": os.environ.get("PREFLIGHT_LOCATE_PROMPT", "locate_claude"), "worked": "worked"}
SCHEMA = {  # structured output: the answer is always parseable JSON (prompt-dev round 2; round 1 had 75% prose)
    "locate": {"type": "object", "additionalProperties": False, "required": ["present", "box", "covered"],
               "properties": {"present": {"type": "boolean"}, "covered": {"type": "boolean"},
                              "box": {"anyOf": [{"type": "array", "items": {"type": "number"}}, {"type": "null"}]}}},
    "worked": {"type": "object", "additionalProperties": False, "required": ["happened", "confidence"],
               "properties": {"happened": {"type": "boolean"}, "confidence": {"type": "number"}}},
}


def _guard(split):
    if split == "test":
        tags = subprocess.run(["git", "tag", "--merged", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.split()
        if "pilot-prereg-w3" not in tags:
            sys.exit("test-split model calls need the pilot-prereg-w3 tag in HEAD's history")


def out_path(model, split, kind):
    return OUT / f"{split}_{model}_{kind}.jsonl"


def done(model, split, kind):
    p = out_path(model, split, kind)
    return {j["pair_id"]: j for j in map(json.loads, p.read_text().splitlines()) if j} if p.exists() else {}


def subset(recs, n, seed=0):
    """n pairs stratified by (page, motion, correct_action at offset 0): round-robin over shuffled strata."""
    if n is None or n >= len(recs):
        return recs
    rng = random.Random(seed)
    strata = {}
    for r in recs:
        strata.setdefault((r["page"], r["motion"], r["truth"][0]["correct_action"]), []).append(r)
    groups = [rng.sample(v, len(v)) for _, v in sorted(strata.items())]
    out = []
    while len(out) < n:
        for g in groups:
            if g and len(out) < n:
                out.append(g.pop())
    return out


def locate_req(r):
    pa = Image.open(ROOT / r["frames"]["planned_a"]).convert("RGB")
    crop, cbox = plan_crop(pa, r["planned_box"])
    cb = Image.open(ROOT / r["frames"]["current_b"]).convert("RGB")
    return [crop, cb], prompt(PROMPT["locate"], **locate_kw(r["planned_box"], cbox))


def worked_req(r):
    b = Image.open(ROOT / r["frames"]["before"]).convert("RGB").resize((640, 400), Image.LANCZOS)
    a = Image.open(ROOT / r["frames"]["after"]).convert("RGB")
    return [b, a], prompt(PROMPT["worked"], expected_effect=r["expected_effect"])


def run(model, split, recs, kind, workers=4):
    _guard(split)
    have = done(model, split, kind)
    todo = [r for r in recs if r["pair_id"] not in have]
    p = out_path(model, split, kind)
    p.parent.mkdir(parents=True, exist_ok=True)
    build = locate_req if kind == "locate" else worked_req

    def one(r):
        ims, txt = build(r)
        a = Fr.ask(model, ims, txt, max_tokens=MAX_TOKENS[model], tag=f"{kind}|{split}|{r['pair_id']}", est_in=1800,
                   schema=SCHEMA[kind])
        return dict(pair_id=r["pair_id"], prompt=PROMPT[kind], schema=True, raw=a["text"], ms=round(a["ms"], 1), usd=a["usd"],
                    stop_reason=a["stop_reason"], request_id=a["request_id"], usage=a["usage"], model=a["model"])

    with p.open("a") as f, ThreadPoolExecutor(workers) as ex:
        for i, row in enumerate(ex.map(one, todo)):
            f.write(json.dumps(row) + "\n")
            f.flush()
            if i % 25 == 0:
                print(f"{model} {kind} {split} {i + 1}/{len(todo)} {row['ms']:.0f} ms spent ${Fr.meter().total:.4f}", flush=True)
    print(f"done; ledger total ${Fr.meter().total:.4f}")


def decisions(model, split, recs, cond):
    """Scored rows for a locate condition, using the Wave 2 scorer."""
    from harness.run_checks import Scorer
    out = done(model, split, "locate")
    sc = Scorer(recs)
    rows = []
    for r in recs:
        o = out.get(r["pair_id"])
        if o is None:
            continue
        parsed = parse_json(o["raw"])
        action, click = locate_decision(parsed, r["planned_box"], (1.0, 1.0))
        rows.append(sc(r["pair_id"], action, click if action == "reaim" else r["click"], o["ms"], cond=cond,
                       reason="parse_fail" if parsed is None else action, usd=o["usd"]))
    return pd.DataFrame(rows)


def score(model, split, recs):
    from harness.run_checks import summarize
    df = decisions(model, split, recs, model)
    print(f"{model} {split}: {len(df)} pairs, parse failures {(df.reason == 'parse_fail').mean():.1%}, "
          f"mean ${df.usd.mean():.5f}/call")
    for tier in (0, 1):
        d = df[df.tier == tier]
        if len(d):
            s = summarize(d)
            print(f"tier {tier}: " + ", ".join(f"{k}={v:.3f}" if isinstance(v, float) else f"{k}={v}" for k, v in s.items()))
    return df


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["run", "worked", "score"])
    ap.add_argument("model")
    ap.add_argument("split")
    ap.add_argument("--n", type=int)
    ap.add_argument("--workers", type=int, default=4)
    a = ap.parse_args()
    if a.cmd == "worked":
        recs = [json.loads(l) for l in (ROOT / f"data/pilot/{a.split}/worked.jsonl").read_text().splitlines() if l.strip()]
        for r in recs:
            r["pair_id"] = r["worked_id"]
        run(a.model, a.split, recs, "worked", a.workers)
        sys.exit()
    _guard(a.split)
    from harness.run_checks import load
    recs = subset(load(a.split), a.n)
    run(a.model, a.split, recs, "locate", a.workers) if a.cmd == "run" else score(a.model, a.split, recs)
