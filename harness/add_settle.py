"""Addition 1 analysis: how long to wait after a navigation (docs/PREREG_ADDITIONS.md, Addition 1). Read-only data in
private/realsite_add/ (never released, never pooled with the benchmark); only statistics are written out.

  python -m harness.add_settle     # -> results/additions/tables/settle_*.csv, figures/add_settle.png
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from harness.metrics import wilson

ROOT = Path(__file__).resolve().parents[1]
PRIV = ROOT / "private/realsite_add"
TAB = ROOT / "results/additions/tables"
FIG = ROOT / "figures"
RULES = ("S0", "S1", "S2", "S3", "S3b", "S4", "S5")
NAMES = {"S0": "immediately", "S1": "0.5 s", "S2": "1 s", "S3": "no layout shift 500 ms (cap 5 s)",
         "S3b": "boxes still 500 ms (cap 5 s; exploratory)", "S4": "load event", "S5": "network idle"}


def records():
    rs = [json.loads(l) for l in (PRIV / "visits.jsonl").read_text().splitlines() if l.strip()]
    return [r for r in rs if r["round"] >= 1]  # round 0 was the smoke test


def tracks(vs):
    rows = []
    for v in vs:
        bad = {t["i"]: False for t in v["targets"]}
        by2 = dict(bad)
        for o in v["offsets"]:
            for t in o["truth"]:
                if not t["go_ok"]:
                    bad[t["i"]] = True
                    if o["offset"] <= 2:
                        by2[t["i"]] = True
        vid = f"{v['site']}|{v['rule']}|{v['round']}"
        for t in v["targets"]:
            rows.append(dict(visit=vid, site=v["site"], kind=v["kind"], rule=v["rule"], round=v["round"], target=t["i"], type=t["type"],
                             invalid=bad[t["i"]], invalid_2s=by2[t["i"]]))
    return pd.DataFrame(rows)


def boot(g, n=2000, seed=0):
    """Cluster bootstrap over visits of the share invalidated within 6.5 s."""
    per = g.groupby("visit").invalid.agg(["sum", "size"]).to_numpy()
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(per), (n, len(per)))
    s = per[idx].sum(1)
    sh = s[:, 0] / s[:, 1]
    return float(np.percentile(sh, 2.5)), float(np.percentile(sh, 97.5))


def rule_rows(tr, vs, by=None):
    rows = []
    keys = [("all", tr)] if by is None else list(tr.groupby(by))
    for key, g in keys:
        for rule in RULES:
            x = g[g.rule == rule]
            if not len(x):
                continue
            k, n = int(x.invalid.sum()), len(x)
            s, lo, hi = wilson(k, n)
            vids = set(x.visit)
            w = vs[vs.visit.isin(vids)].wait_s
            blo, bhi = boot(x)
            rows.append(dict(group=key, rule=rule, name=NAMES[rule], visits=len(vids), pages=x.site.nunique(), tracks=n, invalid=k,
                             share=s, lo=lo, hi=hi, boot_lo=blo, boot_hi=bhi, share_2s=float(x.invalid_2s.mean()),
                             wait_median=float(w.median()), wait_p90=float(w.quantile(0.9))))
    return pd.DataFrame(rows)


def main():
    TAB.mkdir(parents=True, exist_ok=True)
    rs = records()
    ok = [r for r in rs if not r.get("error")]
    vs = pd.DataFrame([dict(visit=f"{r['site']}|{r['rule']}|{r['round']}", site=r["site"], kind=r["kind"], rule=r["rule"], round=r["round"],
                            wait_s=r["wait_s"], timeout=bool(r["info"].get("timeout")), capped=bool(r["info"].get("capped")),
                            fallback=bool(r["info"].get("fallback")), cls_plan=r["cls_plan"], cls_end=r["cls_end"],
                            targets=len(r["targets"]), t=r["t"]) for r in ok])
    # visit log, including errors and "no target" visits (retried errors stay in the log)
    vl = pd.DataFrame([dict(site=r["site"], rule=r["rule"], round=r["round"], t=r["t"], status="ok" if not r.get("error") else
                            ("no target" if r["error"] == "no target" else "error"), error=(r.get("error") or "")[:80]) for r in rs])
    vl.to_csv(TAB / "settle_visits.csv", index=False)
    tr = tracks(ok)
    over = rule_rows(tr, vs)
    over.to_csv(TAB / "settle_rules.csv", index=False)
    kind = rule_rows(tr, vs, by="kind")
    kind.to_csv(TAB / "settle_rules_by_kind.csv", index=False)
    # wait details per rule: timeouts (S4/S5), caps and fallbacks (S3/S3b)
    wd = vs.groupby("rule").agg(visits=("visit", "size"), timeouts=("timeout", "sum"), capped=("capped", "sum"), fallback=("fallback", "sum"),
                                wait_mean=("wait_s", "mean"), wait_max=("wait_s", "max")).reset_index()
    wd.to_csv(TAB / "settle_wait_details.csv", index=False)

    # cheapest rule at <= 1%, and at upper Wilson <= 2%
    o = over.set_index("rule")
    a = o[o.share <= 0.01].sort_values("wait_median")
    b = o[o.hi <= 0.02].sort_values("wait_median")
    s3, s5 = o.loc["S3"], o.loc["S5"]
    e6 = dict(s3_share=s3.share, s3_hi=s3.hi, s3_wait_median=s3.wait_median, s5_wait_median=s5.wait_median,
              part_share=bool(s3.share <= 0.01), part_hi=bool(s3.hi <= 0.02), part_wait=bool(s3.wait_median < s5.wait_median),
              cheapest_le_1pct=a.index[0] if len(a) else "none", cheapest_le_1pct_wait=float(a.wait_median.iloc[0]) if len(a) else np.nan,
              cheapest_hi_le_2pct=b.index[0] if len(b) else "none", cheapest_hi_le_2pct_wait=float(b.wait_median.iloc[0]) if len(b) else np.nan)
    e6["holds"] = e6["part_share"] and e6["part_hi"] and e6["part_wait"]
    pd.DataFrame([e6]).to_csv(TAB / "settle_e6.csv", index=False)

    # does a page's layout-shift score predict its post-navigation burst?
    pg = []
    for site, g in tr[tr.rule == "S0"].groupby("site"):
        pv = vs[vs.site == site]
        pg.append(dict(site=site, kind=g.kind.iloc[0], burst_2s=float(g.invalid_2s.mean()), tracks=len(g),
                       cls_s0=float(pv[pv.rule == "S0"].cls_end.median()), cls_s5=float(pv[pv.rule == "S5"].cls_end.median()) if (pv.rule == "S5").any() else np.nan))
    pg = pd.DataFrame(pg)
    pg.to_csv(TAB / "settle_cls_by_page.csv", index=False)
    cor = []
    rng = np.random.default_rng(0)
    for col in ("cls_s0", "cls_s5"):
        x = pg.dropna(subset=[col])
        rho, p = spearmanr(x[col], x.burst_2s)
        bs = []
        for _ in range(2000):
            i = rng.integers(0, len(x), len(x))
            r_ = spearmanr(x[col].to_numpy()[i], x.burst_2s.to_numpy()[i])[0]
            if np.isfinite(r_):
                bs.append(r_)
        cor.append(dict(cls=col, pages=len(x), spearman_rho=rho, p=p, lo=float(np.percentile(bs, 2.5)), hi=float(np.percentile(bs, 97.5))))
    pd.DataFrame(cor).to_csv(TAB / "settle_cls_spearman.csv", index=False)

    figure(over)
    print(over.round(4).to_string(index=False)); print(wd.round(2).to_string(index=False)); print(pd.DataFrame([e6]).T.to_string())
    print(kind.pivot(index="group", columns="rule", values="share").round(3).to_string()); print(pd.DataFrame(cor).round(3).to_string(index=False))
    print(vl.status.value_counts().to_string()); print(len(vs), "visits", vs.site.nunique(), "pages")


def figure(over):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    # label offsets (points) so the closely spaced rules stay readable
    OFF = {"S0": (8, -4), "S1": (-10, -26), "S2": (8, 6), "S3": (-30, 24), "S3b": (8, -14), "S4": (-60, 16), "S5": (8, 6)}
    fig, axes = plt.subplots(1, 2, figsize=(9.6, 4.0), gridspec_kw=dict(width_ratios=[1, 1.5]))
    for ax, zoom in zip(axes, (False, True)):
        for _, r in over.iterrows():
            if zoom and r.rule == "S0":
                continue
            c = "#555" if r.rule == "S3b" else "#1f5fa8"
            ax.errorbar(r.wait_median, 100 * r.share, yerr=[[100 * max(r.share - r.lo, 0)], [100 * max(r.hi - r.share, 0)]],
                        fmt="o", color=c, capsize=3, mfc="white" if r.rule == "S3b" else c)
            label = r.rule if not zoom else f"{r.rule}: {r['name']}"
            ax.annotate(label, (r.wait_median, 100 * r.share), xytext=OFF[r.rule] if zoom else (6, 3), textcoords="offset points", fontsize=7.5,
                        bbox=dict(boxstyle="round,pad=0.15", fc="white", ec="none", alpha=0.9))
        ax.axhline(1, color="#c33", lw=0.8, ls="--")
        ax.set_xlabel("median wait after domcontentloaded (s)")
        ax.spines[["top", "right"]].set_visible(False)
    axes[0].set_ylabel("planned clicks invalid within 6.5 s (%)")
    axes[0].set_title("all rules", fontsize=9)
    axes[1].set_title("zoom: rules after a wait (95% Wilson CIs)", fontsize=9)
    axes[1].set_xlim(0.3, 1.5); axes[1].set_ylim(0, 5)
    axes[1].text(1.5, 1.05, "1%", color="#c33", ha="right", va="bottom", fontsize=8)
    fig.suptitle("Addition: how long to wait before the planning screenshot (31 real pages, 3 rounds)", fontsize=10)
    fig.tight_layout()
    fig.savefig(FIG / "add_settle.png", dpi=200)


if __name__ == "__main__":
    main()
