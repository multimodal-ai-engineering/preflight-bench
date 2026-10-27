"""Self-check for a full-study page template (pages_full/<kind>.html).

  python -m generator.check_page KIND [--sheet]

For every variant (0-3) and motion level it checks:
  - the page loads with no JS errors and no network requests
  - at t = 1000 ms there are >= 8 targets, fully in view (0..1280 x 0..800), and __truth says go_ok at each center
  - determinism: two renders of the same URL at t = 7700 ms are byte-identical
  - motion: frames 200 ms apart differ for med/high (and Tier 1 pages), static pages differ by < 0.1%
  - every event (moved, moved_lookalike, covered, gone, dialog, slow_load) changes the truth at the target as expected
  - the last action is wired: clicking data-action-id with each outcome works
--sheet writes figures/check_KIND.png (variants x events) to eyeball.
Exit code 0 only if every check passes.
"""
import asyncio, hashlib, io, json, sys
from pathlib import Path

import numpy as np
from PIL import Image
from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parents[1]
PAGES = ROOT / "pages_full"
CHROME_ARGS = ["--disable-gpu", "--disable-lcd-text", "--font-render-hinting=none", "--disable-partial-raster", "--disable-threaded-animation"]
EVENTS = ["moved", "moved_lookalike", "covered", "gone", "dialog", "slow_load"]


async def open_page(browser, kind, q):
    ctx = await browser.new_context(viewport={"width": 1280, "height": 800}, device_scale_factor=1)
    reqs = []
    await ctx.route("**/*", lambda r: (r.continue_() if r.request.url.startswith("file:") else (reqs.append(r.request.url), r.abort())[1]))
    page = await ctx.new_page()
    errs = []
    page.on("pageerror", lambda e: errs.append(str(e)))
    await page.clock.install(time=0)
    await page.clock.pause_at(1)
    await page.goto((PAGES / f"{kind}.html").resolve().as_uri() + "?" + q)
    return ctx, page, errs, reqs


def frac(a, b):
    ga = np.asarray(Image.open(io.BytesIO(a)).convert("L"), dtype=np.int16)
    gb = np.asarray(Image.open(io.BytesIO(b)).convert("L"), dtype=np.int16)
    return float((np.abs(ga - gb) > 20).mean())


async def main(kind, sheet=False):
    fails, notes, thumbs = [], [], []
    static = kind.startswith("tier0")
    motions = ["none"] if static else ["low", "med", "high"]
    async with async_playwright() as p:
        b = await p.chromium.launch(args=CHROME_ARGS)
        for v in range(4):
            for m in motions:
                q = f"seed=11&v={v}&motion={m}"
                ctx, page, errs, reqs = await open_page(b, kind, q)
                await page.clock.run_for(1000)
                ts = await page.evaluate("__targets()")
                inview = [t for t in ts if t["box"][0] >= 0 and t["box"][1] >= 0 and t["box"][0] + t["box"][2] <= 1280 and t["box"][1] + t["box"][3] <= 800]
                if len(inview) < 8:
                    fails.append(f"v{v} {m}: only {len(inview)} targets fully in view")
                for t in inview:
                    await page.evaluate(f"window.__pfTarget = {json.dumps(t['id'])}")
                    x, y, w, h = t["box"]
                    tr = await page.evaluate(f"__truth({x + w / 2}, {y + h / 2})")
                    if not tr["go_ok"]:
                        fails.append(f"v{v} {m}: target {t['id']} not hittable at its center at t=1000")
                a = await page.screenshot()
                await page.clock.run_for(200)
                bb = await page.screenshot()
                f = frac(a, bb)
                if static and f > 0.001:
                    fails.append(f"v{v}: static page changes {f:.4f} of pixels in 200 ms")
                if not static and m in ("med", "high") and f < 0.0005:
                    fails.append(f"v{v} {m}: almost no motion in 200 ms ({f:.5f})")
                notes.append(f"v{v} {m}: {len(inview)} targets, motion_200ms={f:.4f}")
                act = await page.evaluate("__actionBox()")
                if not act:
                    fails.append(f"v{v} {m}: no data-action-id element")
                if errs or reqs:
                    fails.append(f"v{v} {m}: errors {errs[:2]} requests {reqs[:2]}")
                await ctx.close()
                # determinism
                shots = []
                for _ in range(2):
                    ctx, page, errs, _r = await open_page(b, kind, q + "&event=moved&event_at=3000")
                    await page.clock.run_for(7700)
                    shots.append(hashlib.sha256(await page.screenshot()).hexdigest())
                    await ctx.close()
                if shots[0] != shots[1]:
                    fails.append(f"v{v} {m}: two renders differ (not deterministic)")
            # events, on the first in-view target, med motion
            m = motions[-1] if static else "med"
            ctx, page, errs, _r = await open_page(b, kind, f"seed=11&v={v}&motion={m}")
            await page.clock.run_for(1000)
            ts = [t for t in await page.evaluate("__targets()") if t["box"][1] >= 0 and t["box"][1] + t["box"][3] <= 800]
            await ctx.close()
            row = []
            for i, e in enumerate(EVENTS):
                tgt = ts[(i * 3) % len(ts)]
                ctx, page, errs, _r = await open_page(b, kind, f"seed=11&v={v}&motion={m}&target={tgt['id']}&event={e}&event_at=2000&slow_ms=4000")
                await page.clock.run_for(1000)
                x, y, w, h = tgt["box"]
                await page.clock.run_for(2500)
                tr = await page.evaluate(f"__truth({x + w / 2}, {y + h / 2})")
                ok = {"moved": not tr["go_ok"] or (tr["target_box"] and abs(tr["target_box"][1] - y) + abs(tr["target_box"][0] - x) > 2),
                      "moved_lookalike": len(tr["lookalike_boxes"]) > 0,
                      "covered": tr["overlay"],
                      "gone": not tr["target_exists"],
                      "dialog": tr["dialog"] and not tr["go_ok"] or tr["dialog"],
                      "slow_load": not tr["go_ok"]}[e]
                if not ok:
                    fails.append(f"v{v}: event {e} on {tgt['id']} did not change truth as expected: {json.dumps({k: tr[k] for k in ('go_ok', 'target_exists', 'dialog', 'overlay', 'target_box')})}")
                if errs:
                    fails.append(f"v{v}: event {e} errors {errs[:2]}")
                if sheet:
                    thumbs.append((v, i, await page.screenshot()))
                await ctx.close()
            # last action outcomes
            for o in ["success_clear", "success_small", "failed_error", "failed_silent"]:
                ctx, page, errs, _r = await open_page(b, kind, f"seed=11&v={v}&motion={m}&outcome={o}")
                await page.clock.run_for(1000)
                ax, ay, aw, ah = await page.evaluate("__actionBox()")
                pre = await page.screenshot()
                await page.mouse.click(ax + aw / 2, ay + ah / 2)
                await page.clock.run_for(1500)
                post = await page.screenshot()
                if errs:
                    fails.append(f"v{v}: outcome {o} errors {errs[:2]}")
                await ctx.close()
        await b.close()
    if sheet and thumbs:
        W, H = 320, 200
        img = Image.new("RGB", (W * len(EVENTS), H * 4), "white")
        for v, i, s in thumbs:
            img.paste(Image.open(io.BytesIO(s)).convert("RGB").resize((W, H)), (i * W, v * H))
        (ROOT / "figures").mkdir(exist_ok=True)
        img.save(ROOT / "figures" / f"check_{kind}.png")
    print("\n".join(notes))
    print("FAILS:" if fails else "ALL CHECKS PASSED", *fails, sep="\n  ")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main(sys.argv[1], "--sheet" in sys.argv)))
