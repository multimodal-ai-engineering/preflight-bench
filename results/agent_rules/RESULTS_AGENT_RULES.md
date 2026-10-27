# Results: ten agents' post-navigation wait rules, measured on 31 real pages

Preregistration: `docs/PREREG_AGENT_RULES.md` (tag `prereg-agents-v1`, commit 532a88a), frozen before any data in this report was collected. Data: `private/realsite_agents/visits.jsonl` (gitignored). Code: rules `A1`–`A10` in `realsite/collect_add.py` (`--set agents`); analysis `python -m harness.agent_rules` → `results/agent_rules/tables/`.

**What this measures.** Each agent's **wait logic** after a navigation, re-implemented in our harness and run on our 31 approved real pages with Addition 1's protocol. The agents themselves were not run: no LLM was called and no agent code was executed. An agent end to end also adds model latency before its first action, and some re-screenshot after acting; neither is measured here.

**Collection.** Three rounds on 2026-10-26: round 1 starting at about 14:21 PDT, round 2 at 16:26, round 3 at 18:31 (each ≥ 2 h after the last). 930 page × rule × round visits were planned. Of these, 902 produced a planning screenshot and targets, 20 found no target (18 on iris_seismon, 2 on census_popclock in round 3), and 8 failed (census_popclock in round 3, page load timed out on the first try and the retry; see Deviations). Each rule has 89–92 usable visits on 30–31 pages and 1,233–1,300 tracks.

## Table

Invalid = the planned click's target is gone, moved or covered (`go_ok` false) at any of 0.5, 1, 2 or 6.5 s after the planning screenshot. Wait = time from the navigation's `responseStart` (≈ commit) to the screenshot on the page clock; median (p90). Wilson 95% CIs; the cluster bootstrap over visits is wider and given in `tables/agent_rules.csv`.

| Rule | Agent | Rule as implemented | Wait, median (p90) | Tracks | Invalid within 6.5 s (95% CI) | Earlier estimate | Estimate inside CI? | Off by (pts) |
|---|---|---|---|---|---|---|---|---|
| A1 | Anthropic computer-use demo | commit, sleep 2.0 s | 2.02 s (2.06) | 1,264 | **1.98%** (1.34–2.90) | ≈ 3% | no (CI below) | 1.0 |
| A2 | browser-use | commit; first of load / networkidle, cap 8 s; +0.3 s if requests pending | 0.94 s (2.08) | 1,250 | **4.00%** (3.05–5.23) | ≈ 3% | no (CI above) | 1.0 |
| A3 | OpenAI CUA sample app | DOM-ready, no wait | 0.35 s (0.82) | 1,282 | **15.4%** (13.5–17.4) | ≈ 14% | yes | 1.4 |
| A4 | Stagehand v4 | DOM-ready, no wait | 0.34 s (0.90) | 1,241 | **12.5%** (10.8–14.5) | ≈ 14% | yes | 1.5 |
| A5 | Skyvern | load; sleep 0.75–1.25 s; load ≤ 3 s; animations finished ≤ 3 s | 2.03 s (4.67) | 1,294 | **0.46%** (0.21–1.01) | ≤ 3% | yes | 0 |
| A6 | Agent S3 | commit, sleep 1.0 s | 1.02 s (1.13) | 1,300 | **11.7%** (10.1–13.6) | ≥ 3% | yes | 0 |
| A7 | OpenHands (browser-use 0.11.9) | commit; first of load / networkidle, cap 4 s; +0.3 s if requests pending | 0.93 s (1.65) | 1,254 | **2.63%** (1.88–3.67) | ≈ 3% | yes | 0.4 |
| A8 | Playwright MCP | DOM-ready; load ≤ 5 s | 0.88 s (1.69) | 1,233 | **3.00%** (2.18–4.11) | ≈ 3% | yes | 0 |
| A9 | UI-TARS-desktop | commit, sleep 1.0 s | 1.01 s (1.19) | 1,271 | **9.05%** (7.59–10.75) | 3–14% | yes | 0 |
| A10 | magentic-ui | commit; DOM-ready; sleep 3 s; load ≤ 2 s | 3.34 s (3.99) | 1,293 | **1.16%** (0.70–1.91) | 0.5–3% | yes | 0 |

For comparison, Addition 1's rules on the same pages: DOM-ready with no wait (S0) 14.4% (12.6–16.5); 0.5 s, 1 s, load event and layout-shift rules 2.5–3.1%; network idle (S5) 0.46% (0.21–1.0) at a median 1.24 s after DOM-ready.

## E8: held

**E8** said at least 8 of the 10 agent rules leave more than 1% of planned clicks invalid (lower Wilson bound above 1%). **8 of 10 do, so E8 held.** The two that do not are Skyvern (A5, 0.46%, lower bound 0.21%) and magentic-ui (A10, 1.16%, lower bound 0.70%). This is a narrow hold: A10's point estimate is above 1% and its lower bound is not.

## Against the earlier estimates

- **No estimate was wrong by more than 2 points.** The largest misses are the two DOM-ready rules (A3 1.4, A4 1.5 points from ≈ 14%), both within their CIs.
- **Outside the CI of the earlier estimate:** two of ten.
  - A1 (Anthropic demo): measured 1.98% (1.34–2.90); the ≈ 3% estimate is just above the CI. A 2 s sleep is longer than any fixed sleep in Addition 1 (≤ 1 s), so ≈ 3% was too high.
  - A2 (browser-use): measured 4.00% (3.05–5.23); the ≈ 3% estimate is just below the CI. Its screenshot usually comes at the load event (88 of 89 visits); the measured share lies between Addition 1's load-event rule (3.0%) and its no-wait rule.
- **A6 and A9 (1 s after commit).** The estimates were bounds (≥ 3%, 3–14%), and the measured shares (11.7%, 9.1%) are well above the 1 s sleep timed from DOM-ready (S2, 3.1%). The difference comes from the visits where the screenshot was taken before DOM-ready: 7 of 91 (A6) and 6 of 90 (A9), 6 of the 13 on usgs_water (a map page that redirects client-side; every A6 and A9 visit there), the rest on emsc_quakes, emsc_realtime, eia_grid and wikinews. Those visits are 82% and 88% invalid and carry 106 of A6's 152 and 77 of A9's 115 invalid tracks. On visits where the screenshot came after DOM-ready the two rules leave 3.9% and 3.2%.
- **A3 and A4 have the same implementation.** They replicate each other and S0: 15.4% and 12.5%, CIs overlapping each other and S0's. The 2.9-point gap between identical rules shows the run-to-run spread; the bootstrap CIs over visits (9.5–21.9%, 7.1–18.9%) are the more honest interval for these two.

## By page kind (invalid share)

| Kind | A1 | A2 | A3 | A4 | A5 | A6 | A7 | A8 | A9 | A10 |
|---|---|---|---|---|---|---|---|---|---|---|
| dashboard | 0.0% | 9.3% | 6.1% | 1.0% | 0.0% | 7.7% | 9.3% | 10.1% | 0.5% | 0.0% |
| front page | 0.9% | 6.8% | 26.5% | 23.4% | 0.9% | 7.4% | 2.0% | 3.1% | 1.4% | 1.4% |
| listing | 2.3% | 0.0% | 6.6% | 6.6% | 0.0% | 6.6% | 0.0% | 0.0% | 6.6% | 0.0% |
| map | 6.8% | 1.2% | 11.2% | 3.8% | 1.2% | 29.0% | 1.6% | 1.2% | 30.2% | 3.8% |
| reference | 0.0% | 0.0% | 13.3% | 13.3% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% |
| status | 0.0% | 0.7% | 23.8% | 24.1% | 0.0% | 6.1% | 0.0% | 0.7% | 6.1% | 0.0% |

Dashboards are where the load-event rules (A2, A7, A8) lose most: they fill after load.

## Rule internals

- **A2 / A7 race.** The load event won on every visit where a signal arrived (A2 88 of 89, A7 87 of 89); network idle never arrived first. The cap ended the wait on 1 A2 visit (8 s) and 2 A7 visits (4 s). The load event came more than 3 s after commit on 5 of 89 A2 visits, and more than 2 s on 8 of 89 A7 visits: these are the visits where the request's suggested same-domain caps (3 s, 2 s) would have bound.
- **Pending-request gate (A2, A7).** browser-use's check, run verbatim, never reported a pending request, so the +0.3 s never applied. See Deviations.
- **A5 (Skyvern).** The load wait never timed out. The animation check timed out (3 s) on 6 of 92 visits; the median animation wait was 0.007 s.
- **A8, A10.** The load wait never timed out; A10's DOM-ready wait never timed out.

## Deviations and substitutions

1. **CDP events replaced by Playwright's (preregistered substitution).** CDP lifecycle `load` → `wait_for_load_state("load")`; CDP `networkIdle` → `wait_for_load_state("networkidle")`. Playwright computes its own idle (no connections for 500 ms), which may fire at a different moment from Chromium's lifecycle event. Since load won every race, this did not change any A2 or A7 visit's outcome as far as the logs show.
2. **A2 and A7 caps follow the code, not the request's table (preregistered).** 8 s and 4 s (cross-domain branch) instead of 3 s and 2 s. Impact counted above (5 and 8 visits).
3. **Pending-request gate never fired.** The check reads the page's resource timing entries; Chromium adds an entry only when a request completes, so in-flight requests are not visible to it. This is the agent's own JavaScript, so the same is likely true in the agent on Chromium, but we did not run the agent to confirm it.
4. **Timing anchors (preregistered).** A1 and A6 time their sleep from commit, not from the agent's key press, so they wait slightly longer here than in the agent; the measured share is if anything a slight underestimate for those two.
5. **census_popclock, round 3.** census.gov timed out on page load for 8 of 10 rules (A2–A9) on the first try and again in the retry pass; A1 and A10 loaded but found no target. These 8 visits are missing; no extra loads were made outside the round. Each of A2–A9 lost one visit.
6. **iris_seismon** found no target on 18 visits, all under the rules that screenshot within about 1 s (A2, A3, A4, A7, A8 in every round, A9 in two rounds, A6 in one); presumably the page had not yet drawn its clickable elements (not checked). The rules that wait 2 s or more (A1, A5, A10) found targets there every time. It contributes tracks only where targets were found, which slightly favours the early rules.
7. **Round 0 (30 visits) was a smoke test** of the code before round 1 and is excluded from every figure.
8. **Paper build.** The request says `latexmk -pdf`; latexmk and pdflatex are not installed on this machine, so the paper was rebuilt with `tectonic` (same LaTeX source; page count read with `pdfinfo`).

## Files

- `tables/agent_rules.csv` — per rule: visits, pages, tracks, invalid share with Wilson and bootstrap CIs, 2 s share, waits (a, b, c), E8 flag, estimate comparison.
- `tables/agent_rules_by_kind.csv`, `tables/agent_e8.csv`, `tables/agent_rule_details.csv`, `tables/agent_visits.csv` (status of every visit; no screenshots or page content).
