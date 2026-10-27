"""Quick start: run the pixel check on generated screenshot pairs and compare it with the page's own answer.

  python -m generator.make_full --only 40 --part action      # ~40 pairs into data/full_smoke/ (a few minutes)
  python quickstart.py                                       # pixel check on the dev pairs, with the paper's thresholds

For each pair the check sees four screenshots (two when the agent planned, two 6.5 s later) and the box the agent
planned to click. It answers "go" (the click will still land) or "re-plan" (the target moved, was covered or is gone).
The truth comes from the page itself at the moment of the click, never from the pixels.
"""
import argparse, json
from pathlib import Path

from anchored.check import DEFAULTS, check

ROOT = Path(__file__).resolve().parent


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pairs", default="data/full_smoke/dev/pairs.jsonl")
    a = ap.parse_args()
    frozen = json.loads((ROOT / "results/full/frozen_full.json").read_text())
    cfg = {**DEFAULTS, **frozen["C4"], "mask_thr": frozen["mask"][0], "mask_dilate": frozen["mask"][1]}
    recs = [json.loads(l) for l in (ROOT / a.pairs).read_text().splitlines() if l.strip()]
    recs = [r for r in recs if "settled" in r]  # pairs with labels (dev split)
    if not recs:
        raise SystemExit(f"no labelled pairs in {a.pairs}; generate some first (see the docstring)")
    tp = fp = fn = tn = 0
    for r in recs:
        f = {k: ROOT / v for k, v in r["frames"].items()}
        d = check((f["planned_a"], f["planned_b"]), (f["current_a"], f["current_b"]), r["planned_box"],
                  mode="replan_only", config=cfg)
        stale, flagged = bool(r["settled"]), d.action != "go"
        tp += stale and flagged; fn += stale and not flagged; fp += flagged and not stale; tn += not (stale or flagged)
        print(f"{r['kind']:14s} {r['event']:16s} truth={'stale' if stale else 'valid':5s}  check={d.action:7s} "
              f"({d.reason}, {d.ms:.0f} ms)")
    print(f"\n{len(recs)} pairs: caught {tp} of {tp + fn} stale clicks, {fp} false alarms on {fp + tn} valid clicks")


if __name__ == "__main__":
    main()
