"""Post-hoc (not preregistered): where each worked pair's expected effect appears, for the effect-region pixel check.

The region depends only on the expected-effect sentence and the page's layout before the click, both known to the
planner, never on the outcome:
  panel sentence ("A confirmation panel appears ...")  the panel rect the page script places relative to the button
  "Updated just now" (dashboard)                         the #updated element before the click
  "The ... button now reads ..."                         the clicked button (action_box)
Writes data/pilot/worked_effect_boxes.json. PILOT.
"""
import asyncio, json

from playwright.async_api import async_playwright

from generator.make_pairs import CHROME_ARGS, PAGES, ROOT
from generator.make_worked_extra import page_seed, recs


def panel_box(b):
    x, y, w, h = b
    top = min(800 - 130, y + h + 10)
    left = max(10, min(1280 - 360, x - 120))
    return [left, top, 340, 110]


async def updated_box(browser, r):
    ctx = await browser.new_context(viewport={"width": 1280, "height": 800}, device_scale_factor=1)
    await ctx.route("**/*", lambda q: q.continue_() if q.request.url.startswith("file:") else q.abort())
    page = await ctx.new_page()
    await page.clock.install(time=0)
    await page.clock.pause_at(1)
    # outcome does not change layout before the click; success_small is passed only so the URL is well formed
    url = (PAGES / f"{r['page']}.html").resolve().as_uri() + f"?seed={page_seed(r['worked_id'])}&motion={r['motion']}&event=none&outcome=success_small"
    await page.goto(url)
    await page.clock.run_for(1000)
    b = await page.evaluate("(() => { const r = document.querySelector('#updated').getBoundingClientRect(); return [r.left, r.top, r.width, r.height]; })()")
    await ctx.close()
    return b


async def run():
    out = {}
    async with async_playwright() as p:
        browser = await p.chromium.launch(args=CHROME_ARGS)
        for split in ("dev", "test"):
            for r in recs(split):
                eff = r["expected_effect"]
                if eff.startswith("A confirmation panel"):
                    box, kind = panel_box(r["action_box"]), "panel"
                elif "'Updated' time" in eff:
                    box, kind = await updated_box(browser, r), "updated_label"
                else:
                    box, kind = list(r["action_box"]), "button"
                out[r["worked_id"]] = dict(kind=kind, box=box)
        await browser.close()
    (ROOT / "data/pilot/worked_effect_boxes.json").write_text(json.dumps(out, indent=1))
    import collections
    print(len(out), collections.Counter(v["kind"] for v in out.values()))


if __name__ == "__main__":
    asyncio.run(run())
