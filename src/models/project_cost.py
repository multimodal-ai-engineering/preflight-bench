"""Projected Wave 3/4 API spend from free token counts on 20 sample requests per (model, task). PILOT.

  PREFLIGHT_API_KEY=... python -m models.project_cost [--opus-max-tokens N]

Output tokens are charged at max_tokens on every call (upper bound). Stops with exit 1 if the projection
plus what the ledger already holds would pass the cap.
"""
import json, random, sys
from pathlib import Path

from PIL import Image

from models import frontier as Fr
from models.common import plan_crop, prompt
from models.cost_meter import CAP_USD, CostMeter
from models.qwen_jobs import locate_kw

ROOT = Path(__file__).resolve().parents[2]


def jl(p):
    return [json.loads(l) for l in (ROOT / p).read_text().splitlines() if l.strip()]


def locate_req(r):
    pa = Image.open(ROOT / r["frames"]["planned_a"]).convert("RGB")
    crop, cbox = plan_crop(pa, r["planned_box"])
    cb = Image.open(ROOT / r["frames"]["current_b"]).convert("RGB")
    return [crop, cb], prompt("locate_claude", **locate_kw(r["planned_box"], cbox))


def worked_req(r):
    b = Image.open(ROOT / r["frames"]["before"]).convert("RGB").resize((640, 400), Image.LANCZOS)
    a = Image.open(ROOT / r["frames"]["after"]).convert("RGB")
    return [b, a], prompt("worked", expected_effect=r["expected_effect"])


def main(opus_max=100):
    rng = random.Random(0)
    pairs, worked = jl("data/pilot/dev/pairs.jsonl"), jl("data/pilot/dev/worked.jsonl")
    sample = {"locate": [locate_req(r) for r in rng.sample(pairs, 20)],
              "worked": [worked_req(r) for r in rng.sample(worked, 20)]}
    max_out = {Fr.SMALL_HOSTED: 100, Fr.OPUS: opus_max}
    mean_in = {}
    for model in (Fr.SMALL_HOSTED, Fr.OPUS):
        for task, reqs in sample.items():
            n = [Fr.count(model, ims, txt) for ims, txt in reqs]
            mean_in[model, task] = sum(n) / len(n)
            print(f"{model:18s} {task:7s} input tokens mean {mean_in[model, task]:.0f} (min {min(n)}, max {max(n)})")
    n_test_pairs, n_dev_worked, n_test_worked = 620, len(worked), len(jl("data/pilot/test/worked.jsonl"))
    plan = [  # (what, model, task, calls)
        ("Haiku prompt dev, dev pairs x2 rounds", Fr.SMALL_HOSTED, "locate", 2 * len(pairs)),
        ("Opus confirm, 50 dev pairs", Fr.OPUS, "locate", 50),
        ("C8 Opus, 300-pair test subset", Fr.OPUS, "locate", 300),
        ("C9 Haiku, every test pair", Fr.SMALL_HOSTED, "locate", n_test_pairs),
        ("Q3 Haiku, dev + test worked", Fr.SMALL_HOSTED, "worked", n_dev_worked + n_test_worked),
        ("Q3 Opus, dev + test worked", Fr.OPUS, "worked", n_dev_worked + n_test_worked),
    ]
    total = 0.0
    for what, model, task, calls in plan:
        usd = calls * CostMeter.price(model, mean_in[model, task], max_out[model])
        total += usd
        print(f"{what:40s} {calls:4d} calls  ${usd:6.2f}")
    spent = CostMeter().total
    print(f"projected ${total:.2f} (upper bound on output) + spent ${spent:.2f} = ${total + spent:.2f} of ${CAP_USD:.2f} cap")
    if total + spent > CAP_USD:
        sys.exit("projection passes the cap; stopping")


if __name__ == "__main__":
    main(int(sys.argv[sys.argv.index("--opus-max-tokens") + 1]) if "--opus-max-tokens" in sys.argv else 100)
