"""Runs small vision-language model jobs on a Colab GPU (transformers + CUDA). Self-contained. Full study.
SmolVLM2 fails in transformers 5.20.2 (image-feature shape error in inputs_merger); run its jobs with
PYTHONPATH pointing at a separate transformers==4.57.1 + num2words install. The other models use 5.20.2.

  python vlm_runner.py JOBDIR OUTFILE --models qwen2b,qwen4b,smolvlm2,florence2
  VLM_SHARD=k/n python vlm_runner.py ...   # one of n parallel workers (give each its own OUTFILE, same stem prefix)

JOBDIR holds jobs.jsonl and the PNGs it names. Each job:
  {"job_id", "model", "kind", "images": [...], "prompt", "max_tokens", optional "labels", optional "ocr_tiles"}
Chat models (Qwen3-VL 2B/4B, SmolVLM2 2.2B) get the images (optionally each preceded by a text label) and the
prompt; greedy decoding. Florence-2 is not a chat model: for jobs with kind "worked" it reads the after frame
with its <OCR> task, split into ocr_tiles (2x2 by default), and returns the text (matching happens offline).
OUTFILE gets one JSON line per job (appended and flushed, so the file can live on Google Drive and a disconnected
runtime resumes): job_id, model repo, raw text, ms (CUDA-synchronized generate time), token counts, gpu, dtype,
versions. Finished job_ids are skipped.
"""
import hashlib, json, os, sys, time
from pathlib import Path

import torch
from PIL import Image

SHARD = os.environ.get("VLM_SHARD")  # optional "k/n"
REPOS = {"qwen2b": "Qwen/Qwen3-VL-2B-Instruct", "qwen4b": "Qwen/Qwen3-VL-4B-Instruct",
         "smolvlm2": "HuggingFaceTB/SmolVLM2-2.2B-Instruct", "florence2": "florence-community/Florence-2-large"}


def env():
    import transformers
    p = torch.cuda.get_device_properties(0) if torch.cuda.is_available() else None
    return dict(gpu=p.name if p else "cpu", gpu_mem_gb=round(p.total_memory / 2**30, 1) if p else 0,
                torch=torch.__version__, transformers=transformers.__version__,
                # native bf16 needs compute capability 8.0+ (L4, A100 yes; T4 no)
                dtype="bfloat16" if p and torch.cuda.get_device_capability(0) >= (8, 0) else "float16")


def load(name, dtype):
    from transformers import AutoModelForImageTextToText, AutoProcessor
    dt = getattr(torch, dtype)
    if name.startswith("qwen"):
        from transformers import Qwen3VLForConditionalGeneration
        m = Qwen3VLForConditionalGeneration.from_pretrained(REPOS[name], dtype=dt, device_map="cuda")
    elif name == "florence2":
        from transformers import Florence2ForConditionalGeneration
        m = Florence2ForConditionalGeneration.from_pretrained(REPOS[name], dtype=dt, device_map="cuda")
    else:
        m = AutoModelForImageTextToText.from_pretrained(REPOS[name], dtype=dt, device_map="cuda")
    return m.eval(), AutoProcessor.from_pretrained(REPOS[name])


def timed(fn):
    torch.cuda.synchronize(); t0 = time.perf_counter()
    out = fn()
    torch.cuda.synchronize()
    return out, (time.perf_counter() - t0) * 1000


@torch.inference_mode()
def ask_chat(model, proc, images, text, max_tokens, labels=None):
    content = []
    for i, im in enumerate(images):
        if labels:
            content.append({"type": "text", "text": labels[i]})
        content.append({"type": "image", "image": im})
    msgs = [{"role": "user", "content": content + [{"type": "text", "text": text}]}]
    inputs = proc.apply_chat_template(msgs, tokenize=True, add_generation_prompt=True, return_dict=True,
                                      return_tensors="pt").to(model.device)
    if "pixel_values" in inputs:
        inputs["pixel_values"] = inputs["pixel_values"].to(model.dtype)
    out, ms = timed(lambda: model.generate(**inputs, max_new_tokens=max_tokens, do_sample=False))
    new = out[0, inputs["input_ids"].shape[1]:]
    return proc.decode(new, skip_special_tokens=True), ms, int(inputs["input_ids"].shape[1]), int(new.shape[0])


@torch.inference_mode()
def ask_florence_ocr(model, proc, image, tiles=(2, 2)):
    W, H = image.size
    texts, total = [], 0.0
    nin = nout = 0
    for ty in range(tiles[1]):
        for tx in range(tiles[0]):
            crop = image.crop((tx * W // tiles[0], ty * H // tiles[1], (tx + 1) * W // tiles[0], (ty + 1) * H // tiles[1]))
            inputs = proc(text="<OCR>", images=crop, return_tensors="pt").to(model.device)
            inputs["pixel_values"] = inputs["pixel_values"].to(model.dtype)
            out, ms = timed(lambda: model.generate(**inputs, max_new_tokens=256, do_sample=False, num_beams=1))
            total += ms
            texts.append(proc.batch_decode(out, skip_special_tokens=True)[0])
            nin += int(inputs["input_ids"].shape[1]); nout += int(out.shape[1])
    return " | ".join(texts), total, nin, nout


def main(jobdir, outfile, models):
    jobdir, outfile = Path(jobdir), Path(outfile)
    jobs = [json.loads(l) for l in (jobdir / "jobs.jsonl").read_text().splitlines() if l.strip()]
    # finished = rows without an error, in OUTFILE or any sibling with the same stem prefix (parallel workers write
    # full_smol.jsonl etc. next to full.jsonl); errored jobs (e.g. CUDA out of memory) are retried
    done = set()
    for f in outfile.parent.glob(outfile.stem.split("_")[0] + "*.jsonl"):
        for l in f.read_text().splitlines():
            if l.strip():
                try:
                    j = json.loads(l)
                except json.JSONDecodeError:  # a line cut short by a disconnect
                    continue
                if not j.get("error"):
                    done.add(j["job_id"])
    e = env()
    print(json.dumps(e), f"{len(jobs)} jobs, {len(done)} done", flush=True)
    for name in models:
        todo = [j for j in jobs if j["model"] == name and j["job_id"] not in done]
        if SHARD:  # "k/n": this process takes the jobs whose id hashes to k mod n (parallel workers, disjoint sets)
            k, n = map(int, SHARD.split("/"))
            todo = [j for j in todo if int(hashlib.sha1(j["job_id"].encode()).hexdigest(), 16) % n == k]
        if not todo:
            continue
        t = time.perf_counter()
        model, proc = load(name, e["dtype"])
        load_s = time.perf_counter() - t
        imgs = lambda j: [Image.open(jobdir / p).convert("RGB") for p in j["images"]]

        def run(j):
            if name == "florence2":
                return ask_florence_ocr(model, proc, imgs(j)[-1], tuple(j.get("ocr_tiles", (2, 2))))
            return ask_chat(model, proc, imgs(j), j["prompt"], j["max_tokens"], j.get("labels"))
        run(todo[0])  # warm-up, not logged
        with outfile.open("a") as f:
            for i, j in enumerate(todo):
                try:
                    txt, ms, nin, nout = run(j)
                    err = None
                except Exception as ex:  # logged as a parse failure downstream, never dropped
                    txt, ms, nin, nout, err = "", 0.0, 0, 0, repr(ex)[:300]
                f.write(json.dumps(dict(job_id=j["job_id"], model=REPOS[name], kind=j["kind"], raw=txt, ms=round(ms, 1),
                                        n_input_tokens=nin, n_output_tokens=nout, load_s=round(load_s, 1), error=err, **e)) + "\n")
                f.flush()
                if i % 100 == 0:
                    print(f"{name} {i + 1}/{len(todo)} {ms:.0f} ms", flush=True)
        del model
        torch.cuda.empty_cache()


if __name__ == "__main__":
    ms = sys.argv[sys.argv.index("--models") + 1].split(",")
    main(sys.argv[1], sys.argv[2], ms)
