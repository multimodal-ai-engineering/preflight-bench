"""Extension GPU jobs: B.2 latency jobs (stratified test jobs) and D.2 Qwen3-VL 4B re-ground jobs, in one folder.

  python -m colab.make_ext_jobs     # -> results/extension/gpu_jobs/ext/ (+ ext.zip)

B.2: the same pairs for every model. Qwen 2B / 4B / SmolVLM2: 100 action + 100 worked timed jobs and 10 warm-ups
(5 + 5); Florence-2: 200 worked timed jobs and 10 warm-ups. Drawn round-robin over (tier, page kind), seed 0.
D.2: one job per fired step: the current screenshot (1024x640, as the planner saw it) and the re-ground prompt.
"""
import io, json, random, shutil, zipfile
from collections import defaultdict
from pathlib import Path

from PIL import Image

from harness.full_checks import ROOT, load

SRC = ROOT / "results/full/gpu_jobs/full"
OUT = ROOT / "results/extension/gpu_jobs/ext"
D2 = ROOT / "results/extension/live/d2.jsonl"
PRIV = ROOT / "private/ext_d2"


def stratified(ids, meta, n, rng):
    cells = defaultdict(list)
    for i in sorted(ids):
        cells[meta[i]].append(i)
    for v in cells.values():
        rng.shuffle(v)
    keys, out = sorted(cells), []
    while len(out) < n and any(cells.values()):
        for k in keys:
            if cells[k] and len(out) < n:
                out.append(cells[k].pop())
    return out


def main():
    rng = random.Random(0)
    jobs = [json.loads(l) for l in (SRC / "jobs.jsonl").read_text().splitlines() if l.strip()]
    test = [j for j in jobs if j["job_id"].split("|")[2] == "test"]
    by = defaultdict(dict)
    for j in test:
        by[(j["model"], j["kind"])][j["job_id"].split("|")[3]] = j
    meta = {r["pair_id"]: (r["tier"], r["kind"]) for r in load("test") + load("test", "worked")}
    act = set.intersection(*(set(by[(m, "action")]) for m in ("qwen2b", "qwen4b", "smolvlm2")))
    wrk = set.intersection(*(set(by[(m, "worked")]) for m in ("qwen2b", "qwen4b", "smolvlm2", "florence2")))
    a_ids = stratified(act, meta, 105, rng)
    w_ids = stratified(wrk, meta, 210, rng)
    if OUT.exists():
        shutil.rmtree(OUT)
    (OUT / "img").mkdir(parents=True)
    lat = []
    plan = {m: [("action", a_ids[:5], "warmup"), ("worked", w_ids[:5], "warmup"), ("action", a_ids[5:105], "timed"), ("worked", w_ids[5:105], "timed")]
            for m in ("qwen2b", "qwen4b", "smolvlm2")}
    plan["florence2"] = [("worked", w_ids[:10], "warmup"), ("worked", w_ids[10:210], "timed")]
    for m, parts in plan.items():
        for kind, ids, role in parts:
            for pid in ids:
                j = dict(by[(m, kind)][pid], role=role)
                for p in j["images"]:
                    if not (OUT / p).exists():
                        shutil.copy(SRC / p, OUT / p)
                lat.append(j)
    (OUT / "latency_jobs.jsonl").write_text("".join(json.dumps(j) + "\n" for j in lat))
    rg = []
    if D2.exists():
        for l in D2.read_text().splitlines():
            r = json.loads(l)
            if "recoveries" not in r:
                continue
            q = r["recoveries"]["qwen_job"]
            im = Image.open(PRIV / f"{q['stem']}.png").convert("RGB").resize((1024, 640), Image.LANCZOS)
            im.save(OUT / f"img/d2_{q['stem']}.png")
            rg.append(dict(job_id=f"reground|qwen4b|d2|{q['stem']}", model="qwen4b", kind="reground", images=[f"img/d2_{q['stem']}.png"],
                           prompt=q["prompt"], max_tokens=60))
    (OUT / "jobs.jsonl").write_text("".join(json.dumps(j) + "\n" for j in rg))
    for f in ("vlm_runner.py", "latency_runner.py"):
        shutil.copy(ROOT / "colab" / f, OUT / f)
    z = OUT.parent / "ext.zip"
    with zipfile.ZipFile(z, "w", zipfile.ZIP_STORED) as zf:
        for p in OUT.rglob("*"):
            if p.is_file():
                zf.write(p, p.relative_to(OUT.parent))
    print(len(lat), "latency jobs;", len(rg), "re-ground jobs;", z, round(z.stat().st_size / 1e6, 1), "MB")


if __name__ == "__main__":
    main()
