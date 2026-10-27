"""Second frames for the worked set (Q3 pixel baseline), 200 ms after `before` and after `after`. PILOT.

The clock is deterministic, so each worked pair is re-rendered twice from scratch:
  1. load, run 1 s, screenshot (must equal `before`), run 200 ms, screenshot -> before_b
  2. load, run 1 s, click, run 6.7 s, screenshot (must equal `after`), run 200 ms, screenshot -> after_b
Existing frames are never rewritten. A mismatch with the existing frame is reported and the pair is flagged.

Usage: python -m generator.make_worked_extra
"""
import asyncio, hashlib, json
from pathlib import Path

from playwright.async_api import async_playwright

from generator.make_pairs import CHROME_ARGS, PAGES, ROOT

FRAME_GAP_MS = 200


def recs(split):
    return [json.loads(l) for l in (ROOT / f"data/pilot/{split}/worked.jsonl").read_text().splitlines() if l.strip()]


def page_seed(wid):
    return 5000 + int(wid.rsplit("-s", 1)[1]) * 13


def outcome_of(wid):
    return wid.split("-")[1]


async def render(browser, r, click):
    ctx = await browser.new_context(viewport={"width": 1280, "height": 800}, device_scale_factor=1)
    await ctx.route("**/*", lambda q: q.continue_() if q.request.url.startswith("file:") else q.abort())
    page = await ctx.new_page()
    await page.clock.install(time=0)
    await page.clock.pause_at(1)
    url = (PAGES / f"{r['page']}.html").resolve().as_uri() + \
        f"?seed={page_seed(r['worked_id'])}&motion={r['motion']}&event=none&outcome={outcome_of(r['worked_id'])}"
    await page.goto(url)
    await page.clock.run_for(1000)
    if click:
        x, y, w, h = r["action_box"]
        await page.mouse.click(x + w / 2, y + h / 2)
        await page.clock.run_for(6700)
    a = await page.screenshot()
    await page.clock.run_for(FRAME_GAP_MS)
    b = await page.screenshot()
    await ctx.close()
    return a, b


async def one(browser, r):
    out = {}
    for key, click in (("before", False), ("after", True)):
        a, b = await render(browser, r, click)
        src = ROOT / r["frames"][key]
        same = hashlib.sha256(a).hexdigest() == hashlib.sha256(src.read_bytes()).hexdigest()
        p = src.with_name(src.name.replace(f"_{key}.png", f"_{key}_b.png"))
        p.write_bytes(b)
        out[f"{key}_b"] = str(p.relative_to(ROOT))
        out[f"{key}_reproduced"] = same
    return r["worked_id"], out


async def run():
    async with async_playwright() as p:
        browser = await p.chromium.launch(args=CHROME_ARGS)
        sem = asyncio.Semaphore(4)
        res = {}
        for split in ("dev", "test"):
            async def job(r):
                async with sem:
                    k, v = await one(browser, r)
                    res[k] = dict(v, split=split)
            await asyncio.gather(*(job(r) for r in recs(split)))
        await browser.close()
    (ROOT / "data/pilot/worked_extra.json").write_text(json.dumps(dict(sorted(res.items())), indent=1))
    bad = [k for k, v in res.items() if not (v["before_reproduced"] and v["after_reproduced"])]
    print(f"{len(res)} worked pairs, {len(bad)} not reproduced byte-for-byte", bad[:10])


if __name__ == "__main__":
    asyncio.run(run())
