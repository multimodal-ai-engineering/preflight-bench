"""Full study: pixel features, tuning on dev, decisions and per-question scores. No model is called here.

  python -m harness.full_checks features dev|test     # cached pixel features (multiprocess)
  python -m harness.full_checks tune                  # C4 grid, C2 at 2% FA, dialog detector, worked pixel -> results/full/frozen_full.json
  python -m harness.full_checks decisions dev|test    # C0, C1, C2, C4, C7 decisions + scores -> results/full/raw/
"""
import itertools, json, os, pickle, subprocess, sys, time
from multiprocessing import Pool
from pathlib import Path

import numpy as np
import pandas as pd

from anchored import check as A
from anchored import dialog as D
from anchored import whole_screen as WS
from harness import metrics as M
from harness.run_checks import Scorer, summarize

ROOT = Path(__file__).resolve().parents[2]
RES = ROOT / "results/full"
CACHE = RES / "cache"
FROZEN = RES / "frozen_full.json"
MASK = (12, 3)  # pilot's frozen motion mask (thr, dilate); not re-tuned
GRID = dict(tau_in=[0.4, 0.5, 0.6], tau_match=[0.8, 0.85, 0.9], m_unique=[0.1, 0.15, 0.2],
            tau_target=[0.6, 0.7, 0.8], b=[4.5, 6.0, 9.0], d=[25.0, 35.0, 50.0])
WRONG_MAX, FA = 0.01, 0.02


def load(split, part="action"):
    name = "pairs" if part == "action" else "worked"
    rs = [json.loads(l) for l in (ROOT / f"data/full/{split}/{name}.jsonl").read_text().splitlines() if l.strip()]
    if split == "test":
        if "prereg-v1" not in subprocess.run(["git", "tag", "--merged", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.split() \
                and not os.environ.get("PREFLIGHT_REGENERATE"):
            sys.exit("test labels need prereg-v1")
        lab = {j["pair_id"]: j for j in map(json.loads, (ROOT / f"private/full_test_{name}_labels.jsonl").read_text().splitlines()) if j}
        rs = [dict(lab[r["pair_id"]]) for r in rs]
    for r in rs:
        r["page"] = r["kind"]  # the pilot scorer groups by page
    return rs


def _feat(r):
    g = {k: A.gray(ROOT / v) for k, v in r["frames"].items()}
    cfg = {**A.DEFAULTS, "mask_thr": MASK[0], "mask_dilate": MASK[1]}
    t0 = time.perf_counter()
    F = A.features(g["planned_a"], g["planned_b"], g["current_a"], g["current_b"], r["planned_box"], cfg)
    fms = (time.perf_counter() - t0) * 1000
    t1 = time.perf_counter()
    mask = A.motion_mask(g["planned_a"], g["planned_b"], g["current_a"], g["current_b"], *MASK)
    dl = D.dialog_features(g["planned_b"], g["current_b"], mask)
    dms = (time.perf_counter() - t1) * 1000
    t2 = time.perf_counter()
    ws = WS.scores(g["planned_a"], g["current_b"], r["click"])
    wms = (time.perf_counter() - t2) * 1000
    return r["pair_id"], dict(F=F, fms=fms, dlg=dl, dms=dms, ws=ws, wms=wms)


def features(split, recs=None):
    CACHE.mkdir(parents=True, exist_ok=True)
    p = CACHE / f"{split}_features.pkl"
    if p.exists():
        return pickle.loads(p.read_bytes())
    recs = recs or load(split)
    with Pool(4) as pool:
        out = dict(pool.imap_unordered(_feat, recs, chunksize=8))
    p.write_bytes(pickle.dumps(out))
    return out


def run_c4(recs, feats, cfg, scorer, cond="C4", mode="reaim"):
    rows = []
    for r in recs:
        f = feats[r["pair_id"]]
        t0 = time.perf_counter()
        action, click, reason, _ = A.decide(f["F"], r["planned_box"], cfg, mode)
        ms = f["fms"] + (time.perf_counter() - t0) * 1000 + A.FRAME_WAIT_MS
        rows.append(scorer(r["pair_id"], action, click, ms, cond=cond, reason=reason))
    return rows


def objective(df):
    re = df.action == "reaim"
    refind_err = re & (df.outcome == "wrong_reaim") & ~df.stale_during_check
    if re.any() and refind_err.sum() / re.sum() > WRONG_MAX:
        return float("inf")
    return M.expected_seconds(df, 0.05)


def threshold(scores, labels, fa=FA):
    """Smallest theta with false alarms (negatives scored >= theta) <= fa; inf if none."""
    s, y = np.asarray(scores, float), np.asarray(labels, bool)
    neg = np.sort(s[~y])
    for t in np.unique(np.concatenate([s, [np.inf]])):
        if (neg >= t).mean() <= fa:
            return float(t)
    return float("inf")


def settled_score(f, cfg):
    """Continuous 'not settled' score for the anchored check: 1 - in-place NCC, or 1 when the cover check fails."""
    ok, _ = A._cover_state(f["F"]["at_in"], f["F"]["outside_drop"], cfg)
    return 1.0 if not ok else 1.0 - f["F"]["in_place"]


def dialog_score(f):
    d = f["dlg"]
    return max(d["drop"] / 50.0, d["panel_area"] * d["panel_fill"] * 4)


def tune():
    recs = load("dev")
    t1 = [r for r in recs if r["tier"] == 1]
    feats = features("dev", recs)
    sc = Scorer(recs)
    keys = list(GRID)
    # Re-aim mode first. If no setting keeps re-find errors <= 1% of re-aims, the cap leaves only re-plan-only
    # settings (zero re-aims), so the frozen C4 never re-aims; the lowest-error re-aim setting is kept as an
    # exploratory row (C4r), not a preregistered condition. Deviation logged in frozen_full.json.
    log, bests = [], {}
    for mode in ("reaim", "replan_only"):
        best = (float("inf"), None)
        for vals in itertools.product(*GRID.values()):
            cfg = {**A.DEFAULTS, "mask_thr": MASK[0], "mask_dilate": MASK[1], **dict(zip(keys, vals))}
            df = pd.DataFrame(run_c4(t1, feats, cfg, sc, mode=mode))
            re = df.action == "reaim"
            err = int((re & (df.outcome == "wrong_reaim") & ~df.stale_during_check).sum())
            o = objective(df)
            log.append(dict(zip(keys, vals), mode=mode, objective=o, sec_p05=M.expected_seconds(df, 0.05),
                            reaims=int(re.sum()), refind_errors=err))
            if o < best[0]:
                best = (o, cfg)
        bests[mode] = best
        if mode == "reaim" and best[1] is not None:
            break
    tl = pd.DataFrame(log); tl.to_csv(RES / "tuning_c4_dev.csv", index=False)
    c4_mode = "reaim" if bests["reaim"][1] is not None else "replan_only"
    best = bests[c4_mode]
    c4 = {k: best[1][k] for k in ["mask_thr", "mask_dilate", *keys]}
    deviation = None
    if c4_mode == "replan_only":
        r = tl[tl["mode"] == "reaim"].assign(rate=lambda d: d.refind_errors / d.reaims.clip(lower=1))
        r = r.sort_values(["rate", "sec_p05"]).iloc[0]
        c4r = {**{k: (float(r[k])) for k in keys}, "mask_thr": MASK[0], "mask_dilate": MASK[1]}
        deviation = dict(what="no re-aim setting met re-find errors <= 1% on Tier 1 dev; C4 frozen in re-plan-only mode",
                         min_refind_error_rate=float(r.rate), reaims=int(r.reaims), refind_errors=int(r.refind_errors),
                         exploratory_C4r=c4r, prereg_gap="the preregistration did not say what to do when no setting meets the cap")
    # C2: whole-screen thresholds at <= 2% false alarms on Tier 1 dev settled negatives, min s/step
    ss = np.array([feats[r["pair_id"]]["ws"]["ssim"] for r in t1]); fr = np.array([feats[r["pair_id"]]["ws"]["frac_outside"] for r in t1])
    neg = np.array([not r["settled"] for r in t1])
    c2, c2best = None, float("inf")
    for smin in np.unique(np.concatenate([np.quantile(ss, np.linspace(0, 1, 60)), [0.0]])):
        for fmax in np.unique(np.concatenate([np.quantile(fr, np.linspace(0, 1, 60)), [1.0]])):
            flag = (ss < smin) | (fr > fmax)
            if flag[neg].mean() > FA:
                continue
            rows = [sc(r["pair_id"], "replan" if fl else "go", r["click"], feats[r["pair_id"]]["wms"], cond="C2") for r, fl in zip(t1, flag)]
            o = M.expected_seconds(pd.DataFrame(rows), 0.05)
            if o < c2best:
                c2best, c2 = o, dict(ssim_min=float(smin), frac_max=float(fmax))
    # per-question score thresholds at <= 2% FA, per tier, on dev
    q = {}
    for tier in (0, 1, 2):
        rt = [r for r in recs if r["tier"] == tier]
        q[f"settled_t{tier}"] = threshold([settled_score(feats[r["pair_id"]], {**A.DEFAULTS, **c4}) for r in rt], [r["settled"] for r in rt])
        q[f"dialog_t{tier}"] = threshold([dialog_score(feats[r["pair_id"]]) for r in rt], [r["dialog"] for r in rt])
    out = dict(C1=dict(WS.PUBLISHED), C2={**WS.PUBLISHED, **(c2 or {})}, C4=c4, C4_mode=c4_mode, deviation=deviation,
               question_thresholds=q, dev_objective=dict(C4=best[0], C2=c2best), mask=MASK, tuned_on="full dev (variants 0-1); C4/C2 on Tier 1 dev",
               date=time.strftime("%Y-%m-%d"), rule="C4: s/step at p=0.05 with re-find errors <= 1% of re-aims; C2 and question thresholds at <= 2% FA")
    FROZEN.write_text(json.dumps(out, indent=2))
    print(json.dumps(out, indent=2))


def decisions(split):
    fz = json.loads(FROZEN.read_text())
    recs = load(split)
    feats = features(split, recs)
    sc = Scorer(recs)
    c4 = {**A.DEFAULTS, **fz["C4"]}
    rows = []
    for r in recs:
        f = feats[r["pair_id"]]
        base = dict(settled=r["settled"], dialog=r["dialog"], kind=r["kind"], variant=r["variant"], bg=r["bg"], degraded=bool(r.get("degrade")))
        rows.append(sc(r["pair_id"], "go", r["click"], 0.0, cond="C0", reason="no_check", **base))
        for cond, cfg in (("C1", fz["C1"]), ("C2", fz["C2"])):
            flag = f["ws"]["ssim"] < cfg["ssim_min"] or f["ws"]["frac_outside"] > cfg["frac_max"]
            rows.append(sc(r["pair_id"], "replan" if flag else "go", r["click"], f["wms"], cond=cond, reason="flag" if flag else "unchanged",
                           s_settled=float(flag), s_dialog=float(flag), **base))
        t0 = time.perf_counter()
        action, click, reason, _ = A.decide(f["F"], r["planned_box"], c4, fz.get("C4_mode", "reaim"))
        dflag = dialog_score(f) >= fz["question_thresholds"][f"dialog_t{r['tier']}"]
        ms = f["fms"] + f["dms"] + (time.perf_counter() - t0) * 1000 + A.FRAME_WAIT_MS
        s_set = settled_score(f, c4)
        rows.append(sc(r["pair_id"], action, click, ms, cond="C4", reason=reason, s_settled=s_set, s_dialog=dialog_score(f), **base))
        if fz.get("deviation"):
            ar, cr, rr, _ = A.decide(f["F"], r["planned_box"], {**A.DEFAULTS, **fz["deviation"]["exploratory_C4r"]}, "reaim")
            rows.append(sc(r["pair_id"], ar, cr, ms, cond="C4r", reason=rr, s_settled=s_set, s_dialog=dialog_score(f), **base))
        # C7: PUSV as the security screen (its flag logged), anchored as the reliability layer, plus a re-plan when
        # PUSV flags and the anchored dialog detector fires
        pflag = f["ws"]["ssim"] < fz["C1"]["ssim_min"] or f["ws"]["frac_outside"] > fz["C1"]["frac_max"]
        a7, c7, r7 = (("replan", r["click"], "pusv+dialog") if (pflag and dflag) else (action, click, reason))
        rows.append(sc(r["pair_id"], a7, c7, ms + f["wms"], cond="C7", reason=r7, security_flag=pflag,
                       s_settled=s_set, s_dialog=float(pflag and dflag), **base))
    df = pd.DataFrame(rows)
    (RES / "raw").mkdir(parents=True, exist_ok=True)
    df.to_csv(RES / f"raw/pixel_{split}_decisions.csv", index=False)
    print(df.groupby(["tier", "cond"]).apply(lambda d: pd.Series(dict(n=len(d), sec=M.expected_seconds(d, .05),
          fa=float((d[~d.relevant].action == "replan").mean())))).round(3).to_string())
    return df


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "features":
        features(sys.argv[2]); print("features done", sys.argv[2])
    elif cmd == "tune":
        tune()
    else:
        decisions(sys.argv[2])
