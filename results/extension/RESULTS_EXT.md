# Extension results: the inequality, the checker rubric, real-page timing, the planner (2026-10-24)

Preregistration addendum: `docs/PREREG_EXTENSION.md`, tag `prereg-ext-v1` (commit c4eba9c), frozen before any extension number was computed. Parts A and B analyse full-study data and were designed after the full results were seen. Parts C and D collected new data. Everything here is labelled **extension**. H1–H3 of the full study stay exactly as reported in `results/full/RESULTS.md`; nothing here re-scores them. Tables are in `results/extension/tables/`, live logs in `results/extension/live/`, GPU outputs in `results/extension/gpu_out/`. Real-page screenshots and per-track records stay in `private/realsite_ext/`, which is gitignored and never released. Nothing is public.

PUSV (W. Xu 2026, arXiv 2604.18860) is a security defense designed for adversarial change between screenshot and action. Its checks (C1 as published, C2 tuned) appear here as baselines on ordinary moving pages, a workload it was not built for.

## Hypotheses

| | Hypothesis | Result |
|---|---|---|
| E1 | Dev-fed inequality predicts test break-even p*: first order within 0.03 in ≥ 80% of cells, second order within 0.02 in ≥ 80% | **refuted** (69.6% and 51.2% of 750 cells) |
| E2 | Escalation rule picks the cheaper checker on test in ≥ 90% of cells (±20% of M* excluded) | **held** (92.7% of 14,204 cells) |
| E3 | Within 2 s, planned clicks are invalidated more often right after an action than on a settled page (95% CI excludes 0) | **held** (after navigation 17.4% vs settled 0.4%; +17.0 points, CI 9.9–24.7) |
| E4 | Planner misses less with motion frozen, and less with only the latest screenshot (McNemar, Holm) | **refuted** (no difference in either comparison) |
| E5 | Re-grounding the same element: wrong clicks ≤ 3% (upper Wilson), median latency ≤ 50% of a full re-plan | **refuted** (wrong 34.3%, upper bound 38.9%; latency 1.05× a re-plan) |

## Scope as run

| Item | Preregistered | Run |
|---|---|---|
| Part A | 10 checks × 3 tiers × 5 C × 5 k | 750 cells. C_meas = 1.07 s (median Haiku planning time in the full live loop). |
| Part B | B.1, B.3, B.4 on full-study answers | as planned; 14,487 validation cells (283 excluded near M*) |
| B.2 | dedicated T4, 200 calls per model, 10 warm-ups | as planned: Tesla T4, fp16, batch 1, models run strictly one after another (800 timed calls) |
| Part C | ≥ 30 pages, ≥ 3 visits per page per condition at different times, ≥ 1,800 tracks per condition | 31 pages, 3 rounds about 2 h apart, 270 successful visits, 1,330 / 1,241 / 1,278 tracks (settled / navigated / scrolled): short of 1,800 (deviation 2) |
| D.1 | 400 matched steps × 3 conditions | 400 matched steps (50 episodes × 8), 0 skipped |
| D.2 | 800 steps, 6.5 s gap, C4 re-plan-only, 4 recoveries | 786 steps (one episode of 8 lost to a page-clock error), 29 planner parse failures, 434 steps where C4 fired |

**Spend.** Anthropic API $0.64 of the $15 cap (D.1 $0.25, D.2 $0.38; ledger `results/extension/api_spend.jsonl`). Colab: one dedicated T4 session of about 70 minutes, running B.2 and the Qwen re-ground jobs, plus under a minute on an A100 runtime that was stopped (see deviations). Units: not logged by the runner; to be read from the Colab dashboard (estimate 2–3 of the 15).

## Deviations

1. **Qwen3-VL 4B re-ground coordinates (D.2).** The prompt asked for pixel coordinates in the 1024×640 screenshot. Qwen answered in its native 0–1000 relative coordinates; y values up to 978 cannot be pixels on a 640-pixel-high image. Its answers are scored as 0–1000 coordinates. This choice was made after seeing the outputs, so the "as pixels" reading is reported next to it: 115 correct of 434 under 0–1000, 3 of 434 as pixels.
2. **Part C sample.** Part C reached 1,330 / 1,241 / 1,278 target tracks per condition, short of the preregistered 1,800. Many pages offer fewer than 20 eligible visible targets (mean 14.3 targets per visit, median 17), and some visits failed. 26 of the 31 pages have all three conditions in all three rounds. The rest are census.gov (pop clock: navigation timeouts, no targets), iris.edu (no targets after navigation), openstreetmap.org, esa.int and githubstatus.com (screenshot timeouts or no target in one round).
3. **Part C visit errors.** Round 2 first lost 17 of 93 visits to a burst of browser screenshot failures under load (6 parallel pages). The collector was changed to retry errored visits, and the failures were re-run within the same round with fewer workers. Error records stay in the log. Sites that failed every time are listed in `tables/rs_visits.csv`.
4. **D.2 lost episode.** One episode (8 steps) failed on a Playwright clock error ("Cannot fast-forward to the past") and was not rerun. D.2 has 786 of the 800 planned steps.
5. **A100 start.** The first Colab run started on an A100 runtime left over from the full study. It was stopped within a minute, before any model loaded, and nothing from it is used. All B.2 and re-ground numbers come from the T4.
6. **Part B pair intersections and rubric subsets.** B.1 and B.3 use the pairs that both checks of a pair were run on, as preregistered. The prereg did not say which pairs the B.4 rubric table should use; each checker enters on its own pairs, which for the small models is the stratified subset.
7. **D.2 time-per-step charge.** The prereg charges "3·C for a wrong click" and "one full re-plan C_meas" without fixing C for the first. Both use C_meas = 1.07 s (the planner's own median), so the comparison across recovery types uses one planning cost.
8. **Exploratory rows (not preregistered).** (a) A third form of the inequality with an exposure term on the unchanged branch (A); (b) D.2 recoveries split by whether the target was still hittable; (c) C_min also reported for the pooled "all pages" fits. All are labelled exploratory in the tables.

## Part A. The preflight inequality

Derivation and assumptions: `docs/INEQUALITY.md`. First order: p* = (τ + f) / (r(k − 1) + f), with τ = δ/C.

**A.3 Validation** (`tables/ineq_validation.csv`, `ineq_summary.csv`, `ineq_by_check.csv`). Dev rates predict the test replay's break-even.

| | All 750 cells | 730 cells with observed p* inside (0, 1) |
|---|---|---|
| First order within 0.03 (E1a, bar 80%) | **69.6%** | 68.8% |
| Second order within 0.02 (E1b, bar 80%) | **51.2%** | 49.9% |
| Exploratory exposure term within 0.03 | 76.3% | 75.6% |
| First-order error: median / p90 / max | 0.012 / 0.091 / 0.196 | |

By check (share of cells within 0.03, first order): C2 100%, Haiku 100%, C1 87%, C4r 85%, C4 80%, C5r 79%, C7 75%, C6r 63%, Qwen3-VL 4B 20%, Opus 8%.

Where it fails, and why:
- **Slow checkers (Opus 2.4 s, Qwen 4B 2.4 s).** In the replay, an action is scored against the page at action time. A page that was valid when the check looked can go stale before the click. The first-order form ignores this. The preregistered second-order form models it as lower recall (r·(1 − δ/Δt)), but the replay charges it on the *unchanged* branch. The second-order form is therefore worse than the first (51% vs 70%). Charging it where the replay does (exploratory: + h·k on both sides, with h the dev share of unchanged steps that go stale during the check) lifts C4 to 93% and Opus to 32%.
- **Dev-to-test shift.** Opus's dev rates come from 300 pairs (28 on Tier 0); on Tier 2 its false alarms were 0.037 on dev against 0.123 on test. C7's false alarms were 0.29 on dev against 0.17 on test. No closed form fixes rates that move between splits.
- **Small k and Tier 0.** Agreement is lower at k = 2 (59%) than at k = 10 (79%), and on Tier 0 (56%) than on Tier 2 (80%). A small denominator r(k − 1) + f magnifies rate errors.

Tier 1, C = 6.51 s, k = 2 (predicted from dev → observed on test): C2 0.002 → 0.015; C4 0.133 → 0.117; C7 0.308 → 0.226; Haiku 0.594 → 0.593; Opus 0.491 → 0.569; Qwen 4B 0.636 → 0.736.

**A.4 Budgets** (`tables/ineq_budgets.csv`, `figures/ext_budget.png`). Tier 1 test rates: C4 r 0.818, f 0.042, δ 0.312 s; Opus r 0.827, f 0.124, δ 2.366 s. At C = 6.51 s:
- **C4:** its false-alarm budget f_max covers its own 0.042 from p = 0.10 at k = 2 (f_max 0.038 at p = 0.10 is just short; 0.145 at p = 0.20), and from p = 0.02 at k = 10 (f_max 0.101).
- **Opus:** it does not pay at any p ≤ 0.5 when k = 2 (f_max 0.100 at p = 0.5, below its 0.124), and at k = 10 needs p ≥ 0.10 (f_max 0.42).
- **Check-time budget at k = 10:** δ_max is 2.13 s at p = 0.05 for C4 and 1.66 s for Opus, below Opus's own 2.37 s.

**A.5 H2 supplementary** (`tables/h2_supplementary.csv`; H2 stays **not supported**). The full study charged each re-plan 6.51 s while the live planner (Haiku) took a median of 1.07 s.

| Gap | Added time per step, re-plans at 6.51 s (prereg) | Added time, re-plans at 1.07 s | Net time vs no check, stale = 2 × 1.07 s |
|---|---|---|---|
| 2 s | +105% | +23% | −0.21 s (−6.3%) |
| 6.5 s | +45% | +10% | −0.28 s (−3.6%) |
| 12 s | +28% | +6% | −0.28 s (−2.1%) |

Charged at the planner's real speed and counting what stale clicks cost, the preflight saves time per step at every gap in the live loop.

## Part B. The checker rubric

**B.2 Clean latencies** (`tables/b2_latency.csv`; Tesla T4, fp16, batch 1, 10 warm-ups, 200 timed calls per model, nothing else on the GPU).

| Model | settled/dialog call: median (p90) | worked call: median (p90) | Full study (not clean) |
|---|---|---|---|
| Qwen3-VL 2B | 1,450 ms (1,478) | 1,561 ms (1,687) | 1,683 ms, shared T4 |
| Qwen3-VL 4B | 2,425 ms (2,544) | 2,814 ms (2,883) | 1,135 ms, shared A100 |
| SmolVLM2 2.2B | 2,006 ms (2,084) | 1,814 ms (2,137) | 1,542 ms, shared A100 |
| Florence-2 large (OCR, 2×2 tiles) | – | 4,115 ms (7,016) | 6,847 ms, shared A100 |

These replace the full study's numbers everywhere in this extension; Parts A and B were re-run with them.

**B.1/B.3 Escalation threshold and validation** (`tables/rubric_mstar.csv`, `rubric_validation.csv`, `rubric_summary.csv`, `figures/ext_rubric.png`). E2 counts a cell as agreeing when the rule (dev rates) picks the checker with the lower expected test cost E = δ + q(1 − r)M + (1 − q)fC.

| Question | Cells | Excluded (±20% of M*) | Agreement |
|---|---|---|---|
| all | 14,487 | 283 | **92.7%** (E2 held) |
| settled | 7,182 | 168 | 95.9% |
| worked | 3,808 | 42 | 94.5% |
| dialog | 3,497 | 73 | 84.2% |

Dialog is the weak spot because the pixel dialog detector's dev recall (0.98) fell to 0.72 on test (unseen layouts). Every pair that compares against it inherits the shift. Examples of M* on Tier 1 at q = 0.05, C = 6.51 s (dev, then test):
- settled, C2 → C4: escalate when a miss costs more than 36 s (test 19 s)
- settled, C4 → Opus: 335 s (test 5,431 s)
- settled, C4 → Qwen 4B: never; it has lower recall and more false alarms
- worked, pixel → Qwen 2B: 1,097 s (test 371 s)

**B.4 Cost-optimal operating points** (supplementary; H1 stays as reported; `tables/rubric_cost_optimal.csv`, `rubric_table.csv`). Choosing each scored check's threshold by expected cost instead of the fixed 2% false-alarm bar:
- **Florence-2 OCR on Tier 1 "worked".** The full study scored it 0 recall because one dev false alarm in 39 (2.6%) put every usable threshold over the 2% bar. At the cost-chosen threshold (0.6), it catches 89.2% of failed actions on test with 0 false alarms.
- **The pixel "settled" score.** It moves along its curve as misses get costlier (q = 0.05): recall 0.81 at 4.2% false alarms when M ≤ 30 s, 0.93 at 9.8% when M = 120–300 s.

Rubric table, Tier 1, C = 6.51 s (cheapest by dev cost; full grid in `rubric_table.csv`):
- **settled.** The tuned PUSV-style check when problems are rare and misses cheap. The anchored pixel check once q·M is larger: at q = 0.05 from M = 60 s, at q = 0.20 from M = 10 s. The published PUSV check (re-plan on any change) only at the extreme corner: q = 0.2 with M ≥ 600 s, and q = 0.1 with M = 1,800 s.
- **dialog.** The pixel detector in every cell, by dev cost.
- **worked.** The pixel effect score up to M ≈ 120–600 s depending on q, then Qwen3-VL 2B (cheapest model with 100% recall at 0% false alarms on dev).

The dev pick was also the cheapest on test in 71% of rubric cells overall: settled 88%, worked 88%, dialog 37%. On dialog, a model was cheaper on test because of the pixel detector's dev-to-test drop.

## Part C. When real pages change (read-only)

31 public pages (the 10 from the full study plus 21 approved candidates), each visited in three start conditions over three rounds about two hours apart (09:40, 11:41, 13:41 PDT). Each visit tracked up to 20 visible links and buttons for 30 s. There were 270 successful visits, with 1,330 / 1,241 / 1,278 target tracks for settled / just navigated / just scrolled. Tables: `rs_survival.csv`, `rs_fits.csv`, `rs_e3.csv`, `rs_false_alarms.csv`, `rs_cmin.csv`; figure `ext_hazard.png`. Data never pooled with the benchmark.

**E3 (primary): invalidated at any offset ≤ 2 s.**

| Comparison | Share invalidated | Difference (95% CI, bootstrap over visits) |
|---|---|---|
| just navigated vs settled | 0.174 vs 0.004 | **+0.170 (0.099 to 0.247)**: E3 held |
| just scrolled vs settled (secondary) | 0.010 vs 0.004 | +0.006 (−0.004 to 0.022) |

**Survival S(t)** (share of planned clicks still valid), all pages:

| Seconds after t0 | 0.5 | 1 | 2 | 6.5 | 12 | 30 |
|---|---|---|---|---|---|---|
| settled | 0.997 | 0.997 | 0.996 | 0.997 | 0.997 | 0.996 |
| just navigated | 0.855 | 0.828 | 0.826 | 0.829 | 0.830 | 0.829 |
| just scrolled | 0.996 | 0.996 | 0.990 | 0.990 | 0.990 | 0.990 |

**After a fresh navigation the change is a burst, not a rate.** The page re-lays out as stylesheets, fonts and late content arrive. 14.5% of planned clicks are invalid by 0.5 s, 17% by 1 s, and almost nothing changes after that. The two-phase fit is preferred by AIC in every page kind after navigation: all pages a = 0.17, burst rate β ≈ 17/s, steady rate λ ≈ 0. Share invalid by 2 s after navigation, by kind:
- reference 38%
- front page 25%
- status 22%
- map 14%
- listing 13%
- dashboard 5%

**Settled pages barely move.** About 0.4% of planned clicks were invalid at any offset, and that share did not grow between 0.5 s and 30 s. Constant-hazard λ for settled, all pages: 0.0003/s. Only front pages showed any settled change (1.1–1.4%), from rotating carousels. A scroll behaved like a settled page (1.0% by 2 s), mostly on listings (3.7%). Content links and navigation controls behaved alike (navigated: 18% vs 16%).

**False alarms on real pages** (still-valid tracks flagged, pooled over offsets; by offset in `rs_false_alarms.csv`):
- C2: settled 0.1%, scrolled 1.9%, navigated 3.1%
- C4: settled 0.5%, scrolled 2.6%, navigated 6.3%

Where clicks did go stale after navigation, C4 flagged 949 of 1,485 (64%) and C2 271 (18%).

**C_min** (smallest planning time at which the check pays, gap ≈ C; r and δ from benchmark Tier 1 dev, f from real pages, p(C) from the AIC-preferred fit; exploratory for the pooled rows):

| | C2, k = 2 | C2, k = 10 | C4, k = 2 | C4, k = 10 |
|---|---|---|---|---|
| all pages, settled | 14.2 s | 1.4 s | none ≤ 60 s | 14.2 s |
| all pages, just navigated | 0.5 s | 0.5 s | 3.9 s | 0.5 s |
| all pages, just scrolled | none ≤ 60 s | 0.9 s | none ≤ 60 s | 8.3 s |

On settled pages a check is rarely worth it. On the anchored check at k = 2 it never is: changes are too rare to repay even 0.3 s and 0.5% false alarms. Right after a navigation, both checks pay at almost any planning time, because the burst has already happened by the time a plan comes back. A cheaper alternative there is simply to wait for the page to settle before taking the planning screenshot.

## Part D. The planner

**D.1 Why the planner misses** (`tables/d1_rates.csv`, `d1_e4.csv`, `d1_miss_breakdown.csv`, `figures/ext_planner.png`). Tier 1 test pages, 400 matched steps per condition, Haiku 5.5 planner, no gap events, oracle clicks between steps.

| Condition | Misses (200 ms rule) | Rate (95% CI) | At 0 ms | Planning median / p90 |
|---|---|---|---|---|
| (a) motion on, last three screenshots | 34 | 0.085 (0.061–0.116) | 0.080 | 1,064 / 1,743 ms |
| (b) motion frozen, last three | 34 | 0.085 (0.061–0.116) | 0.082 | 1,057 / 1,861 ms |
| (c) motion on, latest only | 30 | 0.075 (0.053–0.105) | 0.070 | 1,015 / 1,697 ms |

E4 (exact McNemar, Holm): (a) vs (b): 9 vs 9 discordant, p = 1.00. (a) vs (c): 9 vs 5, p = 0.42, Holm 0.85. **E4 refuted.** Neither motion nor history screenshots changed how often the planner missed.

What the misses landed on (a / b / c):

| Class | a | b | c |
|---|---|---|---|
| lookalike | 23 | 25 | 23 |
| no click (planner gave no box) | 7 | 8 | 0 |
| no element | 2 | 0 | 2 |
| neighbour | 1 | 0 | 3 |
| earlier screenshot | 0 | 1 | 0 |
| other | 1 | 0 | 2 |

Two-thirds or more of the misses are **lookalikes**: the task names a label ("Sell", "Buy", initials avatars like "BB") that is unique among the page's *targets* but appears on other, non-target elements. The planner clicks a real "Sell" button, just not the named one. The task-generation rule (unique label among targets) was the same in the full study. D.1 therefore suggests that a large share of the full study's 15–17% planner misses came from ambiguous tasks rather than motion. D.1 had no gap events, so it measures 8.5%, not 15–17%, and does not test the remaining difference. By page: market 19–21%, notes 11–20%, map 1–4%, newsfeed 0–4%, canvas 0%. "Earlier screenshot" explains at most 1 miss per condition. The no-click misses occur only with history (a, b): the planner sometimes replied that several elements matched instead of giving a box.

**D.2 Re-ground vs re-plan** (`tables/d2_recoveries.csv`, `d2_recoveries_by_target.csv`, `d2_e5.csv`, `d2_time_per_step.csv`). 434 steps where C4 fired. Four recoveries on the same frozen screenshot, scored against DOM truth without clicking.

| Recovery | Correct | Wrong (any non-target click) | Gone, correctly | Gone, wrongly | No answer | Median latency | Cost per call |
|---|---|---|---|---|---|---|---|
| Full re-plan (Haiku) | 119 (27.4%) | 259 (59.7%) | 0 | 0 | 56 | 1,251 ms | $0.0003 |
| Re-ground (Haiku) | 85 (19.6%) | 149 (34.3%; CI 30.0–38.9%) | 80 | 1 | 119 | 1,315 ms | $0.0001 |
| Re-ground (Qwen3-VL 4B, T4) | 115 (26.5%) | 242 (55.8%) | 72 | 2 | 3 | 2,092 ms | GPU only |
| Pixel re-aim (C4r) | 76 (17.5%) | 20 (4.6%) | 260 | 78 | 0 | 394 ms | 0 |

**E5 refuted** on both counts. The Haiku re-ground's wrong-click upper bound is 38.9%, against a 3% bar, and its latency is 1.05× a full re-plan, against a 0.5× bar. Here a label-only call to the same hosted model was not faster than a full re-plan.

Supplementary split by target state (`d2_recoveries_by_target.csv`). On 267 of the 434 fired steps the target was not hittable at all: removed, or under a dialog or toast. There every click counts as wrong under the strict rule, and the right move is to deal with the overlay or re-plan.

| Target still hittable (167 steps) | correct | wrong | gone-wrong / no answer |
|---|---|---|---|
| Full re-plan | 119 (71%) | 43 (26%) | 0 / 5 |
| Re-ground Haiku | 85 (51%) | 27 (16%) | 1 / 54 |
| Re-ground Qwen 4B | 115 (69%) | 48 (29%) | 2 / 2 |
| Pixel re-aim | 76 (46%) | 13 (8%) | 78 / 0 |

| Target not hittable (267 steps) | said gone / re-plan | clicked something |
|---|---|---|
| Full re-plan | 0 (cannot say gone) | 216, plus 51 no answer |
| Re-ground Haiku | 80 | 122, plus 65 no answer |
| Re-ground Qwen 4B | 72 | 194 |
| Pixel re-aim | 260 | 7 |

Time per step with executed recoveries (C_meas 1.07 s; wrong click 3·C; gone or no answer adds a re-plan): counting the re-plan without executing it (full-study accounting) gives 9.25 s. Executed recoveries give: pixel re-aim 9.52 s, Haiku re-ground 10.40 s, full re-plan 10.68 s, Qwen re-ground 10.88 s.

## What the extension supports

- **The inequality** (Eq. in `docs/INEQUALITY.md`) is the right shape, and it predicted test break-evens well for fast checks: C2, Haiku and C1 almost always, C4 in 80% of cells. It fell short of its preregistered accuracy overall because slow checkers (Opus, Qwen 4B) let pages go stale while they look. A closed form that charges that exposure where it actually falls does better (exploratory).
- **The rubric** (escalate when q·M > Δδ + (1 − q)·Δf·C) picked the checker that was cheaper on test in 93% of cells. Dialog is the weak spot (84%) because the pixel dialog detector does not transfer from dev to test layouts.
- **Charged at the planner's real speed** (1.07 s, not 6.51 s), the anchored preflight in the live loop saves time per step once stale clicks are counted.
- **Real pages:** settled pages almost never invalidate a planned click (0.4% within 30 s). The danger is right after a navigation, when 17% of planned clicks are invalid within 1 s, all in an early burst. Scrolling did not cause that burst.
- **The planner's misses** on the benchmark pages are mostly ambiguous task labels, not motion or stale history. Freezing motion and dropping history changed nothing measurable.
- **Re-grounding** with a short label-only call was not a safe or fast substitute for re-planning. Most wrong clicks came from targets that were gone or covered, which a pixel re-aim mostly recognised (260 of 267).

## Files

Tables: `ineq_validation.csv`, `ineq_summary.csv`, `ineq_by_check.csv`, `ineq_test_rates.csv`, `ineq_budgets.csv`, `h2_supplementary.csv`, `b2_latency.csv`, `rubric_mstar.csv`, `rubric_validation.csv`, `rubric_summary.csv`, `rubric_cost_optimal.csv`, `rubric_table.csv`, `rs_visits.csv`, `rs_survival.csv`, `rs_fits.csv`, `rs_e3.csv`, `rs_false_alarms.csv`, `rs_cmin.csv`, `d1_rates.csv`, `d1_e4.csv`, `d1_miss_breakdown.csv`, `d1_by_kind.csv`, `d2_recoveries.csv`, `d2_recoveries_by_target.csv`, `d2_e5.csv`, `d2_time_per_step.csv`. Figures: `figures/ext_bar.png`, `ext_budget.png`, `ext_hazard.png`, `ext_rubric.png`, `ext_planner.png`. Code: `harness/ext_*.py`, `live/ext_planner.py`, `realsite/collect_ext.py`, `colab/latency_runner.py`, `colab/make_ext_jobs.py`.
