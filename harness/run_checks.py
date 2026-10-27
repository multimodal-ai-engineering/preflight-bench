"""Wave 2 harness: run the pixel checks (C0-C4 and reference rows) on a split, tune on dev, score with action-time truth.

  python -m harness.run_checks tune            # dev: grid search, writes results/pilot/frozen_w2.json + tuning logs
  python -m harness.run_checks test            # test: frozen thresholds only, needs tag pilot-prereg-w2
  python -m harness.run_checks dev             # dev: frozen thresholds, for checking

Feature extraction depends only on the mask settings, so it is cached per (split, mask_thr, mask_dilate) and the
grid search re-runs only the threshold logic. Check time per pair is the measured compute time of that pair,
plus the 200 ms frame wait for the anchored modes.
"""
import argparse, itertools, json, pickle, platform, subprocess, sys, time
from pathlib import Path

import numpy as np
import pandas as pd

from anchored import check as A
from anchored import whole_screen as WS
from harness import metrics as M

ROOT = Path(__file__).resolve().parents[1]
RES = ROOT / "results" / "pilot"
CACHE = RES / "cache"
FROZEN = RES / "frozen_w2.json"

MASKS = [(8, 9), (12, 9), (20, 9), (12, 5), (12, 15)]
GRID = dict(tau_in=[0.80, 0.85, 0.90, 0.95], tau_match=[0.70, 0.80, 0.85, 0.90, 0.95],
            m_unique=[0.0, 0.02, 0.05, 0.10, 0.15], tau_target=[0.5, 0.6, 0.7, 0.8, 0.9],
            b=[6.0, 12.0, 18.0, 30.0], d=[10.0, 25.0, 50.0])
WRONG_MAX = 0.01   # wrong re-aims as a share of re-aims on dev
FA_TARGET = 0.02   # C2 false-alarm rate on Tier 1 dev


def git_hash():
    return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()


def hardware():
    chip = subprocess.run(["sysctl", "-n", "machdep.cpu.brand_string"], capture_output=True, text=True).stdout.strip()
    mem = int(subprocess.run(["sysctl", "-n", "hw.memsize"], capture_output=True, text=True).stdout.strip() or 0) / 2**30
    return f"{chip or platform.processor()}, {mem:.0f} GB, {platform.system()} {platform.release()}"


def load(split):
    recs = [json.loads(l) for l in (ROOT / f"data/pilot/{split}/pairs.jsonl").read_text().splitlines() if l.strip()]
    if split == "test":
        lab = {}
        for l in (ROOT / "private/test_pairs_labels.jsonl").read_text().splitlines():
            if l.strip():
                j = json.loads(l)
                lab[j["pair_id"]] = j
        for r in recs:
            r.update({k: v for k, v in lab[r["pair_id"]].items() if k != "pair_id"})
    return recs


def frames(r):
    return {k: A.gray(ROOT / v) for k, v in r["frames"].items()}


def feature_table(split, recs, thr, dil, refresh=False):
    """pair_id -> (features, compute_ms). Cached on disk."""
    CACHE.mkdir(parents=True, exist_ok=True)
    p = CACHE / f"{split}_feat_m{thr}_d{dil}.pkl"
    if p.exists() and not refresh:
        return pickle.loads(p.read_bytes())
    cfg = {**A.DEFAULTS, "mask_thr": thr, "mask_dilate": dil}
    out = {}
    for r in recs:
        f = frames(r)
        t0 = time.perf_counter()
        F = A.features(f["planned_a"], f["planned_b"], f["current_a"], f["current_b"], r["planned_box"], cfg)
        out[r["pair_id"]] = (F, (time.perf_counter() - t0) * 1000)
    p.write_bytes(pickle.dumps(out))
    return out


def ws_table(split, recs, refresh=False):
    """pair_id -> (scores, compute_ms) for the whole-screen check."""
    CACHE.mkdir(parents=True, exist_ok=True)
    p = CACHE / f"{split}_ws.pkl"
    if p.exists() and not refresh:
        return pickle.loads(p.read_bytes())
    out = {}
    for r in recs:
        f = frames(r)
        t0 = time.perf_counter()
        s = WS.scores(f["planned_a"], f["current_b"], r["click"])
        out[r["pair_id"]] = (s, (time.perf_counter() - t0) * 1000)
    p.write_bytes(pickle.dumps(out))
    return out


class Scorer:
    """Memoized M.score: outcome depends only on (pair, action, click, snapshot)."""

    def __init__(self, recs):
        self.recs = {r["pair_id"]: r for r in recs}
        self.memo = {}

    def __call__(self, pid, action, click, ms, **extra):
        r = self.recs[pid]
        snap = M.snapshot_at(r["truth"], ms / 1000.0)["offset"]
        key = (pid, action, round(click[0], 1), round(click[1], 1), snap)
        o = self.memo.get(key)
        if o is None:
            o = M.score(dict(action=action, click=click, ms=ms), r)
            self.memo[key] = o
        o = dict(o, delta_s=ms / 1000.0, **extra)
        o.update(page=r["page"], seed=r["seed"], tier=r["tier"], motion=r["motion"], event=r["event"],
                 motion_bin=M.motion_bin(r["motion_200ms"]), motion_200ms=r["motion_200ms"])
        return o


def run_anchored(recs, feats, cfg, mode, scorer, cond):
    rows = []
    for r in recs:
        F, fms = feats[r["pair_id"]]
        t0 = time.perf_counter()
        action, click, reason, _ = A.decide(F, r["planned_box"], cfg, mode)
        ms = fms + (time.perf_counter() - t0) * 1000 + A.FRAME_WAIT_MS
        rows.append(scorer(r["pair_id"], action, click, ms, cond=cond, reason=reason))
    return rows


def run_ws(recs, wst, cfg, scorer, cond):
    cfg = {**WS.PUBLISHED, **cfg}
    rows = []
    for r in recs:
        s, ms = wst[r["pair_id"]]
        flag = s["ssim"] < cfg["ssim_min"] or s["frac_outside"] > cfg["frac_max"]
        rows.append(scorer(r["pair_id"], "replan" if flag else "go", r["click"], ms, cond=cond,
                           reason="flag" if flag else "unchanged"))
    return rows


def run_refs(recs, scorer):
    rows = []
    for r in recs:
        t0 = r["truth"][0]
        rows.append(scorer(r["pair_id"], "go", r["click"], 0.0, cond="C0", reason="no_check"))
        rows.append(scorer(r["pair_id"], "replan", r["click"], 0.0, cond="always_replan", reason="always"))
        a = t0["correct_action"]
        if a == "reaim":
            x, y, w, h = t0["target_box"]
            click = (x + w / 2, y + h / 2)
        else:
            click = r["click"]
        rows.append(scorer(r["pair_id"], a, click, 0.0, cond="oracle", reason="truth"))
    return rows


# ---------- summaries ----------

def summarize(df):
    """One row of headline metrics for a condition on a set of pairs."""
    n = len(df)
    nr = df[~df.relevant]
    reaims = df[df.action == "reaim"]
    moved = df[df.correct0 == "reaim"]
    wrong = int((reaims.outcome == "wrong_reaim").sum())
    wr = M.wilson(wrong, len(reaims))
    return dict(
        n=n,
        false_alarm=float((nr.action == "replan").mean()) if len(nr) else np.nan,
        false_replan_per_1000=M.per_1000(df, df.outcome == "false_replan"),
        stale_per_1000=M.per_1000(df, df.outcome == "stale"),
        stale_during_check_per_1000=M.per_1000(df, df.stale_during_check),
        reaim_recovery=float((moved.outcome == "recovered").mean()) if len(moved) else np.nan,
        n_moved=len(moved), n_reaims=len(reaims), wrong_reaims=wrong,
        wrong_share=wr[0], wrong_lo=wr[1], wrong_hi=wr[2],
        ms_median=float(df.delta_s.median() * 1000), ms_p95=float(df.delta_s.quantile(0.95) * 1000),
        sec_p01=M.expected_seconds(df, 0.01), sec_p05=M.expected_seconds(df, 0.05), sec_p20=M.expected_seconds(df, 0.20),
    )


def objective(df):
    """Expected seconds per step at p=0.05, infinite if re-find errors exceed WRONG_MAX of re-aims.

    A re-find error is a wrong re-aim that already misses at offset 0. Wrong re-aims caused only by the page moving
    during the check are excluded from this cap (with ~15 dev re-aims, one such pair makes every config infeasible)
    but count in every reported metric. Deviation recorded in docs/PREREG_PILOT_W2.md.
    """
    re = df.action == "reaim"
    refind_err = re & (df.outcome == "wrong_reaim") & ~df.stale_during_check
    if re.any() and refind_err.sum() / re.sum() > WRONG_MAX:
        return float("inf")
    return M.expected_seconds(df, 0.05)


# ---------- tuning ----------

def tune():
    recs = load("dev")
    t1 = [r for r in recs if r["tier"] == 1]
    scorer = Scorer(recs)
    log = []
    best = {}
    for mode, cond in (("reaim", "C4"), ("replan_only", "C3")):
        best[cond] = (float("inf"), None)
    keys = list(GRID)
    for thr, dil in MASKS:
        print(f"features mask_thr={thr} mask_dilate={dil}", flush=True)
        feats = feature_table("dev", recs, thr, dil)
        for vals in itertools.product(*GRID.values()):
            cfg = {**A.DEFAULTS, "mask_thr": thr, "mask_dilate": dil, **dict(zip(keys, vals))}
            for mode, cond in (("reaim", "C4"), ("replan_only", "C3")):
                if cond == "C3" and (cfg["tau_match"] != GRID["tau_match"][0] or cfg["m_unique"] != GRID["m_unique"][0]):
                    continue  # C3 never searches; tau_match and m_unique do not matter
                df = pd.DataFrame(run_anchored(t1, feats, cfg, mode, scorer, cond))
                obj = objective(df)
                log.append(dict(cond=cond, mask_thr=thr, mask_dilate=dil, **dict(zip(keys, vals)), sec_p05=obj))
                if obj < best[cond][0]:
                    best[cond] = (obj, cfg)
        print({c: round(b[0], 4) for c, b in best.items()}, flush=True)
    pd.DataFrame(log).to_csv(RES / "tuning_w2_anchored.csv", index=False)

    # C2: whole-screen thresholds at a 2% false-alarm rate on Tier 1 dev.
    wst = ws_table("dev", recs)
    ss = np.array([wst[r["pair_id"]][0]["ssim"] for r in t1])
    fr = np.array([wst[r["pair_id"]][0]["frac_outside"] for r in t1])
    c2best, c2log = (float("inf"), None), []
    for smin in np.unique(np.concatenate([np.round(ss, 4), [0.0]])):
        for fmax in np.unique(np.concatenate([np.round(fr, 5), [1.0]])):
            cfg = dict(ssim_min=float(smin), frac_max=float(fmax))
            df = pd.DataFrame(run_ws(t1, wst, cfg, scorer, "C2"))
            fa = float((df[~df.relevant].action == "replan").mean())
            if fa > FA_TARGET:
                continue
            obj = M.expected_seconds(df, 0.05)
            c2log.append(dict(**cfg, fa=fa, sec_p05=obj))
            if obj < c2best[0]:
                c2best = (obj, cfg)
    pd.DataFrame(c2log).to_csv(RES / "tuning_w2_c2.csv", index=False)

    c4 = {k: best["C4"][1][k] for k in ["mask_thr", "mask_dilate", *keys]}
    c3 = {k: best["C3"][1][k] for k in ["mask_thr", "mask_dilate", *keys]}
    frozen = dict(C1=dict(WS.PUBLISHED), C2={**WS.PUBLISHED, **c2best[1]}, C3=c3, C4=c4,
                  dev_objective=dict(C2=c2best[0], C3=best["C3"][0], C4=best["C4"][0]),
                  tuned_on="Tier 1 dev", commit=git_hash(), date=time.strftime("%Y-%m-%d"), hardware=hardware(),
                  constraint=f"re-find errors (wrong re-aims already wrong at offset 0) <= {WRONG_MAX:.0%} of re-aims on dev; C2 false alarms <= {FA_TARGET:.0%}")
    FROZEN.write_text(json.dumps(frozen, indent=2))
    print(json.dumps(frozen, indent=2))
    tradeoff(recs, scorer, c4)


def tradeoff(recs, scorer, c4, split="dev", tag=""):
    """Re-aim recovery against wrong re-aims as m_unique varies, other C4 thresholds fixed."""
    t1 = [r for r in recs if r["tier"] == 1]
    feats = feature_table(split, recs, c4["mask_thr"], c4["mask_dilate"])
    rows = []
    for mu in [0.0, 0.01, 0.02, 0.03, 0.05, 0.075, 0.10, 0.15, 0.20, 0.30]:
        df = pd.DataFrame(run_anchored(t1, feats, {**A.DEFAULTS, **c4, "m_unique": mu}, "reaim", scorer, "C4"))
        s = summarize(df)
        rows.append(dict(m_unique=mu, reaim_recovery=s["reaim_recovery"], wrong_share=s["wrong_share"],
                         wrong_reaims=s["wrong_reaims"], n_reaims=s["n_reaims"], sec_p05=s["sec_p05"]))
    out = pd.DataFrame(rows)
    out.to_csv(RES / f"tradeoff_c4_{split}{tag}.csv", index=False)
    print(out.to_string(index=False))


# ---------- evaluation ----------

def evaluate(split):
    if split == "test":
        tags = subprocess.run(["git", "tag", "--merged", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.split()
        if "pilot-prereg-w2" not in tags:
            sys.exit("test split needs the pilot-prereg-w2 tag in HEAD's history")
    fz = json.loads(FROZEN.read_text())
    recs = load(split)
    scorer = Scorer(recs)
    rows = run_refs(recs, scorer)
    wst = ws_table(split, recs, refresh=True)
    rows += run_ws(recs, wst, fz["C1"], scorer, "C1")
    rows += run_ws(recs, wst, fz["C2"], scorer, "C2")
    for cond, mode in (("C3", "replan_only"), ("C4", "reaim")):
        c = fz[cond]
        feats = feature_table(split, recs, c["mask_thr"], c["mask_dilate"], refresh=True)
        rows += run_anchored(recs, feats, {**A.DEFAULTS, **c}, mode, scorer, cond)
    df = pd.DataFrame(rows)
    meta = dict(split=split, commit=git_hash(), date=time.strftime("%Y-%m-%d %H:%M"), hardware=hardware(),
                n_pairs=len(recs), seeds=sorted({r["seed"] for r in recs}))
    raw = RES / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    df.to_csv(raw / f"w2_{split}_decisions.csv", index=False)
    (raw / f"w2_{split}_meta.json").write_text(json.dumps(meta, indent=2))
    tables(df, split, meta)
    if split == "test":
        tradeoff(recs, scorer, fz["C4"], split="test")
    return df


def tables(df, split, meta):
    order = ["C0", "C1", "C2", "C3", "C4", "oracle", "always_replan"]
    out = []
    for tier in (0, 1):
        for cond in order:
            d = df[(df.cond == cond) & (df.tier == tier)]
            s = summarize(d)
            lo, hi = M.cluster_bootstrap(d, lambda x: M.expected_seconds(x, 0.05))
            fa_lo, fa_hi = M.cluster_bootstrap(d, lambda x: float((x[~x.relevant].action == "replan").mean()) if (~x.relevant).any() else float("nan"))
            out.append(dict(tier=tier, cond=cond, **s, sec_p05_lo=lo, sec_p05_hi=hi, fa_lo=fa_lo, fa_hi=fa_hi))
    t = pd.DataFrame(out)
    t.to_csv(RES / f"w2_{split}_summary.csv", index=False)
    bins = []
    for cond in order:
        for b in ["static", "low", "med", "high"]:
            d = df[(df.cond == cond) & (df.tier == 1) & (df.motion_bin == b)]
            if len(d):
                bins.append(dict(cond=cond, motion_bin=b, **summarize(d)))
    pd.DataFrame(bins).to_csv(RES / f"w2_{split}_by_motion.csv", index=False)
    lk = []
    for cond in ["C3", "C4"]:
        d = df[(df.cond == cond) & (df.event == "moved_lookalike") & (df.tier == 1)]
        lk.append(dict(cond=cond, **summarize(d)))
    pd.DataFrame(lk).to_csv(RES / f"w2_{split}_lookalike.csv", index=False)
    cols = ["tier", "cond", "n", "false_alarm", "fa_lo", "fa_hi", "false_replan_per_1000", "stale_per_1000",
            "stale_during_check_per_1000", "reaim_recovery", "n_reaims", "wrong_reaims", "wrong_hi",
            "ms_median", "ms_p95", "sec_p05", "sec_p05_lo", "sec_p05_hi"]
    print(json.dumps(meta))
    print(t[cols].to_string(index=False, float_format=lambda v: f"{v:.3f}"))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("what", choices=["tune", "dev", "test"])
    a = ap.parse_args()
    tune() if a.what == "tune" else evaluate(a.what)
