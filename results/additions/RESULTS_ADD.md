# Additions: settle rules on real pages, decision agreement, agent screenshot defaults (2026-10-24)

Preregistration: `docs/PREREG_ADDITIONS.md`, tag `prereg-add-v1` (commit c7d4700), frozen before any addition number was computed. Everything here is labelled **addition**. H1–H3 and E1–E5 stay exactly as reported in `results/full/RESULTS.md` and `results/extension/RESULTS_EXT.md`. Tables are in `results/additions/tables/`. Real-page screenshots and per-track records stay in `private/realsite_add/`, which is gitignored and never released. Real pages are never pooled with the benchmark. Nothing is public. No API spend and no Colab were used.

PUSV (W. Xu 2026, arXiv 2604.18860) is a security defense designed for adversarial change between screenshot and action. Its tuned check (C2) appears in Addition 2 only as one of Part A's baseline checks.

## Hypotheses

| | Hypothesis | Result |
|---|---|---|
| E6 | Waiting for 500 ms with no layout shift (cap 5 s) brings planned clicks invalidated within 6.5 s to ≤ 1%, upper 95% Wilson bound ≤ 2%, with a median wait shorter than network idle | **refuted**: 2.8% (95% CI 2.0–3.8%). The wait part held: median 0.65 s against 1.24 s. |
| E7 | At the measured change rates, the dev-fed first-order inequality gives the same check-or-skip decision as the test replay in ≥ 90% of decisions (supplementary, post-hoc) | **held**: 94.7% of 3,000 decisions |

## Scope as run

| Item | Preregistered | Run |
|---|---|---|
| Addition 1 | 31 approved pages × 7 rules × 3 rounds ≥ 2 h apart, rule order rotated, ≥ 3 visits per page per rule | 31 pages, rounds at 18:39, 20:44 and 22:49 PDT. 652 visit records: 644 with targets, 6 with no target, 2 errors. 1,216–1,303 tracks per rule. |
| Addition 2 | 750 Part A cells × 4 change rates | 3,000 decisions per form (first order; exposure term, exploratory) |
| Addition 3 | 8–10 agents by stars and recent commits | 10 agents, with named substitutions (see `agent_defaults.md`) |

Part C's rounds ran in the morning (09:40–13:41 PDT). These ran in the evening. Rule S3's fallback (box stability) was never triggered, because Chromium supports `layout-shift`; S3b ran it as its own rule, as preregistered.

## Deviations

1. **iris.edu with S0 and S4.** At `domcontentloaded` and at the load event, the page had no eligible visible target in any round, so these six visits record "no target". S0 and S4 therefore cover 30 pages and the other rules 31. (In Part C, iris.edu also had no targets after navigation.)
2. **gnu.org, S3b, round 1.** Both tries failed with a connection reset, so gnu.org has two S3b visits instead of three.
3. **Smoke test.** Before round 1, the collector was tried once on three pages (gnu.org, wikipedia.org, time.gov) as "round 0". The prereg did not mention a smoke test. Round 0 is excluded from every number.
4. **Addition 3 substitutions** (allowed by the prereg, listed for completeness). Five candidates had moved or been rewritten and were read at their new location:
   - Anthropic's demo, now in `claude-quickstarts`
   - OpenAI's sample app, now code-acting (its legacy loop is also reported)
   - Stagehand v4 (v3 also reported)
   - OpenHands, now in `software-agent-sdk`
   - Playwright MCP, whose source is in `microsoft/playwright`

   SeeAct was left out as stale. UI-TARS-desktop and magentic-ui were added.

## Addition 1. How long to wait after a navigation (real pages, read-only)

Each visit: a fresh context, `goto` at `domcontentloaded`, a wait under one rule, the planning screenshot, then up to 20 targets (Part C's selector) whose planned clicks were checked at 0.5, 1, 2 and 6.5 s. Tables: `settle_rules.csv`, `settle_rules_by_kind.csv`, `settle_wait_details.csv`, `settle_e6.csv`, `settle_cls_by_page.csv`, `settle_cls_spearman.csv`, `settle_visits.csv`. Figure: `figures/add_settle.png`.

| Rule | Median wait (p90) | Tracks | Invalid within 6.5 s (Wilson 95%) | Bootstrap over visits | Invalid within 2 s |
|---|---|---|---|---|---|
| S0 immediately | 0 s (0) | 1,283 | **14.4%** (12.6–16.5) | 8.8–20.5 | 13.8% |
| S1 0.5 s | 0.50 s (0.50) | 1,262 | 2.5% (1.7–3.5) | 1.0–4.5 | 1.4% |
| S2 1 s | 1.00 s (1.00) | 1,256 | 3.1% (2.3–4.2) | 1.0–6.7 | 2.4% |
| S3 no layout shift 500 ms, cap 5 s | 0.65 s (1.06) | 1,262 | **2.8%** (2.0–3.8) | 1.3–4.9 | 1.9% |
| S3b boxes still 500 ms, cap 5 s (exploratory) | 0.81 s (1.37) | 1,216 | 1.8% (1.2–2.7) | 0.7–3.1 | 1.3% |
| S4 load event | 0.43 s (1.11) | 1,246 | 3.0% (2.2–4.2) | 1.0–6.0 | 2.4% |
| S5 network idle | 1.24 s (3.19) | 1,303 | **0.46%** (0.21–1.0) | 0.14–0.91 | 0.15% |

**E6 refuted.** S3 left 2.8% of planned clicks invalid (upper bound 3.8%, against bars of 1% and 2%). Its median wait was shorter than network idle's (0.65 s against 1.24 s), so only that part held. The layout-shift observer often found little to wait for: 57 of 93 S3 visits took their screenshot within 0.7 s of `domcontentloaded`, close to the 500 ms minimum. The residual comes from a few maps and seismology pages: iris.edu 15 of 35 invalid tracks, emsc.eu 11, gnu.org 3, usgs.gov earthquakes 3, esa.int 3. On those pages, content arrives into fixed-size containers or covers the targets without registering as a layout shift.

**Cheapest rule at ≤ 1%:** network idle (S5), and it is the only one. Median wait 1.24 s, p90 3.19 s, residual 0.46% (6 of 1,303 tracks: one element each on esa.int and usgs.gov earthquakes, in every round). It is also the cheapest rule whose upper bound is ≤ 2%. 13 of 93 S5 visits waited more than 3 s and 5 more than 5 s (eia.gov, gnu.org, iris.edu); one, on gnu.org, hit the 45 s timeout.

**No fixed wait gets there.** 0.5 s and 1 s sleeps leave 2.5–3.1%. The load event leaves 3.0%: it fired a median 0.43 s after `domcontentloaded`, before most of the re-layout. By kind, the load event removed the burst on status pages (0%) but not on dashboards (10%).

**By page kind** (share invalid within 6.5 s):

| Kind | S0 | S1 | S2 | S3 | S3b | S4 | S5 |
|---|---|---|---|---|---|---|---|
| status | 23.5% | 0 | 0 | 0 | 0 | 0 | 0 |
| front page | 18.4% | 0.8% | 0.8% | 0.8% | 2.3% | 3.4% | 0.8% |
| reference | 15.0% | 0 | 28.3% | 5.0% | 0 | 0 | 0 |
| map | 13.3% | 8.5% | 7.6% | 9.5% | 5.6% | 1.2% | 1.2% |
| dashboard | 10.6% | 0 | 0 | 0 | 0 | 10.2% | 0 |
| listing | 6.6% | 2.3% | 0 | 2.3% | 0 | 0 | 0 |

"Reference" is one page (gnu.org, 60 tracks per rule). Its 28% at 1 s is a late re-layout that 0.5 s happened to precede. Maps are where every rule short of the load event or network idle leaves invalid clicks: tiles and overlays keep arriving for over a second.

**Layout shift predicts the burst, moderately.** Over 30 pages, the page's cumulative layout shift and its S0 share invalid within 2 s give Spearman ρ = 0.42 (bootstrap 95% CI 0.10–0.68, p = 0.02) with CLS from the same S0 visits. With CLS from the page's network-idle visits, a whole-load property, ρ = 0.53 (0.22–0.75, p = 0.003). High-CLS pages tend to burst, but several do not: eia.gov has CLS 0.43 and no burst, (only 3 tracks), while emsc.eu's map has CLS 0.04 and a 70% burst.

## Addition 2. Does the inequality make the right call? (E7, supplementary, post-hoc)

For each of Part A's 750 cells and each measured change rate, the predicted decision ("check" iff p > p*_pred, dev) is compared with the replay's (p > p*_obs, test). Tables: `decision_summary.csv`, `decision_by_check.csv`, `decision_by_check_p.csv`, `decision_cells.csv`.

| p | Where it was measured | Agreement, first order | Replay says check | Disagreements: predicted check / predicted skip |
|---|---|---|---|---|
| 0.003 | settled real pages | 95.6% | 6.3% | 33 / 0 |
| 0.010 | scrolled real pages | 90.7% | 11.6% | 64 / 6 |
| 0.171 | just-navigated real pages | 93.3% | 65.7% | 46 / 4 |
| 0.686 | benchmark Tier 1 | 99.3% | 94.8% | 5 / 0 |
| all | | **94.7%** (E7 held) | 44.6% | 148 / 10 |

- **By check** (first order): Haiku 100%, C7 99%, C1 98%, C4 95%, C4r 95%, Opus 93%, Qwen3-VL 4B 93%, C2 92%, C5r 91%, C6r 91%.
- **Cells where the first-order p* was off by more than 0.03:** agreement 93.1% (912 decisions), against 95.5% where it was within 0.03. The inequality usually makes the right call even where it misjudges the break-even, because the measured rates sit far from p* in most cells.
- **Which way it errs:** 148 of 158 disagreements predict "check" where the replay says "skip". It is optimistic about checking, consistent with Part A's finding that slow checks lose changes that land while they look. The errors cluster where p sits near a check's break-even. At p = 0.010 these are the pixel and region checks C4, C4r, C5r and C6r (75–84% agreement), mostly at k = 10–20. At p = 0.171 they are Opus and Qwen3-VL 4B (76–77%).
- **Exposure term (exploratory):** 94.3% overall. It removes most of the optimism (76 predicted-check / 94 predicted-skip) and lifts C4 to 98%, but lowers C2 to 75%: there it predicts "skip" in 71 decisions where the replay says "check". Its 75 disagreements in all fall at p = 0.003 (31) and p = 0.010 (44).

## Addition 3. When do real agents take their screenshot?

Full table, code citations and permalinks: `results/additions/agent_defaults.md`. Summary of the rule after a navigation, with the estimated share of planned clicks invalid (mapped from Addition 1; **estimates**, no agent was run):

| Agent | After navigation | Class | Estimate |
|---|---|---|---|
| Anthropic computer-use demo | 2.0 s after the key press (no page signal) | fixed sleep | ≈ 3% |
| browser-use | first of `load` / CDP `networkIdle`, cap 3–8 s | load event | ≈ 3.0% |
| OpenAI CUA sample app | none from the harness; the model asks for screenshots (legacy loop: `load`) | no wait | ≈ 14% (legacy ≈ 3.0%) |
| Stagehand v4 | `domcontentloaded`, screenshot is a separate call (v3: `load` + 0.5 s) | DOM-ready only | ≈ 14% |
| Skyvern | `load` + 0.75–1.25 s + load/animations ≤ 3 s | load event | ≤ 3.0% |
| Agent S3 | 1.0 s after the key press (no page signal) | fixed sleep | ≈ 3% or more |
| OpenHands | browser-use 0.11.9: first of `load` / `networkIdle`, cap 2–4 s | load event | ≈ 3.0% |
| Playwright MCP | `domcontentloaded`, then `load` ≤ 5 s | load event | ≈ 3.0% |
| UI-TARS-desktop | commit only, then the 1 s loop interval | fixed sleep | 3–14% |
| magentic-ui | `domcontentloaded` + 3 s + `load` ≤ 2 s | fixed sleep | 0.5–3% (not measured) |

**None of the 10 waits for network idle,** the only rule that reached 1% on real pages. browser-use and OpenHands accept CDP `networkIdle` only as an early exit beside `load`.
- Two (Stagehand v4, and the current OpenAI sample app's harness) take the post-navigation screenshot at DOM-ready or with no harness wait (estimate ≈ 14%).
- Four wait for the load event, and four use a fixed sleep of 1–3 s (estimate ≈ 3%; magentic-ui's 3 s was not measured).

After a click, the waits are shorter or the same: 0.5–1.8 s of fixed sleep, a 500 ms settle plus request quiescence (Playwright MCP), or nothing (Stagehand v4, OpenAI legacy).

## What the additions support

- **Wait for network idle before the planning screenshot after a navigation.** On 31 real pages, network idle left 0.46% of planned clicks invalid within 6.5 s, the settled-page level (Part C: 0.4%). Its median cost was 1.24 s and p90 3.2 s.
- **The cheaper signals don't get there.** Every fixed sleep up to 1 s, the load event, and the layout-shift rule left 2.5–3.1%. That is about a sixth of the 14% immediately after `domcontentloaded`, but still six times the settled level. A layout-shift observer does not see content that fills fixed-size boxes or covers targets.
- **The inequality's decisions are robust.** At the change rates actually measured, its check-or-skip call matched the replay 95% of the time, including where its break-even was off. When it errs, it errs towards checking.
- **Common open-source agents screenshot before the page has settled by this measure.** None of the ten waits for network idle. The estimated cost is about 3% of planned clicks after a navigation for most of them, and about 14% for the two that do not wait past DOM-ready.

## Files

Code: `realsite/collect_add.py`, `harness/add_settle.py`, `harness/add_decision.py`. Tables: `settle_rules.csv`, `settle_rules_by_kind.csv`, `settle_wait_details.csv`, `settle_e6.csv`, `settle_cls_by_page.csv`, `settle_cls_spearman.csv`, `settle_visits.csv`, `decision_summary.csv`, `decision_by_check.csv`, `decision_by_check_p.csv`, `decision_cells.csv`. Figure: `figures/add_settle.png`. Agent review: `agent_defaults.md`.
