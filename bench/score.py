"""PreflightBench-Live scorer. The author runs it; test labels stay in private/.

  python -m bench.score SUBMISSION.csv [--split test|dev]

Submission format (CSV, header required):  pair_id,question,prediction,score,reaim_x,reaim_y
  question    settled | dialog | worked
  prediction  1 if the check says positive (settled: the planned click would no longer land; dialog: a dialog is
              shown; worked: the last action FAILED), else 0
  score       optional real number, higher = more likely positive (used for recall at 2% false alarms)
  reaim_x/y   optional, settled rows only: where the check would click instead (page pixels); empty = no re-aim
Output per question and tier: recall and false-alarm rate of `prediction`; recall at a 2% false-alarm rate from
`score` (threshold chosen on the scored split itself, so it is an upper bound; the paper's numbers use dev
thresholds); for settled rows with a re-aim: share landing on the target (re-aim recovery) and wrong re-aims.
"""
import argparse, json, sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


def labels(split):
    if split == "dev":
        a = [json.loads(l) for l in (ROOT / "data/full/dev/pairs.jsonl").read_text().splitlines() if l.strip()]
        w = [json.loads(l) for l in (ROOT / "data/full/dev/worked.jsonl").read_text().splitlines() if l.strip()]
    else:
        a = [json.loads(l) for l in (ROOT / "private/full_test_pairs_labels.jsonl").read_text().splitlines() if l.strip()]
        w = [json.loads(l) for l in (ROOT / "private/full_test_worked_labels.jsonl").read_text().splitlines() if l.strip()]
    lab = {}
    for r in a:
        lab[(r["pair_id"], "settled")] = (r["tier"], bool(r["settled"]), r["truth"][0])
        lab[(r["pair_id"], "dialog")] = (r["tier"], bool(r["dialog"]), None)
    for r in w:
        lab[(r["pair_id"], "worked")] = (r["tier"], bool(r["worked"]), None)
    return lab


def recall_at(scores, y, fa=0.02):
    neg = np.sort(scores[~y])
    for t in np.unique(np.concatenate([scores, [np.inf]])):
        if (neg >= t).mean() <= fa:
            return float((scores[y] >= t).mean()) if y.any() else float("nan")
    return 0.0


def lands(truth, x, y):
    return any(abs(px - x) <= 2 and abs(py - y) <= 2 for px, py in (truth.get("hit_mask") or []))


def main(path, split):
    sub = pd.read_csv(path)
    need = {"pair_id", "question", "prediction"}
    if not need <= set(sub.columns):
        sys.exit(f"submission needs columns {sorted(need)}")
    lab = labels(split)
    rows = []
    for _, s in sub.iterrows():
        k = (s.pair_id, s.question)
        if k not in lab:
            continue
        tier, y, t0 = lab[k]
        rx, ry = s.get("reaim_x"), s.get("reaim_y")
        re = s.question == "settled" and pd.notna(rx) and pd.notna(ry)
        rows.append(dict(question=s.question, tier=tier, y=y, pred=bool(s.prediction),
                         score=float(s["score"]) if "score" in sub and pd.notna(s.get("score")) else float(s.prediction),
                         reaim=re, reaim_ok=lands(t0, float(rx), float(ry)) if re else False))
    d = pd.DataFrame(rows)
    out = []
    for (q, tier), g in d.groupby(["question", "tier"]):
        y = g.y.values
        o = dict(question=q, tier=tier, n=len(g), positives=int(y.sum()),
                 recall=float(g.pred[g.y].mean()) if y.any() else np.nan, false_alarm=float(g.pred[~g.y].mean()) if (~y).any() else np.nan,
                 recall_at_2pct_fa=recall_at(g.score.values, y))
        if q == "settled":
            o.update(reaims=int(g.reaim.sum()), reaim_correct=int(g.reaim_ok.sum()), wrong_reaims=int((g.reaim & ~g.reaim_ok).sum()))
        out.append(o)
    print(pd.DataFrame(out).to_string(index=False, float_format=lambda v: f"{v:.3f}"))
    missing = len(lab) - len(d)
    print(f"{len(d)} scored rows; {missing} labelled (pair, question) items not in the submission")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("submission")
    ap.add_argument("--split", default="test")
    a = ap.parse_args()
    main(a.submission, a.split)
