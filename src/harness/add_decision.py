"""Addition 2 (E7, supplementary, post-hoc): does the inequality make the right check-or-skip call at the change
rates actually measured? docs/PREREG_ADDITIONS.md, Addition 2. Existing data only.

  python -m harness.add_decision    # results/extension/tables/ineq_validation.csv -> results/additions/tables/decision_*.csv
"""
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
TAB = ROOT / "results/additions/tables"
PS = {0.003: "settled real pages", 0.010: "scrolled real pages", 0.171: "just-navigated real pages", 0.686: "benchmark Tier 1"}
FORMS = {"first order": "p_first", "exposure term (exploratory)": "p_exposure_exploratory"}


def check(p, pstar):
    """'check' iff p > p*; an infinite p* (never pays) is 'skip' at every p."""
    return np.isfinite(pstar) & (p > pstar)


def main():
    TAB.mkdir(parents=True, exist_ok=True)
    v = pd.read_csv(ROOT / "results/extension/tables/ineq_validation.csv")
    v["p_obs"] = v.p_obs.replace([np.inf, -np.inf], np.inf)
    rows = []
    for p in PS:
        obs = check(p, v.p_obs.to_numpy())
        for form, col in FORMS.items():
            pred = check(p, v[col].to_numpy())
            rows.append(v[["check", "tier", "C", "k", "err_first"]].assign(p=p, p_label=PS[p], form=form, pred_check=pred, obs_check=obs,
                                                                         agree=pred == obs))
    d = pd.concat(rows, ignore_index=True)
    d["err_first_gt_003"] = d.err_first > 0.03
    d.to_csv(TAB / "decision_cells.csv", index=False)

    def agg(g):
        dis = g[~g.agree]
        return pd.Series(dict(decisions=len(g), agreement=g.agree.mean(), obs_check_share=g.obs_check.mean(),
                              pred_check_obs_skip=int((dis.pred_check).sum()), pred_skip_obs_check=int((~dis.pred_check).sum())))
    out = []
    for form, g in d.groupby("form"):
        out.append(agg(g).to_frame().T.assign(form=form, subset="all", value="all"))
        for p, gg in g.groupby("p"):
            out.append(agg(gg).to_frame().T.assign(form=form, subset="p", value=f"{p} ({PS[p]})"))
        for e, gg in g.groupby("err_first_gt_003"):
            out.append(agg(gg).to_frame().T.assign(form=form, subset="first-order error", value="> 0.03" if e else "<= 0.03"))
    s = pd.concat(out, ignore_index=True)[["form", "subset", "value", "decisions", "agreement", "obs_check_share", "pred_check_obs_skip", "pred_skip_obs_check"]]
    s["E7_holds"] = np.where((s.form == "first order") & (s.subset == "all"), s.agreement >= 0.9, None)
    s.to_csv(TAB / "decision_summary.csv", index=False)
    by = d.groupby(["form", "check"]).apply(agg).reset_index()
    by.to_csv(TAB / "decision_by_check.csv", index=False)
    byp = d[d.form == "first order"].groupby(["check", "p"]).agree.mean().unstack().reset_index()
    byp.to_csv(TAB / "decision_by_check_p.csv", index=False)
    print(s.round(3).to_string(index=False)); print(by.round(3).to_string(index=False)); print(byp.round(3).to_string(index=False))


if __name__ == "__main__":
    main()
