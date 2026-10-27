# Addition 3: when do real agents take their screenshot? (code review, no experiments)

Prereg: `docs/PREREG_ADDITIONS.md`, Addition 3 (tag `prereg-add-v1`). Snapshot of 2026-10-24. Public code was read only (through `gh api`); nothing was run and nothing was filed against any repo. Stars and last-commit dates are from the GitHub API on that day. Line numbers refer to the commit given. For each agent we traced the call chain from the action to the screenshot (or page observation) the model next sees, after a navigation and after a click, at default settings.

**Repos that changed shape** (substitutions are allowed by the prereg and named here):
- **Anthropic's computer-use reference implementation:** now in `anthropics/claude-quickstarts` (renamed).
- **OpenAI's CUA sample app:** rewritten into code-acting agents (the model writes PyAutoGUI or Playwright code and asks for its own screenshots). The last `computer_call` loop (2025-04-08) is reported as well.
- **Stagehand:** v4 (2026-08-10) removed the built-in agent handlers. The v4 Claude CUA integration is the current path; the last v3 handler is also reported.
- **OpenHands:** the browser tool now lives in `OpenHands/software-agent-sdk` and wraps browser-use 0.11.9 (pinned).
- **Playwright MCP:** the `microsoft/playwright-mcp` repo is a wrapper; the source is in `microsoft/playwright`.
- **Agent S:** the shipped `gui-agents` S3 CLI (S4 is a research harness released 2026-10-20).
- **SeeAct** was left out (last commit 2025-02-03). **UI-TARS-desktop** and **magentic-ui** were added.

## How the estimates are made

Each agent's post-navigation rule is mapped to the Addition 1 rule with the same mechanism or the nearest wait. Share of planned clicks invalid within 6.5 s of the screenshot (31 real pages, 3 rounds; Wilson 95% CI; `tables/settle_rules.csv`):

| Addition 1 rule | Median wait after `domcontentloaded` | Invalid within 6.5 s |
|---|---|---|
| S0 immediately (DOM-ready) | 0 s | 14.4% (12.6–16.5) |
| S1 0.5 s | 0.50 s | 2.5% (1.7–3.5) |
| S2 1 s | 1.00 s | 3.1% (2.3–4.2) |
| S3 no layout shift for 500 ms | 0.65 s | 2.8% (2.0–3.8) |
| S4 load event | 0.43 s | 3.0% (2.2–4.2) |
| S5 network idle | 1.24 s | 0.46% (0.21–1.0) |

These are **estimates**, not measurements of the agents. No agent was run. The mapping ignores several things: an agent's own page mix; desktop agents timing their sleep from a key press rather than from `domcontentloaded`; and fixed sleeps longer than 1 s, which Addition 1 did not measure. Part C's survival curve after navigation was flat from 1 s to 30 s, so a sleep longer than 1 s is not expected to fall far below S2. A sleep of 2–3 s is therefore given S2's value as an upper estimate.

## The table (default settings, after a navigation and after a click)

| Agent | Stars · last commit | Commit read | After navigation (file:line) | After click (file:line) | Class (navigation) | Estimated invalid after navigation |
|---|---|---|---|---|---|---|
| Anthropic computer-use demo (`anthropics/claude-quickstarts`, desktop, xdotool) | 18,978 · 2026-10-23 | `930ad10` | No navigate action: the model types a URL and presses Return; the `key` action sleeps `_screenshot_delay = 2.0`, then screenshots (`computer-use-demo/computer_use_demo/tools/computer.py` L99, L273–275). No page-load signal. | Same fixed 2.0 s (L273–275) | fixed sleep (2.0 s from the key press) | ≈ 3% (S2, upper estimate) |
| browser-use (`browser-use/browser-use`) | 119,062 · 2026-10-22 | `3df5806` | `NavigateToUrlEvent` defaults to `wait_until='load'`; `_navigate_and_wait` returns on the first CDP `networkIdle` or `load` lifecycle event, capped at 3 s same-domain / 8 s cross-domain (`browser_use/browser/session.py` L1064, L1108–1111). Before every screenshot: +0.3 s if any resource is pending (`browser/watchdogs/dom_watchdog.py` L270–289). | Download-detection wait of 0.5 s (`default_action_watchdog.py` L48, L130) + 0.05 s new-tab check, then the same 0–0.3 s gate | load event (capped 3/8 s) | ≈ 3.0% (S4) |
| OpenAI CUA sample app (`openai/openai-cua-sample-app`) | 1,910 · 2026-10-19 | `6dd34b4` | Current code: code-acting agents; the model writes PyAutoGUI or Playwright code and asks for its own screenshots. The harness adds no settle wait (`python-app/app/responses_loop.py` ~L59–65; `javascript-app/src/responses-loop.ts` L138 advises `domcontentloaded` waits). Legacy `computer_call` loop (`a8a75a3`, 2025-04-08): `page.goto(url)` (Playwright default `load`), then an immediate screenshot (`agent/agent.py` L79–82). | Current: none from the harness. Legacy: none (`agent/agent.py` L79–82). | no wait (current; model-driven) · load event (legacy) | ≈ 14% if the model screenshots at once (S0); legacy ≈ 3.0% (S4) |
| Stagehand (`browserbase/stagehand`, v4) | 25,803 · 2026-10-23 | `8023f34` | `page.goto(url, { waitUntil: "domcontentloaded" })` (`packages/integrations/claude-cua-sdk/src/executor.ts` L369–380); the screenshot is a separate model call with no wait (L597–600). v3 handler (`7566804`): `goto` with `waitUntil: "load"` (L621) + 0.5 s. | v4: CDP mouse events only, no wait (L427–458). v3: 0.3 s before + 0.5 s after (`v3CuaAgentHandler.ts` L139–182). | DOM-ready only (v4) · load event + 0.5 s (v3) | ≈ 14% (S0); v3 ≤ 3.0% (S4) |
| Skyvern (`Skyvern-AI/skyvern`) | 23,266 · 2026-10-25 | `647b920` | `goto(wait_until="load", timeout=60000)`, then a fixed settle of 750 ms + 0–500 ms jitter (`navigate_to_url`, `_wait_for_settle`), then before every screenshot: load ≤ 3 s and CSS animations finished ≤ 3 s (`skyvern/webeye/utils/page.py` L3075–3112). An optional page-ready mode (network idle, DOM stable) is off by default. | 0.3 s pre-click delay; 0.5–1.0 s random inter-action delay; then load ≤ 3 s + animations ≤ 3 s | load event + fixed 0.75–1.25 s | ≤ 3.0% (between S4 and S5; not measured) |
| Agent S3 (`simular-ai/Agent-S`, desktop, pyautogui) | 12,725 · 2026-10-21 | `0fff0e6` | No browser hooks: URL + Enter, then `time.sleep(1.0)` before the next `pyautogui.screenshot()` (`gui_agents/s3/cli_app.py` L207–216) | Same fixed 1.0 s (+ pyautogui `PAUSE` 0.1 s) | fixed sleep (1.0 s from the key press) | ≈ 3% (S2) or more, since 1 s from the key press is less than 1 s after `domcontentloaded` |
| OpenHands (`OpenHands/software-agent-sdk`, wraps browser-use 0.11.9) | 1,302 · 2026-10-25 (`OpenHands/OpenHands` 91,754) | `7234ea2` (browser-use `c011d07`) | browser-use 0.11.9 `_navigate_and_wait`: first `networkIdle` or `load`, capped at 2 s / 4 s (`browser_use/browser/session.py` L796–876); screenshot only when the model calls `browser_get_state(include_screenshot=True)` (`openhands-tools/.../browser_use/impl.py` L487–493) | 0.5 s download-detection wait + 0.05 s | load event (capped 2/4 s) | ≈ 3.0% (S4) |
| Playwright MCP (`microsoft/playwright-mcp`; source in `microsoft/playwright`) | 38,593 · 2026-10-22 | `0c4107a` (monorepo `91a765d`) | `goto(url, { waitUntil: 'domcontentloaded' })`, then `waitForLoadState('load', { timeout: 5000 })` (`packages/playwright-core/src/tools/backend/tab.ts` L378, L397). Default observation is an ARIA snapshot; screenshots come from a separate tool with no extra wait. | 500 ms settle; then load ≤ 10 s if it navigated, else responses to requests started during the click ≤ 5 s, + 500 ms if there were any (`backend/utils.ts` L20–58) | load event (capped 5 s) | ≈ 3.0% (S4) |
| UI-TARS-desktop (`bytedance/UI-TARS-desktop`) | 39,378 · 2026-10-09 | `3ac2cb8` | Browser operator: `page.goto(url, { waitUntil: [] })`, no load event (`packages/ui-tars/operators/browser-operator/src/browser-operator.ts` L556–568), then the app's 1,000 ms loop interval (`apps/ui-tars/src/main/store/setting.ts` L28; `GUIAgent.ts` L424–428) | Browser: 0.8 s after the click + 1.0 s loop (L319–336). Desktop operator: 1.0 s loop only. | fixed sleep (1.0 s from commit, no load wait) | 3–14% (between S0 and S2) |
| magentic-ui (`microsoft/magentic-ui`, Fara web surfer) | 10,096 · 2026-07-23 | `d3c9d13` | `goto(wait_until="commit")` (`playwright_controller_fara.py` L408), then `wait_for_load(state="domcontentloaded")` and `asyncio.sleep(3)` (`agents/web_surfer/fara/_fara_qwen3.py` L739–743), then load ≤ 2 s before the screenshot (L342, L355) | 1 s popup wait, then the same DOM-ready + 3 s + load ≤ 2 s | fixed sleep (3 s after `domcontentloaded`) | between 0.5% and 3% (not measured; longer than any fixed rule tested) |

Permalinks for each file and line are in the review notes below.

## What it shows

- **No agent waits for network idle as a requirement.** That is the only Addition 1 rule that reached 1% or less. browser-use and OpenHands accept CDP `networkIdle` only as an early exit next to `load`, and `load` usually fires first (median 0.43 s after `domcontentloaded` on the 31 pages).
- **Two take the post-navigation screenshot at DOM-ready or with no harness wait:** Stagehand v4 and the current OpenAI sample app (where the model decides). UI-TARS's browser operator does not wait for a load event either; it relies on its 1 s loop interval. Estimated ≈ 14% for the first two.
- **Four wait for the load event** in current code, capped at 2–8 s: browser-use, OpenHands, Playwright MCP and Skyvern. So did the legacy OpenAI loop. Skyvern adds about 1 s. Estimated ≈ 3%.
- **Four use a fixed sleep:** Anthropic's demo 2 s, Agent S 1 s, UI-TARS 1 s, magentic-ui 3 s. The two desktop agents have no page signal at all. Estimated ≈ 3%, with magentic-ui's 3 s not measured.
- Counted by navigation rule (one per agent, current code): no wait or DOM-ready 2, load event 4, fixed sleep 4. Skyvern is counted under load event. **All 10 take the planning screenshot before the point Addition 1 found to be settled (network idle).**

## Review notes (permalinks)

- Anthropic: https://github.com/anthropics/claude-quickstarts/blob/930ad10bb2e21a9ef97fe1a88d2037e18a24465c/computer-use-demo/computer_use_demo/tools/computer.py#L267-L276. The `type` action screenshots straight away with no sleep (L179). A sibling example in the same repo (`computer-use-best-practices/computer_use/tools/browser.py` L166–167) uses `goto(..., wait_until="domcontentloaded")` and then screenshots immediately.
- browser-use: https://github.com/browser-use/browser-use/blob/3df5806a0d097a1546d92c49bcf1b28c9972c3bd/browser_use/browser/session.py#L1034-L1115 and https://github.com/browser-use/browser-use/blob/3df5806a0d097a1546d92c49bcf1b28c9972c3bd/browser_use/browser/watchdogs/dom_watchdog.py#L268-L289. The profile settings `minimum_wait_page_load_time` (0.25) and `wait_for_network_idle_page_load_time` (0.5) are declared and passed through, but nothing in the action-to-screenshot path reads them at this commit.
- OpenAI legacy loop: https://github.com/openai/openai-cua-sample-app/blob/a8a75a301304137656c6b56168c521bfc326d17d/agent/agent.py#L70-L84
- Stagehand v4: https://github.com/browserbase/stagehand/blob/8023f34161d650c196dc343d2c232fb5e129a826/packages/integrations/claude-cua-sdk/src/executor.ts#L369-L458. v3: https://github.com/browserbase/stagehand/blob/7566804ed4b97649706782bccdcab5d80f6fe588/packages/core/lib/v3/handlers/v3CuaAgentHandler.ts#L139-L182
- Skyvern: https://github.com/Skyvern-AI/skyvern/blob/647b92071bf439809dda7373ae0304dafe4aa66d/skyvern/webeye/utils/page.py#L3075-L3112
- Agent S3: https://github.com/simular-ai/Agent-S/blob/0fff0e634869dab72027435b4586e62300185d41/gui_agents/s3/cli_app.py#L200-L216
- OpenHands / browser-use 0.11.9: https://github.com/browser-use/browser-use/blob/c011d07e7e9e41c06b5c72036c6e3efa5b9f287d/browser_use/browser/session.py#L796-L876
- Playwright MCP: https://github.com/microsoft/playwright/blob/91a765d1681cb3eeb0d0fb89fefec3cf0d21bd9b/packages/playwright-core/src/tools/backend/tab.ts#L369-L398 and https://github.com/microsoft/playwright/blob/91a765d1681cb3eeb0d0fb89fefec3cf0d21bd9b/packages/playwright-core/src/tools/backend/utils.ts#L20-L58. `playwright-mcp` pins playwright-core 1.64.0-alpha (2026-09-28); the same logic was confirmed at monorepo commit `e8149b8` from that date.
- UI-TARS: https://github.com/bytedance/UI-TARS-desktop/blob/3ac2cb8d946d78d5ff92ad17b318eaafa18c178c/packages/ui-tars/operators/browser-operator/src/browser-operator.ts#L319-L336
- magentic-ui: https://github.com/microsoft/magentic-ui/blob/d3c9d13c39288257286a66daabf7c5b5fb72ee69/src/magentic_ui/agents/web_surfer/fara/_fara_qwen3.py#L726-L743

**Uncertain points.**
- Stagehand v4: that `batchStagehand.page` resolves to the understudy `Page` was assumed, not traced in full.
- UI-TARS: Puppeteer's `waitUntil: []` was read as commit only.
- Skyvern: whether the hosted service turns on `enable_page_ready_wait` is unknown.
- Playwright MCP: the logic was read in the monorepo, not in the published tarball.

Three citations were spot-checked by hand against the stated commits: Anthropic L99 and L273–275, browser-use `session.py` L1064 and L1108–1111, and Playwright `tab.ts` L378 and L397.
