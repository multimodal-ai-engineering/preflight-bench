"""Exploratory validation of the layout-shift signal on the 31-page study (Addition 1 visits), run before the
preregistration was written. Writes inputs/validation_visits.csv: one row per visit with whether a layout shift
happened between the planning screenshot and the end of tracking (CLS rose by more than 1e-4), the number of
tracked targets and how many were invalidated (go_ok false at 0.5, 1, 2 or 6.5 s, Addition 1's primary outcome).

  python3 validate_proxy.py ../private/realsite_add/visits.jsonl
"""
import csv, json, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SHIFT_EPS = 1e-4


def visits(path):
    for line in open(path):
        if not line.strip():
            continue
        r = json.loads(line)
        if r.get("error") or not r.get("offsets") or not r.get("ls_supported"):
            continue
        if r.get("cls_plan") is None or r.get("cls_end") is None:
            continue
        bad = {}
        for o in r["offsets"]:
            for t in o["truth"]:
                bad[t["i"]] = bad.get(t["i"], False) or (not t["go_ok"])
        yield dict(site=r["site"], rule=r["rule"], round=r["round"],
                   shift=int(r["cls_end"] - r["cls_plan"] > SHIFT_EPS), tracks=len(bad), stale=sum(bad.values()))


def main(path):
    rows = list(visits(path))
    out = HERE / "inputs" / "validation_visits.csv"
    out.parent.mkdir(exist_ok=True)
    with out.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    s1 = [r for r in rows if r["shift"]]
    s0 = [r for r in rows if not r["shift"]]
    b = sum(r["stale"] for r in s1) / sum(r["tracks"] for r in s1)
    a = sum(r["stale"] for r in s0) / sum(r["tracks"] for r in s0)
    sens = sum(r["stale"] for r in s1) / sum(r["stale"] for r in rows)
    print(f"{len(rows)} visits, {len({r['site'] for r in rows})} sites -> {out.relative_to(HERE)}")
    print(f"stale share with a shift after the screenshot b = {b:.4f}; without a = {a:.4f}; share of stale clicks in shift visits = {sens:.3f}")


if __name__ == "__main__":
    main(sys.argv[1])
