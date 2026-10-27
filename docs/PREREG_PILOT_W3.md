# Pre-registration, Wave 3 (models) and Q3 thresholds. PILOT

Frozen 2026-10-23, before any model saw the test split. Qwen hardware for all reported model numbers: Colab Tesla T4. Tag: `pilot-prereg-w3`.
Wave 2 thresholds (`results/pilot/frozen_w2.json`) stay fixed. Wave 3 settings: `results/pilot/frozen_w3.json`.
Code: `harness/run_models.py` (replays logged answers), `models/hosted_locate.py`, `models/qwen_jobs.py`, `colab/qwen_runner.py`, `anchored/check.py`.
All data are pilot data.

## Models and hardware

| Model | ID | Where | Settings |
|---|---|---|---|
| Qwen3-VL 2B | `Qwen/Qwen3-VL-2B-Instruct` (snapshot 8964489) | Colab, Tesla T4, fp16, transformers 5.20.2 | greedy, max 32 new tokens (escalation, worked) |
| Qwen3-VL 4B | `Qwen/Qwen3-VL-4B-Instruct` (snapshot ebb281e) | same | greedy, max 64 (locate) or 32 new tokens |
| Claude Opus 5.5 | `claude-opus-5-5` (models endpoint, 2026-10-22) | Anthropic API from the laptop | structured output, effort `low`, max_tokens 1024 |
| Claude Haiku 5.5 | `claude-haiku-5-5` (models endpoint, 2026-10-22) | Anthropic API from the laptop | structured output, thinking disabled, max_tokens 100 |

No L4 was assigned, so Qwen ran on a T4. Qwen latencies are T4 generate times (CUDA-synchronized); hosted latencies are API wall times from the laptop; pixel-check times are laptop times.

## Conditions

- **C4** as frozen in Wave 2 (reference).
- **C5 / C6, anchored + Qwen3-VL 2B / 4B escalation.** C4's rule, plus:
  - Ambiguous re-find: when `best ≥ τ_low` and (`best < τ_match` or margin `< m_unique`), ask the tie-break question with the planned context patch and the top three search peaks scoring at least `cand_min` = 0.5. A choice re-aims to that candidate; `null` or a parse failure re-plans.
  - Uncertain cover: when target NCC, brightness shift or outside drop is within `cover_band` × (its threshold scale) of its threshold, ask the cover question with the planned target crop and the current crop at that spot. `covered: false` keeps the spot; anything else re-plans.
  - δ = laptop pixel time + 200 ms frame wait + the sum of the escalation calls' T4 generate times.
- **C7, Qwen3-VL 4B alone**, on every pair. **C8, Opus 5.5 alone**, on a 300-pair test subset stratified by page, motion and `correct_action` (round-robin over strata, seed 0). **C9, Haiku 5.5 alone**, on every test pair. Decision rule for C7–C9: present, IoU > 0.5 with the planned box and not covered → go; present elsewhere and not covered → re-aim to the box center; otherwise re-plan. A parse failure re-plans.

## Prompts (frozen; files in `models/prompts/`)

- `locate_qwen.txt` (C7), `locate_claude.txt` (C8, C9), `tiebreak.txt`, `cover.txt`, `worked.txt`.
- Hosted prompt development on Tier 1 + Tier 0 dev with Haiku 5.5, logged in `results/pilot/hosted_out/`:
  1. `locate_claude` without structured output: 75% of 20 outputs were prose that ran past max_tokens (parse failures).
  2. `locate_claude` with structured output (JSON schema): 0% parse failures on 300 dev pairs. **Chosen.**
  3. `locate_claude_v2` (adds "the target may have moved; do not assume its earlier position"): Tier 1 dev 4.02 s/step vs 3.32 s for round 2. Not used.
- Qwen locate (C7) prompt development on dev, 4B on Colab (`results/pilot/qwen_out/`):
  1. `locate_qwen_v1_pixels.txt` gave the earlier box in pixels and asked for a 0–1000 relative answer. On the 58 dev pairs with no event, 24 boxes matched the target in pixels, 6 in relative units and 28 neither; 189 of 191 re-aims were wrong. Not used.
  2. `locate_qwen.txt` (v2) gives the earlier box in 0–1000 relative units and asks for the same units back. **Chosen** (dev results below).
- Opus 5.5 confirmation on 50 stratified dev pairs: 0 parse failures, every call `end_turn`, output 36 tokens on average, 211 at most.

## Escalation tuning (Tier 1 dev, 240 pairs) and frozen values

- Grid: `τ_low` ∈ {0.5, 0.6, 0.7, 0.8, 0.85, 0.9, 0.95} × `cover_band` ∈ {0, 0.1, 0.25, 0.5, 0.75} (`results/pilot/tuning_w3_escalate.csv`).
- Objective: expected seconds per step at p = 0.05, model time included (the prompt's C5/C6 rule).
- **Frozen: C5 and C6 both `τ_low` = 0.95, `cover_band` = 0, `cand_min` = 0.5** (`results/pilot/frozen_w3.json`). Dev objective: C5 0.810 s, C6 0.878 s; C4 0.616 s.
- The optimum is the grid edge with the least escalation. Above 0.95 nothing escalates and C5/C6 reduce to C4, so on dev every escalation setting costs more than C4. C5/C6 are defined to escalate, so the grid optimum is frozen and tested as is.
- Tie-break prompt development: v1 (`tiebreak_v1_unlabelled.txt`, images with no labels) — Qwen 4B answered "2" on nearly every two- and three-candidate question, apparently counting the reference image; 2B answered "1" on nearly all. v2 (`tiebreak.txt`) puts a text label ("Reference", "Candidate 1" …) before each image. 4B's choices then vary; 2B still answers "1" on 214 of 226 multi-candidate questions. **v2 chosen.** Cover questions were not changed.
- Test escalation jobs: only the questions the frozen rule can ask (`models/qwen_jobs.needed_escalate`; for a tie-break, the cover questions every possible choice could trigger). On dev this subset (64 of 2,966 jobs) reproduces every C5 and C6 decision.

Dev values with frozen settings (Tier 1, s/step at p = 0.05): C4 0.616, C5 0.810, C6 0.878, C7 9.08, C8 (50-pair subset) 2.99, C9 3.32 (`results/pilot/w3_dev_summary.csv`).

## Q3 (did it work), frozen in `results/pilot/frozen_q3.json`

- Pixel check: changed fraction (|before − after| > 20 gray levels) inside the clicked control's box padded by 24 px, over pixels outside the background-motion mask (union of |before − before_b| and |after − after_b|, C4 mask settings). The `_b` frames are 200 ms later, re-rendered with the deterministic clock; all 300 reproduce the existing frames byte for byte (`generator/make_worked_extra.py`).
- Model checks: failure score = 1 if the answer is `happened: false`, else 0; parse failure = 0.5. Confidence is logged but not used: on dev, Qwen reports it as P(happened) while Claude reports certainty in its own answer.
- Threshold per check: smallest θ with dev false alarms (successes flagged) ≤ 2%. No pixel threshold reaches 2% on dev: the dashboard's small success effect ("Updated: just now") falls outside the clicked control, so 10% of dev successes show no change in the region, the same as failures. Pixel θ = ∞ (flags nothing).

## Deviations from the prompt

- **No re-find-error cap for C5/C6 tuning.** Wave 2 tuned C4 under a cap on re-find errors (1% of re-aims). The prompt's C5/C6 rule is only "minimize expected seconds per step"; wrong re-aims are already charged at C_wrong. On dev no escalation setting meets the cap (tie-breaks pick look-alikes on gone and covered pairs), so the cap is reported per setting (`cap_ok`) and not applied.
- **Opus max_tokens 1024, not 100.** Opus 5.5 cannot turn thinking off; at effort `low` its dev outputs reached 211 tokens, so a 100-token cap would truncate answers. Haiku keeps 100.
- **Structured output for hosted calls.** Without it Haiku answered in prose despite "JSON only".
- **Qwen on a Colab T4 in fp16**, not mlx-vlm on the laptop (the laptop swapped; the 4B model's latency would not have been measurable).
- **Tie-break candidates use a fixed floor (0.5)** rather than `τ_low`, so the logged answers stay valid while `τ_low` is tuned.

## Predictions (frozen)

- **P4 (slow checks):** on Tier 1 at high motion, C8 has more stale actions per 1,000 steps than C4.
- **P5 (tie-breaking):** C6 has fewer wrong re-aims than C4 on `moved_lookalike` pairs, adding at most 300 ms per step on average.
- **P6 (Q3):** at a 2% false-alarm rate, pixels catch at most half the failures, and Qwen3-VL 4B lands within 10 points of the frontier model on failure recall.

## Test procedure

1. Pack test jobs (`python -m models.qwen_jobs pack test locate,worked,escalate`), run them on Colab.
2. Hosted: `python -m models.hosted_locate run claude-opus-5-5 test --n 300`, `run claude-haiku-5-5 test`, `worked` for both models.
3. `python -m harness.run_models test`, then `TALK_NUMBERS.md` v2. No threshold or prompt changes after this tag.
