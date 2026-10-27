"""Packs Qwen3-VL jobs for the Colab runner (colab/qwen_runner.py) and reads its outputs back.

  python -m models.qwen_jobs pack SPLIT KIND[,KIND...]   # -> results/pilot/qwen_jobs/SPLIT_KIND/ (jobs.jsonl + img/)
  python -m models.qwen_jobs status SPLIT_KIND

Kinds:
  locate     C7: 448x336 planning crop + full current_b, Qwen3-VL 4B
  worked     Q3: before at 640x400 + after at full size + expected effect, 2B and 4B
  escalate   C5/C6: tie-break and cover questions for every dev/test pair, 2B and 4B. Candidates are the top three
             search peaks scoring at least TAU_LOW_MIN, and cover questions are sent for every candidate spot and the
             in-place spot, so tuning tau_low and the cover band reuses the answers without new calls.

Test-split jobs are refused until the pilot-prereg-w3 tag is in HEAD's history.
"""
import json, subprocess, sys
from pathlib import Path

from PIL import Image

from anchored import check as A
from models.common import plan_crop, prompt

ROOT = Path(__file__).resolve().parents[1]
JOBS = ROOT / "results/pilot/qwen_jobs"
TAU_LOW_MIN = 0.5


def _guard(split):
    if split == "test":
        tags = subprocess.run(["git", "tag", "--merged", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.split()
        if "pilot-prereg-w3" not in tags:
            sys.exit("test-split model jobs need the pilot-prereg-w3 tag in HEAD's history")


def _save(im, d, name):
    p = d / "img" / name
    if not p.exists():
        im.save(p)
    return f"img/{name}"


def locate_kw(box, crop_box):
    """Pixel fields for locate_claude; 0-1000 relative fields for locate_qwen (Qwen3-VL's grounding convention).
    locate_qwen v1 gave the earlier box in pixels and asked for relative output; Qwen mixed the two on dev
    (24 of 58 unchanged pairs answered in pixels, 6 in relative units), so v2 uses relative units throughout."""
    x, y, _, _ = [round(v) for v in box]
    cx, cy, w, h = crop_box
    rel = dict(rx1=round(x / 1.28), ry1=round(y / 0.8), rx2=round((x + w) / 1.28), ry2=round((y + h) / 0.8))
    return dict(x=x, y=y, w=w, h=h, cx=cx, cy=cy, **rel)


def pack_locate(split, recs, d, models=("4b",)):
    out = []
    for r in recs:
        pa = Image.open(ROOT / r["frames"]["planned_a"]).convert("RGB")
        crop, cbox = plan_crop(pa, r["planned_box"])
        a = _save(crop, d, f"{r['pair_id']}_plancrop.png")
        b = _save(Image.open(ROOT / r["frames"]["current_b"]).convert("RGB"), d, f"{r['pair_id']}_current_b.png")
        for m in models:
            out.append(dict(job_id=f"locate|{m}|{r['pair_id']}", model=m, kind="locate", pair_id=r["pair_id"],
                            images=[a, b], prompt=prompt("locate_qwen", **locate_kw(r["planned_box"], cbox)), max_tokens=64))
    return out


def pack_worked(split, d, models=("2b", "4b")):
    recs = [json.loads(l) for l in (ROOT / f"data/pilot/{split}/worked.jsonl").read_text().splitlines() if l.strip()]
    out = []
    for r in recs:
        r["pair_id"] = r["worked_id"]
        fr = r["frames"]
        a = _save(Image.open(ROOT / fr["before"]).convert("RGB").resize((640, 400), Image.LANCZOS), d, f"{r['pair_id']}_before640.png")
        b = _save(Image.open(ROOT / fr["after"]).convert("RGB"), d, f"{r['pair_id']}_after.png")
        for m in models:
            out.append(dict(job_id=f"worked|{m}|{r['pair_id']}", model=m, kind="worked", pair_id=r["pair_id"], images=[a, b],
                            prompt=prompt("worked", expected_effect=r["expected_effect"]), max_tokens=32))
    return out


def pack_escalate(split, recs, d, models=("2b", "4b")):
    from harness.run_checks import feature_table
    fz = json.loads((ROOT / "results/pilot/frozen_w2.json").read_text())["C4"]
    feats = feature_table(split, recs, fz["mask_thr"], fz["mask_dilate"])
    out = []
    for r in recs:
        F, _ = feats[r["pair_id"]]
        pa = A.gray(ROOT / r["frames"]["planned_a"])
        cb = A.gray(ROOT / r["frames"]["current_b"])
        x, y, w, h = [int(round(v)) for v in r["planned_box"]]
        X0, Y0, W, H = F["ctx"]
        pid = r["pair_id"]
        tgt = _save(A._padded(Image.fromarray(pa[y:y + h, x:x + w])), d, f"{pid}_tgt.png")
        cands = [p for p in F["peaks"] if p["score"] >= TAU_LOW_MIN][:3]
        spots = [("in", F["at_in"])] + [(f"p{i}", p) for i, p in enumerate(F["peaks"])]
        jobs_pair = []
        if cands:
            tpl = _save(Image.fromarray(pa[Y0:Y0 + H, X0:X0 + W]), d, f"{pid}_ctx.png")
            imgs = [tpl]
            for i, p in enumerate(cands):
                c = cb[max(0, Y0 + p["dy"]):Y0 + p["dy"] + H, max(0, X0 + p["dx"]):X0 + p["dx"] + W]
                imgs.append(_save(Image.fromarray(c), d, f"{pid}_cand{i}.png"))
            n = len(cands)
            jobs_pair.append(("tiebreak", imgs, prompt("tiebreak", n=n, choices="|".join(str(i + 1) for i in range(n))),
                              ["Reference"] + [f"Candidate {i + 1}" for i in range(n)]))
        for name, s in spots:
            X, Y = x + s["dx"], y + s["dy"]
            c = cb[max(0, Y):Y + h, max(0, X):X + w]
            if c.size == 0:
                continue
            cur = _save(A._padded(Image.fromarray(c)), d, f"{pid}_cover_{name}.png")
            jobs_pair.append((f"cover_{name}", [tgt, cur], prompt("cover"), None))
        for m in models:
            for kind, imgs, pr, labels in jobs_pair:
                j = dict(job_id=f"{kind}|{m}|{pid}", model=m, kind=kind, pair_id=pid, images=imgs, prompt=pr, max_tokens=32)
                if labels:
                    j["labels"] = labels
                out.append(j)
    return out


def needed_escalate(split, recs, jobs):
    """Only the escalation questions the frozen C5/C6 settings will ask (pixel features decide which); test packing uses
    this so the T4 does not answer questions the frozen rule never reads. The answer to a tie-break can change which
    cover question follows, so both cover questions a tie-break could lead to are kept."""
    from harness.run_checks import feature_table
    fz2 = json.loads((ROOT / "results/pilot/frozen_w2.json").read_text())["C4"]
    fz3 = json.loads((ROOT / "results/pilot/frozen_w3.json").read_text())
    feats = feature_table(split, recs, fz2["mask_thr"], fz2["mask_dilate"])
    keep = set()
    for r in recs:
        F, _ = feats[r["pair_id"]]
        for cond, size in (("C5", "2b"), ("C6", "4b")):
            cfg = {**A.DEFAULTS, **fz2, **fz3[cond]}
            asked = []

            def ask(kind, arg, size=size, pid=r["pair_id"]):
                if kind == "cover":
                    name = "in" if arg is F["at_in"] else f"p{F['peaks'].index(arg)}"
                    asked.append(f"cover_{name}|{size}|{pid}")
                    return {"covered": False}
                asked.append(f"tiebreak|{size}|{pid}")
                n = len(arg)
                for i in range(n):  # every possible choice -> every cover question it could trigger
                    A.decide(F, r["planned_box"], cfg, "escalate", lambda k, a: ask(k, a) if k == "cover" else {"choice": i + 1})
                return {"choice": None}
            A.decide(F, r["planned_box"], cfg, "escalate", ask)
            keep.update(asked)
    return [j for j in jobs if j["job_id"] in keep]


def pack(split, kinds):
    _guard(split)
    from harness.run_checks import load
    recs = load(split) if split == "dev" else [json.loads(l) for l in (ROOT / f"data/pilot/{split}/pairs.jsonl").read_text().splitlines() if l.strip()]
    for kind in kinds:
        d = JOBS / f"{split}_{kind}"
        (d / "img").mkdir(parents=True, exist_ok=True)
        jobs = {"locate": lambda: pack_locate(split, recs, d), "worked": lambda: pack_worked(split, d),
                "escalate": lambda: (needed_escalate(split, recs, pack_escalate(split, recs, d)) if split == "test"
                                     else pack_escalate(split, recs, d))}[kind]()
        (d / "jobs.jsonl").write_text("".join(json.dumps(j) + "\n" for j in jobs))
        print(f"{d.relative_to(ROOT)}: {len(jobs)} jobs, {len(list((d / 'img').iterdir()))} images")


def results(name):
    """job_id -> output row, from results/pilot/qwen_out/NAME.jsonl (copied back from the runtime)."""
    p = ROOT / "results/pilot/qwen_out" / f"{name}.jsonl"
    return {j["job_id"]: j for j in map(json.loads, p.read_text().splitlines()) if j} if p.exists() else {}


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "pack":
        pack(sys.argv[2], sys.argv[3].split(","))
    elif cmd == "status":
        jobs = (JOBS / sys.argv[2] / "jobs.jsonl").read_text().splitlines()
        print(f"{len(results(sys.argv[2]))}/{len(jobs)} done")
