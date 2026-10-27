"""Checkpoint smoke test: warm latency per call (20 calls) for Qwen3-VL 2B / 4B and the hosted models,
plus the projected Wave 3 API spend from the free token-counting endpoint.

Usage: python -m models.smoke [--qwen] [--hosted]
"""
import argparse, json, platform, statistics, subprocess, time
from pathlib import Path

from PIL import Image

from models.qwen import REPOS as REPO
from models.common import plan_crop, prompt, parse_json

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results/pilot/smoke.json"


def hardware():
    chip = subprocess.run(["sysctl", "-n", "machdep.cpu.brand_string"], capture_output=True, text=True).stdout.strip()
    mem = int(subprocess.run(["sysctl", "-n", "hw.memsize"], capture_output=True, text=True).stdout.strip()) / 2**30
    return f"{chip}, {mem:.0f} GB, macOS {platform.mac_ver()[0]}"


def samples(n=20):
    recs = [json.loads(l) for l in (ROOT / "data/pilot/dev/pairs.jsonl").read_text().splitlines()]
    recs = [r for r in recs if r["tier"] == 1][:: max(1, len(recs) // n)][:n]
    out = []
    for r in recs:
        pa = Image.open(ROOT / r["frames"]["planned_a"]).convert("RGB")
        cb = Image.open(ROOT / r["frames"]["current_b"]).convert("RGB")
        crop, (cx, cy, w, h) = plan_crop(pa, r["planned_box"])
        x, y, _, _ = [round(v) for v in r["planned_box"]]
        out.append((r, crop, cb, dict(x=x, y=y, w=w, h=h, cx=cx, cy=cy)))
    return out


def qwen_latency(size, S):
    from models.qwen import Qwen
    t = time.perf_counter()
    q = Qwen(size)
    load_s = time.perf_counter() - t
    q.ask([S[0][1], S[0][2]], prompt("locate_qwen", **S[0][3]), max_tokens=48)  # warm-up
    ms, parsed = [], 0
    for r, crop, cb, kw in S:
        txt, m = q.ask([crop, cb], prompt("locate_qwen", **kw), max_tokens=48)
        ms.append(m); print(f"  {size} call {len(ms)}: {m:.0f} ms", flush=True)
        parsed += parse_json(txt) is not None
    # Tie-break call (small crops) is the escalation path for C5/C6.
    tb = []
    for r, crop, cb, kw in S[:10]:
        c = crop.crop((112, 104, 336, 232))
        txt, m = q.ask([c, c, c], prompt("tiebreak", n=2, choices="1|2"), max_tokens=24)
        tb.append(m)
    import gc, mlx.core as mx
    from models import qwen as _q
    _q._CACHE.clear(); del q; gc.collect(); mx.clear_cache()  # 8 GB laptop: one model in memory at a time
    return dict(model=REPO[size], load_s=round(load_s, 1), locate_ms_median=round(statistics.median(ms)), locate_ms_p95=round(sorted(ms)[int(.95 * len(ms)) - 1]),
                locate_parse_ok=f"{parsed}/{len(S)}", tiebreak_ms_median=round(statistics.median(tb)), last_raw=txt)


def hosted(S):
    from models import frontier as F
    res = {}
    try:
        ids = F.list_models()
        res["models_endpoint"] = ids
    except Exception as e:
        res["models_endpoint_error"] = f"{type(e).__name__}: {str(e)[:300]}"
        return res
    for model in [F.SMALL_HOSTED, F.OPUS]:
        toks = [F.count(model, [c, cb], prompt("locate_claude", **kw)) for _, c, cb, kw in S]
        res[model] = dict(mean_input_tokens=statistics.mean(toks))
        lat, outs = [], []
        for _, c, cb, kw in S:
            r = F.ask(model, [c, cb], prompt("locate_claude", **kw), max_tokens=100, tag="smoke", est_in=max(toks))
            lat.append(r["ms"]); outs.append(r)
        res[model].update(ms_median=round(statistics.median(lat)), ms_p95=round(sorted(lat)[int(.95 * len(lat)) - 1]),
                          stop_reasons=dict((k, sum(o["stop_reason"] == k for o in outs)) for k in {o["stop_reason"] for o in outs}),
                          mean_output_tokens=statistics.mean(o["usage"]["output"] for o in outs),
                          parse_ok=sum(parse_json(o["text"]) is not None for o in outs), served_model=outs[0]["model"],
                          usd_20=round(sum(o["usd"] for o in outs), 4), sample_raw=outs[0]["text"][:200])
    return res


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--qwen", action="store_true")
    ap.add_argument("--hosted", action="store_true")
    a = ap.parse_args()
    S = samples()
    out = json.loads(OUT.read_text()) if OUT.exists() else {}
    out.update(hardware=hardware(), date=time.strftime("%Y-%m-%d %H:%M"))
    if a.qwen:
        for size in ["2b", "4b"]:
            out[f"qwen_{size}"] = qwen_latency(size, S)
            print(json.dumps(out[f"qwen_{size}"], indent=1), flush=True)
    if a.hosted:
        out["hosted"] = hosted(S)
        print(json.dumps(out["hosted"], indent=1, default=str))
    OUT.write_text(json.dumps(out, indent=1, default=str))
