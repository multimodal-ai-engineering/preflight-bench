"""Generate the pilot worked set (Q3): did the last action work?

Per page x outcome x seed: load, warm up 1 s, capture `before`, click the page's last-action
control, run the clock 6.7 s on the moving page, capture `after`. The planner's expected effect is
one sentence. For failed outcomes the planner still expects success, so the sentence is drawn
from the page's two success effects.

Usage: python -m generator.make_worked [--out DIR]
"""
import argparse, asyncio, hashlib, json, random, time
from pathlib import Path

from playwright.async_api import async_playwright

from generator.make_pairs import CHROME_ARGS, PAGES, ROOT, git_hash

OUTCOMES = ["success_clear", "success_small", "failed_error", "failed_silent"]
PAGE_LIST = ["tier0_booking", "live_feed", "live_dashboard", "live_doc", "live_news"]
EFFECTS = {
    "tier0_booking": ("A confirmation panel appears saying 'Booking confirmed.'", "The Book button now reads 'Booked ✓'."),
    "live_feed": ("A confirmation panel appears saying 'Your post is live.'", "The Post button now reads 'Posted ✓'."),
    "live_dashboard": ("A confirmation panel appears saying 'Data refreshed.'", "The 'Updated' time shows 'just now'."),
    "live_doc": ("A confirmation panel appears saying 'Page published.'", "The Publish button now reads 'Published ✓'."),
    "live_news": ("A confirmation panel appears saying 'You are on the list.'", "The Sign up button now reads 'Signed up ✓'."),
}
DEV_SEEDS = set(range(1, 6))  # 5 of 15 seeds (33%)


def specs():
    out = []
    for page in PAGE_LIST:
        for o in OUTCOMES:
            for seed in range(1, 16):
                wid = f"{page}-{o}-s{seed:02d}"
                r = random.Random(hashlib.sha256(("worked" + wid).encode()).hexdigest())
                motion = "none" if page == "tier0_booking" else r.choice(["low", "med", "high"])
                clear, small = EFFECTS[page]
                eff = clear if o == "success_clear" else small if o == "success_small" else r.choice([clear, small])
                out.append(dict(worked_id=wid, page=page, outcome=o, seed=seed, motion=motion, expected_effect=eff,
                                label="worked" if o.startswith("success") else "failed",
                                split="dev" if seed in DEV_SEEDS else "test", page_seed=5000 + seed * 13))
    return out


async def one(browser, s, out: Path):
    ctx = await browser.new_context(viewport={"width": 1280, "height": 800}, device_scale_factor=1)
    await ctx.route("**/*", lambda r: r.continue_() if r.request.url.startswith("file:") else r.abort())
    page = await ctx.new_page()
    await page.clock.install(time=0)
    await page.clock.pause_at(1)  # stop natural time flow; only run_for advances it
    url = (PAGES / f"{s['page']}.html").resolve().as_uri() + f"?seed={s['page_seed']}&motion={s['motion']}&event=none&outcome={s['outcome']}"
    await page.goto(url)
    await page.clock.run_for(1000)
    x, y, w, h = await page.evaluate("__actionBox()")
    d = out / "worked_frames"
    d.mkdir(parents=True, exist_ok=True)
    fb, fa = d / f"{s['worked_id']}_before.png", d / f"{s['worked_id']}_after.png"
    await page.screenshot(path=fb)
    await page.mouse.click(x + w / 2, y + h / 2)
    await page.clock.run_for(6700)
    await page.screenshot(path=fa)
    await ctx.close()
    rel = lambda p: str(p.relative_to(ROOT) if p.is_relative_to(ROOT) else p)
    return dict(s, action_box=[x, y, w, h], frames={"before": rel(fb), "after": rel(fa)})


async def run(sp, out_root):
    sem = asyncio.Semaphore(4)
    res = []
    async with async_playwright() as p:
        b = await p.chromium.launch(args=CHROME_ARGS)

        async def job(s):
            async with sem:
                res.append(await one(b, s, out_root / s["split"]))
        await asyncio.gather(*(job(s) for s in sp))
        await b.close()
    return sorted(res, key=lambda r: r["worked_id"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "data" / "pilot"))
    a = ap.parse_args()
    t0 = time.time()
    recs = asyncio.run(run(specs(), Path(a.out)))
    for split in ["dev", "test"]:
        rs = [r for r in recs if r["split"] == split]
        d = Path(a.out) / split
        if split == "dev":
            (d / "worked.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rs))
        else:
            keep = ["worked_id", "page", "seed", "motion", "expected_effect", "split", "action_box", "frames"]
            (d / "worked.jsonl").write_text("".join(json.dumps({k: r[k] for k in keep}) + "\n" for r in rs))
            (ROOT / "private" / "test_worked_labels.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rs))
    meta = dict(commit=git_hash(), date=time.strftime("%Y-%m-%d %H:%M"), n=len(recs), seconds=round(time.time() - t0, 1))
    (Path(a.out) / "worked_meta.json").write_text(json.dumps(meta, indent=1))
    print(json.dumps(meta))


if __name__ == "__main__":
    main()
