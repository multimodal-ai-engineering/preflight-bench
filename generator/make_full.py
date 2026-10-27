"""Generate PreflightBench-Live (full study) from pages_full/. Run only after the `prereg-v1` tag.

  python -m generator.make_full [--only N] [--workers 4] [--kinds a,b] [--part action|worked|all]

Timeline in page time (Playwright clock installed at 0, paused; only run_for advances it):
  action pairs: planned_a @1000, planned_b @1200, current_a @7500, current_b @7700 (6.5 s gap),
                truth at current_b + {0, .1, .25, .5, 1, 2, 4, 8, 16} s
  Tier 2:       the check sees current frames delayed by d in 100-500 ms, partly repainted from 300 ms older
                frames, scaled and JPEG-compressed (planning frames scaled and compressed too); truth stays at 7700
  worked pairs: before @1000, before_b @1200, click @1200, after @7900, after_b @8100
Labels come from the DOM / render state (window.__truth), never from the event name.
IDs are opaque (16 hex). Test labels go only to private/full_*_labels.jsonl.
"""
import argparse, asyncio, hashlib, io, json, os, platform, random, subprocess, time
from pathlib import Path

import numpy as np
from PIL import Image
from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parents[1]
PAGES = ROOT / "pages_full"
OUT = ROOT / "data" / "full"
PRIV = ROOT / "private"
CHROME_ARGS = ["--disable-gpu", "--disable-lcd-text", "--font-render-hinting=none", "--disable-partial-raster", "--disable-threaded-animation"]
KINDS = ["tier0_form", "live_market", "live_newsfeed", "live_notes", "live_map", "live_canvas"]
EVENT_COUNTS = dict(none=24, moved=16, moved_lookalike=16, covered=12, gone=12, dialog=50, slow_load=12)
WORKED_PER_TEMPLATE = 125
TIER2_ACTION, TIER2_WORKED = 1200, 600
OFFSETS = [0, 0.1, 0.25, 0.5, 1, 2, 4, 8, 16]
T_PLAN, T_CUR = 1000, 7700
DEV_VARIANTS = {0, 1}
SEED0 = 1001


def oid(*parts):
    return hashlib.sha256(("full|" + "|".join(map(str, parts))).encode()).hexdigest()[:16]


def action_specs():
    specs, seed = [], SEED0
    for kind in KINDS:
        for v in range(4):
            n = 0
            for ev, cnt in EVENT_COUNTS.items():
                for i in range(cnt):
                    specs.append(dict(part="action", tier=0 if kind.startswith("tier0") else 1, kind=kind, variant=v, event=ev, seed=seed,
                                      motion="none" if kind.startswith("tier0") else ["low", "med", "high"][n % 3],
                                      bg=["none", "near", "away"][(n // 3) % 3]))
                    seed += 1; n += 1
    # Tier 2: fresh seeds, balanced over kinds/variants/events in the same proportions
    rng = random.Random(2026)
    base = [s for s in specs]
    for i in range(TIER2_ACTION):
        b = dict(base[rng.randrange(len(base))])
        b.update(tier=2, seed=seed, degrade=dict(delay=rng.randint(100, 500), jpeg=rng.randint(20, 60), scale=round(rng.uniform(0.6, 0.9), 3),
                                                 repaint=0.2, dseed=rng.randrange(1 << 30)))
        specs.append(b); seed += 1
    for s in specs:
        r = random.Random(s["seed"] * 7 + 3)
        s["split"] = "dev" if s["variant"] in DEV_VARIANTS else "test"
        s["event_at"] = T_PLAN + round(r.uniform(500, 6000))
        s["slow_ms"] = round(r.uniform(1500, 9000))
        s["event2"] = r.choice(["moved", "moved_lookalike", "covered", "gone", "dialog"]) if r.random() < 0.25 else None
        s["event2_at"] = T_CUR + round(r.uniform(0, 16000)) if s["event2"] else None
        s["target_u"] = r.random()
        s["page_seed"] = s["seed"] * 13 + 5
        s["pair_id"] = oid("action", s["tier"], s["kind"], s["variant"], s["event"], s["seed"])
    return specs


def worked_specs():
    specs, seed = [], 50001
    outs = ["success_clear", "success_small", "failed_error", "failed_silent"]
    for kind in KINDS:
        for v in range(4):
            for i in range(WORKED_PER_TEMPLATE):
                specs.append(dict(part="worked", tier=0 if kind.startswith("tier0") else 1, kind=kind, variant=v, outcome=outs[i % 4], seed=seed,
                                  motion="none" if kind.startswith("tier0") else ["low", "med", "high"][(i // 4) % 3]))
                seed += 1
    rng = random.Random(2027)
    base = list(specs)
    for i in range(TIER2_WORKED):
        b = dict(base[rng.randrange(len(base))])
        b.update(tier=2, seed=seed, degrade=dict(delay=rng.randint(100, 500), jpeg=rng.randint(20, 60), scale=round(rng.uniform(0.6, 0.9), 3),
                                                 repaint=0.2, dseed=rng.randrange(1 << 30)))
        specs.append(b); seed += 1
    for s in specs:
        r = random.Random(s["seed"] * 11 + 1)
        s["split"] = "dev" if s["variant"] in DEV_VARIANTS else "test"
        s["page_seed"] = s["seed"] * 13 + 5
        s["effect_pick"] = r.random()
        s["pair_id"] = oid("worked", s["tier"], s["kind"], s["variant"], s["outcome"], s["seed"])
    return specs


def url(s, extra=""):
    q = f"seed={s['page_seed']}&v={s['variant']}&motion={s['motion']}"
    if s["part"] == "action":
        q += f"&event={s['event']}&event_at={s['event_at']}&slow_ms={s['slow_ms']}&bg={s['bg']}"
        if s["event2"]:
            q += f"&event2={s['event2']}&event2_at={s['event2_at']}"
    else:
        q += f"&outcome={s['outcome']}"
    return (PAGES / f"{s['kind']}.html").resolve().as_uri() + "?" + q + extra


def degrade(img_bytes, older_bytes, d, rng):
    """Remote-desktop look: partial repaint from an older frame, scale down/up, JPEG. Returns PNG bytes."""
    im = np.asarray(Image.open(io.BytesIO(img_bytes)).convert("RGB")).copy()
    if older_bytes is not None:
        old = np.asarray(Image.open(io.BytesIO(older_bytes)).convert("RGB"))
        for y in range(0, 800, 128):
            for x in range(0, 1280, 128):
                if rng.random() < d["repaint"]:
                    im[y:y + 128, x:x + 128] = old[y:y + 128, x:x + 128]
    pim = Image.fromarray(im)
    w, h = round(1280 * d["scale"]), round(800 * d["scale"])
    pim = pim.resize((w, h), Image.BILINEAR).resize((1280, 800), Image.BILINEAR)
    buf = io.BytesIO(); pim.save(buf, "JPEG", quality=d["jpeg"]); buf.seek(0)
    out = io.BytesIO(); Image.open(buf).convert("RGB").save(out, "PNG")
    return out.getvalue()


def motion_frac(a, b):
    ga = np.asarray(Image.open(io.BytesIO(a)).convert("L"), dtype=np.int16)
    gb = np.asarray(Image.open(io.BytesIO(b)).convert("L"), dtype=np.int16)
    return float((np.abs(ga - gb) > 20).mean())


async def new_page(browser, s):
    ctx = await browser.new_context(viewport={"width": 1280, "height": 800}, device_scale_factor=1)
    await ctx.route("**/*", lambda r: r.continue_() if r.request.url.startswith("file:") else r.abort())
    page = await ctx.new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    await page.clock.install(time=0)
    await page.clock.pause_at(1)
    await page.goto(url(s))
    return ctx, page, errors


async def choose_target(page, s):
    cands = []
    for t in await page.evaluate("__targets()"):
        x, y, w, h = t["box"]
        if x >= 0 and y >= 0 and x + w <= 1280 and y + h <= 800 and w > 0 and h > 0:
            await page.evaluate("id => { window.__pfTarget = id; }", t["id"])
            if (await page.evaluate("([x,y]) => __truth(x,y).go_ok", [x + w / 2, y + h / 2])):
                cands.append(t)
    cands.sort(key=lambda t: t["id"])
    return cands


async def gen_action(browser, s):
    ctx, page, errors = await new_page(browser, s)
    await page.clock.run_for(T_PLAN)
    cands = await choose_target(page, s)
    if not cands:
        await ctx.close()
        return None
    tgt = cands[int(s["target_u"] * len(cands))]
    await page.evaluate("id => { window.__pfTarget = id; P.startBgMotion(); }", tgt["id"])
    x, y, w, h = tgt["box"]
    click = [x + w / 2, y + h / 2]
    shots = {}
    shots["planned_a"] = await page.screenshot()
    plan_truth = await page.evaluate("([x,y]) => __truth(x,y)", click)
    await page.clock.run_for(200)
    shots["planned_b"] = await page.screenshot()
    now = T_PLAN + 200
    d = s.get("degrade")
    if d:  # frames the remote session shows: delayed by d, with older frames for partial repaint
        times = {"old_a": T_CUR - 200 - d["delay"] - 300, "old_b": T_CUR - d["delay"] - 300,
                 "current_a": T_CUR - 200 - d["delay"], "current_b": T_CUR - d["delay"]}
    else:
        times = {"current_a": T_CUR - 200, "current_b": T_CUR}
    for k, t in sorted(times.items(), key=lambda kv: kv[1]):
        await page.clock.run_for(t - now); now = t
        shots[k] = await page.screenshot()
    if now < T_CUR:
        await page.clock.run_for(T_CUR - now); now = T_CUR
    truth, prev = [], 0.0
    for off in OFFSETS:
        if off > prev:
            await page.clock.run_for(round((off - prev) * 1000))
        prev = off
        snap = await page.evaluate("([x,y]) => __truth(x,y)", click)
        snap["offset"] = off
        truth.append(snap)
    bgkind = await page.evaluate("document.documentElement.dataset.bgKind || null")
    virtual = await page.evaluate("id => !!P.virtual[id]", tgt["id"])
    await ctx.close()
    m200 = motion_frac(shots["current_a"], shots["current_b"])
    if d:
        rng = random.Random(d["dseed"])
        nod = dict(d, repaint=0.0)
        shots["planned_a"] = degrade(shots["planned_a"], None, nod, rng)
        shots["planned_b"] = degrade(shots["planned_b"], None, nod, rng)
        shots["current_a"] = degrade(shots["current_a"], shots.pop("old_a"), d, rng)
        shots["current_b"] = degrade(shots["current_b"], shots.pop("old_b"), d, rng)
    fdir = OUT / s["split"] / "frames"
    fdir.mkdir(parents=True, exist_ok=True)
    frames = {}
    for k in ["planned_a", "planned_b", "current_a", "current_b"]:
        p = fdir / f"{s['pair_id']}_{k}.png"
        p.write_bytes(shots[k])
        frames[k] = str(p.relative_to(ROOT))
    t0 = truth[0]
    rec = {k: s[k] for k in ["pair_id", "part", "tier", "kind", "variant", "split", "event", "motion", "bg", "seed", "event_at", "slow_ms", "event2", "event2_at", "page_seed"]}
    rec.update(degrade=d, target_id=tgt["id"], target_virtual=virtual, planned_box=tgt["box"], click=click,
               n_candidates=len(cands), frames=frames, plan_go_ok=plan_truth["go_ok"], motion_200ms=m200, bg_kind=bgkind,
               settled=not t0["go_ok"], dialog=bool(t0["dialog"]), correct_action=t0["correct_action"], truth=truth, page_errors=errors)
    return rec


async def gen_worked(browser, s):
    ctx, page, errors = await new_page(browser, s)
    await page.clock.run_for(T_PLAN)
    act = await page.evaluate("__actionBox()")
    cfg = await page.evaluate("({...P.action, label: document.querySelector(`[data-action-id=\"${P.action.id}\"]`).textContent.trim(),"
                              " small: P.action.smallSel ? (r => [r.left, r.top, r.width, r.height])(document.querySelector(P.action.smallSel).getBoundingClientRect()) : null})")
    x, y, w, h = act
    clear = f"A confirmation panel appears saying '{cfg['panelText']}'"
    small = (f"The status now reads '{cfg['smallLabel']}'." if cfg.get("smallSel") else f"The {cfg['label']} button now reads '{cfg['smallLabel']}'.")
    o = s["outcome"]
    eff = clear if o == "success_clear" else small if o == "success_small" else (clear if s["effect_pick"] < 0.5 else small)
    if eff == clear:
        effect_box = [max(10, min(1280 - 360, x - 120)), min(800 - 130, y + h + 10), 340, 110]
    else:
        effect_box = cfg["small"] if cfg.get("smallSel") else act
    shots = {"before": await page.screenshot()}
    await page.clock.run_for(200)
    shots["before_b"] = await page.screenshot()
    await page.mouse.click(x + w / 2, y + h / 2)
    d = s.get("degrade")
    t_after = 6700 - (d["delay"] if d else 0)
    await page.clock.run_for(t_after - 300)
    old = await page.screenshot()
    await page.clock.run_for(300)
    shots["after"] = await page.screenshot()
    await page.clock.run_for(200)
    shots["after_b"] = await page.screenshot()
    await ctx.close()
    if d:
        rng = random.Random(d["dseed"]); nod = dict(d, repaint=0.0)
        shots = {k: degrade(v, old if k == "after" else None, d if k == "after" else nod, rng) for k, v in shots.items()}
    fdir = OUT / s["split"] / "worked_frames"
    fdir.mkdir(parents=True, exist_ok=True)
    frames = {}
    for k, v in shots.items():
        p = fdir / f"{s['pair_id']}_{k}.png"
        p.write_bytes(v)
        frames[k] = str(p.relative_to(ROOT))
    rec = {k: s[k] for k in ["pair_id", "part", "tier", "kind", "variant", "split", "motion", "seed", "page_seed", "outcome"]}
    rec.update(degrade=d, expected_effect=eff, effect_kind="panel" if eff == clear else ("status" if cfg.get("smallSel") else "button"),
               effect_box=effect_box, action_box=act, frames=frames, worked=o.startswith("failed"), page_errors=errors)
    return rec


async def run(specs, workers):
    out = []
    sem = asyncio.Semaphore(workers)
    t0 = time.time()
    async with async_playwright() as p:
        browser = await p.chromium.launch(args=CHROME_ARGS)

        async def job(s):
            async with sem:
                try:
                    r = await (gen_action(browser, s) if s["part"] == "action" else gen_worked(browser, s))
                except Exception as e:  # logged, never silently dropped
                    r = dict(pair_id=s["pair_id"], part=s["part"], error=repr(e)[:300], split=s["split"])
                out.append(r)
                if len(out) % 200 == 0:
                    print(f"  {len(out)}/{len(specs)} {time.time() - t0:.0f}s", flush=True)
        await asyncio.gather(*(job(s) for s in specs))
        await browser.close()
    return out


PUBLIC_ACTION = ["pair_id", "part", "tier", "kind", "variant", "split", "motion", "seed", "target_id", "planned_box", "click", "frames", "degrade"]
PUBLIC_WORKED = ["pair_id", "part", "tier", "kind", "variant", "split", "motion", "seed", "expected_effect", "effect_kind", "effect_box", "action_box", "frames", "degrade"]


def write(recs, part):
    ok = [r for r in recs if r and "error" not in r]
    bad = [r for r in recs if r and "error" in r]
    PRIV.mkdir(exist_ok=True)
    pub = PUBLIC_ACTION if part == "action" else PUBLIC_WORKED
    name = "pairs" if part == "action" else "worked"
    for split in ("dev", "test"):
        rs = sorted([r for r in ok if r["split"] == split], key=lambda r: r["pair_id"])
        d = OUT / split
        d.mkdir(parents=True, exist_ok=True)
        if split == "dev":
            (d / f"{name}.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rs))
        else:
            (d / f"{name}.jsonl").write_text("".join(json.dumps({k: r.get(k) for k in pub}) + "\n" for r in rs))
            (PRIV / f"full_test_{name}_labels.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rs))
    (OUT / f"{name}_errors.jsonl").write_text("".join(json.dumps(r) + "\n" for r in bad))
    return len(ok), len(bad)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", type=int, default=0)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--part", default="all")
    ap.add_argument("--kinds", default="")
    a = ap.parse_args()
    tags = subprocess.run(["git", "tag", "--merged", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.split()
    if "prereg-v1" not in tags and not a.only and not os.environ.get("PREFLIGHT_REGENERATE"):
        raise SystemExit("The study generated its data only after the prereg-v1 tag. In a public clone, set "
                         "PREFLIGHT_REGENERATE=1 to regenerate the full benchmark, or use --only N for a sample.")
    commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    for part, fn in (("action", action_specs), ("worked", worked_specs)):
        if a.part not in ("all", part):
            continue
        specs = fn()
        if a.kinds:
            specs = [s for s in specs if s["kind"] in a.kinds.split(",")]
        if a.only:
            specs = specs[:: max(1, len(specs) // a.only)][: a.only]
            global OUT
            OUT = ROOT / "data" / "full_smoke"
        t0 = time.time()
        recs = asyncio.run(run(specs, a.workers))
        n_ok, n_bad = write(recs, part)
        meta = dict(part=part, commit=commit, date=time.strftime("%Y-%m-%d %H:%M"), n=n_ok, errors=n_bad,
                    seconds=round(time.time() - t0, 1), hardware=platform.platform())
        (OUT / f"{part}_meta.json").write_text(json.dumps(meta, indent=1))
        print(json.dumps(meta))


if __name__ == "__main__":
    main()
