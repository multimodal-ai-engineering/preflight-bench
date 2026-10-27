"""Generate pilot action pairs (Q1, Q2) with action-time truth.

Timeline in page time (Playwright clock, installed at 0 before load):
  0-1000 ms warm-up | planned_a @1000 | planned_b @1200 | current_a @7500 | current_b @7700
  truth snapshots at current_b + {0, .1, .25, .5, 1, 2, 4, 8, 16} s
Labels come from the DOM (window.__truth), never from the event name.

Usage: python -m generator.make_pairs [--only N] [--out DIR] [--determinism]
"""
import argparse, asyncio, hashlib, json, random, subprocess, sys, time
from pathlib import Path

import numpy as np
from PIL import Image
from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parents[1]
PAGES = ROOT / "pages"
EVENTS = ["none", "moved", "covered", "gone", "moved_lookalike"]
TIER1_PAGES = ["live_feed", "live_dashboard", "live_doc", "live_news"]
MOTIONS = ["low", "med", "high"]
OFFSETS = [0, 0.1, 0.25, 0.5, 1, 2, 4, 8, 16]
T_PLAN, T_CUR = 1000, 7700
# Software raster and no LCD text keep screenshots byte-identical across runs.
CHROME_ARGS = ["--disable-gpu", "--disable-lcd-text", "--font-render-hinting=none", "--disable-partial-raster", "--disable-threaded-animation"]
DEV_SEEDS_T0 = set(range(1, 13))   # 12 of 40 seeds (30%)
DEV_SEEDS_T1 = set(range(1, 5))    # 4 of 12 seeds (33%)


def pair_specs():
    specs = []
    for ev in EVENTS:
        for seed in range(1, 41):
            specs.append(dict(tier=0, page="tier0_booking", motion="none", event=ev, seed=seed))
    for page in TIER1_PAGES:
        for m in MOTIONS:
            for ev in EVENTS:
                for seed in range(1, 13):
                    specs.append(dict(tier=1, page=page, motion=m, event=ev, seed=seed))
    for s in specs:
        s["pair_id"] = f"{s['page']}-{s['motion']}-{s['event']}-s{s['seed']:02d}"
        s["split"] = "dev" if s["seed"] in (DEV_SEEDS_T0 if s["tier"] == 0 else DEV_SEEDS_T1) else "test"
        # Per-pair RNG for timing and target choice; background motion depends only on (page, motion, seed).
        r = random.Random(hashlib.sha256(s["pair_id"].encode()).hexdigest())
        s["event_at"] = T_PLAN + round(r.uniform(500, 6000))
        s["event2"] = r.choice(EVENTS[1:]) if r.random() < 0.25 else None
        s["event2_at"] = T_CUR + round(r.uniform(0, 16000)) if s["event2"] else None
        s["target_u"] = r.random()
        s["sample_truthshots"] = r.random() < 0.10
        s["page_seed"] = s["seed"] * 101 + MOTIONS.index(s["motion"]) if s["motion"] in MOTIONS else s["seed"] * 101
    return specs


def url_for(s):
    q = f"seed={s['page_seed']}&motion={s['motion']}&event={s['event']}&event_at={s['event_at']}"
    if s["event2"]:
        q += f"&event2={s['event2']}&event2_at={s['event2_at']}"
    return (PAGES / f"{s['page']}.html").resolve().as_uri() + "?" + q


def motion_frac(a, b):
    ga = np.asarray(Image.open(a).convert("L"), dtype=np.int16)
    gb = np.asarray(Image.open(b).convert("L"), dtype=np.int16)
    return float((np.abs(ga - gb) > 20).mean())


async def gen_one(browser, s, out: Path):
    ctx = await browser.new_context(viewport={"width": 1280, "height": 800}, device_scale_factor=1)
    # Local only: block anything that is not a file:// load.
    await ctx.route("**/*", lambda r: r.continue_() if r.request.url.startswith("file:") else r.abort())
    page = await ctx.new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    await page.clock.install(time=0)
    await page.clock.pause_at(1)  # stop natural time flow; only run_for advances it
    await page.goto(url_for(s))
    await page.clock.run_for(T_PLAN)
    # Choose a target that is fully in view and hittable at its center at planning time.
    cands = []
    for t in await page.evaluate("__targets()"):
        x, y, w, h = t["box"]
        if x >= 0 and y >= 0 and x + w <= 1280 and y + h <= 800 and w > 0:
            hit = await page.evaluate(
                "([id,x,y]) => { const e=document.elementFromPoint(x,y); const t=document.querySelector(`[data-target-id=\"${id}\"]`); return !!(e && (e===t || t.contains(e))); }",
                [t["id"], x + w / 2, y + h / 2])
            if hit:
                cands.append(t)
    cands.sort(key=lambda t: t["id"])
    tgt = cands[int(s["target_u"] * len(cands))]
    await page.evaluate("id => { window.__pfTarget = id; }", tgt["id"])
    x, y, w, h = tgt["box"]
    click = [x + w / 2, y + h / 2]
    fdir = out / "frames"
    fdir.mkdir(parents=True, exist_ok=True)
    pid = s["pair_id"]
    paths = {k: fdir / f"{pid}_{k}.png" for k in ["planned_a", "planned_b", "current_a", "current_b"]}
    await page.screenshot(path=paths["planned_a"])
    plan_truth = await page.evaluate("([x,y]) => __truth(x,y)", click)
    await page.clock.run_for(200)
    await page.screenshot(path=paths["planned_b"])
    await page.clock.run_for(T_CUR - 200 - T_PLAN - 200)
    await page.screenshot(path=paths["current_a"])
    await page.clock.run_for(200)
    await page.screenshot(path=paths["current_b"])
    truth, prev = [], 0.0
    tdir = out / "truthshots"
    for off in OFFSETS:
        if off > prev:
            await page.clock.run_for(round((off - prev) * 1000))
        prev = off
        snap = await page.evaluate("([x,y]) => __truth(x,y)", click)
        snap["offset"] = off
        truth.append(snap)
        if s["sample_truthshots"]:
            tdir.mkdir(parents=True, exist_ok=True)
            await page.screenshot(path=tdir / f"{pid}_t{off:05.2f}.png")
    await ctx.close()
    t0 = truth[0]
    rec = {k: s[k] for k in ["pair_id", "tier", "page", "motion", "event", "seed", "split", "event_at", "event2", "event2_at", "page_seed"]}
    rec.update(
        target_id=tgt["id"], planned_box=tgt["box"], click=click, n_candidates=len(cands),
        frames={k: str(p.relative_to(ROOT) if p.is_relative_to(ROOT) else p) for k, p in paths.items()},
        plan_go_ok=plan_truth["go_ok"],
        motion_200ms=motion_frac(paths["current_a"], paths["current_b"]),
        change_gap=motion_frac(paths["planned_a"], paths["current_b"]),
        correct_action=t0["correct_action"],
        truth=truth, page_errors=errors,
        truthshots=bool(s["sample_truthshots"]),
    )
    return rec


def inputs_only(rec):
    """What a check may see on the test split: frames, planned box, click, page and motion level."""
    return {k: rec[k] for k in ["pair_id", "tier", "page", "motion", "seed", "split", "target_id", "planned_box", "click", "frames"]}


async def run(specs, out_root: Path, workers=4):
    out = []
    sem = asyncio.Semaphore(workers)
    t_start = time.time()
    async with async_playwright() as p:
        browser = await p.chromium.launch(args=CHROME_ARGS)

        async def job(s):
            async with sem:
                r = await gen_one(browser, s, out_root / s["split"])
                out.append(r)
                if len(out) % 50 == 0:
                    print(f"  {len(out)}/{len(specs)} pairs, {time.time() - t_start:.0f}s", flush=True)
        await asyncio.gather(*(job(s) for s in specs))
        await browser.close()
    return sorted(out, key=lambda r: r["pair_id"])


def git_hash():
    try:
        return subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", "--short", "HEAD"], text=True).strip()
    except Exception:
        return "uncommitted"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", type=int, default=0)
    ap.add_argument("--out", default=str(ROOT / "data" / "pilot"))
    ap.add_argument("--determinism", action="store_true")
    a = ap.parse_args()
    specs = pair_specs()
    if a.determinism:
        pick = [s for s in specs if s["seed"] == 1 and s["event"] in ("moved", "moved_lookalike") and s["motion"] in ("none", "high")]
        pick = [s for s in pick if s["tier"] == 0][:1] + [s for s in pick if s["tier"] == 1 and s["event"] == "moved"][:4]
        for s in pick:
            s["split"] = "det"
        scratch = ROOT / "data" / "det_check"
        r1 = asyncio.run(run(pick, scratch / "run1"))
        r2 = asyncio.run(run(pick, scratch / "run2"))
        same = True
        for a1, a2 in zip(r1, r2):
            for k in a1["frames"]:
                b1 = Path(ROOT / a1["frames"][k]).read_bytes()
                b2 = Path(ROOT / a2["frames"][k]).read_bytes()
                ok = b1 == b2
                same &= ok
                print(a1["pair_id"], k, "MATCH" if ok else "DIFF")
            same &= a1["truth"] == a2["truth"]
        print("DETERMINISM", "PASS" if same else "FAIL")
        (ROOT / "results" / "pilot").mkdir(parents=True, exist_ok=True)
        (ROOT / "results" / "pilot" / "determinism.txt").write_text(
            f"commit {git_hash()} date {time.strftime('%Y-%m-%d %H:%M')} pairs {[s['pair_id'] for s in pick]} result {'PASS' if same else 'FAIL'}\n")
        sys.exit(0 if same else 1)
    if a.only:
        specs = specs[:: max(1, len(specs) // a.only)][: a.only]
    out_root = Path(a.out)
    t0 = time.time()
    recs = asyncio.run(run(specs, out_root))
    meta = dict(commit=git_hash(), date=time.strftime("%Y-%m-%d %H:%M"), n=len(recs), seconds=round(time.time() - t0, 1),
                hardware="Apple M3, 8 GB, macOS", generator="make_pairs.py")
    priv = ROOT / "private"
    priv.mkdir(exist_ok=True)
    for split in ["dev", "test"]:
        rs = [r for r in recs if r["split"] == split]
        d = out_root / split
        d.mkdir(parents=True, exist_ok=True)
        if split == "dev":
            (d / "pairs.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rs))
        else:
            (d / "pairs.jsonl").write_text("".join(json.dumps(inputs_only(r)) + "\n" for r in rs))
            (priv / "test_pairs_labels.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rs))
    (out_root / "pairs_meta.json").write_text(json.dumps(meta, indent=1))
    print(json.dumps(meta))


if __name__ == "__main__":
    main()
