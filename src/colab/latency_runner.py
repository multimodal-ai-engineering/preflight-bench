"""Extension B.2: clean latencies on a dedicated T4 (nothing else on the GPU). Self-contained apart from vlm_runner.py
next to it (same loaders and prompts as the full study).

  python latency_runner.py JOBDIR OUTFILE --models qwen2b,qwen4b,florence2
  PYTHONPATH=/content/tf457 python latency_runner.py JOBDIR OUTFILE --models smolvlm2   # transformers 4.57.1

JOBDIR/latency_jobs.jsonl: full-study test jobs, each with "role": "warmup" or "timed". Per model: the 10 warm-up
calls (not logged), then every timed job, one at a time (batch 1, fp16 on a T4, CUDA-synchronized generate time).
OUTFILE gets one JSON line per timed call. Run models one after another, never two processes at once.
"""
import json, sys, time
from pathlib import Path

import torch
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))
from vlm_runner import REPOS, ask_chat, ask_florence_ocr, env, load  # noqa: E402


def main(jobdir, outfile, models):
    jobdir, outfile = Path(jobdir), Path(outfile)
    jobs = [json.loads(l) for l in (jobdir / "latency_jobs.jsonl").read_text().splitlines() if l.strip()]
    done = set()
    if outfile.exists():
        done = {json.loads(l)["model_key"] for l in outfile.read_text().splitlines() if l.strip()}
    e = env()
    print(json.dumps(e), flush=True)
    for name in models:
        if name in done:  # a model is timed in one go or not at all
            continue
        mine = [j for j in jobs if j["model"] == name]
        model, proc = load(name, e["dtype"])
        imgs = lambda j: [Image.open(jobdir / p).convert("RGB") for p in j["images"]]

        def run(j):
            if name == "florence2":
                return ask_florence_ocr(model, proc, imgs(j)[-1], tuple(j.get("ocr_tiles", (2, 2))))
            return ask_chat(model, proc, imgs(j), j["prompt"], j["max_tokens"], j.get("labels"))
        for j in [j for j in mine if j["role"] == "warmup"]:
            run(j)
        rows = []
        for j in [j for j in mine if j["role"] == "timed"]:
            txt, ms, nin, nout = run(j)
            rows.append(dict(model_key=name, model=REPOS[name], job_id=j["job_id"], kind=j["kind"], ms=round(ms, 1), n_input_tokens=nin,
                             n_output_tokens=nout, gpu_procs=torch.cuda.device_count(), **e))
        with outfile.open("a") as f:
            for r in rows:
                f.write(json.dumps(r) + "\n")
        print(name, len(rows), "timed; median ms", sorted(r["ms"] for r in rows)[len(rows) // 2], flush=True)
        del model
        torch.cuda.empty_cache()


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[sys.argv.index("--models") + 1].split(","))
