"""Addition 1: how long to wait after a navigation (read-only). docs/PREREG_ADDITIONS.md, Addition 1.
Agent rules A1-A10: each agent's post-navigation wait, re-implemented (docs/PREREG_AGENT_RULES.md).

  python -m realsite.collect_add --round 1 [--workers 3]                 # S rules -> private/realsite_add/
  python -m realsite.collect_add --set agents --round 1 [--workers 3]    # A rules -> private/realsite_agents/

Per site and wait rule (S0-S5, plus S3b exploratory), one visit per round: fresh context, goto at domcontentloaded,
wait under the rule, planning screenshot, then Part C's target selector (up to 20, seeded) and DOM truth at 0.5, 1, 2,
6.5 s after the screenshot. A PerformanceObserver on layout-shift (installed before navigation) gives S3's quiet
window and the page's CLS. Rule order rotates per site and round. One visit at a time per site, >= 10 s between loads.
Everything goes to private/realsite_add/ (gitignored, never released).
"""
import argparse, asyncio, json, random, time
from pathlib import Path

from playwright.async_api import async_playwright

from realsite.collect_ext import PICK, TRUTH, UA, MIN_GAP_S, sites

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "private/realsite_add"
RULES = ("S0", "S1", "S2", "S3", "S3b", "S4", "S5")
SETS = {"settle": (ROOT / "private/realsite_add", RULES, 70000),
        "agents": (ROOT / "private/realsite_agents", tuple(f"A{i}" for i in range(1, 11)), 90000)}
OFFSETS = (0.5, 1, 2, 6.5)
QUIET_MS, CAP_S, LOAD_TIMEOUT_MS = 500, 5.0, 45000

OBSERVER = """(() => {
  window.__pf = {cls: 0, last: 0, n: 0, supported: (PerformanceObserver.supportedEntryTypes || []).includes('layout-shift')};
  if (!window.__pf.supported) return;
  new PerformanceObserver(l => { for (const e of l.getEntries()) {
    window.__pf.n += 1; window.__pf.last = Math.max(window.__pf.last, e.startTime + (e.duration || 0));
    if (!e.hadRecentInput) window.__pf.cls += e.value; } }).observe({type: 'layout-shift', buffered: true});
})();"""
STATE = "() => ({now: performance.now(), cls: __pf.cls, last: __pf.last, n: __pf.n, supported: __pf.supported})"
# navigation timing on the page clock: responseStart (~commit) and domContentLoadedEventEnd (0 until DOM-ready)
NAVT = """() => { const n = performance.getEntriesByType('navigation')[0] || {};
  return {now: performance.now(), rs: n.responseStart || null, dcl: n.domContentLoadedEventEnd || null, load: n.loadEventEnd || null}; }"""
# browser-use's pending-request check, verbatim (browser-use@3df5806 dom_watchdog.py, _get_pending_network_requests;
# identical in 0.11.9). Resource entries with responseEnd === 0, minus ads/trackers, >10 s old, and images/fonts >3 s old.
PENDING_JS = """
(function() {
	const now = performance.now();
	const resources = performance.getEntriesByType('resource');
	const pending = [];

	// Check document readyState
	const docLoading = document.readyState !== 'complete';

	// Common ad/tracking domains and patterns to filter out
	const adDomains = [
		// Standard ad/tracking networks
		'doubleclick.net', 'googlesyndication.com', 'googletagmanager.com',
		'facebook.net', 'analytics', 'ads', 'tracking', 'pixel',
		'hotjar.com', 'clarity.ms', 'mixpanel.com', 'segment.com',
		// Analytics platforms
		'demdex.net', 'omtrdc.net', 'adobedtm.com', 'ensighten.com',
		'newrelic.com', 'nr-data.net', 'google-analytics.com',
		// Social media trackers
		'connect.facebook.net', 'platform.twitter.com', 'platform.linkedin.com',
		// CDN/image hosts (usually not critical for functionality)
		'.cloudfront.net/image/', '.akamaized.net/image/',
		// Common tracking paths
		'/tracker/', '/collector/', '/beacon/', '/telemetry/', '/log/',
		'/events/', '/eventBatch', '/track.', '/metrics/'
	];

	// Get resources that are still loading (responseEnd is 0)
	let totalResourcesChecked = 0;
	let filteredByResponseEnd = 0;
	const allDomains = new Set();

	for (const entry of resources) {
		totalResourcesChecked++;

		// Track all domains from recent resources (for logging)
		try {
			const hostname = new URL(entry.name).hostname;
			if (hostname) allDomains.add(hostname);
		} catch (e) {}

		if (entry.responseEnd === 0) {
			filteredByResponseEnd++;
			const url = entry.name;

			// Filter out ads and tracking
			const isAd = adDomains.some(domain => url.includes(domain));
			if (isAd) continue;

			// Filter out data: URLs and very long URLs (often inline resources)
			if (url.startsWith('data:') || url.length > 500) continue;

			const loadingDuration = now - entry.startTime;

			// Skip requests that have been loading for >10 seconds (likely stuck/polling)
			if (loadingDuration > 10000) continue;

			const resourceType = entry.initiatorType || 'unknown';

			// Filter out non-critical resources (images, fonts, icons) if loading >3 seconds
			const nonCriticalTypes = ['img', 'image', 'icon', 'font'];
			if (nonCriticalTypes.includes(resourceType) && loadingDuration > 3000) continue;

			// Filter out image URLs even if type is unknown
			const isImageUrl = /\\.(jpg|jpeg|png|gif|webp|svg|ico)(\\?|$)/i.test(url);
			if (isImageUrl && loadingDuration > 3000) continue;

			pending.push({
				url: url,
				method: 'GET',
				loading_duration_ms: Math.round(loadingDuration),
				resource_type: resourceType
			});
		}
	}

	return {
		pending_requests: pending,
		document_loading: docLoading,
		document_ready_state: document.readyState,
		debug: {
			total_resources: totalResourcesChecked,
			with_response_end_zero: filteredByResponseEnd,
			after_all_filters: pending.length,
			all_domains: Array.from(allDomains)
		}
	};
})()
"""
# Skyvern's isAnimationFinished, verbatim (Skyvern@647b920 skyvern/webeye/scraper/domUtils.js L4143-4152)
ANIM_DONE = """() => {
  const animations = document.getAnimations({ subtree: true });
  const unfinishedAnimations = animations.filter(
    (a) => a.playState !== "finished",
  );
  if (!unfinishedAnimations || unfinishedAnimations.length == 0) {
    return true;
  }
  return false;
}"""
BOXES = """() => Array.from(document.querySelectorAll('a[href], button, [role=button]')).map(e => {
  const r = e.getBoundingClientRect(); return [Math.round(r.left), Math.round(r.top), Math.round(r.width), Math.round(r.height)].join(',');
}).join(';')"""


async def wait_rule(page, rule, t_dcl):
    """Returns extra info; the caller times the wait from t_dcl."""
    info = {}
    if rule in ("S1", "S2"):
        await asyncio.sleep(max(0.0, t_dcl + (0.5 if rule == "S1" else 1.0) - time.perf_counter()))
    elif rule in ("S4", "S5"):
        try:
            await page.wait_for_load_state("load" if rule == "S4" else "networkidle", timeout=LOAD_TIMEOUT_MS)
        except Exception:
            info["timeout"] = True
    elif rule == "S3":
        s0 = await page.evaluate(STATE)
        if not s0["supported"]:
            info["fallback"] = True
            return info | await box_quiet(page, t_dcl)
        dcl_page = await page.evaluate("() => (performance.getEntriesByType('navigation')[0] || {}).domContentLoadedEventEnd || 0")
        if not dcl_page:  # page clock at domcontentloaded, estimated
            dcl_page = s0["now"] - (time.perf_counter() - t_dcl) * 1000
        while True:
            s = await page.evaluate(STATE)
            quiet_since = max(dcl_page, s["last"])
            if s["now"] - quiet_since >= QUIET_MS:
                break
            if time.perf_counter() - t_dcl >= CAP_S:
                info["capped"] = True
                break
            await asyncio.sleep(0.05)
    elif rule == "S3b":
        info |= await box_quiet(page, t_dcl)
    return info


async def box_quiet(page, t_dcl):
    prev, since = None, time.perf_counter()
    while True:
        b = await page.evaluate(BOXES)
        now = time.perf_counter()
        if b != prev:
            prev, since = b, now
        if now - since >= QUIET_MS / 1000:
            return {}
        if now - t_dcl >= CAP_S:
            return {"capped": True}
        await asyncio.sleep(0.05)


# ---------- agent rules (docs/PREREG_AGENT_RULES.md); each does its own navigation ----------

async def _ignore(coro):
    try:
        await coro
        return False
    except Exception:
        return True  # timeout (or error) ignored, as the agent does


async def first_signal(page, t_commit, cap_s):
    """browser-use's _navigate_and_wait: first of CDP load / networkIdle (Playwright equivalents), capped after commit."""
    tasks = {asyncio.create_task(page.wait_for_load_state(s, timeout=LOAD_TIMEOUT_MS)): s for s in ("load", "networkidle")}
    done, pend = await asyncio.wait(tasks, timeout=max(0.0, t_commit + cap_s - time.perf_counter()), return_when=asyncio.FIRST_COMPLETED)
    for t in pend:
        t.cancel()
    await asyncio.gather(*pend, return_exceptions=True)
    ok = [tasks[t] for t in done if not t.exception()]
    return dict(signal=ok[0] if ok else None, signal_s=round(time.perf_counter() - t_commit, 3), capped=not ok)


async def pending_gate(page, cap_s):
    """browser-use's DOMWatchdog gate: +0.3 s if its pending-request check finds anything."""
    try:
        r = await asyncio.wait_for(page.evaluate(PENDING_JS), timeout=cap_s) if cap_s else await page.evaluate(PENDING_JS)
        n = len(r["pending_requests"])
    except Exception:
        return dict(pending=None)
    if n:
        await asyncio.sleep(0.3)
    return dict(pending=n)


async def agent_rule(page, rule, url, seed):
    info = {}
    commit = lambda: page.goto(url, wait_until="commit", timeout=LOAD_TIMEOUT_MS)
    if rule in ("A1", "A6", "A9"):  # Anthropic demo 2.0 s, Agent S3 1.0 s, UI-TARS 1.0 s loop: fixed sleep from commit
        await commit()
        await asyncio.sleep({"A1": 2.0, "A6": 1.0, "A9": 1.0}[rule])
    elif rule in ("A2", "A7"):  # browser-use (cross-domain cap 8 s, gate check capped 2 s); OpenHands / browser-use 0.11.9 (4 s, uncapped)
        await commit()
        t_commit = time.perf_counter()
        info |= await first_signal(page, t_commit, 8.0 if rule == "A2" else 4.0)
        info |= await pending_gate(page, 2.0 if rule == "A2" else None)
    elif rule in ("A3", "A4"):  # OpenAI sample app (no harness wait); Stagehand v4: DOM-ready, then screenshot
        await page.goto(url, wait_until="domcontentloaded", timeout=LOAD_TIMEOUT_MS)
    elif rule == "A5":  # Skyvern: load, settle 0.75 s + U(0, 0.5) s, then load <= 3 s and animations finished <= 3 s
        await page.goto(url, wait_until="load", timeout=60000)
        settle = 0.75 + random.Random(seed).uniform(0, 0.5)
        await asyncio.sleep(settle)
        info["settle_s"] = round(settle, 3)
        info["load_timeout"] = await _ignore(page.wait_for_load_state("load", timeout=3000))
        t = time.perf_counter()
        try:
            async with asyncio.timeout(3.0):
                while not await page.evaluate(ANIM_DONE):
                    await asyncio.sleep(0.1)
            info["anim_timeout"] = False
        except TimeoutError:
            info["anim_timeout"] = True
        info["anim_s"] = round(time.perf_counter() - t, 3)
    elif rule == "A8":  # Playwright MCP: DOM-ready, then load capped at 5 s
        await page.goto(url, wait_until="domcontentloaded", timeout=LOAD_TIMEOUT_MS)
        info["load_timeout"] = await _ignore(page.wait_for_load_state("load", timeout=5000))
    elif rule == "A10":  # magentic-ui: commit, DOM-ready <= 20 s, sleep 3 s, load <= 2 s
        await page.goto(url, wait_until="commit", timeout=20000)
        info["dcl_timeout"] = await _ignore(page.wait_for_load_state("domcontentloaded", timeout=20000))
        await asyncio.sleep(3)
        info["load_timeout"] = await _ignore(page.wait_for_load_state("load", timeout=2000))
    return info


async def visit(browser, site, rule, rnd, seed, out):
    ctx = await browser.new_context(viewport={"width": 1280, "height": 800}, device_scale_factor=1, user_agent=UA)
    await ctx.add_init_script(OBSERVER)
    page = await ctx.new_page()
    rec = dict(site=site["name"], url=site["url"], kind=site["kind"], rule=rule, round=rnd, seed=seed, t=time.strftime("%Y-%m-%dT%H:%M:%S"))
    try:
        timing = {}
        if rule.startswith("A"):
            t_go = time.perf_counter()
            info = await agent_rule(page, rule, site["url"], seed)
            nt = await page.evaluate(NAVT)
            wait_s = (nt["now"] - nt["rs"]) / 1000 if nt["rs"] else None  # since responseStart (~commit), page clock
            timing = dict(wait_dcl_s=round((nt["now"] - nt["dcl"]) / 1000, 3) if nt["dcl"] else None,
                          wait_wall_s=round(time.perf_counter() - t_go, 3), nav=nt)
        else:
            await page.goto(site["url"], wait_until="domcontentloaded", timeout=LOAD_TIMEOUT_MS)
            t_dcl = time.perf_counter()
            info = await wait_rule(page, rule, t_dcl)
            wait_s = time.perf_counter() - t_dcl
        wait_s = round(wait_s, 3) if wait_s is not None else None
        d = out / "frames"
        d.mkdir(parents=True, exist_ok=True)
        shot = d / f"{site['name']}_{rule}_r{rnd}.png"
        await page.screenshot(path=shot)
        t0 = time.perf_counter()
        st0 = await page.evaluate(STATE)
        sel = await page.evaluate(PICK, seed)
        ts = sel["targets"]
        if not ts:
            await ctx.close()
            return dict(rec, wait_s=wait_s, **timing, info=info, cls_plan=st0["cls"], error="no target")
        offs = []
        for o in OFFSETS:
            w = t0 + o - time.perf_counter()
            if w > 0:
                await asyncio.sleep(w)
            tt = time.perf_counter() - t0
            offs.append(dict(offset=o, t_truth=round(tt, 3), truth=await page.evaluate(TRUTH, ts)))
        st1 = await page.evaluate(STATE)
        await ctx.close()
        return dict(rec, wait_s=wait_s, **timing, info=info, cls_plan=st0["cls"], cls_end=st1["cls"], shifts_end=st1["n"], ls_supported=st0["supported"],
                    n_candidates=sel["n_candidates"], targets=ts, offsets=offs, frame=str(shot.relative_to(ROOT)))
    except Exception as e:
        await ctx.close()
        return dict(rec, error=repr(e)[:300])


async def main(rnd, workers, only=None, rule_set="settle"):
    out, rules, seed0 = SETS[rule_set]
    out.mkdir(parents=True, exist_ok=True)
    log = out / "visits.jsonl"
    # resume: a visit that ended in an error is retried (its error record stays in the log); "no target" counts as done
    done = lambda j: not j.get("error") or j["error"] == "no target"
    have = {(j["site"], j["rule"], j["round"]) for j in map(json.loads, log.read_text().splitlines()) if j and done(j)} if log.exists() else set()
    ss = [s for s in sites() if not only or s["name"] in only]
    sem = asyncio.Semaphore(workers)
    async with async_playwright() as p:
        b = await p.chromium.launch()
        with log.open("a") as f:
            async def per_site(si, site):
                last = 0.0
                start = (si + rnd) % len(rules)  # cyclic Latin square over sites and rounds
                for rule in rules[start:] + rules[:start]:
                    if (site["name"], rule, rnd) in have:
                        continue
                    async with sem:
                        w = last + MIN_GAP_S - time.monotonic()
                        if w > 0:
                            await asyncio.sleep(w)
                        last = time.monotonic()
                        r = await visit(b, site, rule, rnd, seed=seed0 + rnd * 1000 + si * 10 + rules.index(rule), out=out)
                    f.write(json.dumps(r) + "\n"); f.flush()
                    print(site["name"], rule, r.get("error") or f"{len(r['targets'])} targets, wait {r['wait_s']} s", flush=True)
            await asyncio.gather(*(per_site(i, s) for i, s in enumerate(sites()) if s in ss))
        await b.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--round", type=int, required=True)
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--set", default="settle", choices=sorted(SETS))
    a = ap.parse_args()
    asyncio.run(main(a.round, a.workers, a.only, a.set))
