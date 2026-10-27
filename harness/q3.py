"""Q3: did the last action work? Failure detection on the worked set. PILOT.

  python -m harness.q3 tune        # thresholds on dev at <= 2% false alarms -> results/pilot/frozen_q3.json
  python -m harness.q3 dev|test    # recall on failures per check and outcome type

A false alarm = a successful action flagged as failed. Checks, each giving a failure score (higher = more likely failed):
  pixel   1 - changed fraction inside the clicked control's region (action box padded by REGION_PAD px), over pixels
          outside the background-motion mask (union of |before - before_b| and |after - after_b|, Wave 2 C4 mask params)
  models  1 if the answer is happened = false, else 0; a parse failure scores 0.5. The confidence field is logged but
          not used: on dev, Qwen reports it as P(happened) ({"happened": false, "confidence": 0}) while Claude reports
          certainty in its own answer, so one formula cannot rank both.
Threshold: flag failed when score >= theta; theta is the smallest value with dev false alarms <= 2%.
"""
import json, subprocess, sys
from pathlib import Path

import numpy as np
import pandas as pd

from anchored import check as A
from harness import metrics as M
from models import hosted_locate as H
from models.common import parse_json
from models.qwen_jobs import results

ROOT = Path(__file__).resolve().parents[1]
RES = ROOT / "results/pilot"
FROZEN_Q3 = RES / "frozen_q3.json"
REGION_PAD = 24
DIFF_THR = 20  # gray levels, as in Layer 2a
FA_MAX = 0.02
CHECKS = ["pixel", "qwen3-vl-2b", "qwen3-vl-4b", "claude-haiku-5-5", "claude-opus-5-5"]


def recs(split):
    rs = [json.loads(l) for l in (ROOT / f"data/pilot/{split}/worked.jsonl").read_text().splitlines() if l.strip()]
    if split == "test":
        lab = {j["worked_id"]: j for j in map(json.loads, (ROOT / "private/test_worked_labels.jsonl").read_text().splitlines()) if j}
        rs = [dict(r, outcome=lab[r["worked_id"]]["outcome"], label=lab[r["worked_id"]]["label"]) for r in rs]
    extra = json.loads((ROOT / "data/pilot/worked_extra.json").read_text())
    for r in rs:
        r["frames"].update({k: extra[r["worked_id"]][k] for k in ("before_b", "after_b")})
    return rs


def pixel_score(r, thr, dil):
    g = {k: A.gray(ROOT / v) for k, v in r["frames"].items()}
    mask = A.motion_mask(g["before"], g["before_b"], g["after"], g["after_b"], thr, dil)
    x, y, w, h = r["action_box"]
    H_, W_ = g["before"].shape
    x0, y0 = int(max(0, x - REGION_PAD)), int(max(0, y - REGION_PAD))
    x1, y1 = int(min(W_, x + w + REGION_PAD)), int(min(H_, y + h + REGION_PAD))
    keep = ~mask[y0:y1, x0:x1]
    diff = np.abs(g["before"][y0:y1, x0:x1].astype(np.int16) - g["after"][y0:y1, x0:x1].astype(np.int16)) > DIFF_THR
    frac = float(diff[keep].mean()) if keep.any() else 0.0
    return 1.0 - frac, float(keep.mean())


def model_score(raw):
    j = parse_json(raw)
    if not isinstance(j, dict) or not isinstance(j.get("happened"), bool):
        return 0.5, True
    return (1.0 if j["happened"] is False else 0.0), False


def scores(split):
    fz = json.loads((RES / "frozen_w2.json").read_text())["C4"]
    rs = recs(split)
    q = results(f"{split}_worked")
    host = {m: H.done(m, split, "worked") for m in ("claude-haiku-5-5", "claude-opus-5-5")}
    rows = []
    for r in rs:
        wid = r["worked_id"]
        base = dict(worked_id=wid, page=r["page"], seed=r["seed"], outcome=r["outcome"], failed=r["label"] == "failed")
        s, keep = pixel_score(r, fz["mask_thr"], fz["mask_dilate"])
        rows.append(dict(base, check="pixel", score=s, parse_fail=False, unmasked=keep, missing=False))
        for size in ("2b", "4b"):
            o = q.get(f"worked|{size}|{wid}")
            s, pf = model_score(o["raw"]) if o else (0.5, True)
            rows.append(dict(base, check=f"qwen3-vl-{size}", score=s, parse_fail=pf, missing=o is None, ms=o["ms"] if o else np.nan))
        for m, out in host.items():
            o = out.get(wid)
            s, pf = model_score(o["raw"]) if o else (0.5, True)
            rows.append(dict(base, check=m, score=s, parse_fail=pf, missing=o is None, ms=o["ms"] if o else np.nan))
    return pd.DataFrame(rows)


def threshold(d):
    """Smallest theta with false alarms (successes scored >= theta) <= FA_MAX."""
    ok = np.sort(d[~d.failed].score.values)
    cands = np.unique(np.concatenate([d.score.values, [np.inf]]))
    for t in cands:
        if (ok >= t).mean() <= FA_MAX:
            return float(t)
    return float("inf")


def report(df, th):
    out = []
    for c in CHECKS:
        d = df[df.check == c]
        t = th[c]
        flag = d.score >= t
        fails = d[d.failed]
        rec = float(flag[d.failed].mean())
        lo, hi = M.wilson(int(flag[d.failed].sum()), len(fails))[1:]
        row = dict(check=c, theta=t, n=len(d), recall_failures=rec, recall_lo=lo, recall_hi=hi,
                   false_alarm=float(flag[~d.failed].mean()), parse_fail=float(d.parse_fail.mean()),
                   missing=int(d.missing.sum()), ms_median=float(d.ms.median()) if "ms" in d and d.ms.notna().any() else np.nan)
        for o in ["failed_error", "failed_silent", "success_clear", "success_small"]:
            row[f"flag_{o}"] = float(flag[d.outcome == o].mean())
        out.append(row)
    return pd.DataFrame(out)


def main(what):
    if what == "tune":
        df = scores("dev")
        th = {c: threshold(df[df.check == c]) for c in CHECKS}
        FROZEN_Q3.write_text(json.dumps(dict(theta=th, fa_max=FA_MAX, region_pad=REGION_PAD, diff_thr=DIFF_THR,
                                             tuned_on="dev worked set (100 pairs)"), indent=2))
        t = report(df, th)
    else:
        if what == "test":
            tags = subprocess.run(["git", "tag", "--merged", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.split()
            if "pilot-prereg-w3" not in tags:
                sys.exit("test split needs the pilot-prereg-w3 tag")
        th = json.loads(FROZEN_Q3.read_text())["theta"]
        df = scores(what)
        t = report(df, th)
    (RES / "raw").mkdir(exist_ok=True)
    df.to_csv(RES / "raw" / f"q3_{what}_scores.csv", index=False)
    t.to_csv(RES / f"q3_{what}_summary.csv", index=False)
    print(t.to_string(index=False, float_format=lambda v: f"{v:.3f}"))


if __name__ == "__main__":
    main(sys.argv[1])
