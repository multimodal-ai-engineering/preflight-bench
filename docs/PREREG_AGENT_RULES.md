# Preregistration addendum: each agent's post-navigation wait rule, measured

Frozen 2026-10-26, tag `prereg-agents-v1`, before any measurement in this addendum was collected. It adds to `docs/PREREGISTRATION.md`, `docs/PREREG_EXTENSION.md` and `docs/PREREG_ADDITIONS.md`, all unchanged. It replaces the estimated column of the paper's Table 2 (`tab:settle`, from `results/additions/agent_defaults.md`) with measurements. Results go in `results/agent_rules/`. Any later change to a spec below is a deviation and gets its own section in `results/agent_rules/RESULTS_AGENT_RULES.md`.

**What this measures.** Each agent's **wait logic** after a navigation, re-implemented in our harness and run on our 31 approved real pages. It does not run the agents end to end: no LLM is called, and no agent code is executed. The paper must say so.

**Rules carried over.** No API key and no LLM; none is needed. Read-only (no login, no clicks, no form input) on the 31 pages approved for Part C. Honest user agent `preflight-research (read-only; contact via repo)`, at least 10 s between loads on any one site, one visit at a time per site. Screenshots and per-track records stay in `private/realsite_agents/` (gitignored, never released); only aggregate statistics leave it. Real pages are never pooled with the benchmark. Commit locally, no push. Every result is reported.

**Seen before this was written.** All of Addition 1 (rules S0–S5 and their invalid shares) and the code review in `agent_defaults.md`, including its estimates.

## Hypothesis

- **E8.** At least 8 of the 10 agent rules leave more than 1% of planned clicks invalid within 6.5 s of the planning screenshot, meaning their lower 95% Wilson bound is above 1%.

## The ten rules

Each visit is a fresh browser context: navigate, wait under the rule, take the planning screenshot. Where a rule says "commit", it calls `page.goto(url, wait_until="commit")` and starts its timers when that call returns. CDP lifecycle events are replaced by Playwright's equivalents: CDP `load` by `wait_for_load_state("load")`, and CDP `networkIdle` by `wait_for_load_state("networkidle")`. Both mean no network connections for 500 ms, but Playwright computes its own. Code citations are from `results/additions/agent_defaults.md` (commits read 2026-10-24).

| Rule | Agent | Implemented wait before the planning screenshot | Read from |
|---|---|---|---|
| A1 | Anthropic computer-use demo | commit, then sleep 2.0 s | `anthropics/claude-quickstarts@930ad10` `computer-use-demo/computer_use_demo/tools/computer.py` L99, L273–275 |
| A2 | browser-use | commit; then the first of `load` or `networkidle`, capped at **8 s** after commit; then browser-use's pending-request check (its JavaScript, verbatim), and +0.3 s if it reports any pending request (check capped at 2 s) | `browser-use/browser-use@3df5806` `browser_use/browser/session.py` L1064, L1108–1111; `browser/watchdogs/dom_watchdog.py` L93–200, L270–289 |
| A3 | OpenAI CUA sample app (current) | `goto(wait_until="domcontentloaded")`, screenshot immediately (no harness wait; same as S0) | `openai/openai-cua-sample-app@6dd34b4` `python-app/app/responses_loop.py` ~L59–65 |
| A4 | Stagehand v4 | `goto(wait_until="domcontentloaded")`, screenshot immediately | `browserbase/stagehand@8023f34` `packages/integrations/claude-cua-sdk/src/executor.ts` L369–380, L597–600 |
| A5 | Skyvern | `goto(wait_until="load", timeout=60 s)`; sleep 0.75 s + uniform(0, 0.5) s; then `load` ≤ 3 s, then poll every 0.1 s until every animation in `document.getAnimations({subtree: true})` has `playState === "finished"` (Skyvern's `isAnimationFinished`). The load wait and the animation wait each have their own 3 s cap, and timeouts are ignored. | `Skyvern-AI/skyvern@647b920` `skyvern/webeye/utils/page.py` L3075–3112; `skyvern/webeye/scraper/domUtils.js` L4143–4152 |
| A6 | Agent S3 | commit, then sleep 1.0 s | `simular-ai/Agent-S@0fff0e6` `gui_agents/s3/cli_app.py` L207–216 |
| A7 | OpenHands (browser-use 0.11.9) | commit; then the first of `load` or `networkidle`, capped at **4 s** after commit; then the same pending-request check and +0.3 s if any (no 2 s cap in this version) | `OpenHands/software-agent-sdk@7234ea2` → `browser-use/browser-use@c011d07` `browser_use/browser/session.py` L810–818, L796–876; `dom_watchdog.py` L262–285 |
| A8 | Playwright MCP | `goto(wait_until="domcontentloaded")`, then `wait_for_load_state("load", timeout=5000)`, ignoring a timeout | `microsoft/playwright@91a765d` `packages/playwright-core/src/tools/backend/tab.ts` L378, L397 |
| A9 | UI-TARS-desktop | commit, then sleep 1.0 s (the app's loop interval) | `bytedance/UI-TARS-desktop@3ac2cb8` `browser-operator.ts` L556–568; `apps/ui-tars/src/main/store/setting.ts` L28 |
| A10 | magentic-ui | commit (timeout 20 s); `wait_for_load_state("domcontentloaded", timeout=20000)`; sleep 3 s; then `wait_for_load_state("load", timeout=2000)`, ignoring a timeout | `microsoft/magentic-ui@d3c9d13` `playwright_controller_fara.py` L342, L355, L408; `_fara_qwen3.py` L739–743 |

**Where this differs from the request's table, the agent's code wins** (the request says "match the agent's code"):
- **A2 and A7 caps.** browser-use sets the cap to 3 s (0.11.9: 2 s) only when the new URL is on the same domain as the current page, and otherwise to 8 s (0.11.9: 4 s). A fresh navigation from a blank tab, as here, takes the cross-domain branch (`session.py` L1056–1064 at `3df5806`; L810–818 at `c011d07`). We implement 8 s and 4 s. We also log when the first signal arrived, so the number of visits where a 3 s or 2 s cap would have bound can be reported.
- **A7's pending-request gate.** OpenHands' screenshot comes from browser-use's `get_state`, which runs the same pending-request check and +0.3 s sleep as A2, so A7 includes it.
- **A3 and A4** are the same implementation. Both are run, as requested, and act as replicates of each other and of Addition 1's S0.
- **Timing anchors.** The desktop agents (A1, A6) time their sleep from the Enter key press. We time it from commit, which comes after the key press, so A1 and A6 wait slightly longer here than in the agent.

## Protocol (identical to Addition 1)

- **Sites, browser and visits:** the same 31 pages, Chromium through Playwright, viewport 1280×800, device scale 1. One visit per page × rule per round. 3 rounds at least 2 h apart (different times of day). Rule order rotated per page and round (cyclic Latin square: page i in round r starts at rule (i + r) mod 10). Errored visits are retried within the round. Expected: up to 930 visits.
- **Targets:** after the planning screenshot, up to 20 targets with Part C's selector (seeded per visit). DOM truth (`go_ok`) at 0.5, 1, 2 and 6.5 s after the screenshot.
- **Wait cost, logged per visit:** (a) on the page clock at the screenshot, time since the navigation's `responseStart` (≈ commit; the primary wait, comparable across rules); (b) time since `domContentLoadedEventEnd`, which is negative if the screenshot comes before DOM-ready, so it compares with Addition 1's S rules; (c) wall time since the `goto` call. Also logged: the rule's internal events (which signal arrived first and when, caps hit, the pending-request gate, animation polling).
- **Data:** `private/realsite_agents/visits.jsonl`. Code: rules `A1`–`A10` in `realsite/collect_add.py` (`--set agents`), analysis in `harness/agent_rules.py`.

## Analysis

- **Per rule:** visits, pages, tracks; median and p90 wait (a) and (b); share of tracks invalid within 6.5 s (`go_ok` false at any of 0.5, 1, 2, 6.5 s) with a Wilson 95% CI, plus a cluster bootstrap CI over visits (2,000 resamples) as a secondary interval; the same by page kind.
- **E8:** count of rules whose Wilson lower bound exceeds 1%; it holds at 8 or more.
- **Against the earlier estimates** (`agent_defaults.md`):
  - *Inside its estimate:* a point estimate (≈ x) is inside when x lies in the measured Wilson CI. A bound ("≤ x", "≥ x") or a range ("a–b") is inside when it intersects the CI.
  - *Wrong by more than 2 points:* the measured share is more than 2 percentage points from the point estimate, or from the nearest end of the bound or range.
- **Paper:** Table 2's right-hand column becomes the measured share (Wilson CI) and median wait. The caption, the two sentences in Section 5.2 and the Limitations paragraph that call the figures estimates are changed to say the rules were re-implemented and measured, and the agents were not run.
