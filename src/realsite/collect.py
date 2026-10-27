"""Read-only real-site set (full study; separate, never released, never pooled with the benchmark).

  python -m realsite.collect [--per-site 40]

For each approved public page: load it (no login, no clicks, no form input), wait for it to settle, choose a visible
link or button fully in view (seeded), take planning frames 200 ms apart, wait 6.5 s of real time, take current
frames 200 ms apart, and read the truth from the live DOM: the target's box now, whether the element at the planned
click point is still the target (or inside it), and whether it is still connected. Pages run in real time (their
clocks cannot be paused), so truth is read once, right after the second current frame.
Frames and records go to data/realsite/ (gitignored: third-party content, not released).
"""
import argparse, asyncio, json, random, time
from pathlib import Path

from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data/realsite"
SITES = []  # filled from realsite/sites.json once the author approves the list
UA = "preflight-research (read-only; contact via repo)"

PICK = """(seed) => {
  let s = seed; const rnd = () => { s = (s * 1103515245 + 12345) % 2147483648; return s / 2147483648; };
  const els = Array.from(document.querySelectorAll('a[href], button, [role=button]')).filter(e => {
    const r = e.getBoundingClientRect();
    if (r.width < 8 || r.height < 8 || r.left < 0 || r.top < 0 || r.right > innerWidth || r.bottom > innerHeight) return false;
    const h = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
    return h && (h === e || e.contains(h));
  });
  if (!els.length) return null;
  const e = els[Math.floor(rnd() * els.length)];
  e.setAttribute('data-pf-real', '1');
  const r = e.getBoundingClientRect();
  return {box: [r.left, r.top, r.width, r.height], tag: e.tagName, n: els.length};
}"""
TRUTH = """([x, y]) => {
  const t = document.querySelector('[data-pf-real="1"]');
  const out = {exists: !!(t && t.isConnected), box: null, go_ok: false, center_hit: false};
  if (!out.exists) return out;
  const r = t.getBoundingClientRect(); out.box = [r.left, r.top, r.width, r.height];
  const hit = (px, py) => { const h = document.elementFromPoint(px, py); return !!(h && (h === t || t.contains(h))); };
  out.go_ok = x >= 0 && y >= 0 && x < innerWidth && y < innerHeight && hit(x, y);
  out.center_hit = hit(r.left + r.width / 2, r.top + r.height / 2);
  out.correct_action = out.go_ok ? 'go' : (out.center_hit ? 'reaim' : 'replan');
  return out;
}"""


async def one(browser, site, k, seed):
    ctx = await browser.new_context(viewport={"width": 1280, "height": 800}, device_scale_factor=1, user_agent=UA)
    page = await ctx.new_page()
    rec = dict(site=site["name"], url=site["url"], k=k, seed=seed, t=time.strftime("%Y-%m-%dT%H:%M:%S"))
    try:
        await page.goto(site["url"], wait_until="networkidle", timeout=45000)
    except Exception:
        await page.wait_for_timeout(3000)
    await page.wait_for_timeout(2000)
    tgt = await page.evaluate(PICK, seed)
    if not tgt:
        await ctx.close()
        return dict(rec, error="no target")
    x, y, w, h = tgt["box"]
    click = [x + w / 2, y + h / 2]
    d = OUT / "frames"
    d.mkdir(parents=True, exist_ok=True)
    stem = f"{site['name']}_{k:03d}"
    fr = {}
    for name, wait in (("planned_a", 0), ("planned_b", 200), ("current_a", 6300), ("current_b", 200)):
        if wait:
            await page.wait_for_timeout(wait)
        p = d / f"{stem}_{name}.png"
        await page.screenshot(path=p)
        fr[name] = str(p.relative_to(ROOT))
    truth = await page.evaluate(TRUTH, click)
    await ctx.close()
    return dict(rec, planned_box=tgt["box"], click=click, n_candidates=tgt["n"], tag=tgt["tag"], frames=fr, truth=truth,
                settled=not truth["go_ok"], correct_action=truth.get("correct_action", "replan"))


async def main(per_site):
    sites = json.loads((Path(__file__).parent / "sites.json").read_text())
    OUT.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as p:
        b = await p.chromium.launch()
        prev = OUT / "pairs.jsonl"
        have = {(j["site"], j["k"]) for j in map(json.loads, prev.read_text().splitlines()) if j} if prev.exists() else set()
        with prev.open("a") as f:
            for site in sites:
                for k in range(per_site):  # sequential per site: one page load at a time, polite
                    if (site["name"], k) in have:  # resume
                        continue
                    r = await one(b, site, k, 7000 + k)
                    f.write(json.dumps(r) + "\n"); f.flush()
                print(site["name"], "done", flush=True)
        await b.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-site", type=int, default=40)
    asyncio.run(main(ap.parse_args().per_site))
