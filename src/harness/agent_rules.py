"""Agent rules A1-A10: each agent's post-navigation wait rule, re-implemented and measured on the 31 real pages
(docs/PREREG_AGENT_RULES.md). Read-only data in private/realsite_agents/; only statistics are written out.

  python -m harness.agent_rules     # -> results/agent_rules/tables/*.csv
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd

from harness.add_settle import boot, tracks
from harness.metrics import wilson

ROOT = Path(__file__).resolve().parents[2]
PRIV = ROOT / "private/realsite_agents"
TAB = ROOT / "results/agent_rules/tables"
RULES = tuple(f"A{i}" for i in range(1, 11))
AGENT = {"A1": "Anthropic computer-use demo", "A2": "browser-use", "A3": "OpenAI CUA sample app (current)", "A4": "Stagehand v4",
         "A5": "Skyvern", "A6": "Agent S3", "A7": "OpenHands (browser-use 0.11.9)", "A8": "Playwright MCP", "A9": "UI-TARS-desktop",
         "A10": "magentic-ui"}
IMPL = {"A1": "commit, sleep 2.0 s", "A2": "commit; first of load / networkidle, cap 8 s; +0.3 s if requests pending",
        "A3": "domcontentloaded, no wait", "A4": "domcontentloaded, no wait",
        "A5": "load; 0.75-1.25 s; load <= 3 s; animations finished <= 3 s", "A6": "commit, sleep 1.0 s",
        "A7": "commit; first of load / networkidle, cap 4 s; +0.3 s if requests pending", "A8": "domcontentloaded; load <= 5 s",
        "A9": "commit, sleep 1.0 s", "A10": "commit; domcontentloaded; sleep 3 s; load <= 2 s"}
# earlier estimates from results/additions/agent_defaults.md, in percent: (kind, low, high)
EST = {"A1": ("approx", 3.0, 3.0), "A2": ("approx", 3.0, 3.0), "A3": ("approx", 14.0, 14.0), "A4": ("approx", 14.0, 14.0),
       "A5": ("le", None, 3.0), "A6": ("ge", 3.0, None), "A7": ("approx", 3.0, 3.0), "A8": ("approx", 3.0, 3.0),
       "A9": ("range", 3.0, 14.0), "A10": ("range", 0.5, 3.0)}
EST_TXT = {"approx": "≈ {lo:g}%", "le": "≤ {hi:g}%", "ge": "≥ {lo:g}%", "range": "{lo:g}–{hi:g}%"}


def est_compare(rule, share, lo, hi):
    kind, a, b = EST[rule]
    a_, b_ = (a if a is not None else -np.inf), (b if b is not None else np.inf)
    m, l, h = 100 * share, 100 * lo, 100 * hi
    inside = not (h < a_ or l > b_)  # the estimate (point, bound or range) intersects the measured CI
    dist = 0.0 if a_ <= m <= b_ else min(abs(m - a_), abs(m - b_))
    return dict(estimate=EST_TXT[kind].format(lo=a or 0, hi=b or 0), inside_ci=inside, off_points=round(dist, 2), wrong_by_gt_2pts=dist > 2)


def main():
    TAB.mkdir(parents=True, exist_ok=True)
    rs = [json.loads(l) for l in (PRIV / "visits.jsonl").read_text().splitlines() if l.strip()]
    rs = [r for r in rs if r["round"] >= 1]  # round 0 was the smoke test
    ok = [r for r in rs if not r.get("error")]
    vs = pd.DataFrame([dict(visit=f"{r['site']}|{r['rule']}|{r['round']}", site=r["site"], kind=r["kind"], rule=r["rule"], round=r["round"],
                            wait_s=r["wait_s"], wait_dcl_s=r["wait_dcl_s"], wait_wall_s=r["wait_wall_s"], t=r["t"], **{f"i_{k}": v for k, v in r["info"].items()})
                       for r in ok])
    pd.DataFrame([dict(site=r["site"], rule=r["rule"], round=r["round"], t=r["t"], status="ok" if not r.get("error") else
                       ("no target" if r["error"] == "no target" else "error"), error=(r.get("error") or "")[:80]) for r in rs]
                 ).to_csv(TAB / "agent_visits.csv", index=False)
    tr = tracks(ok)
    rows, kinds = [], []
    for rule in RULES:
        x, v = tr[tr.rule == rule], vs[vs.rule == rule]
        k, n = int(x.invalid.sum()), len(x)
        s, lo, hi = wilson(k, n)
        blo, bhi = boot(x)
        rows.append(dict(rule=rule, agent=AGENT[rule], implemented=IMPL[rule], visits=len(v), pages=x.site.nunique(), tracks=n, invalid=k,
                         share=s, lo=lo, hi=hi, boot_lo=blo, boot_hi=bhi, share_2s=float(x.invalid_2s.mean()),
                         wait_median=float(v.wait_s.median()), wait_p90=float(v.wait_s.quantile(0.9)),
                         wait_dcl_median=float(v.wait_dcl_s.median()), wait_dcl_p90=float(v.wait_dcl_s.quantile(0.9)),
                         wait_wall_median=float(v.wait_wall_s.median()), lower_above_1pct=bool(lo > 0.01), **est_compare(rule, s, lo, hi)))
        for kd, g in x.groupby("kind"):
            kinds.append(dict(rule=rule, kind=kd, tracks=len(g), share=float(g.invalid.mean())))
    out = pd.DataFrame(rows)
    out.to_csv(TAB / "agent_rules.csv", index=False)
    pd.DataFrame(kinds).pivot(index="kind", columns="rule", values="share")[list(RULES)].to_csv(TAB / "agent_rules_by_kind.csv")
    e8 = dict(rules_lower_above_1pct=int(out.lower_above_1pct.sum()), of=len(out))
    e8["holds"] = e8["rules_lower_above_1pct"] >= 8
    pd.DataFrame([e8]).to_csv(TAB / "agent_e8.csv", index=False)
    # rule internals: caps, signals, gates, timeouts
    det = []
    for rule, v in vs.groupby("rule"):
        d = dict(rule=rule, visits=len(v))
        if "i_signal" in v:
            d |= dict(signal_load=int((v.i_signal == "load").sum()), signal_networkidle=int((v.i_signal == "networkidle").sum()),
                      capped=int(v.i_capped.fillna(False).astype(bool).sum()), signal_after_3s=int((v.i_signal_s > 3).sum()),
                      signal_after_2s=int((v.i_signal_s > 2).sum()), pending_gate_fired=int((v.i_pending.fillna(0) > 0).sum()))
        for c in ("i_load_timeout", "i_anim_timeout", "i_dcl_timeout"):
            if c in v and v[c].notna().any():
                d[c[2:]] = int(v[c].fillna(False).astype(bool).sum())
        if "i_anim_s" in v and v.i_anim_s.notna().any():
            d["anim_wait_median"] = float(v.i_anim_s.median())
        det.append(d)
    det = pd.DataFrame(det).set_index("rule").loc[[r for r in RULES if r in set(vs.rule)]].reset_index()
    det.to_csv(TAB / "agent_rule_details.csv", index=False)
    pd.set_option("display.width", 250)
    print(out[["rule", "agent", "visits", "pages", "tracks", "invalid", "share", "lo", "hi", "boot_lo", "boot_hi", "wait_median", "wait_p90",
               "wait_dcl_median", "estimate", "inside_ci", "off_points"]].round(4).to_string(index=False))
    print(e8); print(det.to_string(index=False)); print(pd.read_csv(TAB / "agent_rules_by_kind.csv").round(3).to_string(index=False))
    print(pd.read_csv(TAB / "agent_visits.csv").status.value_counts().to_string())


if __name__ == "__main__":
    main()
