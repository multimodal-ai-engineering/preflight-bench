"""Read-only real-site set: frozen pixel checks (C1, C2, C4, C4r) on public pages. Separate from the benchmark,
never pooled. Truth is read once from the live DOM right after the current frames (pages run in real time).

  python -m harness.realsite_eval   # -> results/full/realsite/pixel_decisions.csv, summary.csv
"""
import json
from multiprocessing import Pool
from pathlib import Path

import pandas as pd
from harness.metrics import wilson

from anchored import check as A
from anchored import whole_screen as WS
from harness.full_checks import MASK

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results/full/realsite"
FZ = json.loads((ROOT / "results/full/frozen_full.json").read_text())


def one(r):
    g = {k: A.gray(ROOT / v) for k, v in r["frames"].items()}
    cfg = {**A.DEFAULTS, "mask_thr": MASK[0], "mask_dilate": MASK[1]}
    F = A.features(g["planned_a"], g["planned_b"], g["current_a"], g["current_b"], r["planned_box"], cfg)
    ws = WS.scores(g["planned_a"], g["current_b"], r["click"])
    rows = []
    for cond, c in (("C1", FZ["C1"]), ("C2", FZ["C2"])):
        flag = ws["ssim"] < c["ssim_min"] or ws["frac_outside"] > c["frac_max"]
        rows.append(dict(cond=cond, action="replan" if flag else "go"))
    a, _, reason, _ = A.decide(F, r["planned_box"], {**A.DEFAULTS, **FZ["C4"]}, FZ.get("C4_mode", "reaim"))
    rows.append(dict(cond="C4", action=a, reason=reason))
    if FZ.get("deviation"):
        a, _, reason, _ = A.decide(F, r["planned_box"], {**A.DEFAULTS, **FZ["deviation"]["exploratory_C4r"]}, "reaim")
        rows.append(dict(cond="C4r", action=a, reason=reason))
    return [dict(x, site=r["site"], k=r["k"], settled=r["settled"]) for x in rows]


def main():
    rs = [json.loads(l) for l in (ROOT / "data/realsite/pairs.jsonl").read_text().splitlines() if l.strip()]
    rs = [r for r in rs if not r.get("error")]
    with Pool(4) as p:
        d = pd.DataFrame([x for rows in p.map(one, rs) for x in rows])
    OUT.mkdir(parents=True, exist_ok=True)
    d.to_csv(OUT / "pixel_decisions.csv", index=False)
    out = []
    for cond, g in d.groupby("cond"):
        neg = g[~g.settled]
        k, n = int((neg.action != "go").sum()), len(neg)
        lo, hi = wilson(k, n)[-2:]
        out.append(dict(cond=cond, pairs=len(g), still_valid=n, false_alarms=k, fa_rate=k / n, fa_lo=lo, fa_hi=hi,
                        settled_pairs=int(g.settled.sum()), settled_caught=int((g[g.settled].action != "go").sum())))
    s = pd.DataFrame(out)
    s.to_csv(OUT / "summary.csv", index=False)
    print(s.round(3).to_string(index=False))
    print(d[d.cond == "C4"].groupby("site").apply(lambda g: (g.action != "go").mean()).round(3).to_string())


if __name__ == "__main__":
    main()
