# Preregistration addendum: three additions (settle rules on real pages, decision agreement, agent defaults)

Frozen 2026-10-24, tag `prereg-add-v1`, before any addition number was computed. It adds to `docs/PREREGISTRATION.md` (tag `prereg-v1`) and `docs/PREREG_EXTENSION.md` (tag `prereg-ext-v1`), both unchanged. Nothing here re-scores H1–H3 or E1–E5. Every result lives in `results/additions/` and is labelled "addition". Any later change to a spec below is a deviation and gets its own section in `results/additions/RESULTS_ADD.md`.

**Rules carried over.** Key only from `PREFLIGHT_API_KEY` or the Keychain, never `ANTHROPIC_API_KEY`; none of the additions needs the API or Colab, and none is planned. Real-site work is read-only (no login, no clicks, no form input) on the 31 pages already approved for Part C (`realsite/sites.json` plus `realsite/sites_ext_candidates.json`). Screenshots and per-track records stay in `private/realsite_add/` (gitignored, never released); only aggregate statistics leave it. Real pages are never pooled with the benchmark. Commit locally, no push. Every result is reported, held or not. PUSV (W. Xu 2026, arXiv 2604.18860) is a security defense designed for adversarial change wherever it appears.

**What was seen before this was written.** All of Part C (including the 0.4% settled and 17% just-navigated shares and the burst shape), and all of Part A's tables (`ineq_validation.csv`). E7 is therefore post-hoc: the Part A predicted and observed p* are already computed, and only the decision comparison at the measured change rates is new. Addition 1 collects new data.

## Hypotheses

- **E6. Settle rule.** Rule S3 below (no layout shift for 500 ms, capped at 5 s, timed from `domcontentloaded`) brings the share of planned clicks invalidated within 6.5 s of the planning screenshot to at most 1% (point estimate), with the upper 95% Wilson bound at most 2%. In addition, S3's median wait is shorter than S5's (network idle). E6 holds only if all three parts hold; each is reported.
- **E7. Decision agreement (supplementary, post-hoc).** At the change rates actually measured, p ∈ {0.003 (settled real pages), 0.010 (scrolled), 0.171 (just navigated), 0.686 (benchmark Tier 1)}, the first-order inequality fed dev numbers gives the same check-or-skip decision as the test replay in at least 90% of (cell × p) decisions over Part A's 750 cells.

## Addition 1. How long to wait after a navigation (real pages, read-only; new data)

**Sites and browser.** The same 31 pages, Chromium through Playwright, viewport 1280×800, device scale 1, honest user agent `preflight-research (read-only; contact via repo)`, at least 10 s between loads on any one site, one visit at a time per site. Each page keeps its Part C page kind.

**Wait rules.** Each visit is a fresh browser context: `page.goto(url, wait_until="domcontentloaded")`, then the planning screenshot is taken under one rule. Wait cost is timed from the moment `goto` returns at `domcontentloaded` to the start of the planning screenshot (monotonic clock).
- **S0:** immediately (Part C's "just navigated").
- **S1:** 0.5 s after `domcontentloaded`.
- **S2:** 1 s after.
- **S3:** once 500 ms have passed with no layout shift, capped at 5 s after `domcontentloaded`. Shifts are detected by a `PerformanceObserver` on `layout-shift` entries (`buffered: true`), installed with an init script before navigation. The quiet window starts at `domcontentloaded` or the last entry's `startTime + duration`, whichever is later. If the browser does not list `layout-shift` in `PerformanceObserver.supportedEntryTypes`, the fallback is used: the bounding boxes of all candidate targets (the elements the Part C selector would consider) unchanged for 500 ms, polled every 50 ms.
- **S3b (exploratory, not part of E6):** the fallback rule run as its own rule, so the two signals can be compared: candidate boxes unchanged for 500 ms, capped at 5 s.
- **S4:** at the `load` event (Playwright `wait_for_load_state("load")`, 45 s timeout, then go on).
- **S5:** at network idle (`wait_for_load_state("networkidle")`, 45 s timeout, then go on; a timeout is logged and its wait cost is the time actually waited).

**Targets and tracking.** Immediately after the planning screenshot, up to 20 targets are selected with Part C's selector (visible `a[href]`, `button`, `[role=button]`, fully in view and hit at their centre, stratified by viewport third × navigation control / content link, seeded per visit). The planned click is each target's box centre at that moment. DOM truth (`go_ok`: `elementFromPoint` at the planned click is the target or inside it; `exists`; centre displacement) is read at 0.5, 1, 2 and 6.5 s after the planning screenshot. Actual timestamps are logged; offsets are nominal. Only the planning screenshot is saved.

**Layout shift.** The same observer accumulates the page's cumulative layout shift (CLS: the sum of `value` over entries without `hadRecentInput`) from navigation start. It is read at the planning screenshot and at the end of tracking (6.5 s), and both values are logged.

**Visits.** One visit per page × rule per round, 3 rounds at least 2 h apart (different times of day). The order of the seven rules within each page is rotated across pages and rounds (a cyclic Latin square: page i in round r starts at rule (i + r) mod 7). Expected: up to 31 × 7 × 3 = 651 visits; a visit that errors is retried within its round. Target: at least 3 visits per page per rule, giving roughly 1,200 or more target tracks per rule (Part C averaged 14 targets per visit).

**Analysis** (`harness/add_settle.py`).
- **Primary outcome:** a target track is invalidated if `go_ok` is false at any of 0.5, 1, 2 or 6.5 s.
- **Per rule:** median and p90 wait cost (over visits); share invalidated with a Wilson 95% CI (over tracks), overall and by page kind; also a cluster bootstrap CI over visits (2,000 resamples) as a secondary interval.
- **Trade-off curve:** median wait against share invalidated, one point per rule with both intervals, as `figures/add_settle.png`.
- **Cheapest rule at ≤ 1%:** among rules whose point estimate is at most 1%, the one with the lowest median wait. Also reported: the cheapest rule whose upper Wilson bound is at most 2%.
- **E6:** S3's share ≤ 0.01, its upper Wilson bound ≤ 0.02, and median wait S3 < median wait S5.
- **Layout shift as a predictor:** per page, the median over the page's S0 visits of the end-of-tracking CLS, against the page's S0 share invalidated within 2 s (the post-navigation burst). Spearman ρ over pages with a bootstrap CI over pages (2,000 resamples). Also reported: the same with CLS from the page's S5 visits (a whole-load property not measured in the same visit as the burst).
- **Visits and failures:** per page, rule and round, in `results/additions/tables/settle_visits.csv`.

## Addition 2. Does the inequality make the right call? (existing data; E7)

**Cells.** Every row of `results/extension/tables/ineq_validation.csv` (check × tier × C × k, 750 cells), crossed with p ∈ {0.003, 0.010, 0.171, 0.686}: 3,000 decisions.

**Decisions.** The predicted decision is "check" iff p > p*_pred (first order, dev rates, unclipped; p* above 1 means "skip" at every p). The observed decision is "check" iff p > p*_obs from the test replay (an infinite p*_obs means "skip" at every p; p*_obs = 0 means "check" at every p > 0). They agree when both say check or both say skip.

**Reported** (`results/additions/tables/decision_*.csv`):
- agreement over all 3,000 decisions (E7 holds at ≥ 0.90), and per p;
- by check;
- among the cells whose first-order error exceeded 0.03, and among those within 0.03;
- the same for the exploratory exposure form (Part A's `p_exposure_exploratory`), labelled exploratory;
- for disagreements, which way they go (predicted check where the replay says skip, and vice versa).

## Addition 3. When do real agents take their screenshot? (code review, no experiments)

**Agents.** 8 to 10 widely used open-source computer-use and browser agents, chosen by GitHub stars and a commit in the last six months: for example Anthropic's computer-use reference implementation, browser-use, OpenAI's CUA sample app, Stagehand, Skyvern, Agent S, OpenHands' browsing agent, and the Playwright MCP server. Substitutions are allowed if one of these is archived, closed or not public; each is named.

**For each agent,** from the default branch's code at a recorded commit:
- repo, commit hash, and file and line of the wait before the screenshot the planner sees, after a navigation and after a click;
- the class of the wait, one of: fixed sleep (value), load event, network idle, DOM-ready only, no wait. Where a rule combines several (for example load event plus a fixed sleep, or network idle with a short timeout), the class is the one that bounds the wait in practice, and the full rule is quoted;
- an **estimate** of the share of planned clicks that would be invalid after a navigation, mapped from Addition 1 (the rule with the nearest wait) and Part C. It is labelled an estimate; no agent is run.

Read-only: public code only, nothing is run, nothing is filed against any repo. Output: `results/additions/agent_defaults.md`.

## Outputs

`results/additions/RESULTS_ADD.md` (scope as run, deviations, E6 and E7 each marked "held" or "refuted", the agent-defaults table), `results/additions/tables/`, `results/additions/agent_defaults.md`, `figures/add_settle.png`, and one line per slide-worthy number appended to `results/extension/TALK_NUMBERS_EXT.md`.
