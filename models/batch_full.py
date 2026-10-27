"""Hosted Claude checks for the full study through the Message Batches API (half price). PILOT-free: full study only.

  PREFLIGHT_STUDY=full PREFLIGHT_API_KEY=... python -m models.batch_full project MODEL SPLIT KIND [--n N]
  PREFLIGHT_STUDY=full PREFLIGHT_API_KEY=... python -m models.batch_full submit  MODEL SPLIT KIND [--n N]
  PREFLIGHT_STUDY=full PREFLIGHT_API_KEY=... python -m models.batch_full collect MODEL SPLIT KIND
  PREFLIGHT_STUDY=full PREFLIGHT_API_KEY=... python -m models.batch_full latency MODEL [--n 150]

KIND: action (questions settled + dialog in one structured answer) or worked.
project: free token counts on 20 sampled requests, projected cost at batch price with output charged at max_tokens;
         exits 1 if spent + projection would pass the $100 cap. submit runs project first.
Batches are chunked (<= 50 requests each) to stay under the request-size limit; batch ids are logged in
results/full/hosted/batches.jsonl and answers in results/full/hosted/{split}_{model}_{kind}.jsonl.
latency: standard (non-batch) calls on random dev pairs, because batch timing is not real latency.
"""
import argparse, json, random, sys, time
from pathlib import Path

from PIL import Image

from models import frontier as Fr
from models.common import plan_crop
from models.cost_meter import CostMeter

ROOT = Path(__file__).resolve().parents[1]
H = ROOT / "results/full/hosted"
PROMPTS = ROOT / "models/prompts_full"
MAX_TOKENS = {Fr.SMALL_HOSTED: 100, Fr.OPUS: 1024}
SCHEMA = {
    "action": {"type": "object", "additionalProperties": False, "required": ["same_place", "dialog"],
               "properties": {"same_place": {"type": "boolean"}, "dialog": {"type": "boolean"}}},
    "worked": {"type": "object", "additionalProperties": False, "required": ["happened", "confidence"],
               "properties": {"happened": {"type": "boolean"}, "confidence": {"type": "number"}}},
}
CHUNK = 50


def recs(split, kind):
    name = "pairs" if kind == "action" else "worked"
    return [json.loads(l) for l in (ROOT / f"data/full/{split}/{name}.jsonl").read_text().splitlines() if l.strip()]


def rel_box(box):
    x, y, w, h = box
    return dict(rx1=round(x / 1.28), ry1=round(y / 0.8), rx2=round((x + w) / 1.28), ry2=round((y + h) / 0.8))


def build(r, kind):
    if kind == "action":
        pa = Image.open(ROOT / r["frames"]["planned_a"]).convert("RGB")
        crop, _ = plan_crop(pa, r["planned_box"])
        cb = Image.open(ROOT / r["frames"]["current_b"]).convert("RGB")
        text = (PROMPTS / "action_q.txt").read_text().strip().format(**rel_box(r["planned_box"]))
        return [crop, cb], text
    b = Image.open(ROOT / r["frames"]["before"]).convert("RGB").resize((640, 400), Image.LANCZOS)
    a = Image.open(ROOT / r["frames"]["after"]).convert("RGB")
    return [b, a], (PROMPTS / "worked.txt").read_text().strip().format(expected_effect=r["expected_effect"])


def params(model, kind, images, text):
    p = Fr._params(model, MAX_TOKENS[model])
    p["output_config"] = {**p.get("output_config", {}), "format": {"type": "json_schema", "schema": SCHEMA[kind]}}
    p["messages"] = [{"role": "user", "content": Fr.content(images, text)}]
    return p


def subset(rs, n, seed=0):
    if not n or n >= len(rs):
        return rs
    rng = random.Random(seed)
    key = lambda r: (r["tier"], r["kind"], r.get("event", r.get("expected_effect", "")))
    strata = {}
    for r in rs:
        strata.setdefault(key(r), []).append(r)
    groups = [rng.sample(v, len(v)) for _, v in sorted(strata.items())]
    out = []
    while len(out) < n:
        for g in groups:
            if g and len(out) < n:
                out.append(g.pop())
    return out


def project(model, split, kind, n=None):
    rs = subset(recs(split, kind), n)
    rng = random.Random(1)
    sample = rng.sample(rs, min(20, len(rs)))
    toks = [Fr.count(model, *build(r, kind)) for r in sample]
    mean_in = sum(toks) / len(toks)
    usd = len(rs) * CostMeter.price(model, mean_in, MAX_TOKENS[model]) * 0.5
    spent = CostMeter().total
    print(f"{model} {split} {kind}: {len(rs)} requests, mean input {mean_in:.0f} tok, projected ${usd:.2f} (batch, output at max) "
          f"+ spent ${spent:.2f} = ${usd + spent:.2f} of ${CostMeter().cap:.0f}")
    if usd + spent > CostMeter().cap:
        sys.exit("projection passes the cap; not submitting")
    return rs, usd


def submit(model, split, kind, n=None):
    from anthropic.types.messages.batch_create_params import Request
    rs, _ = project(model, split, kind, n)
    H.mkdir(parents=True, exist_ok=True)
    have = done(model, split, kind)
    rs = [r for r in rs if r["pair_id"] not in have]
    # skip requests already submitted (subset order is deterministic; logged chunks are a prefix)
    logged = [json.loads(l) for l in (H / "batches.jsonl").read_text().splitlines() if l.strip()] if (H / "batches.jsonl").exists() else []
    sent = sum(j["n"] for j in logged if (j["model"], j["split"], j["kind"]) == (model, split, kind) and not j.get("canceled"))
    if have and sent:
        sys.exit("both collected answers and logged batches exist; resolve by hand")
    rs = rs[sent:]
    c = Fr.client()
    for i in range(0, len(rs), CHUNK):
        chunk = rs[i:i + CHUNK]
        reqs = [Request(custom_id=r["pair_id"], params=params(model, kind, *build(r, kind))) for r in chunk]
        for attempt in range(5):
            try:
                b = c.messages.batches.create(requests=reqs)
                break
            except Exception as e:  # connection drops on large uploads; the batch was not created
                print("retry", attempt + 1, repr(e)[:120], flush=True); time.sleep(20 * (attempt + 1))
        else:
            sys.exit("batch create kept failing")
        with (H / "batches.jsonl").open("a") as f:
            f.write(json.dumps(dict(batch_id=b.id, model=model, split=split, kind=kind, n=len(chunk), t=time.strftime("%Y-%m-%dT%H:%M:%S"))) + "\n")
        print("submitted", b.id, len(chunk), flush=True)


def out_path(model, split, kind):
    return H / f"{split}_{model}_{kind}.jsonl"


def done(model, split, kind):
    p = out_path(model, split, kind)
    return {j["pair_id"]: j for j in map(json.loads, p.read_text().splitlines()) if j} if p.exists() else {}


def collect(model, split, kind, wait=True):
    c = Fr.client()
    m = Fr.meter()
    have = done(model, split, kind)
    led = m.ledger if hasattr(m, "ledger") else None
    dup_seen = {json.loads(l).get("tag") for l in Path(led).read_text().splitlines() if l.strip()} if led and Path(led).exists() else set()
    batches = [json.loads(l) for l in (H / "batches.jsonl").read_text().splitlines()]
    batches = [b for b in batches if b["model"] == model and b["split"] == split and b["kind"] == kind]
    pending = 0
    with out_path(model, split, kind).open("a") as f:
        for b in batches:
            st = c.messages.batches.retrieve(b["batch_id"])
            if st.processing_status != "ended":
                pending += 1
                continue
            for res in c.messages.batches.results(b["batch_id"]):
                if res.result.type == "canceled":  # a cancelled duplicate chunk; the request lives in another batch
                    continue
                if res.custom_id in have:
                    tag = f"batch-dup|{kind}|{split}|{res.custom_id}|{b['batch_id']}"
                    if res.result.type == "succeeded" and b["batch_id"] != have[res.custom_id].get("batch_id") and tag not in dup_seen:
                        # duplicate answer (overlapping resubmission): billed, so it goes in the ledger, not the answers
                        m.record(model, res.result.message.usage, tag=tag, discount=0.5); dup_seen.add(tag)
                    continue
                row = dict(pair_id=res.custom_id, batch_id=b["batch_id"], type=res.result.type)
                if res.result.type == "succeeded":
                    msg = res.result.message
                    usd = m.record(model, msg.usage, tag=f"batch|{kind}|{split}|{res.custom_id}", discount=0.5)
                    row.update(raw=next((x.text for x in msg.content if x.type == "text"), ""), usd=usd, stop_reason=msg.stop_reason,
                               usage=dict(input=msg.usage.input_tokens, output=msg.usage.output_tokens), model=msg.model)
                else:
                    row.update(raw="", error=str(getattr(res.result, "error", ""))[:300])
                f.write(json.dumps(row) + "\n")
                have[res.custom_id] = row
    print(f"{model} {split} {kind}: {len(have)} answers, {pending} batches pending, spent ${m.total:.2f}")
    return pending


def latency(model, n=150):
    rs = recs("dev", "action")
    rng = random.Random(5)
    p = H / f"latency_{model}.jsonl"
    with p.open("a") as f:
        for r in rng.sample(rs, n):
            a = Fr.ask(model, *build(r, "action"), max_tokens=MAX_TOKENS[model], tag=f"latency|{r['pair_id']}", est_in=2000, schema=SCHEMA["action"])
            f.write(json.dumps(dict(pair_id=r["pair_id"], ms=round(a["ms"], 1), usd=a["usd"], raw=a["text"], model=a["model"])) + "\n")
    print("latency done", model)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["project", "submit", "collect", "latency"])
    ap.add_argument("model")
    ap.add_argument("split", nargs="?")
    ap.add_argument("kind", nargs="?")
    ap.add_argument("--n", type=int)
    a = ap.parse_args()
    if a.cmd == "latency":
        latency(a.model, a.n or 150)
    else:
        {"project": project, "submit": submit, "collect": collect}[a.cmd](a.model, a.split, a.kind, *([a.n] if a.cmd != "collect" else []))
