"""Live loop (full study, H2): a real Claude planner clicks targets on Tier 1 test-variant pages that keep moving.

  PREFLIGHT_STUDY=full PREFLIGHT_API_KEY=... python -m live.loop smoke [--model claude-haiku-5-5]
  PREFLIGHT_STUDY=full PREFLIGHT_API_KEY=... python -m live.loop run --planner MODEL [--steps 400] [--workers 3]

Exact gaps: the page clock is paused while the planner thinks, then advanced by exactly the gap (2, 6.5, 12 s),
so the gap does not depend on the planner's speed. Each episode is one page load with 8 tasks; the planner keeps
the last three screenshots (1024x640) in context and the fixed instructions are a cached prefix.
Conditions per step: "none" (click where planned) and "preflight" (the recommended anchored check runs on two
planning frames 200 ms apart and two current frames 200 ms apart; the clock also advances by its compute time).
Outcome per step from the live DOM at the moment of the click: success, stale, recovered (re-aim hit), wrong_reaim,
replan (counted and costed, not executed), planner_miss (the planned click missed the named element before the gap;
not a stale action, reported separately). Seeded events during the gap use the benchmark's mix.
Log: results/full/live/{name}.jsonl.
"""
import argparse, asyncio, base64, io, json, random, re, time
from pathlib import Path

from PIL import Image
from playwright.async_api import async_playwright

from anchored import check as A
from models import frontier as Fr

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "results/full/live"
PAGES = ROOT / "benchmark" / "pages_full"
CHROME_ARGS = ["--disable-gpu", "--disable-lcd-text", "--font-render-hinting=none", "--disable-partial-raster", "--disable-threaded-animation"]
TIER1 = ["live_market", "live_newsfeed", "live_notes", "live_map", "live_canvas"]
EVENTS = ["none", "none", "moved", "moved_lookalike", "covered", "gone", "dialog"]
SYSTEM = ("You operate a web page by clicking. Each turn you get the current screenshot (1024x640 pixels) and one task. "
          "Reply with JSON only: {\"box\": [x1, y1, x2, y2], \"label\": \"the visible text or icon you will click\"} where box is "
          "the element you will click, in screenshot pixels. You will click the center of the box.")


def shot_b64(png, size=(1024, 640)):
    im = Image.open(io.BytesIO(png)).convert("RGB").resize(size, Image.LANCZOS)
    buf = io.BytesIO(); im.save(buf, "PNG")
    return base64.standard_b64encode(buf.getvalue()).decode()


def describe(t):
    """Task text from the target's visible label (never its id)."""
    lab = (t.get("label") or "").strip()
    role = t.get("role") or "button"
    return f"Click the {role} labelled \"{lab}\"." if lab else f"Click the {role} described as \"{t.get('aria') or 'icon'}\"."


class Planner:
    def __init__(self, model, keep=2):
        self.model, self.c, self.m = model, Fr.client(), Fr.meter()
        self.keep = keep  # earlier turns kept in context (2 -> three screenshots; 0 -> latest only, extension D.1c)
        self.history = []  # list of (user_content, assistant_text)

    def ask(self, png, task, tag):
        img = {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": shot_b64(png)}}
        user = [img, {"type": "text", "text": task}]
        msgs = []
        for u, a in (self.history[-self.keep:] if self.keep else []):  # with the new one, three screenshots in context
            msgs += [{"role": "user", "content": u}, {"role": "assistant", "content": a}]
        msgs.append({"role": "user", "content": user})
        p = Fr._params(self.model, 1024 if self.model == Fr.OPUS else 200)
        self.m.check(self.model, 4000, p["max_tokens"])
        t0 = time.perf_counter()
        for attempt in range(6):
            try:
                t0 = time.perf_counter()
                r = self.c.messages.create(system=[{"type": "text", "text": SYSTEM, "cache_control": {"type": "ephemeral"}}], messages=msgs, **p)
                break
            except Exception as e:  # connection drops; the page clock is paused, so waiting changes nothing on the page
                if attempt == 5:
                    raise
                time.sleep(5 * (attempt + 1))
        ms = (time.perf_counter() - t0) * 1000
        usd = self.m.record(self.model, r.usage, tag=tag)
        txt = "".join(b.text for b in r.content if b.type == "text")
        # keep history images small: replace older images by their text only after 3 turns (handled by slicing)
        self.history.append((user, txt or "{}"))
        m = re.search(r"\{.*\}", txt, re.S)
        try:
            j = json.loads(m.group(0)) if m else None
            x1, y1, x2, y2 = [float(v) for v in j["box"]]
            x1, x2 = min(x1, x2), max(x1, x2); y1, y2 = min(y1, y2), max(y1, y2)
            box = [x1 * 1.25, y1 * 1.25, max(x2 - x1, 1) * 1.25, max(y2 - y1, 1) * 1.25]  # 1024x640 -> 1280x800; a point is a 1 px box
        except Exception:
            box = None
        return box, txt, ms, usd


async def targets_with_labels(page):
    return await page.evaluate("""() => __targets().map(t => {
        const e = document.querySelector(`[data-target-id="${t.id}"]`);
        const label = e ? (e.innerText || e.getAttribute('aria-label') || e.title || '').trim().slice(0, 40) : (P.virtual[t.id] && P.virtual[t.id].label) || '';
        const role = e ? (e.tagName === 'A' ? 'link' : 'button') : 'item on the canvas';
        return {...t, label, role, aria: e ? e.getAttribute('aria-label') : null};
    })""")


async def episode(browser, ep, cond, gap_s, planner_model, cfg, log):
    rng = random.Random(ep["seed"])
    ctx = await browser.new_context(viewport={"width": 1280, "height": 800}, device_scale_factor=1)
    await ctx.route("**/*", lambda r: r.continue_() if r.request.url.startswith("file:") else r.abort())
    page = await ctx.new_page()
    await page.clock.install(time=0)
    await page.clock.pause_at(1)
    await page.goto((PAGES / f"{ep['kind']}.html").resolve().as_uri() + f"?seed={ep['seed']}&v={ep['variant']}&motion={ep['motion']}")
    await page.clock.run_for(1000)
    planner = Planner(planner_model)
    for k in range(ep["n_tasks"]):
        ts = [t for t in await targets_with_labels(page) if t["box"][0] >= 0 and t["box"][1] >= 0 and t["box"][0] + t["box"][2] <= 1280
              and t["box"][1] + t["box"][3] <= 800 and t["label"]]
        labels = {}
        for t in ts:
            labels.setdefault(t["label"], []).append(t)
        ts = [v[0] for v in labels.values() if len(v) == 1]  # tasks must name a unique visible label
        # ...and an element that is clickable right now (not under a leftover toast or dialog)
        ok = []
        for t in ts:
            await page.evaluate("id => { window.__pfTarget = id; }", t["id"])
            if await page.evaluate("([x,y]) => __truth(x,y).go_ok", [t["box"][0] + t["box"][2] / 2, t["box"][1] + t["box"][3] / 2]):
                ok.append(t)
        ts = ok
        if not ts:
            break
        tgt = rng.choice(sorted(ts, key=lambda t: t["id"]))
        await page.evaluate("id => { window.__pfTarget = id; }", tgt["id"])
        pa = await page.screenshot()
        box, txt, plan_ms, usd = await asyncio.to_thread(planner.ask, pa, describe(tgt), f"live|{cond}|{gap_s}|{ep['id']}|{k}")
        await page.clock.run_for(200)
        pb = await page.screenshot()
        row = dict(episode=ep["id"], kind=ep["kind"], variant=ep["variant"], motion=ep["motion"], cond=cond, gap_s=gap_s, step=k,
                   target_id=tgt["id"], task=describe(tgt), planner=planner_model, plan_ms=round(plan_ms, 1), usd=usd, raw=txt[:300])
        if box is None or box[2] <= 0 or box[3] <= 0:
            row.update(outcome="parse_fail", action="replan", check_ms=0.0)
            log.write(json.dumps(row) + "\n"); log.flush()
            continue
        click = [box[0] + box[2] / 2, box[1] + box[3] / 2]
        plan_hit = (await page.evaluate("([x,y]) => __truth(x,y).go_ok", click))
        # seeded event during the gap (benchmark mix), applied at a random moment inside the gap
        ev = rng.choice(EVENTS)
        ev_at = rng.uniform(0.1, 0.9) * gap_s * 1000
        await page.clock.run_for(round(ev_at))
        if ev != "none":
            await page.evaluate("name => P.events[name](P.evRand)", ev)
        await page.clock.run_for(round(gap_s * 1000 - ev_at) - 200)
        ca = await page.screenshot()
        await page.clock.run_for(200)
        cb = await page.screenshot()
        action, final, check_ms, reason = "go", click, 0.0, "no_check"
        if cond == "preflight":
            g = lambda b: Image.open(io.BytesIO(b)).convert("RGB")
            d = A.check((g(pa), g(pb)), (g(ca), g(cb)), box, mode=cfg.get("_mode", "reaim"), config=cfg)
            action, final, reason = d.action, list(d.click), d.reason
            check_ms = d.ms
            await page.clock.run_for(max(0, round(d.ms - A.FRAME_WAIT_MS)))  # compute time passes on the page too
        tr = await page.evaluate("([x,y]) => __truth(x,y)", final)
        if not plan_hit:  # the planner missed before the gap: not a stale action; counted separately
            outcome = "planner_miss"
        elif action == "replan":
            outcome = "replan_needed" if not (await page.evaluate("([x,y]) => __truth(x,y).go_ok", click)) else "replan_false"
        elif action == "reaim":
            outcome = "recovered" if tr["go_ok"] else "wrong_reaim"
        else:
            outcome = "success" if tr["go_ok"] else "stale"
        row.update(plan_hit=plan_hit, event=ev, action=action, reason=reason, check_ms=round(check_ms, 1), outcome=outcome,
                   click=click, final_click=final)
        log.write(json.dumps(row) + "\n"); log.flush()
        if action in ("go", "reaim"):
            await page.mouse.click(*final)
        await page.clock.run_for(500)
        # between tasks the agent dismisses any toast or dialog left by this step's event, so the next task starts clear
        await page.evaluate("() => document.querySelectorAll('.pf-cover').forEach(e => e.remove())")
    await ctx.close()


def episodes(n_steps, seed0=90001, n_tasks=8):
    rng = random.Random(seed0)
    eps = []
    for i in range((n_steps + n_tasks - 1) // n_tasks):
        eps.append(dict(id=i, seed=seed0 + i, kind=TIER1[i % len(TIER1)], variant=2 + (i // len(TIER1)) % 2,
                        motion=["low", "med", "high"][rng.randrange(3)], n_tasks=n_tasks))
    return eps


async def run_cells(planner_model, n_steps, workers, conds=("none", "preflight"), gaps=(2.0, 6.5, 12.0), name="loop"):
    fz = json.loads((ROOT / "results/full/frozen_full.json").read_text())
    cfg = {**A.DEFAULTS, **fz["C4"], "_mode": fz.get("C4_mode", "reaim")}
    OUT.mkdir(parents=True, exist_ok=True)
    eps = episodes(n_steps)
    sem = asyncio.Semaphore(workers)
    with (OUT / f"{name}.jsonl").open("a") as log:
        async with async_playwright() as p:
            b = await p.chromium.launch(args=CHROME_ARGS)

            async def job(ep, c, g):
                async with sem:
                    try:
                        await episode(b, ep, c, g, planner_model, cfg, log)
                    except Exception as e:  # one failed episode does not stop the run; it is logged and can be resumed
                        print("episode failed", ep["id"], c, g, repr(e)[:200], flush=True)
            # resume: skip (episode, condition, gap) cells already in the log (an episode cut short by a crash stays short)
            have = set()
            if (OUT / f"{name}.jsonl").exists():
                have = {(j["episode"], j["cond"], j["gap_s"]) for j in map(json.loads, (OUT / f"{name}.jsonl").read_text().splitlines()) if j}
            await asyncio.gather(*(job(ep, c, g) for g in gaps for c in conds for ep in eps if (ep["id"], c, g) not in have))
            await b.close()


async def smoke(model, n=50):
    """Planner rule: >= 90% of clicks hit the named element on Tier 0 (dev variants)."""
    OUT.mkdir(parents=True, exist_ok=True)
    hits = []
    with (OUT / f"smoke_{model}.jsonl").open("a") as log:
        async with async_playwright() as p:
            b = await p.chromium.launch(args=CHROME_ARGS)
            rng = random.Random(4242)
            i = 0
            while len(hits) < n:
                ctx = await b.new_context(viewport={"width": 1280, "height": 800}, device_scale_factor=1)
                await ctx.route("**/*", lambda r: r.continue_() if r.request.url.startswith("file:") else r.abort())
                page = await ctx.new_page()
                await page.clock.install(time=0); await page.clock.pause_at(1)
                await page.goto((PAGES / "tier0_form.html").resolve().as_uri() + f"?seed={80001 + i}&v={i % 2}&motion=none")
                await page.clock.run_for(1000)
                planner = Planner(model)
                ts = [t for t in await targets_with_labels(page) if t["label"]]
                labs = {}
                for t in ts:
                    labs.setdefault(t["label"], []).append(t)
                uniq = [v[0] for v in labs.values() if len(v) == 1]
                for t in rng.sample(uniq, min(5, len(uniq))):
                    await page.evaluate("id => { window.__pfTarget = id; }", t["id"])
                    box, txt, ms, usd = await asyncio.to_thread(planner.ask, await page.screenshot(), describe(t), f"smoke|{i}")
                    hit = bool(box) and await page.evaluate("([x,y]) => __truth(x,y).go_ok", [box[0] + box[2] / 2, box[1] + box[3] / 2])
                    hits.append(hit)
                    log.write(json.dumps(dict(model=model, task=describe(t), hit=hit, raw=txt[:200], ms=round(ms, 1))) + "\n")
                    if len(hits) >= n:
                        break
                await ctx.close(); i += 1
            await b.close()
    rate = sum(hits) / len(hits)
    print(f"smoke {model}: {sum(hits)}/{len(hits)} = {rate:.0%} hit the named element -> {'use' if rate >= 0.9 else 'do not use'} as planner")
    return rate


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["smoke", "run"])
    ap.add_argument("--model", default=Fr.SMALL_HOSTED)
    ap.add_argument("--planner", default=Fr.SMALL_HOSTED)
    ap.add_argument("--steps", type=int, default=400)
    ap.add_argument("--workers", type=int, default=3)
    a = ap.parse_args()
    if a.cmd == "smoke":
        asyncio.run(smoke(a.model))
    else:
        asyncio.run(run_cells(a.planner, a.steps, a.workers))
