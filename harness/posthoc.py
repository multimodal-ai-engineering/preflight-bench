"""Post-hoc checks requested after the preregistered results (2026-10-23). NOT preregistered. PILOT.

  python -m harness.posthoc pixel_effect     # Q3 pixel check over the region where the expected effect appears
  python -m harness.posthoc tier0            # P3 direction; Tier 0 test pairs where C4 re-planned and go was correct
  python -m harness.posthoc none_share       # Tier 1 'none' pairs whose correct action at offset 0 is not go
  python -m harness.posthoc cap              # C5/C6 retuned under Wave 2's 1% re-find-error cap
  python -m harness.posthoc q3_opaque        # Q3 rerun with opaque IDs and shuffled order (after the runs)
Outputs: results/pilot/posthoc/.
"""
import itertools, json, sys
from pathlib import Path

import numpy as np
import pandas as pd

from anchored import check as A
from harness import metrics as M
from harness import q3 as Q

ROOT = Path(__file__).resolve().parents[1]
RES = ROOT / "results/pilot"
OUT = RES / "posthoc"


def pixel_effect():
    fz = json.loads((RES / "frozen_w2.json").read_text())["C4"]
    boxes = json.loads((ROOT / "data/pilot/worked_effect_boxes.json").read_text())
    res = {}
    for split in ("dev", "test"):
        rows = []
        for r in Q.recs(split):
            rr = dict(r, action_box=boxes[r["worked_id"]]["box"])  # same score, region = expected-effect box
            s, keep = Q.pixel_score(rr, fz["mask_thr"], fz["mask_dilate"])
            rows.append(dict(worked_id=r["worked_id"], page=r["page"], outcome=r["outcome"], failed=r["label"] == "failed",
                             check="pixel_effect_region", region=boxes[r["worked_id"]]["kind"], score=s, unmasked=keep,
                             parse_fail=False, missing=False, ms=np.nan))
        res[split] = pd.DataFrame(rows)
    th = Q.threshold(res["dev"])
    out = []
    for split, d in res.items():
        flag = d.score >= th
        k, n = int(flag[d.failed].sum()), int(d.failed.sum())
        w = M.wilson(k, n)
        row = dict(split=split, theta=th, recall_failures=k / n, recall_lo=w[1], recall_hi=w[2], false_alarm=float(flag[~d.failed].mean()))
        for o in ["failed_error", "failed_silent", "success_clear", "success_small"]:
            row[f"flag_{o}"] = float(flag[d.outcome == o].mean())
        out.append(row)
        d.to_csv(OUT / f"q3_pixel_effect_{split}_scores.csv", index=False)
    t = pd.DataFrame(out)
    t.to_csv(OUT / "q3_pixel_effect.csv", index=False)
    print(t.to_string(index=False, float_format=lambda v: f"{v:.3f}"))


def tier0():
    df = pd.read_csv(RES / "raw/w3_test_decisions.csv")
    t0 = df[df.tier == 0]
    fa = {c: float((t0[(t0.cond == c) & ~t0.relevant].action == "replan").mean()) for c in ("C4",)}
    w2 = pd.read_csv(RES / "raw/w2_test_decisions.csv")
    w0 = w2[w2.tier == 0]
    fa["C1"] = float((w0[(w0.cond == "C1") & ~w0.relevant].action == "replan").mean())
    from harness.run_checks import feature_table, load
    fz = json.loads((RES / "frozen_w2.json").read_text())["C4"]
    recs = {r["pair_id"]: r for r in load("test") if r["tier"] == 0}
    feats = feature_table("test", list(recs.values()), fz["mask_thr"], fz["mask_dilate"])
    c4 = t0[(t0.cond == "C4") & (t0.correct0 == "go") & (t0.action == "replan")]
    rows = []
    for _, d in c4.iterrows():
        F, _ = feats[d.pair_id]
        r = recs[d.pair_id]
        p = F["peaks"][0] if F["peaks"] else None
        rows.append(dict(pair_id=d.pair_id, event=d.event, motion_bin=d.motion_bin, reason=d.reason, scored_outcome=d.outcome,
                         in_place_ncc=round(F["in_place"], 3), tau_in=fz["tau_in"],
                         best_peak=round(p["score"], 3) if p else None, best_shift_px=(p["dx"], p["dy"]) if p else None,
                         target_ncc_in_place=round(F["at_in"]["target_ncc"], 3), bright_shift=round(F["at_in"]["bright_shift"], 2),
                         outside_drop=round(F["outside_drop"], 2),
                         truth_shift_px=None if not r["truth"][0].get("target_box") else
                         (round(r["truth"][0]["target_box"][0] - r["planned_box"][0], 1), round(r["truth"][0]["target_box"][1] - r["planned_box"][1], 1))))
    t = pd.DataFrame(rows)
    t.to_csv(OUT / "tier0_c4_false_replans.csv", index=False)
    print("Tier 0 test false-alarm rate: C1", round(fa["C1"], 3), "C4", round(fa["C4"], 3))
    print(t.to_string(index=False))


def none_share():
    from harness.run_checks import load
    rows = []
    for split in ("dev", "test", "all"):
        recs = (load("dev") + load("test")) if split == "all" else load(split)
        d = pd.DataFrame([dict(page=r["page"], seed=r["seed"], ca=r["truth"][0]["correct_action"]) for r in recs
                          if r["tier"] == 1 and r["event"] == "none"])
        for page, g in list(d.groupby("page")) + [("all pages", d)]:
            k, n = int((g.ca != "go").sum()), len(g)
            w = M.wilson(k, n)
            rows.append(dict(split=split, page=page, n=n, not_go=k, share=k / n, lo=w[1], hi=w[2],
                             reaim=int((g.ca == "reaim").sum()), replan=int((g.ca == "replan").sum())))
    t = pd.DataFrame(rows)
    t.to_csv(OUT / "none_not_go_share.csv", index=False)
    print(t.to_string(index=False, float_format=lambda v: f"{v:.3f}"))


def cap():
    """C5/C6 tuned exactly like Wave 2: expected s/step at p=0.05, infeasible if re-find errors exceed 1% of re-aims.
    Adds tau_low = 1.01 (tie-break never fires; cover escalation only) so cover-only settings are on the grid."""
    from harness.run_checks import Scorer, feature_table, load, objective, summarize
    from harness.run_models import GRID, run_escalate
    from models.qwen_jobs import TAU_LOW_MIN, results
    fz2 = json.loads((RES / "frozen_w2.json").read_text())["C4"]
    recs = [r for r in load("dev") if r["tier"] == 1]
    feats = feature_table("dev", recs, fz2["mask_thr"], fz2["mask_dilate"])
    outs, sc = results("dev_escalate"), Scorer(recs)
    log, best = [], {}
    for cond, size in (("C5", "2b"), ("C6", "4b")):
        for tl, cb in itertools.product(GRID["tau_low"] + [1.01], GRID["cover_band"]):
            cfg = {**A.DEFAULTS, **fz2, "tau_low": tl, "cover_band": cb, "cand_min": TAU_LOW_MIN}
            d = pd.DataFrame(run_escalate(recs, feats, cfg, size, outs, sc, cond))
            obj = objective(d)
            log.append(dict(cond=cond, tau_low=tl, cover_band=cb, objective=obj, escalated=float(d.escalated.mean()),
                            missing=int(d.missing.sum()), **{k: v for k, v in summarize(d).items() if k in ("reaim_recovery", "n_reaims", "wrong_reaims", "sec_p05")}))
            if np.isfinite(obj) and d.escalated.any() and (cond not in best or obj < best[cond][0]):
                best[cond] = (obj, dict(tau_low=tl, cover_band=cb, cand_min=TAU_LOW_MIN))
    pd.DataFrame(log).to_csv(OUT / "cap_tuning_dev.csv", index=False)
    frozen = {c: v[1] for c, v in best.items()}
    frozen["dev_objective"] = {c: v[0] for c, v in best.items()}
    frozen["rule"] = "Wave 2 objective(): s/step at p=0.05, re-find errors <= 1% of re-aims; settings that never escalate excluded"
    (OUT / "frozen_cap.json").write_text(json.dumps(frozen, indent=2))
    lg = pd.DataFrame(log)
    print(lg[np.isfinite(lg.objective)].sort_values(["cond", "objective"]).groupby("cond").head(4).to_string(index=False))
    print(json.dumps(frozen, indent=2))


def cap_test():
    from harness.run_checks import Scorer, feature_table, load, summarize
    from harness.run_models import run_escalate
    from models.qwen_jobs import results
    fz2 = json.loads((RES / "frozen_w2.json").read_text())["C4"]
    fz3 = json.loads((RES / "frozen_w3.json").read_text())
    fc = json.loads((OUT / "frozen_cap.json").read_text())
    recs = load("test")
    feats = feature_table("test", recs, fz2["mask_thr"], fz2["mask_dilate"])
    sc = Scorer(recs)
    outs = {**results("test_escalate"), **results("test_escalate_cap")}
    rows = []
    for cond, size in (("C5", "2b"), ("C6", "4b")):
        for name, cfg3 in (("prereg", fz3[cond]), ("cap", fc.get(cond))):
            if cfg3 is None:
                continue
            d = pd.DataFrame(run_escalate(recs, feats, {**A.DEFAULTS, **fz2, **cfg3}, size, outs, sc, cond))
            d1 = d[d.tier == 1]
            s = summarize(d1)
            lk = d1[(d1.event == "moved_lookalike") & (d1.action == "reaim")]
            rows.append(dict(cond=cond, rule=name, tau_low=cfg3["tau_low"], cover_band=cfg3["cover_band"], escalated=float(d1.escalated.mean()),
                             missing=int(d.missing.sum()), sec_p05=s["sec_p05"], reaim_recovery=s["reaim_recovery"], n_reaims=s["n_reaims"],
                             wrong_reaims=s["wrong_reaims"], wrong_hi=s["wrong_hi"], lookalike_wrong=int((lk.outcome == "wrong_reaim").sum()),
                             lookalike_reaims=len(lk), ms_mean=float(d1.delta_s.mean() * 1000)))
    t = pd.DataFrame(rows)
    t.to_csv(OUT / "cap_test.csv", index=False)
    print(t.to_string(index=False, float_format=lambda v: f"{v:.3f}"))


# ---------- reruns: opaque IDs, shuffled order; capped C5/C6 cover answers ----------

def _opaque_map():
    """worked_id -> opaque id (random hex, seed 20261023). Kept in private/ so no model-side file ever holds the ID."""
    import secrets, random
    p = ROOT / "private/q3_opaque_map.json"
    if p.exists():
        return json.loads(p.read_text())
    rng = random.Random(20261023)
    ids = [r["worked_id"] for r in Q.recs("test")]
    m = {w: "%016x" % rng.getrandbits(64) for w in ids}
    assert len(set(m.values())) == len(m)
    p.write_text(json.dumps(m, indent=1))
    return m


def pack_rerun():
    """One Colab job dir: Q3 test worked jobs with opaque job IDs and image names, shuffled order, plus the capped
    C5/C6 cover questions that the preregistered test run did not ask."""
    import random, shutil
    from PIL import Image
    from models.common import prompt
    from models.qwen_jobs import JOBS, pack_escalate
    from harness.run_checks import feature_table, load
    from harness.run_models import replay_asker
    from models.qwen_jobs import results
    m = _opaque_map()
    d = JOBS / "test_posthoc"
    if d.exists():
        shutil.rmtree(d)
    (d / "img").mkdir(parents=True)
    jobs = []
    for r in Q.recs("test"):
        o = m[r["worked_id"]]
        b = Image.open(ROOT / r["frames"]["before"]).convert("RGB").resize((640, 400), Image.LANCZOS)
        a = Image.open(ROOT / r["frames"]["after"]).convert("RGB")
        b.save(d / "img" / f"{o}_a.png"); a.save(d / "img" / f"{o}_b.png")
        for size in ("2b", "4b"):
            jobs.append(dict(job_id=f"q3|{size}|{o}", model=size, kind="worked", images=[f"img/{o}_a.png", f"img/{o}_b.png"],
                             prompt=prompt("worked", expected_effect=r["expected_effect"]), max_tokens=32))
    random.Random(7).shuffle(jobs)
    # capped C5/C6: questions the cap setting asks that the test run never answered
    fz2 = json.loads((RES / "frozen_w2.json").read_text())["C4"]
    fc = json.loads((OUT / "frozen_cap.json").read_text())
    recs = load("test")
    feats = feature_table("test", recs, fz2["mask_thr"], fz2["mask_dilate"])
    have = results("test_escalate")
    need = set()
    for r in recs:
        F, _ = feats[r["pair_id"]]
        for cond, size in (("C5", "2b"), ("C6", "4b")):
            calls = []
            A.decide(F, r["planned_box"], {**A.DEFAULTS, **fz2, **fc[cond]}, "escalate", replay_asker(F, r["pair_id"], size, have, calls))
            need |= {c["job_id"] for c in calls if c["missing"]}
    full = [j for j in pack_escalate("test", recs, JOBS / "test_escalate") if j["job_id"] in need]
    for j in full:
        for p in j["images"]:
            dst = d / p.replace("img/", "img/esc_")
            if not dst.exists():
                shutil.copy(JOBS / "test_escalate" / p, dst)
        j["images"] = [p.replace("img/", "img/esc_") for p in j["images"]]
    jobs += full
    (d / "jobs.jsonl").write_text("".join(json.dumps(j) + "\n" for j in jobs))
    print(f"{len(jobs)} jobs ({len(jobs) - len(full)} Q3 opaque, {len(full)} capped cover questions), {len(list((d / 'img').iterdir()))} images")


def q3_hosted(model):
    """Hosted Q3 rerun: shuffled order, results keyed by opaque ID (the API never received IDs in either run)."""
    import random
    from models import frontier as Fr
    from models.hosted_locate import MAX_TOKENS, SCHEMA, worked_req
    m = _opaque_map()
    recs = Q.recs("test")
    random.Random(11).shuffle(recs)
    p = RES / f"hosted_out/test_{model}_worked_opaque.jsonl"
    done = {json.loads(l)["opaque_id"] for l in p.read_text().splitlines()} if p.exists() else set()
    with p.open("a") as f:
        for i, r in enumerate(recs):
            o = m[r["worked_id"]]
            if o in done:
                continue
            ims, txt = worked_req(r)
            a = Fr.ask(model, ims, txt, max_tokens=MAX_TOKENS[model], tag=f"posthoc_q3|test|{o}", est_in=1800, schema=SCHEMA["worked"])
            f.write(json.dumps(dict(opaque_id=o, raw=a["text"], ms=round(a["ms"], 1), usd=a["usd"], stop_reason=a["stop_reason"],
                                    request_id=a["request_id"], model=a["model"])) + "\n")
            f.flush()
            if i % 50 == 0:
                print(model, i + 1, "spent", round(Fr.meter().total, 4), flush=True)


def q3_opaque():
    """Score the opaque, shuffled Q3 rerun with the frozen thresholds; compare with the preregistered run pair by pair."""
    from models import hosted_locate as H
    from models.qwen_jobs import results
    inv = {v: k for k, v in _opaque_map().items()}
    th = json.loads((RES / "frozen_q3.json").read_text())["theta"]
    recs = {r["worked_id"]: r for r in Q.recs("test")}
    q_new = {j: o for j, o in results("test_posthoc").items() if j.startswith("q3|")}
    q_old = results("test_worked")
    sources = {}
    for size in ("2b", "4b"):
        sources[f"qwen3-vl-{size}"] = ({inv[j.split("|")[2]]: o["raw"] for j, o in q_new.items() if j.split("|")[1] == size},
                                       {j.split("|")[2]: o["raw"] for j, o in q_old.items() if j.split("|")[1] == size})
    for m in ("claude-haiku-5-5", "claude-opus-5-5"):
        p = RES / f"hosted_out/test_{m}_worked_opaque.jsonl"
        new = {inv[j["opaque_id"]]: j["raw"] for j in map(json.loads, p.read_text().splitlines())} if p.exists() else {}
        sources[m] = (new, {k: v["raw"] for k, v in H.done(m, "test", "worked").items()})
    rows = []
    for check, (new, old) in sources.items():
        if not new:
            continue
        for run, ans in (("preregistered", old), ("opaque_shuffled", new)):
            sc = {w: Q.model_score(ans[w])[0] if w in ans else 0.5 for w in recs}
            flag = {w: sc[w] >= th[check] for w in recs}
            f = [w for w in recs if recs[w]["label"] == "failed"]
            k = sum(flag[w] for w in f)
            wl = M.wilson(k, len(f))
            row = dict(check=check, run=run, n=len(recs), answered=sum(w in ans for w in recs), recall_failures=k / len(f),
                       recall_lo=wl[1], recall_hi=wl[2], false_alarm=float(np.mean([flag[w] for w in recs if recs[w]["label"] != "failed"])))
            for o in ["failed_error", "failed_silent", "success_clear", "success_small"]:
                row[f"flag_{o}"] = float(np.mean([flag[w] for w in recs if recs[w]["outcome"] == o]))
            rows.append(row)
        same = [Q.model_score(new[w])[0] == Q.model_score(old[w])[0] for w in recs if w in new and w in old]
        rows[-1]["same_answer_as_prereg"] = float(np.mean(same))
    t = pd.DataFrame(rows)
    t.to_csv(OUT / "q3_opaque.csv", index=False)
    print(t.to_string(index=False, float_format=lambda v: f"{v:.3f}"))


if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    cmd = sys.argv[1]
    if cmd == "q3_hosted":
        q3_hosted(sys.argv[2])
    else:
        {"pixel_effect": pixel_effect, "tier0": tier0, "none_share": none_share, "cap": cap, "cap_test": cap_test,
         "pack_rerun": pack_rerun, "q3_opaque": q3_opaque}[cmd]()
