"""Extension Part D: the planner (docs/PREREG_EXTENSION.md, D.1 and D.2). Haiku 5.5 planner, Tier 1 test-variant pages.

  PREFLIGHT_STUDY=extension PREFLIGHT_API_KEY=... python -m live.ext_planner d1 [--episodes 50] [--workers 3]
  PREFLIGHT_STUDY=extension PREFLIGHT_API_KEY=... python -m live.ext_planner d2 [--episodes 100] [--workers 3]

D.1: each episode loads the same page twice: A with motion on, B with motion frozen (motion=none plus CSS that
disables animations and transitions). Each step names one target that is clickable and uniquely labelled on both
pages; three planners get the same task: (a) A's screenshot with the last three in context, (b) B's screenshot with
the last three, (c) A's screenshot alone. Both pages are then clicked at the target's true centre (oracle click), so
page states never depend on a planner's answer. No seeded gap events. Planner miss = click not on the named element
200 ms after the screenshot (the full study's rule); the miss at 0 ms is logged too, with the DOM facts for
classifying each miss.
D.2: the full study's loop at a 6.5 s gap with its event mix and C4 in re-plan-only mode. On every step where C4
re-plans, the page clock stays paused and four recoveries are scored on the same current screenshot without
clicking: full re-plan, Haiku re-ground (label only, max_tokens 60), Qwen3-VL 4B re-ground (saved for the T4),
C4r pixel re-aim. Logs: results/extension/live/{d1,d2}.jsonl; Qwen jobs and frames: private/ext_d2/.
"""
import argparse, asyncio, io, json, random, re, time
from pathlib import Path

from PIL import Image
from playwright.async_api import async_playwright

from anchored import check as A
from live.loop import CHROME_ARGS, EVENTS, PAGES, TIER1, Planner, describe, shot_b64, targets_with_labels
from models import frontier as Fr

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "results/extension/live"
PRIV = ROOT / "private/ext_d2"
FREEZE_CSS = "*, *::before, *::after { animation: none !important; transition: none !important; }"
REGROUND = ('The element labelled "{label}" may have moved. Return its box in this screenshot as JSON {{"box": [x1, y1, x2, y2]}}, '
            'or {{"gone": true}}. Screenshot pixels, 1024x640. JSON only.')

HITINFO = """([x, y, tid]) => {
  const h = document.elementFromPoint(x, y);
  const t = document.querySelector(`[data-target-id="${tid}"]`);
  if (!h) return {root: true, empty: true};
  const ht = h.closest('[data-target-id]');
  const box = e => { const r = e.getBoundingClientRect(); return [r.left, r.top, r.width, r.height]; };
  const cont = e => e && (e.closest('li, tr, [role=row]') || e.parentElement);
  const txt = e => ((e && (e.innerText || e.getAttribute('aria-label') || e.title)) || '').trim().slice(0, 60);
  const virt = Object.entries(P.virtual).filter(([id, v]) => { const b = v.box(); return b && x >= b[0] && y >= b[1] && x < b[0] + b[2] && y < b[1] + b[3]; }).map(([id]) => id);
  return {tag: h.tagName, root: h === document.body || h === document.documentElement,
          empty: !txt(h) && !ht, hit_tid: ht ? ht.dataset.targetId : (virt[0] || null), hit_text: txt(ht || h),
          hit_tag: (ht || h).tagName, same_container: !!(t && (ht || h) !== t && cont(ht || h) === cont(t)),
          target_text: txt(t), target_tag: t ? t.tagName : null, virt_hits: virt};
}"""
GRID = """() => {  // 8 px grid: 0 = page root or empty container, 1 = another element, 2 = the target
  const id = window.__pfTarget, out = [];
  for (let y = 4; y < innerHeight; y += 8) { const row = [];
    for (let x = 4; x < innerWidth; x += 8) {
      const t = __truth(x, y);
      if (t.go_ok) { row.push(2); continue; }
      const h = document.elementFromPoint(x, y);
      const txt = h ? (h.innerText || h.getAttribute('aria-label') || '').trim() : '';
      row.push(!h || h === document.body || h === document.documentElement || (!txt && !h.closest('[data-target-id]')) ? 0 : 1);
    } out.push(row.join('')); }
  return out;
}"""


def episodes(n, seed0):
    rng = random.Random(seed0)
    return [dict(id=i, seed=seed0 + i, kind=TIER1[i % len(TIER1)], variant=2 + (i // len(TIER1)) % 2,
                 motion=["low", "med", "high"][rng.randrange(3)], n_tasks=8) for i in range(n)]


async def open_page(browser, ep, frozen=False):
    ctx = await browser.new_context(viewport={"width": 1280, "height": 800}, device_scale_factor=1)
    await ctx.route("**/*", lambda r: r.continue_() if r.request.url.startswith("file:") else r.abort())
    page = await ctx.new_page()
    if frozen:
        await page.add_init_script("document.addEventListener('DOMContentLoaded', () => { const s = document.createElement('style'); "
                                   f"s.textContent = {json.dumps(FREEZE_CSS)}; document.head.appendChild(s); }});")
    await page.clock.install(time=0)
    await page.clock.pause_at(1)
    motion = "none" if frozen else ep["motion"]
    await page.goto((PAGES / f"{ep['kind']}.html").resolve().as_uri() + f"?seed={ep['seed']}&v={ep['variant']}&motion={motion}")
    await page.clock.run_for(1000)
    return ctx, page


async def clickable(page):
    """Uniquely labelled targets in view whose centre is clickable now: {id: (label, role, box)}."""
    ts = [t for t in await targets_with_labels(page) if t["box"][0] >= 0 and t["box"][1] >= 0 and t["box"][0] + t["box"][2] <= 1280
          and t["box"][1] + t["box"][3] <= 800 and t["label"]]
    by = {}
    for t in ts:
        by.setdefault(t["label"], []).append(t)
    out = {}
    for v in by.values():
        if len(v) != 1:
            continue
        t = v[0]
        await page.evaluate("id => { window.__pfTarget = id; }", t["id"])
        if await page.evaluate("([x,y]) => __truth(x,y).go_ok", [t["box"][0] + t["box"][2] / 2, t["box"][1] + t["box"][3] / 2]):
            out[t["id"]] = t
    return out


async def boxes(page):
    return {t["id"]: t["box"] for t in await page.evaluate("() => __targets()")}


def center(box):
    return [box[0] + box[2] / 2, box[1] + box[3] / 2]


async def probe(page, pt, tid):
    hit = await page.evaluate("([x,y]) => __truth(x,y).go_ok", pt)
    info = await page.evaluate(HITINFO, [pt[0], pt[1], tid])
    return hit, info


# ---------------- D.1 ----------------

async def d1_episode(browser, ep, log):
    rng = random.Random(ep["seed"])
    ca, pa = await open_page(browser, ep)
    cb, pb = await open_page(browser, ep, frozen=True)
    P = {"a": Planner(Fr.SMALL_HOSTED), "b": Planner(Fr.SMALL_HOSTED), "c": Planner(Fr.SMALL_HOSTED, keep=0)}
    hist = {"A": [], "B": []}  # target boxes at each earlier screenshot
    for k in range(ep["n_tasks"]):
        ta, tb = await clickable(pa), await clickable(pb)
        common = sorted(i for i in ta if i in tb and ta[i]["label"] == tb[i]["label"])
        if not common:
            log.write(json.dumps(dict(episode=ep["id"], step=k, skipped="no common target")) + "\n"); log.flush()
            continue
        tid = rng.choice(common)
        task = describe(ta[tid])
        for pg in (pa, pb):
            await pg.evaluate("id => { window.__pfTarget = id; }", tid)
        bx = {"A": await boxes(pa), "B": await boxes(pb)}
        sa, sb = await pa.screenshot(), await pb.screenshot()
        tag = f"d1|{ep['id']}|{k}"
        res = await asyncio.gather(asyncio.to_thread(P["a"].ask, sa, task, tag + "|a"), asyncio.to_thread(P["b"].ask, sb, task, tag + "|b"),
                                   asyncio.to_thread(P["c"].ask, sa, task, tag + "|c"))
        out = {}
        for cond, (box, txt, ms, usd) in zip("abc", res):
            pg = pb if cond == "b" else pa
            pt = center(box) if box else None
            r = dict(plan_ms=round(ms, 1), usd=usd, raw=txt[:200], click=pt)
            if pt:
                r["hit0"], r["info0"] = await probe(pg, pt, tid)
            out[cond] = r
        for pg in (pa, pb):
            await pg.clock.run_for(200)
        for cond in "abc":
            pg = pb if cond == "b" else pa
            if out[cond]["click"]:
                out[cond]["hit200"], out[cond]["info200"] = await probe(pg, out[cond]["click"], tid)
                out[cond]["target_box200"] = (await pg.evaluate("([x,y]) => __truth(x,y)", out[cond]["click"]))["target_box"]
            out[cond]["miss"] = not out[cond].get("hit200", False)
        log.write(json.dumps(dict(episode=ep["id"], kind=ep["kind"], variant=ep["variant"], motion=ep["motion"], step=k, target_id=tid, task=task,
                                  target_box={"A": bx["A"].get(tid), "B": bx["B"].get(tid)},
                                  prev_boxes={"A": [h.get(tid) for h in hist["A"][-2:]], "B": [h.get(tid) for h in hist["B"][-2:]]},
                                  **{c: out[c] for c in "abc"})) + "\n"); log.flush()
        hist["A"].append(bx["A"]); hist["B"].append(bx["B"])
        # oracle click at the target's true centre on both pages, then dismiss leftovers and let the pages run
        for pg in (pa, pb):
            t = await pg.evaluate("([x,y]) => __truth(x,y)", [0, 0])
            if t["target_box"]:
                await pg.mouse.click(*center(t["target_box"]))
            await pg.clock.run_for(500)
            await pg.evaluate("() => document.querySelectorAll('.pf-cover').forEach(e => e.remove())")
            await pg.clock.run_for(6500)
    await ca.close(); await cb.close()


# ---------------- D.2 ----------------

def reground_haiku(c, m, png, label, tag):
    img = {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": shot_b64(png)}}
    p = Fr._params(Fr.SMALL_HOSTED, 60)
    m.check(Fr.SMALL_HOSTED, 2000, 60)
    for attempt in range(6):
        try:
            t0 = time.perf_counter()
            r = c.messages.create(messages=[{"role": "user", "content": [img, {"type": "text", "text": REGROUND.format(label=label)}]}], **p)
            break
        except Exception:
            if attempt == 5:
                raise
            time.sleep(5 * (attempt + 1))
    ms = (time.perf_counter() - t0) * 1000
    usd = m.record(Fr.SMALL_HOSTED, r.usage, tag=tag)
    txt = "".join(b.text for b in r.content if b.type == "text")
    return parse_reground(txt), txt, ms, usd


def parse_reground(txt):
    """-> ('box', [x, y] in 1280x800) | ('gone', None) | ('none', None)."""
    m = re.search(r"\{.*\}", txt or "", re.S)
    try:
        j = json.loads(m.group(0))
    except Exception:
        return ("none", None)
    if j.get("gone"):
        return ("gone", None)
    try:
        x1, y1, x2, y2 = [float(v) for v in j["box"]]
        return ("box", [(x1 + x2) / 2 * 1.25, (y1 + y2) / 2 * 1.25])
    except Exception:
        return ("none", None)


def plan_label(txt):
    m = re.search(r"\{.*\}", txt or "", re.S)
    try:
        return str(json.loads(m.group(0)).get("label") or "").strip()
    except Exception:
        return ""


async def score_point(page, pt):
    if pt is None:
        return None
    t = await page.evaluate("([x,y]) => __truth(x,y)", pt)
    h = await page.evaluate("([x,y]) => { const h = document.elementFromPoint(x,y); if (!h) return 0; "
                            "const txt = (h.innerText || h.getAttribute('aria-label') || '').trim(); "
                            "return (h === document.body || h === document.documentElement || (!txt && !h.closest('[data-target-id]'))) ? 0 : 1; }", pt)
    return dict(correct=bool(t["go_ok"]), other_element=bool(not t["go_ok"] and h == 1))


async def d2_episode(browser, ep, cfg, cfg_r, log):
    rng = random.Random(ep["seed"])
    gap_s = 6.5
    ctx, page = await open_page(browser, ep)
    planner = Planner(Fr.SMALL_HOSTED)
    c, m = Fr.client(), Fr.meter()
    g = lambda b: Image.open(io.BytesIO(b)).convert("RGB")
    for k in range(ep["n_tasks"]):
        ts = list((await clickable(page)).values())
        if not ts:
            break
        tgt = rng.choice(sorted(ts, key=lambda t: t["id"]))
        await page.evaluate("id => { window.__pfTarget = id; }", tgt["id"])
        task = describe(tgt)
        pa = await page.screenshot()
        box, txt, plan_ms, usd = await asyncio.to_thread(planner.ask, pa, task, f"d2|{ep['id']}|{k}")
        await page.clock.run_for(200)
        pb = await page.screenshot()
        row = dict(episode=ep["id"], kind=ep["kind"], variant=ep["variant"], motion=ep["motion"], step=k, target_id=tgt["id"], task=task,
                   plan_ms=round(plan_ms, 1), usd=usd, raw=txt[:200])
        if box is None or box[2] <= 0 or box[3] <= 0:
            log.write(json.dumps(dict(row, outcome="parse_fail")) + "\n"); log.flush()
            continue
        click = center(box)
        plan_hit = await page.evaluate("([x,y]) => __truth(x,y).go_ok", click)
        ev = rng.choice(EVENTS)
        ev_at = rng.uniform(0.1, 0.9) * gap_s * 1000
        await page.clock.run_for(round(ev_at))
        if ev != "none":
            await page.evaluate("name => P.events[name](P.evRand)", ev)
        await page.clock.run_for(round(gap_s * 1000 - ev_at) - 200)
        ca = await page.screenshot()
        await page.clock.run_for(200)
        cb = await page.screenshot()
        d = A.check((g(pa), g(pb)), (g(ca), g(cb)), box, mode=cfg["_mode"], config=cfg)
        await page.clock.run_for(max(0, round(d.ms - A.FRAME_WAIT_MS)))
        go_ok = await page.evaluate("([x,y]) => __truth(x,y).go_ok", click)
        row.update(plan_hit=plan_hit, event=ev, action=d.action, reason=d.reason, check_ms=round(d.ms, 1), go_ok_at_action=go_ok)
        if d.action == "replan":  # C4 fired: clock stays paused; four recoveries on the same current screenshot
            truth = await page.evaluate("([x,y]) => __truth(x,y)", click)
            gone = not truth["hit_mask"]
            label = plan_label(txt) or tgt["label"]
            rec = {}
            # 1. full re-plan (normal planner call, with its history)
            b2, t2, ms2, u2 = await asyncio.to_thread(planner.ask, cb, task, f"d2|{ep['id']}|{k}|replan")
            rec["replan"] = dict(kind="box" if b2 else "none", click=center(b2) if b2 else None, ms=round(ms2, 1), usd=u2, raw=t2[:200])
            # 2. Haiku re-ground
            (kd, pt), t3, ms3, u3 = await asyncio.to_thread(reground_haiku, c, m, cb, label, f"d2|{ep['id']}|{k}|reground")
            rec["reground_haiku"] = dict(kind=kd, click=pt, ms=round(ms3, 1), usd=u3, raw=t3[:200])
            # 4. C4r pixel re-aim on the same four frames
            dr = A.check((g(pa), g(pb)), (g(ca), g(cb)), box, mode="reaim", config=cfg_r)
            rec["pixel_reaim"] = dict(kind="box" if dr.action == "reaim" else "gone", click=list(dr.click) if dr.action == "reaim" else None,
                                      ms=round(dr.ms, 1), usd=0.0, raw=dr.reason)
            for r in rec.values():
                r["score"] = await score_point(page, r["click"])
            # 3. Qwen3-VL 4B re-ground: saved for the T4, scored offline against this moment's hit grid
            stem = f"ep{ep['id']:03d}_s{k}"
            PRIV.mkdir(parents=True, exist_ok=True)
            (PRIV / f"{stem}.png").write_bytes(cb)
            grid = await page.evaluate(GRID)
            rec["qwen_job"] = dict(stem=stem, label=label, prompt=REGROUND.format(label=label))
            (PRIV / f"{stem}_grid.json").write_text(json.dumps(dict(grid=grid, hit_mask=truth["hit_mask"], gone=gone)))
            row.update(gone=gone, label=label, recoveries=rec, truth_box=truth["target_box"])
        outcome = ("planner_miss" if not plan_hit else ("replan_needed" if not go_ok else "replan_false") if d.action == "replan"
                   else ("success" if go_ok else "stale"))
        row["outcome"] = outcome
        log.write(json.dumps(row) + "\n"); log.flush()
        if d.action == "go":
            await page.mouse.click(*click)
        await page.clock.run_for(500)
        await page.evaluate("() => document.querySelectorAll('.pf-cover').forEach(e => e.remove())")
    await ctx.close()


async def run(part, n_eps, workers):
    OUT.mkdir(parents=True, exist_ok=True)
    fz = json.loads((ROOT / "results/full/frozen_full.json").read_text())
    cfg = {**A.DEFAULTS, **fz["C4"], "_mode": fz.get("C4_mode", "reaim")}
    cfg_r = {**A.DEFAULTS, **fz["deviation"]["exploratory_C4r"]}
    eps = episodes(n_eps, 95001 if part == "d1" else 97001)
    p = OUT / f"{part}.jsonl"
    have = {j["episode"] for j in map(json.loads, p.read_text().splitlines()) if j} if p.exists() else set()
    sem = asyncio.Semaphore(workers)
    with p.open("a") as log:
        async with async_playwright() as pw:
            b = await pw.chromium.launch(args=CHROME_ARGS)

            async def job(ep):
                async with sem:
                    try:
                        if part == "d1":
                            await d1_episode(b, ep, log)
                        else:
                            await d2_episode(b, ep, cfg, cfg_r, log)
                    except Fr.anthropic.APIStatusError as e:
                        print("api error", ep["id"], repr(e)[:200], flush=True)
                    except Exception as e:
                        print("episode failed", ep["id"], repr(e)[:300], flush=True)
                    print(part, "episode", ep["id"], "done", flush=True)
            await asyncio.gather(*(job(ep) for ep in eps if ep["id"] not in have))
            await b.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("part", choices=["d1", "d2"])
    ap.add_argument("--episodes", type=int, default=None)
    ap.add_argument("--workers", type=int, default=3)
    a = ap.parse_args()
    asyncio.run(run(a.part, a.episodes or (50 if a.part == "d1" else 100), a.workers))
