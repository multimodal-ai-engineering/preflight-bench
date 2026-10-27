# Preregistration addendum: extension (the inequality, the checker rubric, real-page timing, the planner)

Frozen 2026-10-24, tag `prereg-ext-v1`, before any extension number was computed. It adds to `docs/PREREGISTRATION.md` (tag `prereg-v1`, unchanged). Nothing here re-scores H1–H3; they stay as reported in `results/full/RESULTS.md`. Every result this addendum produces is labelled "extension" and lives in `results/extension/`. Any later change to a spec below is a deviation and gets its own section in `results/extension/RESULTS_EXT.md`.

**Designed after the full results were seen.** Parts A and B analyse data from the full study. The author and I designed them after reading the full study's results: the observed break-evens, the H1 cells left untestable by the 2% false-alarm bar, and H2's added time. They are therefore not blind analyses. They test whether a closed-form rule, fed only dev numbers, reproduces what test shows. The specs below were written before any extension number was computed. Parts C and D collect new data.

**Budgets.** Anthropic API $15, metered in `results/extension/api_spend.jsonl` (`PREFLIGHT_STUDY=extension` in `models/cost_meter.py`) and enforced in code. Colab 15 compute units, through the Colab MCP server, with every output synced to Drive before any runtime switch. Personal resources only. Real-site work is read-only. Nothing is pushed or made public.

**Notation.** C = planning time per plan (s). δ = check time (s). τ = δ/C. p = chance the planned target changes during the gap. r = recall (share of changed steps the check flags). f = false-alarm rate (share of unchanged steps it flags). k = cost of a stale action in planning rounds. Δt = the gap (s).

## Hypotheses

- **E1. Inequality.** Fed only dev numbers (r, f, δ for each check, from dev), the first-order inequality predicts the test break-even p* within 0.03 in at least 80% of cells (check × tier × C × k). This part is E1a. The second-order version (A.2) predicts it within 0.02 in at least 80% of cells. This part is E1b. E1 holds only if E1a and E1b both hold. Each part is reported separately.
- **E2. Rubric.** With rates from dev, the escalation rule picks the checker that is cheaper on test in at least 90% of grid cells. Cells within ±20% of the predicted threshold M* are excluded.
- **E3. When real pages change.** Within 2 s, the planned click is invalidated more often right after an action than on a settled page. The difference is reported with a 95% CI, which must exclude zero.
- **E4. Planner misses.** The planner misses its named target less often with page motion frozen than with motion on. It also misses less often when it sees only the latest screenshot than when it sees the last three. Each comparison uses an exact paired McNemar test on matched tasks, α = 0.05, Holm-corrected over the two tests. E4 holds only if both comparisons are significant after Holm and both go in the predicted direction. Each is also reported on its own.
- **E5. Re-ground.** Asking the planner (Haiku 5.5) only for the new location of the same element gives a wrong-click rate whose upper 95% Wilson bound is at most 3%. Its median latency must be at most 50% of a full re-plan's, both measured in D.2.

## Part A. The preflight inequality (existing data; no API, no GPU)

**A.1 First-order form.** Per step, with no check: E_0 = p·k·C. With a check: E_1 = δ + p·[r·C + (1 − r)·k·C] + (1 − p)·f·C. The check pays when E_1 < E_0, which gives p* = (τ + f) / (r·(k − 1) + f). The derivation and its assumptions go in `docs/INEQUALITY.md`.

**A.2 Second-order form.** Two assumptions are relaxed.

(i) **Exposure during the check.** A change that happens after the check has looked is missed. Effective recall is r_eff = r·(1 − δ/Δt), with the change time uniform over the gap.

(ii) **Re-aims, at the preregistered costs.** On a changed step, the dev shares of all changed steps are: s_go (not flagged), s_rp (flagged, re-plan), s_ok (re-aim that lands) and s_wr (re-aim that misses). Exposure scales the three flagged shares by (1 − δ/Δt) and moves the lost mass to s_go. On an unchanged step, the dev shares are f_rp (false re-plan) and f_wr (re-aim that misses); a re-aim that lands costs nothing beyond δ.

Costs in units of C are: stale k, re-plan 1, wrong re-aim 3, successful re-aim 0 beyond δ. Then:
- m1 = s_go'·k + s_rp' + 3·s_wr'
- φ = f_rp + 3·f_wr
- p* = (τ + φ) / (k − m1 + φ)

With no re-aims and δ/Δt → 0, this reduces to A.1. For the benchmark replay, Δt = 6.5 s.

**A.3 Validation.**

- **Checks:** pixel conditions C1, C2, C4, C7 and C4r; C5r and C6r on the Qwen dev and test subsets; and models alone as `settled` checkers: Opus 5.5, Haiku 5.5, and Qwen3-VL 4B on its subsets.
- **Grid:** tiers 0, 1, 2; C ∈ {measured Haiku planning median from `results/full/live/loop.jsonl` (median `plan_ms` over all steps), 3, 6.51, 12, 20} s; k ∈ {2, 3, 5, 10, 20}.
- **Dev inputs:**
  - r = share of dev pairs changed at t0 (`relevant`) whose action is not `go`.
  - f = share of unchanged dev pairs whose action is not `go`.
  - The re-aim shares in A.2 also come from dev.
  - δ for pixel conditions = median dev `delta_s`.
  - δ for models = measured median latency: Opus 2.366 s and Haiku 1.276 s (the full study's 150 standard calls each); Qwen3-VL 4B from B.2's clean T4 median. Until B.2 has run, the shared-A100 median of 1.135 s stands in provisionally; those cells are recomputed after B.2.
  - A model's decision is re-plan when it answers "moved". A parse failure counts as re-plan, which matches the native decision (score ≥ 0.5). Models never re-aim.
- **Observed p\* (test replay):** the preregistered replay, scored at action time (truth at the first snapshot at or after δ), with costs generalized to stale k·C, re-plan or false re-plan C, wrong re-aim 3·C, and a successful re-aim 0.
  - Expected cost is E(p) = mean δ + (1 − p)·m0 + p·m1, with E_0 from C0 on the same pairs. Both are linear in p, so the root of E_1 = E_0 is found in closed form.
  - Model checkers are scored the same way: decision at δ, truth at the first snapshot at or after δ.
- **Cell error:** |p*_pred − p*_obs|, with both values clipped to [0, 1]. A value above 1 means the check never pays.
  - **Primary:** the share of all cells within 0.03 (first order) and within 0.02 (second order).
  - **Secondary:** the same shares among cells whose observed p* lies strictly inside (0, 1).
  - Also reported: the full error distribution (median, p90, max) and the table.

**A.4 Budgets** (descriptive; Tier 1 test rates). For C4 and Opus as checker:
- f_max = (p·r·(k − 1) − τ) / (1 − p)
- δ_max = C·[p·r·(k − 1) − (1 − p)·f]

Over p ∈ {0.01, 0.02, 0.05, 0.1, 0.2, 0.5}, k ∈ {2, 5, 10, 20} and C ∈ {1.24, 6.51, 20} s.

**A.5 H2 supplementary** (live loop, `results/full/live/loop.jsonl`; H2 stays "not supported"):
- (a) Added time per step with re-plans charged at the planner's measured median planning time instead of 6.51 s.
- (b) Net time per step including stale actions: mean check time + re-plans per step × C_meas + stale actions per step × 2·C_meas, for no check and the preflight, at each gap.

Both are labelled supplementary.

## Part B. The checker rubric

**B.1 Escalation threshold.**
- **Checks per question:**
  - settled: C1, C2, C4 (pixel), C7, Qwen3-VL 2B, Qwen3-VL 4B, SmolVLM2, Haiku, Opus
  - dialog: pixel dialog detector, C2, Qwen 2B, Qwen 4B, SmolVLM2, Haiku, Opus
  - worked: pixel effect score, Qwen 2B, Qwen 4B, SmolVLM2, Florence-2, Haiku, Opus
- **Rates:** recall and false alarms at each check's native decision, from dev, as in Table 1's supplementary view. The pixel worked score and Florence-2 use the dev threshold at ≤ 2% false alarms.
- **Cost order:** checks are ordered by δ, with ties broken by name.
  - Pixel checks: the median dev `delta_s` of their condition. The dialog detector uses C4's.
  - Pixel worked score: timed on the laptop over 200 dev worked pairs.
  - Haiku 1.276 s, Opus 2.366 s.
  - Qwen 2B, Qwen 4B, SmolVLM2 and Florence-2: B.2 clean T4 medians. Until then the full study's numbers stand in provisionally (Qwen 2B 1.683 s, T4; the others shared A100).
- **Threshold:** for every ordered pair (A cheaper, B costlier), on the pairs where both were run:
  - M* = [(δ_B − δ_A) + (1 − q)·(f_B − f_A)·C] / [q·(r_B − r_A)], at each (q, C) of the B.3 grid.
  - If r_B ≤ r_A: "never escalate". If M* ≤ 0: "always escalate".
  - For settled and dialog, M* is also computed with r_eff = r·(1 − δ/6.5).
  - A pair whose dev intersection has fewer than 10 positives is reported and left out.

**B.2 Clean latencies.**
- **Hardware:** a dedicated Colab T4 runtime with nothing else on the GPU, fp16, batch 1, CUDA-synchronized generate time, the full study's prompts and jobs.
- **Calls:** per model, 10 warm-up calls (not logged), then 200 timed calls.
  - Qwen3-VL 2B, Qwen3-VL 4B and SmolVLM2: 100 action and 100 worked test jobs.
  - Florence-2: 200 worked test jobs.
  - Jobs are drawn stratified by tier and page kind, seed 0.
- **Reported:** median and p90 per model and job kind.

These replace the shared-A100 numbers everywhere in the extension, and every latency-dependent cell is recomputed.

**B.3 Validation.**
- **Expected cost per step on test:** E_X = δ_X + q·(1 − r_X)·M + (1 − q)·f_X·C. Here M is the extra cost of a miss over a catch, in seconds.
- **Grid:** q ∈ {0.01, 0.02, 0.05, 0.10, 0.20}, M ∈ {10, 30, 60, 120, 300, 600, 1800} s, C ∈ {1.24, 6.51} s, per question and tier, for every ordered pair from B.1.
- **Rule:** pick B iff q·M·(r_B − r_A) > (δ_B − δ_A) + (1 − q)·(f_B − f_A)·C, with dev rates. Agreement means the rule's pick has the lower test E_X.
- **E2 denominator:** all cells except those with r_B,dev > r_A,dev and 0.8·M* ≤ M ≤ 1.2·M*.
- **Also reported:** the test-rate M* next to the dev M*, i.e. where the ranking actually flips.

**B.4 Cost-optimal operating points** (supplementary; H1 stays as reported).
- **Checks:** those that output a score: the pixel `settled` score, the pixel `dialog` score, the pixel worked score, and the Florence-2 OCR score.
- **Threshold choice:** at each (q, M, C), choose θ from the dev scores, plus a never-flag and an always-flag option, to minimize the dev E_X. Evaluate it on test.
- **Rubric table:** for each question and Tier 1 (other tiers in the CSV), in each (q, M) cell at C = 6.51 s:
  - the checker with the lowest dev E_X (yes/no checkers at their native decision, scored checks at their cost-optimal θ)
  - whether it is also lowest on test

## Part C. When real pages change (read-only; new data)

**C.1 Sites.**
- The 10 approved pages in `realsite/sites.json`, plus up to 20 that the author approves from `realsite/sites_ext_candidates.json`.
- Each site gets one page kind from: news or front page, status page, dashboard, map, listing or feed, reference or static.
- Excluded: sites whose robots.txt or terms forbid automated access, that need a login, or that show personal data.

**C.2 Design.**
- **Start conditions:**
  - **settled:** network idle (45 s timeout, then go on), then a wait uniform in 2–5 s.
  - **nav**, just acted: fresh navigation, t0 as soon as `domcontentloaded` fires.
  - **scroll**, just acted: settled as above, then `scrollBy(0, innerHeight)`, then t0 at once. Run only if the author approves it.
- **Targets:** at t0, up to 20 visible `a[href]`, `button` or `[role=button]` elements, fully in view and hit at their centre by `elementFromPoint`.
  - Stratified by thirds of the viewport (top, middle, bottom) × type: navigation control (inside `nav`, `header`, `footer`, `[role=navigation]` or a menu, or a button) versus content link (any other `a[href]`).
  - Up to 4 per cell, filled from other cells when a cell is short. Seeded per visit.
  - The planned click is each target's box centre at t0.
- **Offsets after t0:** 0.5, 1, 2, 4, 6.5, 12 and 30 s.
  - At t0 and at each offset: two screenshots 200 ms apart, then DOM truth for every target. Truth: whether `elementFromPoint` at the planned click is the target or inside it (`go_ok`), whether the target still exists, and its centre displacement in px.
  - Actual timestamps are logged. Offsets are nominal.
- **Visits:** at least 3 visits per page per condition, in rounds at least 2 h apart (different times of day), and at least 10 s between loads on any one site.
  - Honest user agent: `preflight-research (read-only; contact via repo)`.
  - Target: at least 30 pages, giving at least 1,800 target tracks per start condition.
- **Data handling:** screenshots and per-track records live under `private/realsite_ext/` (gitignored, never released). Only labels and aggregate statistics leave `private/`. Real pages are never pooled with the benchmark.
- **Check decisions:** at each offset, C2 and C4 (frozen full-study settings; C4 re-plan-only) are scored per target with the t0 pair as the planning frames and the offset pair as the current frames.

**C.3 Analysis.**
- **Survival:** S(t) is the share of planned clicks still valid at t, with Wilson CIs, per page kind × start condition × target type.
- **Fits:** maximum-likelihood binomial fits on track × offset outcomes, compared by AIC.
  - Constant hazard: S(t) = e^(−λt).
  - Two-phase: S(t) = [1 − a·(1 − e^(−βt))]·e^(−λt), with a ∈ [0, 1] and β > λ.
  - λ is reported for both. Tracks are repeated measures, so AIC is treated as approximate.
- **C_min:** for C2 and C4, k ∈ {2, 10}, per page kind × start condition: the smallest C on a 200-point log grid over [0.5, 60] s with p(C) > p*(C).
  - p(C) = 1 − S(C) from the AIC-preferred fit, with the gap ≈ C.
  - p*(C) is first order, with r and δ from benchmark Tier 1 dev, and f from real pages (the share of still-valid tracks flagged, pooled over offsets, per kind × condition).
  - If no such C exists, the result is "none ≤ 60 s". Real-page recall is reported where positives exist; it is not used in p*.
- **False alarms:** C2 and C4 false alarms at each offset, with Wilson CIs.
- **E3 (primary):** the share of target tracks invalidated at any offset ≤ 2 s (0.5, 1 or 2 s), nav minus settled.
  - 95% CI by cluster bootstrap over visits (2,000 resamples). E3 holds if the CI's lower bound is above 0.
  - Scroll minus settled is reported as a secondary comparison if scroll runs.

## Part D. The planner (live loop, Haiku 5.5 planner, `live/` harness; new data)

**D.1 Why the planner misses.**
- **Setup:** Tier 1 test-variant pages, fresh episode seeds from 95001, 50 episodes × 8 tasks = 400 matched steps per condition. Seeded gap events are off.
- **Pages:** each episode loads two copies of the same page (same kind, variant, seed and motion level):
  - Page A runs with motion on.
  - Page B runs with motion frozen: `motion=none` (tickers, insertions, panning and the collaborator cursor stopped), plus injected CSS `*{animation:none!important;transition:none!important}`.
- **Task:** at each step, one target is chosen with the episode's seeded RNG from the ids that are clickable and uniquely labelled on both pages. The same task text goes to three planners:
  - **(a) motion on:** sees page A's screenshot and keeps the last three screenshots, as in the full study.
  - **(b) motion frozen:** sees page B's screenshot, last three.
  - **(c) motion on, latest only:** sees the same page-A screenshot as (a) with no history.
- **Keeping states identical:** after each step, both pages are clicked at the target's true centre (an oracle click), so page states do not depend on any planner's answer. Leftover overlays are dismissed and both clocks advance 6.5 s. A step with no common target is skipped for all three conditions.
- **Planner miss:** as in the full study, the planned click is not on the named element 200 ms after the planning screenshot. The miss at the screenshot moment itself (0 ms) is also logged.
- **E4:** (a) vs (b) and (a) vs (c), exact McNemar on matched steps, Holm over the two tests.
- **Miss classes** (in this order, first match wins), from the DOM state recorded at each screenshot (all target boxes and labels, and the element under the click):
  1. **earlier screenshot:** the click lies in the target's box in one of the two previous screenshots and not in its current box. For (c), computed against the same previous screenshots that (a) saw, as a control.
  2. **neighbour:** the element hit shares a list or row container (`li`, `tr`, `[role=row]`, or the same parent element) with the target.
  3. **lookalike:** the element hit has the same tag and identical visible text, or a text similarity ratio ≥ 0.8.
  4. **no element:** the hit is `html`, `body`, or a container with no text and no target id.
  5. **other.**
- **Also reported:** planner-miss rates with Wilson CIs, and planning time median and p90.

**D.2 Re-ground vs re-plan.**
- **Setup:** 800 steps at a 6.5 s gap, fresh seeds from 97001, the full study's event mix, and C4 frozen in re-plan-only mode, as in the full study's live loop.
- **Recoveries:** on every step where C4 re-plans, the page clock stays paused. Four recoveries are issued on the same current screenshot (`current_b`) and scored against DOM truth at that moment, without clicking:
  1. **Full re-plan:** the planner's normal call (same task, its usual history).
  2. **Re-ground (Haiku):** a new call with only the current screenshot and the text "The element labelled `<label from the plan>` may have moved. Return its box in this screenshot as JSON {"box": [x1, y1, x2, y2]}, or {"gone": true}." max_tokens 60.
  3. **Re-ground (Qwen3-VL 4B):** the same prompt and image, run later on the B.2 T4 if it fits inside the Colab cap. It is scored against a hit map saved at that moment (`__truth` hit mask of the target at a 4 px grid, plus the element under each grid point at 8 px).
  4. **Pixel re-aim:** C4r (the full study's exploratory re-aim setting) on the same four frames.
- **Outcomes:**
  - **correct:** the click is on the target.
  - **wrong:** a returned click not on the target. This is strict, and includes clicks on empty space; clicks on another element are also counted apart.
  - **gone-correct:** answered "gone" (or C4r chose re-plan) and the target has no hittable cell.
  - **gone-wrong:** answered "gone" while the target is hittable.
  - Wilson CIs throughout.
- **E5:** Haiku re-ground. Wrong over all fired steps, upper Wilson bound ≤ 3%, and median latency ≤ 0.5 × the median full re-plan latency.
- **Time per step with executed recoveries**, per recovery type: planning + gap + check, plus on fired steps the recovery latency, plus:
  - 3·C for a wrong click (the preregistered wrong re-aim cost)
  - one full re-plan C_meas when the recovery answers "gone" or gives no click, with C_meas the measured planning median
- **Cost per call** from the meter.

## Outputs

`results/extension/RESULTS_EXT.md`, `TALK_NUMBERS_EXT.md` and `tables/`; `docs/INEQUALITY.md`; `paper/inserts_ext.tex`; and figures `figures/ext_{bar,budget,hazard,rubric,planner}.png`. Each of E1–E5 is marked "held" or "refuted". PUSV (W. Xu 2026, arXiv 2604.18860) is described as a security defense designed for adversarial change wherever it appears.
