"""Run the pixel check on preflight-bench straight from the Hugging Face Hub, with LanceDB.

  uv run --with lancedb python lance_quickstart.py                       # 200 dev pairs
  uv run --with lancedb python lance_quickstart.py --n 0                 # every dev pair
  uv run --with lancedb python lance_quickstart.py --out my_check.csv    # also write a CSV for bench.score

There is no generation step and no full download: LanceDB reads only the rows and frames it needs from the Hub.
For each planned click the check sees four screenshots (two when the agent planned, two 6.5 s later) and the box
the agent planned to click, and answers "go" (the click will still land) or "re-plan". The truth (`stale`) comes
from the page itself at the moment of the click. To test your own check, replace the call to `check` in `run`.
"""
import argparse, csv, io, json, statistics
from pathlib import Path

import lancedb
from PIL import Image

from anchored.check import DEFAULTS, check

ROOT = Path(__file__).resolve().parent
HUB = "hf://datasets/multimodal-ai-engineering/preflight-bench/data"
FRAMES = ["planned_a", "planned_b", "current_a", "current_b"]


def rows(table, ids, size=32):
    """Fetch rows with their four frames, a few at a time, so memory stays small."""
    for i in range(0, len(ids), size):
        chunk = ids[i:i + size]
        where = "pair_id IN (" + ", ".join(f"'{p}'" for p in chunk) + ")"
        yield from (table.search().where(where).select(["pair_id", "page", "event", "stale", "planned_box"] + FRAMES)
                    .limit(len(chunk)).to_list())


def run(r, cfg):
    f = {k: Image.open(io.BytesIO(r[k])) for k in FRAMES}
    return check((f["planned_a"], f["planned_b"]), (f["current_a"], f["current_b"]), r["planned_box"],
                 mode="replan_only", config=cfg)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="dev", choices=["dev", "test"])
    ap.add_argument("--n", type=int, default=200, help="number of pairs (0 = the whole split)")
    ap.add_argument("--out", help="write a submission CSV in the format of src/bench/score.py")
    a = ap.parse_args()
    frozen = json.loads((ROOT / "results/full/frozen_full.json").read_text())
    cfg = {**DEFAULTS, **frozen["C4"], "mask_thr": frozen["mask"][0], "mask_dilate": frozen["mask"][1]}

    clicks = lancedb.connect(HUB).open_table("click_pairs")
    ids = [r["pair_id"] for r in clicks.search().where(f"split = '{a.split}'").select(["pair_id"])
           .limit(clicks.count_rows()).to_list()]
    ids = sorted(ids)[:a.n] if a.n else sorted(ids)

    tp = fp = fn = tn = 0
    ms, out = [], []
    for r in rows(clicks, ids):
        d = run(r, cfg)
        stale, flagged = bool(r["stale"]), d.action != "go"
        tp += stale and flagged; fn += stale and not flagged; fp += flagged and not stale; tn += not (stale or flagged)
        ms.append(d.ms)
        out.append({"pair_id": r["pair_id"], "question": "settled", "prediction": int(flagged), "score": "",
                    "reaim_x": "", "reaim_y": ""})
        print(f"{r['page']:14s} {r['event']:16s} truth={'stale' if stale else 'valid':5s}  check={d.action:7s} "
              f"({d.reason}, {d.ms:.0f} ms)")
    print(f"\n{len(ids)} {a.split} pairs: caught {tp} of {tp + fn} stale clicks, {fp} false alarms on {fp + tn} valid "
          f"clicks, median {statistics.median(ms) / 1000:.2f} s per check (including the 0.2 s between frames)")
    if a.out:
        with open(a.out, "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(out[0]))
            w.writeheader(); w.writerows(out)
        print(f"wrote {a.out}: score it with  uv run python -m bench.score {a.out} --split {a.split}")


if __name__ == "__main__":
    main()
