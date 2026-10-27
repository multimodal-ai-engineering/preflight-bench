"""Pack full-study GPU jobs for colab/vlm_runner.py (Qwen3-VL 2B/4B, SmolVLM2, Florence-2).

  python -m models.full_jobs pack        # -> results/full/gpu_jobs/full/{jobs.jsonl, img/} (dev first, then test)
  python -m models.full_jobs subsets     # print the subset sizes

Subsets (preregistered sizes): per tier, test 600 action pairs and 300 worked pairs; dev 150 and 75. Stratified
only by public fields (template kind, variant, tier, background setting / effect kind), never by labels.
Escalation questions (C5/C6) are packed for the action subsets: every tie-break or cover question the anchored check
could ask under any setting of the C5/C6 grid (tau_low, cover band) with the frozen C4 thresholds, so tuning on dev
and scoring on test need no second GPU round.
"""
import json, random, sys
from pathlib import Path

from PIL import Image

from anchored import check as A
from models.common import plan_crop

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results/full/gpu_jobs/full"
PROMPTS = ROOT / "models/prompts_full"
SIZES = {"test": dict(action=600, worked=300), "dev": dict(action=150, worked=75)}
CHAT = ["qwen2b", "qwen4b", "smolvlm2"]
ESC_GRID = dict(tau_low=[0.5, 0.6, 0.7, 0.8, 0.85, 0.9, 0.95, 1.01], cover_band=[0.0, 0.1, 0.25, 0.5, 0.75])


def public(split, part):
    name = "pairs" if part == "action" else "worked"
    return [json.loads(l) for l in (ROOT / f"data/full/{split}/{name}.jsonl").read_text().splitlines() if l.strip()]


def strat(rs, n, key, seed):
    rng = random.Random(seed)
    groups = {}
    for r in rs:
        groups.setdefault(key(r), []).append(r)
    g = [rng.sample(v, len(v)) for _, v in sorted(groups.items())]
    out = []
    while len(out) < min(n, len(rs)):
        for x in g:
            if x and len(out) < n:
                out.append(x.pop())
    return out


def subsets(split):
    a, w = public(split, "action"), public(split, "worked")
    out = {}
    for tier in (0, 1, 2):
        out[("action", tier)] = strat([r for r in a if r["tier"] == tier], SIZES[split]["action"],
                                      lambda r: (r["kind"], r["variant"], r.get("motion"), str(r.get("degrade") is not None)), 11 + tier)
        out[("worked", tier)] = strat([r for r in w if r["tier"] == tier], SIZES[split]["worked"],
                                      lambda r: (r["kind"], r["variant"], r["effect_kind"]), 21 + tier)
    return out


def rel_box(box):
    x, y, w, h = box
    return dict(rx1=round(x / 1.28), ry1=round(y / 0.8), rx2=round((x + w) / 1.28), ry2=round((y + h) / 0.8))


def save(im, name):
    p = OUT / "img" / name
    if not p.exists():
        im.save(p)
    return f"img/{name}"


def esc_questions(r, F, c4):
    """job specs (kind, images-builder, prompt, labels) for every escalation question any grid setting can ask."""
    import itertools
    asked = {}
    def ask_rec(kind, arg):
        if kind == "cover":
            name = "in" if arg is F["at_in"] else f"p{F['peaks'].index(arg)}"
            asked[f"cover_{name}"] = arg
            return {"covered": False}
        asked["tiebreak"] = arg
        return {"choice": None}
    for tl, cb in itertools.product(*ESC_GRID.values()):
        cfg = {**A.DEFAULTS, **c4, "tau_low": tl, "cover_band": cb, "cand_min": 0.5}
        A.decide(F, r["planned_box"], cfg, "escalate", ask_rec)
        if "tiebreak" in asked:  # every choice could lead to a cover question on that candidate
            for i in range(len(asked["tiebreak"])):
                A.decide(F, r["planned_box"], cfg, "escalate", lambda k, a, i=i: ask_rec(k, a) if k == "cover" else {"choice": i + 1})
    return asked


def pack():
    import shutil
    from harness.full_checks import features
    if OUT.exists():
        shutil.rmtree(OUT)
    (OUT / "img").mkdir(parents=True)
    c4 = json.loads((ROOT / "results/full/frozen_full.json").read_text())["C4"]
    jobs = []
    for split in ("dev", "test"):
        ss = subsets(split)
        feats = features(split)
        for (part, tier), rs in sorted(ss.items()):
            for r in rs:
                pid = r["pair_id"]
                if part == "action":
                    pa = Image.open(ROOT / r["frames"]["planned_a"]).convert("RGB")
                    crop, _ = plan_crop(pa, r["planned_box"])
                    imgs = [save(crop, f"{pid}_crop.png"), save(Image.open(ROOT / r["frames"]["current_b"]).convert("RGB"), f"{pid}_cur.png")]
                    pr = (PROMPTS / "action_q.txt").read_text().strip().format(**rel_box(r["planned_box"]))
                    for m in CHAT:
                        jobs.append(dict(job_id=f"action|{m}|{split}|{pid}", model=m, kind="action", images=imgs, prompt=pr, max_tokens=40))
                    # escalation questions (Tier 1 and 2 only matter for tuning, but all tiers are scored)
                    F = feats[pid]["F"]
                    pag = A.gray(ROOT / r["frames"]["planned_a"]); cbg = A.gray(ROOT / r["frames"]["current_b"])
                    x, y, w, h = [int(round(v)) for v in r["planned_box"]]
                    X0, Y0, W, H = F["ctx"]
                    for q, arg in esc_questions(r, F, c4).items():
                        if q == "tiebreak":
                            tpl = save(Image.fromarray(pag[Y0:Y0 + H, X0:X0 + W]), f"{pid}_ctx.png")
                            ims = [tpl] + [save(Image.fromarray(cbg[max(0, Y0 + p["dy"]):Y0 + p["dy"] + H, max(0, X0 + p["dx"]):X0 + p["dx"] + W]), f"{pid}_cand{i}.png")
                                           for i, p in enumerate(arg)]
                            n = len(arg)
                            pr2 = (PROMPTS / "tiebreak.txt").read_text().strip().format(n=n, choices="|".join(str(i + 1) for i in range(n)))
                            labels = ["Reference"] + [f"Candidate {i + 1}" for i in range(n)]
                        else:
                            X, Y = x + arg["dx"], y + arg["dy"]
                            c = cbg[max(0, Y):Y + h, max(0, X):X + w]
                            if c.size == 0:
                                continue
                            ims = [save(A._padded(Image.fromarray(pag[y:y + h, x:x + w])), f"{pid}_tgt.png"), save(A._padded(Image.fromarray(c)), f"{pid}_{q}.png")]
                            pr2, labels = (PROMPTS / "cover.txt").read_text().strip(), None
                        for m in ("qwen2b", "qwen4b"):
                            j = dict(job_id=f"{q}|{m}|{split}|{pid}", model=m, kind=q.split("_")[0], images=ims, prompt=pr2, max_tokens=32)
                            if labels:
                                j["labels"] = labels
                            jobs.append(j)
                else:
                    b = save(Image.open(ROOT / r["frames"]["before"]).convert("RGB").resize((640, 400), Image.LANCZOS), f"{pid}_before640.png")
                    a = save(Image.open(ROOT / r["frames"]["after"]).convert("RGB"), f"{pid}_after.png")
                    pr = (PROMPTS / "worked.txt").read_text().strip().format(expected_effect=r["expected_effect"])
                    for m in CHAT:
                        jobs.append(dict(job_id=f"worked|{m}|{split}|{pid}", model=m, kind="worked", images=[b, a], prompt=pr, max_tokens=32))
                    jobs.append(dict(job_id=f"worked|florence2|{split}|{pid}", model="florence2", kind="worked", images=[b, a], prompt="<OCR>",
                                     max_tokens=256, ocr_tiles=[2, 2]))
    # order: per model, dev before test, worked and action interleaved as packed
    (OUT / "jobs.jsonl").write_text("".join(json.dumps(j) + "\n" for j in jobs))
    from collections import Counter
    print(len(jobs), "jobs", Counter((j["model"], j["job_id"].split("|")[2], j["kind"]) for j in jobs))


if __name__ == "__main__":
    if sys.argv[1] == "pack":
        pack()
    else:
        for split in ("dev", "test"):
            print(split, {k: len(v) for k, v in subsets(split).items()})
