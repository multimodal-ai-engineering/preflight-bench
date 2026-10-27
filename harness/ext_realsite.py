"""Extension Part C analysis: when real pages change (docs/PREREG_EXTENSION.md, C.3). Read-only data in
private/realsite_ext/ (never released, never pooled with the benchmark); only statistics are written out.

  python -m harness.ext_realsite checks   # C2 / C4 decisions per target and offset (cached, multiprocess)
  python -m harness.ext_realsite all      # survival, hazard fits, C_min, false alarms, E3 -> results/extension/tables/rs_*.csv
"""
import json, sys
from multiprocessing import Pool
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import minimize

from anchored import check as A
from anchored import whole_screen as WS
from harness.full_checks import MASK
from harness.metrics import wilson

ROOT = Path(__file__).resolve().parents[1]
PRIV = ROOT / "private/realsite_ext"
TAB = ROOT / "results/extension/tables"
FZ = json.loads((ROOT / "results/full/frozen_full.json").read_text())
OFFSETS = (0.5, 1, 2, 4, 6.5, 12, 30)


def visits():
    vs = [json.loads(l) for l in (PRIV / "visits.jsonl").read_text().splitlines() if l.strip()]
    return [v for v in vs if not v.get("error")]


def tracks(vs):
    """One row per target x offset: survival truth at the offset (read before the frames)."""
    rows = []
    for v in vs:
        vid = f"{v['site']}|{v['cond']}|{v['round']}"
        tg = {t["i"]: t for t in v["targets"]}
        for o in v["offsets"]:
            if o["offset"] == 0:
                continue
            for tr in o["truth"]:
                t = tg[tr["i"]]
                rows.append(dict(visit=vid, site=v["site"], kind=v["kind"], cond=v["cond"], round=v["round"], target=tr["i"],
                                 type=t["type"], third=t["third"], offset=o["offset"], t=o["t_truth"], valid=bool(tr["go_ok"]),
                                 exists=bool(tr["exists"]), disp=tr["disp"]))
    return pd.DataFrame(rows)


# ---------- check decisions ----------

def _one(args):
    v, oi = args
    o = v["offsets"][oi]
    p0 = v["offsets"][0]
    g = [A.gray(ROOT / p) for p in p0["frames"] + o["frames"]]
    cfg = {**A.DEFAULTS, "mask_thr": MASK[0], "mask_dilate": MASK[1]}
    c4 = {**A.DEFAULTS, **FZ["C4"]}
    out = []
    post = {t["i"]: t for t in o["truth_post"]}
    for t in v["targets"]:
        try:
            F = A.features(g[0], g[1], g[2], g[3], t["box"], cfg)
            a, _, reason, _ = A.decide(F, t["box"], c4, FZ.get("C4_mode", "reaim"))
            ws = WS.scores(g[0], g[3], t["click"])
            c2 = ws["ssim"] < FZ["C2"]["ssim_min"] or ws["frac_outside"] > FZ["C2"]["frac_max"]
            out.append(dict(visit=f"{v['site']}|{v['cond']}|{v['round']}", site=v["site"], kind=v["kind"], cond=v["cond"], target=t["i"],
                            type=t["type"], offset=o["offset"], valid_post=bool(post[t["i"]]["go_ok"]), C4=a != "go", C2=bool(c2), C4_reason=reason))
        except Exception as e:
            out.append(dict(visit=f"{v['site']}|{v['cond']}|{v['round']}", target=t["i"], offset=o["offset"], error=repr(e)[:200]))
    return out


def checks():
    p = ROOT / "results/extension/cache/rs_checks.pkl"
    vs = visits()
    done = pd.read_pickle(p) if p.exists() else pd.DataFrame()
    have = set(zip(done.visit, done.offset)) if len(done) else set()
    todo = [(v, i) for v in vs for i, o in enumerate(v["offsets"]) if o["offset"] > 0 and (f"{v['site']}|{v['cond']}|{v['round']}", o["offset"]) not in have]
    with Pool(6) as pool:
        new = pd.DataFrame([r for rows in pool.imap_unordered(_one, todo, chunksize=4) for r in rows])
    d = pd.concat([done, new], ignore_index=True)
    p.parent.mkdir(parents=True, exist_ok=True)
    d.to_pickle(p)
    print(len(todo), "visit-offsets added;", len(d), "rows")
    return d


# ---------- survival and fits ----------

def survival(tr):
    rows = []
    for keys, g in tr.groupby(["kind", "cond", "type", "offset"]):
        k, n = int(g.valid.sum()), len(g)
        s, lo, hi = wilson(k, n)
        rows.append(dict(zip(["kind", "cond", "type", "offset"], keys), n=n, S=s, S_lo=lo, S_hi=hi))
    for keys, g in tr.groupby(["kind", "cond", "offset"]):
        k, n = int(g.valid.sum()), len(g)
        s, lo, hi = wilson(k, n)
        rows.append(dict(zip(["kind", "cond", "offset"], keys), type="all", n=n, S=s, S_lo=lo, S_hi=hi))
    for keys, g in tr.groupby(["cond", "offset"]):
        k, n = int(g.valid.sum()), len(g)
        s, lo, hi = wilson(k, n)
        rows.append(dict(zip(["cond", "offset"], keys), kind="all", type="all", n=n, S=s, S_lo=lo, S_hi=hi))
    return pd.DataFrame(rows)


def S1(t, lam):
    return np.exp(-lam * t)


def S2(t, a, beta, lam):
    return (1 - a * (1 - np.exp(-beta * t))) * np.exp(-lam * t)


def nll(S, t, y):
    s = np.clip(S, 1e-9, 1 - 1e-9)
    return -float(np.sum(y * np.log(s) + (1 - y) * np.log(1 - s)))


def fit(g):
    t, y = g.t.values.astype(float), g.valid.values.astype(float)
    r1 = minimize(lambda x: nll(S1(t, np.exp(x[0])), t, y), [np.log(0.01)], method="Nelder-Mead")
    lam1 = float(np.exp(r1.x[0]))

    def f2(x):
        a, beta, lam = 1 / (1 + np.exp(-x[0])), np.exp(x[1]), np.exp(x[2])
        return nll(S2(t, a, beta, lam), t, y) + (1e6 if beta <= lam else 0)
    best = None
    for x0 in ([-2, np.log(2), np.log(0.005)], [-1, np.log(0.5), np.log(0.01)], [-3, np.log(5), np.log(0.001)]):
        r = minimize(f2, x0, method="Nelder-Mead", options=dict(maxiter=4000, xatol=1e-6, fatol=1e-6))
        if best is None or r.fun < best.fun:
            best = r
    a, beta, lam2 = 1 / (1 + np.exp(-best.x[0])), float(np.exp(best.x[1])), float(np.exp(best.x[2]))
    aic1, aic2 = 2 * 1 + 2 * r1.fun, 2 * 3 + 2 * best.fun
    return dict(n=len(g), lam_const=lam1, aic_const=aic1, a=a, beta=beta, lam_two=lam2, aic_two=aic2,
                preferred="two-phase" if aic2 < aic1 else "constant")


def p_of(fr, C):
    if fr["preferred"] == "two-phase":
        return 1 - S2(C, fr["a"], fr["beta"], fr["lam_two"])
    return 1 - S1(C, fr["lam_const"])


def boot_diff(tr, a, b, n=2000, seed=0):
    """Share of tracks invalid at any offset <= 2 s: cond a minus cond b; cluster bootstrap over visits."""
    early = tr[tr.offset <= 2].groupby(["visit", "cond", "target"]).valid.min().reset_index()
    early["inv"] = ~early.valid
    va, vb = early[early.cond == a], early[early.cond == b]
    ga = {k: g.inv.values for k, g in va.groupby("visit")}; gb = {k: g.inv.values for k, g in vb.groupby("visit")}
    ka, kb = list(ga), list(gb)
    obs = va.inv.mean() - vb.inv.mean()
    rng = np.random.default_rng(seed)
    ds = []
    for _ in range(n):
        xa = np.concatenate([ga[ka[i]] for i in rng.integers(0, len(ka), len(ka))])
        xb = np.concatenate([gb[kb[i]] for i in rng.integers(0, len(kb), len(kb))])
        ds.append(xa.mean() - xb.mean())
    lo, hi = np.percentile(ds, [2.5, 97.5])
    return dict(comparison=f"{a} - {b}", share_a=float(va.inv.mean()), share_b=float(vb.inv.mean()), tracks_a=len(va), tracks_b=len(vb),
                visits_a=len(ka), visits_b=len(kb), diff=float(obs), lo=float(lo), hi=float(hi), excludes_zero=bool(lo > 0 or hi < 0))


def main():
    TAB.mkdir(parents=True, exist_ok=True)
    vs = visits()
    tr = tracks(vs)
    allv = [json.loads(l) for l in (PRIV / "visits.jsonl").read_text().splitlines() if l.strip()]
    cov = pd.DataFrame([dict(site=v["site"], kind=v["kind"], cond=v["cond"], round=v["round"], error=v.get("error"),
                             targets=len(v.get("targets", []))) for v in allv])
    cov.to_csv(TAB / "rs_visits.csv", index=False)
    print("visits ok:", len(vs), "of", len(allv), "| tracks per cond:", tr[tr.offset == 0.5].groupby("cond").size().to_dict(),
          "| pages with >= 1 ok visit:", tr.site.nunique())
    sv = survival(tr)
    sv.to_csv(TAB / "rs_survival.csv", index=False)
    fits = []
    for keys, g in list(tr.groupby(["kind", "cond"])) + [((("all",) + (c,)), g) for c, g in tr.groupby("cond")]:
        fits.append(dict(kind=keys[0], cond=keys[1], **fit(g)))
    fits = pd.DataFrame(fits)
    fits.to_csv(TAB / "rs_fits.csv", index=False)
    e3 = [boot_diff(tr, "nav", "settled")]
    if (tr.cond == "scroll").any():
        e3.append(boot_diff(tr, "scroll", "settled"))
    e3 = pd.DataFrame(e3)
    e3["role"] = ["E3 primary"] + ["secondary"] * (len(e3) - 1)
    e3.to_csv(TAB / "rs_e3.csv", index=False)
    print(e3.round(3).to_string(index=False))
    print(fits.round(4).to_string(index=False))
    ck = ROOT / "results/extension/cache/rs_checks.pkl"
    if ck.exists():
        d = pd.read_pickle(ck)
        d = d[d.get("error").isna()] if "error" in d else d
        fa = []
        for (c, o), g in d.groupby(["cond", "offset"]):
            neg, pos = g[g.valid_post], g[~g.valid_post]
            for chk in ("C2", "C4"):
                k, n = int(neg[chk].sum()), len(neg)
                f, lo, hi = wilson(k, n)
                fa.append(dict(cond=c, offset=o, check=chk, valid=n, false_alarms=k, fa=f, fa_lo=lo, fa_hi=hi,
                               changed=len(pos), caught=int(pos[chk].sum()), recall=float(pos[chk].mean()) if len(pos) else np.nan))
        fa = pd.DataFrame(fa)
        fa.to_csv(TAB / "rs_false_alarms.csv", index=False)
        # C_min: smallest C with p(C) > p*(C), gap ~ C; r and delta from benchmark Tier 1 dev, f from real pages
        v = pd.read_csv(TAB / "ineq_validation.csv")
        bench = {c: v[(v.check == c) & (v.tier == 1)].iloc[0] for c in ("C2", "C4")}
        grid = np.exp(np.linspace(np.log(0.5), np.log(60), 200))
        cm = []
        for _, fr in fits.iterrows():
            g = d if fr.kind == "all" else d[d.kind == fr.kind]
            g = g[(g.cond == fr.cond) & g.valid_post]
            for chk in ("C2", "C4"):
                f = float(g[chk].mean()) if len(g) else np.nan
                r, delta = float(bench[chk].r_dev), float(bench[chk].delta_dev)
                for k in (2, 10):
                    ps = (delta / grid + f) / (r * (k - 1) + f)
                    pc = np.array([p_of(fr, C) for C in grid])
                    ok = np.where(pc > ps)[0]
                    cm.append(dict(kind=fr.kind, cond=fr.cond, check=chk, k=k, r_bench=r, delta_bench=delta, f_real=f,
                                   C_min=float(grid[ok[0]]) if len(ok) else np.nan, C_min_label=f"{grid[ok[0]]:.2f} s" if len(ok) else "none <= 60 s"))
        cm = pd.DataFrame(cm)
        cm.to_csv(TAB / "rs_cmin.csv", index=False)
        print(fa.groupby(["check", "cond"]).agg(fa=("fa", "mean")).round(3).to_string())
        print(cm[cm.kind == "all"].to_string(index=False))


if __name__ == "__main__":
    {"checks": checks, "all": main}[sys.argv[1]]()
