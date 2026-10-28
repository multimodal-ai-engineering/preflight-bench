"""Spot checks (Step 4.2): 3 BOOK and 3 GOV pages drawn with a fixed seed, recomputed by hand from the preregistered
definitions and compared with analyze.page_record. Network idle is found here by sweeping time forward past merged in-flight spans instead of
analyze.py's candidate-point search.

  python commercial/spot_check.py
"""
import random

import analyze as A

SEED = 20261027


def merged_busy(iv, t_from):
    """In-flight spans (merged) that reach past t_from; an unfinished request runs to infinity."""
    spans = sorted((s, e if e is not None else float("inf")) for s, e in iv)
    out = []
    for s, e in spans:
        if e <= t_from:
            continue
        if out and s <= out[-1][1]:
            out[-1][1] = max(out[-1][1], e)
        else:
            out.append([s, e])
    return out


def idle_by_sweep(iv, t0, quiet=500, horizon_ms=200_000):
    """First integer ms t >= t0 with no request in flight anywhere in (t, t + quiet). None if none before the horizon."""
    busy = merged_busy(iv, t0)
    t = int(t0) if t0 == int(t0) else int(t0) + 1
    t = max(t, t0)
    while t < t0 + horizon_ms:
        hit = next((b for b in busy if b[0] < t + quiet and b[1] > t), None)
        if hit is None:
            return t
        t = max(t + 1, hit[1]) if hit[1] != float("inf") else t0 + horizon_ms
    return None


def by_hand(p, r):
    t0 = A.fnum(p["dcl_end_ms"])
    if not t0 or t0 <= 0:
        t0 = A.fnum(p["dcl_start_ms"])
    load = A.fnum(p["load_ms"])
    shifts = A.parse_shifts(p["shifts"])
    iv = r["intervals"]
    idle = idle_by_sweep(iv, t0) if r["n_parsed"] == r["n_requests"] else None
    T = {"S0": t0, "S1": t0 + 500, "S2": t0 + 1000, "S4": load if load and load >= t0 else None}
    if r["n_parsed"] == r["n_requests"]:
        quiet_at = None if idle is None else idle + 500
        T["S5"] = t0 + 3000 if (quiet_at is None or quiet_at > t0 + 3000) else quiet_at
        ends = [e for _, e in iv if e is not None]
        end = max([A.fnum(p["fully_loaded_ms"]) or 0, load or 0] + ends + [t for t, _ in shifts])
        T["S5u"] = quiet_at if quiet_at is not None else end
    y = {k: (None if t is None else int(sum(sc for ts, sc in shifts if t < ts <= t + 6500) > 1e-4)) for k, t in T.items()}
    return t0, load, idle, T, y, shifts


def main():
    pages, req = A.load_pages("desktop")
    groups, _ = A.assign_groups(pages)
    rng = random.Random(SEED)
    bad = 0
    for g in ("BOOK", "GOV"):
        elig = [p for p in groups[g] if p["page"] in req and A.page_record(p, req[p["page"]]) is not None
                and A.page_record(p, req[p["page"]])["shifts_ok"]]
        for p in rng.sample(sorted(elig, key=lambda x: x["page"]), 3):
            r = req[p["page"]]
            rec = A.page_record(p, r)
            t0, load, idle, T, y, shifts = by_hand(p, r)
            print(f"== {g} rank {p['rank']}  (page not named)")
            print(f"   DOM ready t0 {t0:.0f} ms, load {load}, fully loaded {p['fully_loaded_ms']}, CLS {p['cls']}")
            print(f"   requests {r['n_requests']} (parsed {r['n_parsed']}, unfinished {sum(1 for _, e in r['intervals'] if e is None)})")
            busy = merged_busy(r["intervals"], t0)
            print("   in-flight spans after t0:", ", ".join(f"{s:.0f}-{e:.0f}" for s, e in busy[:8]) + (" ..." if len(busy) > 8 else ""))
            print(f"   network idle by hand: window starts {idle}, quiet at {None if idle is None else idle + 500}; analyze.py: {rec['idle_start']}")
            print("   shifts (ms:score):", ", ".join(f"{t:.0f}:{s:.4f}" for t, s in shifts[:12]) + (" ..." if len(shifts) > 12 else ""))
            for k in A.RULES:
                th, ta = T.get(k), rec.get(f"T_{k}")
                ok = (th is None and ta is None) or (th is not None and ta is not None and abs(th - ta) <= 1) and y.get(k) == rec.get(f"y_{k}")
                bad += not ok
                print(f"   {k:4s} T by hand {th if th is None else round(th)}  analyze {ta if ta is None else round(ta)}  "
                      f"shift by hand {y.get(k)}  analyze {rec.get(f'y_{k}')}  censored {rec.get(f'cens_{k}')}  {'OK' if ok else 'DISAGREE'}")
    print("disagreements:", bad)


if __name__ == "__main__":
    main()
