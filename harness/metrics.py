"""Scoring with action-time truth, the cost model, and uncertainty.

A decision made after check time delta is scored against the first truth snapshot at or after delta.
Snapshots exist at offsets 0, .1, .25, .5, 1, 2, 4, 8, 16 s after current_b.
"""
import math

import numpy as np
import pandas as pd

C_PLAN = 6.51  # s, screenshot-to-action gap measured by W. Xu (2026, arXiv 2604.18860)
BASE = dict(stale=2.0, wrong=3.0)  # multiples of C_PLAN
P_VALUES = (0.01, 0.05, 0.20)


def snapshot_at(truth, delta_s):
    for s in truth:
        if s["offset"] >= delta_s - 1e-9:
            return s
    return truth[-1]


def lands(snap, pt):
    """A re-aim counts only if it lands on a hit cell (4 px grid) in that snapshot."""
    if not snap.get("hit_mask"):
        return False
    m = np.asarray(snap["hit_mask"], dtype=float)
    return bool(((np.abs(m[:, 0] - pt[0]) <= 2) & (np.abs(m[:, 1] - pt[1]) <= 2)).any())


def score(dec, rec):
    """Outcome of one decision on one pair."""
    truth = rec["truth"]
    t0 = truth[0]
    delta = dec["ms"] / 1000.0
    s = snapshot_at(truth, delta)
    a = dec["action"]
    out = dict(pair_id=rec["pair_id"], action=a, delta_s=delta, snap_offset=s["offset"],
               relevant=not t0["go_ok"], correct0=t0["correct_action"], escalated=dec.get("escalated", False),
               usd=dec.get("usd", 0.0), n_calls=len(dec.get("model_calls", [])))
    if a == "go":
        ok = s["go_ok"]
        out["outcome"] = "success" if ok else "stale"
        out["stale_during_check"] = (not ok) and t0["go_ok"]
    elif a == "reaim":
        ok = lands(s, dec["click"])
        out["outcome"] = "recovered" if ok else "wrong_reaim"
        out["stale_during_check"] = (not ok) and lands(t0, dec["click"])
    else:
        out["outcome"] = "false_replan" if s["go_ok"] else "replan"
        out["stale_during_check"] = False
    return out


def costs(df, stale=BASE["stale"], wrong=BASE["wrong"]):
    c = pd.Series(0.0, index=df.index)
    c[df.outcome == "stale"] = stale * C_PLAN
    c[df.outcome == "wrong_reaim"] = wrong * C_PLAN
    c[df.outcome.isin(["replan", "false_replan"])] = C_PLAN
    return c


def expected_seconds(df, p=0.05, stale=BASE["stale"], wrong=BASE["wrong"]):
    """mean delta + (1-p) * mean cost | no relevant change + p * mean cost | relevant change."""
    c = costs(df, stale, wrong)
    rel = df.relevant.values
    m0 = c[~rel].mean() if (~rel).any() else 0.0
    m1 = c[rel].mean() if rel.any() else 0.0
    return float(df.delta_s.mean() + (1 - p) * m0 + p * m1)


def per_1000(df, mask):
    return 1000.0 * float(mask.mean()) if len(df) else float("nan")


def wilson(k, n, z=1.96):
    if n == 0:
        return (float("nan"), float("nan"), float("nan"))
    ph = k / n
    den = 1 + z * z / n
    c = (ph + z * z / (2 * n)) / den
    h = z * math.sqrt(ph * (1 - ph) / n + z * z / (4 * n * n)) / den
    return (ph, max(0.0, c - h), min(1.0, c + h))


def cluster_bootstrap(df, stat, n_boot=2000, seed=0, cluster_cols=("page", "seed")):
    """95% CI of stat(df) resampling (page, seed) clusters with replacement."""
    rng = np.random.default_rng(seed)
    keys = df[list(cluster_cols)].astype(str).agg("|".join, axis=1)
    groups = {k: idx for k, idx in df.groupby(keys).indices.items()}
    names = list(groups)
    vals = []
    for _ in range(n_boot):
        pick = rng.integers(0, len(names), len(names))
        idx = np.concatenate([groups[names[i]] for i in pick])
        v = stat(df.iloc[idx])
        if v == v:
            vals.append(v)
    if not vals:
        return (float("nan"), float("nan"))
    return (float(np.percentile(vals, 2.5)), float(np.percentile(vals, 97.5)))


def motion_bin(m200):
    """Measured motion bins from motion_200ms (fraction of pixels changing >20/255 in 200 ms)."""
    if m200 <= 1e-4:
        return "static"
    if m200 <= 0.003:
        return "low"
    if m200 <= 0.008:
        return "med"
    return "high"
