# Preregistration: "What Does 'Now' Cost?" full study (PreflightBench-Live v1)

Frozen 2026-10-23, before any full-study pair was generated. Tag: `prereg-v1`. Everything after this tag that changes a threshold, prompt, model, metric or hypothesis is a deviation and is reported as one.
The pilot (`results/pilot/`, tags `pilot-prereg-w2`, `pilot-prereg-w3`) is separate: the full study uses fresh page templates (`pages_full/`), fresh seeds (1001 and up), and no pilot pair.

## Scope agreed for this run (2026-10-23)

The author asked for the full study in one day and chose the "core" scope. In: fresh data for all three tiers; pixel, PUSV, anchored and combined checks; Qwen3-VL 2B and 4B, SmolVLM2 and Florence-2 zero-shot; Claude Haiku 5.5 on every test pair; Claude Opus 5.5 on every test pair (Batch API) plus 150 standard calls per hosted model for latency; the live loop with a Claude planner on the Tier 1 browser pages; a separate read-only real-site set.
Deferred (not run, not claimed): LoRA; Moondream and PaliGemma 2; the large open model; Opus inside the planner's context; reference rows from external benchmarks; the live loop on a real remote-desktop session; release v1.0.
Budgets: $100 Anthropic API (meter `results/full/api_spend.jsonl`, enforced in code), at most 60 Colab compute units on a T4 or L4.

## Data

**Templates.** Six page kinds, each with four layout variants (`?v=0..3`, different layout and palette): Tier 0 `tier0_form` (static booking form); Tier 1 `live_market` (tickers, charts, re-sorting table), `live_newsfeed` (items inserted at the top), `live_notes` (a second cursor typing, text reflow), `live_map` (panning map, tile loads), `live_canvas` (canvas drawing app; canvas targets get truth from render state). **Split by template:** variants 0–1 are dev, variants 2–3 are test, so every test layout is unseen.

**Known template properties (recorded before generation).** On `live_canvas`, the board's own motion (collaborator cursor, progressive stroke, decorative shapes, grid scroll) never moves the canvas targets; they move only through seeded events. On `live_notes`, low motion can leave a 200 ms window with no visible change. All six templates pass `generator/check_page.py` (determinism, targets in view and hittable, every event changes the truth, last action wired).

**Action pairs** (questions `settled`, `dialog`; replay; re-aim). Per page kind × variant: 24 `none`, 16 `moved`, 16 `moved_lookalike`, 12 `covered` (toast or popover over the target), 12 `gone`, 50 `dialog` (session timeout, cookie consent, or a dialog styled like the page), 12 `slow_load`. Tier 1 pages run at motion low/med/high (balanced); Tier 0 at none. Background motion near the target, away from it, or none (balanced; a spinner or caret placed 20–60 px from the target or ≥ 300 px away). Timeline as in the pilot: planning frames at 1.0/1.2 s, current frames at 7.5/7.7 s (6.5 s gap), truth at 0, 0.1, 0.25, 0.5, 1, 2, 4, 8, 16 s after the current frame. 25% of pairs get a second event after the current frame.
**Tier 2** (remote-desktop conditions): 1,200 more action pairs on the same kinds and splits, rendered with fresh seeds and degraded: the frames the check sees are delayed by 100–500 ms (truth stays at the real moment), JPEG-compressed (quality 20–60), scaled down by 0.6–0.9 and back, and partly repainted (each 128×128 tile has a 20% chance of coming from a frame 300 ms older).
**Worked pairs** (question `worked`): per page kind × variant 125 pairs, outcomes balanced (success with a clear panel, success with a small change, failure with an error toast, silent failure), plus 600 Tier 2 worked pairs. IDs are opaque (random hex); outcomes live only in `private/`.

**Labels** (from the DOM and render state, never from the event name): `settled` positive when the planned click would not land on the planned target at the current frame (`go_ok` false at offset 0). `dialog` positive when a dialog overlay (`.pf-dialog`) is visible at offset 0. `worked` positive when the last action failed. Re-aim truth: target box in both frames, uniqueness (no identical-signature element in view), and the hit mask.
Expected positives (from the counts above, before generation): `dialog` ≈ 1,200 + Tier 2 ≈ 1,550; `settled` ≥ 1,600; `worked` = 1,800. If any question ends below 1,500 positives after generation, more pairs of that kind are generated with new seeds before any check runs.

## Checks (conditions)

| | Condition | Questions |
|---|---|---|
| C0 | no check | – |
| C1 | PUSV as published (reimplemented from Xu 2026: SSIM < 0.92 on a 160×160 patch, > 0.2% of outside pixels changed by > 20/255; layer 2b omitted) | all (any flag = positive / re-plan) |
| C2 | PUSV-style, thresholds tuned on dev to 2% false alarms | all |
| C4 | anchored, pixels only (motion mask, masked NCC re-find with uniqueness margin, cover check, dialog detector) | settled, dialog; worked by the effect-region pixel check |
| C5 / C6 | C4 + Qwen3-VL 2B / 4B escalation (tie-break and cover questions) | settled, dialog |
| C7 | PUSV + anchored combined: PUSV flags reported as security flags; reliability decision from C4, plus a re-plan whenever PUSV flags and C4's dialog detector fires | settled, dialog |
| M-* | model alone on every question: Qwen3-VL 2B, Qwen3-VL 4B, SmolVLM2 2.2B, Florence-2 (worked only, by reading the effect text with OCR), Haiku 5.5, Opus 5.5 (frontier reference) | settled, dialog, worked |

Model inputs, as in the pilot: a 448×336 crop of the planning frame around the target plus the planned box as text, plus the full current frame; for `worked`, the before frame at 640×400, the after frame and the expected effect. Hosted calls use structured JSON output; Haiku with thinking disabled and max_tokens 100; Opus at effort low with max_tokens 1024 (it cannot disable thinking; pilot outputs reached 211 tokens). Prompts are developed on Haiku on dev and confirmed with 300 Opus dev calls; Qwen/SmolVLM2 prompts are developed on dev only.
Small models run on stratified test subsets (per tier: 600 action pairs, 300 worked pairs; stratified by page kind, event and outcome) because of GPU time; Haiku and Opus run on every test pair; H1 compares on the subset where both were run.

**Tuning on dev (Tier 1 dev unless noted):** C4 thresholds on the pilot grid around the pilot optimum, objective expected seconds per step at p = 0.05 with re-find errors ≤ 1% of re-aims; C5/C6 τ_low and cover band under the same objective and cap (the stricter rule from the pilot's post-hoc check); C2 to 2% false alarms; per question, each check's score threshold at ≤ 2% false alarms on dev (thresholds per tier).

## Metrics

Per question, tier and event type: recall at 2% false alarms (threshold from dev), false-alarm rate on background-motion pairs (`settled` negatives with background motion), re-aim recovery on moved-target pairs, wrong re-aims (shown first in every re-aim table), latency per check including the 200 ms second frame (measured: laptop for pixel checks, T4/L4 for local models, 150 standard API calls for hosted models), cost per 1,000 checks. 95% CIs: bootstrap over templates × seeds (2,000 resamples); Wilson for shares.

**Replay and cost model.** As in the pilot, scored at action time (truth at the first snapshot ≥ δ). Event rates p_gap ∈ {0.01, 0.05} per tier (and 0.20 for continuity with the pilot). Costs: C_plan = 6.51 s; stale action 2 × C_plan; wrong re-aim 3 × C_plan; a successful re-aim costs C_reaim = its check time only. Extended false-alarm budget: a flag costs C_reaim when the re-aim succeeds and C_plan otherwise. Predicted break-even p* against C0 is computed from dev rates; observed from test rates; both reported.

## Hypotheses (frozen)

- **H1.** For each question (settled, dialog, worked) and each tier (0, 1, 2), some check with ≤ 4B parameters (pixel checks, Qwen3-VL 2B/4B, SmolVLM2, Florence-2) is within 2 points of Opus 5.5 on recall at 2% false alarms. Test: one-sided non-inferiority with margin 2 points, paired over the same test pairs, p from a paired bootstrap over templates × seeds (H0: recall_small − recall_frontier ≤ −0.02), α = 0.05, Holm correction over the 9 question × tier tests, using for each test the small check with the best dev recall (chosen on dev, not test).
- **H2.** In the live loop, the recommended preflight cuts stale actions by at least 50% relative to no check, at no more than 10% added time per step, and the upper 95% Wilson bound on wrong re-aims (share of re-aims) is below 10%.
- **H3.** On Tier 1 and Tier 2 test pairs, the combined PUSV + anchored check keeps PUSV's dialog flags (dialog recall within 2 points of C1's) while cutting re-plans on background-motion pairs (`settled` negatives) by at least 50% relative to C1.

## Live loop

Planner rule: a 50-step smoke test with Claude Haiku 5.5 on Tier 0 (`tier0_form`, dev variants); if ≥ 90% of its clicks hit the element it named, Haiku 5.5 is the planner, otherwise Claude Sonnet 5.5. The planner sees 1024×640 screenshots, keeps the last three in context and caches the fixed prefix. Tasks: "click the <target described by its visible label/role>" on Tier 1 test-variant pages. Exact gaps: the page clock pauses while the planner thinks and then advances by exactly the gap (2, 6.5, 12 s). Two conditions: no check, and the recommended preflight (the anchored condition with the lowest dev seconds per step). 6 cells × 400 steps = 2,400 steps. Outcome per step: success, stale, re-aim recovered, wrong re-aim, re-plan (counted and costed, not executed).

## Real-site set (separate, read-only, not released)

Public pages approved by the author, no logins, no personal data, no clicks. For each page: load, choose a DOM target in view, take planning frames, wait 6.5 s, take current frames; truth from the live DOM (target box, elementFromPoint at the planned click). Reported separately: share of `settled` positives, and C1/C2/C4 decisions against DOM truth. Never pooled with the benchmark, never released.

## Reporting

Every number from a logged run (commit, seed, model ID, hardware, date). Refuted hypotheses are findings. PUSV is described as a security defense designed for adversarial change, evaluated here on ordinary moving screens.
