"""Extension Part C: when real pages change (read-only). docs/PREREG_EXTENSION.md, C.2.

  python -m realsite.collect_ext --round 1 [--workers 6]

Per site and start condition (settled, nav, scroll), one visit per round: load the page (no login, no clicks, no
form input), mark up to 20 visible links/buttons at t0 (stratified by viewport third x navigation control / content
link, round-robin, seeded), then at t0 and at each offset (0.5, 1, 2, 4, 6.5, 12, 30 s): DOM truth for every target
(survival), two screenshots 200 ms apart, and DOM truth again right after them (for scoring the C2/C4 decision at
that offset). Real time; actual timestamps are logged. One visit at a time per site, >= 10 s between loads.
Everything goes to private/realsite_ext/ (gitignored, never released).
"""
import argparse, asyncio, json, random, time
from pathlib import Path

from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "private/realsite_ext"
UA = "preflight-research (read-only; contact via repo)"
OFFSETS = (0.5, 1, 2, 4, 6.5, 12, 30)
CONDS = ("settled", "nav", "scroll")
KINDS0 = {"timegov": "dashboard", "census_popclock": "dashboard", "usgs_quakes": "map", "nws_radar": "map", "noaa_swpc": "dashboard",
          "wikipedia_main": "front_page", "openstreetmap": "map", "arxiv_csai_new": "listing", "nasa": "front_page", "gnu": "reference"}
MIN_GAP_S = 10

PICK = """(seed) => {
  let s = seed; const rnd = () => { s = (s * 1103515245 + 12345) % 2147483648; return s / 2147483648; };
  const H = innerHeight, W = innerWidth;
  const els = Array.from(document.querySelectorAll('a[href], button, [role=button]')).filter(e => {
    const r = e.getBoundingClientRect();
    if (r.width < 8 || r.height < 8 || r.left < 0 || r.top < 0 || r.right > W || r.bottom > H) return false;
    const h = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
    return h && (h === e || e.contains(h));
  });
  const cells = {};
  for (const e of els) {
    const r = e.getBoundingClientRect(), cy = r.top + r.height / 2;
    const third = cy < H / 3 ? 'top' : (cy < 2 * H / 3 ? 'middle' : 'bottom');
    const nav = !!e.closest('nav, header, footer, [role=navigation], [role=menu], [role=menubar], [role=tablist]') || e.tagName === 'BUTTON' || e.getAttribute('role') === 'button';
    const key = third + '|' + (nav ? 'nav_control' : 'content_link');
    (cells[key] = cells[key] || []).push(e);
  }
  const keys = Object.keys(cells).sort();
  for (const k of keys) { const a = cells[k]; for (let i = a.length - 1; i > 0; i--) { const j = Math.floor(rnd() * (i + 1)); [a[i], a[j]] = [a[j], a[i]]; } }
  const picked = [];
  let more = true;
  while (picked.length < 20 && more) {
    more = false;
    for (const k of keys) { if (picked.length >= 20) break; const e = cells[k].shift(); if (e) { picked.push([k, e]); more = true; } }
  }
  return {n_candidates: els.length, targets: picked.map(([k, e], i) => {
    e.setAttribute('data-pf-ext', String(i));
    const r = e.getBoundingClientRect();
    return {i, box: [r.left, r.top, r.width, r.height], click: [r.left + r.width / 2, r.top + r.height / 2],
            third: k.split('|')[0], type: k.split('|')[1], tag: e.tagName};
  })};
}"""
TRUTH = """(ts) => ts.map(t => {
  const e = document.querySelector(`[data-pf-ext="${t.i}"]`);
  const out = {i: t.i, exists: !!(e && e.isConnected), go_ok: false, disp: null};
  if (!out.exists) return out;
  const r = e.getBoundingClientRect();
  out.disp = Math.hypot(r.left + r.width / 2 - t.click[0], r.top + r.height / 2 - t.click[1]);
  const [x, y] = t.click;
  if (x >= 0 && y >= 0 && x < innerWidth && y < innerHeight) { const h = document.elementFromPoint(x, y); out.go_ok = !!(h && (h === e || e.contains(h))); }
  return out;
})"""


def sites():
    s0 = [dict(x, kind=KINDS0[x["name"]]) for x in json.loads((ROOT / "realsite/sites.json").read_text())]
    return s0 + json.loads((ROOT / "realsite/sites_ext_candidates.json").read_text())


async def visit(browser, site, cond, rnd, seed):
    ctx = await browser.new_context(viewport={"width": 1280, "height": 800}, device_scale_factor=1, user_agent=UA)
    page = await ctx.new_page()
    rec = dict(site=site["name"], url=site["url"], kind=site["kind"], cond=cond, round=rnd, seed=seed, t=time.strftime("%Y-%m-%dT%H:%M:%S"))
    try:
        if cond == "nav":
            await page.goto(site["url"], wait_until="domcontentloaded", timeout=45000)
        else:
            try:
                await page.goto(site["url"], wait_until="networkidle", timeout=45000)
            except Exception:
                pass  # network never idle: go on, as in the full study
            await page.wait_for_timeout(random.Random(seed).uniform(2000, 5000))
            if cond == "scroll":
                await page.evaluate("() => window.scrollBy(0, innerHeight)")
        t0 = time.perf_counter()
        sel = await page.evaluate(PICK, seed)
        ts = sel["targets"]
        if not ts:
            await ctx.close()
            return dict(rec, error="no target")
        d = OUT / "frames"
        d.mkdir(parents=True, exist_ok=True)
        stem = f"{site['name']}_{cond}_r{rnd}"
        offs = []
        for o in (0.0,) + OFFSETS:
            wait = t0 + o - time.perf_counter()
            if wait > 0:
                await asyncio.sleep(wait)
            tt = time.perf_counter() - t0
            truth = await page.evaluate(TRUTH, ts)
            fa, fb = d / f"{stem}_{o:g}_a.png", d / f"{stem}_{o:g}_b.png"
            ta = time.perf_counter() - t0
            await page.screenshot(path=fa)
            await page.wait_for_timeout(200)
            tb = time.perf_counter() - t0
            await page.screenshot(path=fb)
            post = await page.evaluate(TRUTH, ts)
            offs.append(dict(offset=o, t_truth=round(tt, 3), t_frame_a=round(ta, 3), t_frame_b=round(tb, 3), t_post=round(time.perf_counter() - t0, 3),
                             truth=truth, truth_post=post, frames=[str(fa.relative_to(ROOT)), str(fb.relative_to(ROOT))]))
        await ctx.close()
        return dict(rec, n_candidates=sel["n_candidates"], targets=ts, offsets=offs)
    except Exception as e:
        await ctx.close()
        return dict(rec, error=repr(e)[:300])


async def main(rnd, workers):
    OUT.mkdir(parents=True, exist_ok=True)
    log = OUT / "visits.jsonl"
    # resume: a visit that ended in an error is retried (its error record stays in the log)
    have = {(j["site"], j["cond"], j["round"]) for j in map(json.loads, log.read_text().splitlines()) if j and not j.get("error")} if log.exists() else set()
    ss = sites()
    sem = asyncio.Semaphore(workers)
    async with async_playwright() as p:
        b = await p.chromium.launch()
        with log.open("a") as f:
            async def per_site(si, site):
                last = 0.0
                for ci, cond in enumerate(CONDS):  # one visit at a time per site, >= 10 s between loads
                    if (site["name"], cond, rnd) in have:
                        continue
                    async with sem:
                        w = last + MIN_GAP_S - time.monotonic()
                        if w > 0:
                            await asyncio.sleep(w)
                        last = time.monotonic()
                        r = await visit(b, site, cond, rnd, seed=50000 + rnd * 1000 + si * 10 + ci)
                    f.write(json.dumps(r) + "\n"); f.flush()
                    print(site["name"], cond, "error" if r.get("error") else len(r["targets"]), flush=True)
            await asyncio.gather(*(per_site(i, s) for i, s in enumerate(ss)))
        await b.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--round", type=int, required=True)
    ap.add_argument("--workers", type=int, default=6)
    a = ap.parse_args()
    asyncio.run(main(a.round, a.workers))
