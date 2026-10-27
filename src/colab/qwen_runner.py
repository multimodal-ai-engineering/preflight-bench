"""Runs Qwen3-VL jobs on a Colab GPU runtime (transformers + CUDA). Self-contained: copy to the runtime and run.

  python qwen_runner.py JOBDIR OUTFILE [--models 2b,4b]

JOBDIR holds jobs.jsonl and the PNGs it names. Each job:
  {"job_id", "model": "2b"|"4b", "kind", "images": ["img/....png", ...], "prompt", "max_tokens", optional "labels"}
OUTFILE gets one JSON line per job: job_id, model, raw text, ms (generate wall time, CUDA-synchronized),
n_input_tokens, n_output_tokens. Already finished job_ids in OUTFILE are skipped, so a disconnected runtime
can resume. Greedy decoding (temperature 0).
"""
import json, sys, time
from pathlib import Path

import torch
from PIL import Image
from transformers import AutoProcessor, Qwen3VLForConditionalGeneration

REPOS = {"2b": "Qwen/Qwen3-VL-2B-Instruct", "4b": "Qwen/Qwen3-VL-4B-Instruct"}


def env():
    import transformers
    p = torch.cuda.get_device_properties(0) if torch.cuda.is_available() else None
    return dict(gpu=p.name if p else "cpu", gpu_mem_gb=round(p.total_memory / 2**30, 1) if p else 0,
                torch=torch.__version__, transformers=transformers.__version__,
                # native bf16 needs compute capability 8.0+ (L4 yes, T4 no; is_bf16_supported() also counts emulation)
                dtype="bfloat16" if p and torch.cuda.get_device_capability(0) >= (8, 0) else "float16")


def load(size, dtype):
    m = Qwen3VLForConditionalGeneration.from_pretrained(REPOS[size], dtype=getattr(torch, dtype), device_map="cuda")
    return m.eval(), AutoProcessor.from_pretrained(REPOS[size])


@torch.inference_mode()
def ask(model, proc, images, text, max_tokens, labels=None):
    content = []
    for i, im in enumerate(images):
        if labels:  # optional text label before each image (tie-break: "Reference", "Candidate 1", ...)
            content.append({"type": "text", "text": labels[i]})
        content.append({"type": "image", "image": im})
    msgs = [{"role": "user", "content": content + [{"type": "text", "text": text}]}]
    inputs = proc.apply_chat_template(msgs, tokenize=True, add_generation_prompt=True, return_dict=True,
                                      return_tensors="pt").to(model.device)
    torch.cuda.synchronize()
    t0 = time.perf_counter()
    out = model.generate(**inputs, max_new_tokens=max_tokens, do_sample=False)
    torch.cuda.synchronize()
    ms = (time.perf_counter() - t0) * 1000
    new = out[0, inputs["input_ids"].shape[1]:]
    return proc.decode(new, skip_special_tokens=True), ms, int(inputs["input_ids"].shape[1]), int(new.shape[0])


def main(jobdir, outfile, models=("2b", "4b")):
    jobdir, outfile = Path(jobdir), Path(outfile)
    jobs = [json.loads(l) for l in (jobdir / "jobs.jsonl").read_text().splitlines() if l.strip()]
    done = set()
    if outfile.exists():
        done = {json.loads(l)["job_id"] for l in outfile.read_text().splitlines() if l.strip()}
    e = env()
    print(json.dumps(e), f"{len(jobs)} jobs, {len(done)} done", flush=True)
    for size in models:
        todo = [j for j in jobs if j["model"] == size and j["job_id"] not in done]
        if not todo:
            continue
        t = time.perf_counter()
        model, proc = load(size, e["dtype"])
        load_s = time.perf_counter() - t
        imgs = lambda j: [Image.open(jobdir / p).convert("RGB") for p in j["images"]]
        ask(model, proc, imgs(todo[0]), todo[0]["prompt"], todo[0]["max_tokens"], todo[0].get("labels"))  # warm-up, not logged
        with outfile.open("a") as f:
            for i, j in enumerate(todo):
                txt, ms, nin, nout = ask(model, proc, imgs(j), j["prompt"], j["max_tokens"], j.get("labels"))
                f.write(json.dumps(dict(job_id=j["job_id"], model=REPOS[size], kind=j["kind"], raw=txt, ms=round(ms, 1),
                                        n_input_tokens=nin, n_output_tokens=nout, load_s=round(load_s, 1), **e)) + "\n")
                f.flush()
                if i % 50 == 0:
                    print(f"{size} {i + 1}/{len(todo)} {ms:.0f} ms", flush=True)
        del model
        torch.cuda.empty_cache()


if __name__ == "__main__":
    ms = sys.argv[sys.argv.index("--models") + 1].split(",") if "--models" in sys.argv else ("2b", "4b")
    main(sys.argv[1], sys.argv[2], ms)
