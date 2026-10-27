# Results: preflight checks on pages that never stop moving. PILOT

All numbers are pilot data from logged runs on 2026-10-22/23. Test split: 620 pairs (480 Tier 1 moving pages, 140 Tier 0 static control), 200 worked pairs. Prereg tags come before each wave's test run: `pilot-prereg-w2` (596e3cb) and `pilot-prereg-w3` (6e04555).
Hardware: pixel checks on an Apple M3 laptop (8 GB); Qwen3-VL 2B/4B on a Google Colab Tesla T4 (fp16); `claude-opus-5-5` and `claude-haiku-5-5` through the Anthropic API.
Cost model: C_plan = 6.51 s (W. Xu 2026), C_stale = 2 × C_plan, C_wrong = 3 × C_plan; expected seconds per step = mean check time + (1 − p) · mean cost on pairs with no relevant change + p · mean cost on pairs with one. CIs: cluster bootstrap over (page, seed), 2,000 resamples; Wilson for shares of re-aims and recall.
Source tables: `results/pilot/tables_test/`. C8 runs on a 300-pair stratified subset (276 Tier 1).

Conditions: C0 no check · C1 whole-screen check, PUSV as published (reimplemented) · C2 whole-screen, tuned · C3 anchored, re-plan only · C4 anchored with re-aim, pixels only · C5/C6 C4 + Qwen3-VL 2B/4B escalation · C7 Qwen3-VL 4B alone · C8 Opus 5.5 alone · C9 Haiku 5.5 alone.

## Q1: what does a pre-action check cost per step?

**Table 1.** Tier 1 test, all motion levels. Per 1,000 steps; seconds and dollars at p = 0.05.

| Cond | False re-plans | Stale actions | …of which page moved during check | Check time median / p95 (ms) | Escalated | s/step (95% CI) | $ per 1,000 steps |
|---|---|---|---|---|---|---|---|
| C0 | 0 | 779 (748–813) | 0 | 0 / 0 | – | 0.65 | 0 |
| C1 | 221 (188–252) | 0 | 0 | 2 / 3 | – | 6.51 (6.51–6.51) | 0 |
| C2 | 10 (2–19) | 292 (254–331) | 0 | 2 / 3 | – | 0.74 (0.52–0.97) | 0 |
| C3 | 8 (2–17) | 244 (194–298) | 2 (0–6) | 240 / 246 | – | 1.02 (0.77–1.35) | 0 |
| C4 | 8 (2–17) | 244 (194–298) | 2 (0–6) | 241 / 246 | – | 1.00 (0.74–1.33) | 0 |
| C5 | 8 (2–17) | 244 (194–298) | 4 (0–10) | 241 / 1,028 | 11% | 1.15 (0.89–1.51) | 0 (T4 time) |
| C6 | 8 (2–17) | 244 (194–298) | 4 (0–10) | 241 / 1,435 | 11% | 1.20 (0.93–1.55) | 0 (T4 time) |
| C7 | 8 (2–17) | 408 (352–465) | 29 (15–44) | 4,441 / 4,504 | – | 10.04 (8.55–11.71) | 0 (T4 time) |
| C8 | 11 (0–24) | 199 (163–231) | 62 (33–95) | 2,337 / 3,887 | – | 4.00 (3.38–4.74) | 8.82 |
| C9 | 25 (15–35) | 313 (279–346) | 21 (8–35) | 1,544 / 2,561 | – | 3.73 (3.16–4.36) | 0.22 |
| oracle | 0 | 0 | 0 | 0 | – | 0.21 (0.20–0.23) | – |
| always re-plan | 221 | 0 | 0 | 0 | – | 6.51 | – |

False-alarm rate (re-plans on the 106 Tier 1 pairs with no relevant change): C1 100%, C2 4.7% (1.1–8.3), C3–C6 3.8% (0.9–7.3), C7 5.7%, C8 3.5% (0–7.7, 85 pairs), C9 12.3% (7.2–17.6) (`false_alarm_tier1.csv`).

By measured motion (s/step at p = 0.05; full table with all rates and CIs in `table1_q1.csv`):

| Cond | static (112) | low (114) | med (215) | high (39) |
|---|---|---|---|---|
| C0 | 0.65 | 0.65 | 0.65 | 0.65 |
| C1 | 6.51 | 6.51 | 6.51 | 6.51 |
| C2 | 0.44 | 0.86 | 0.80 | 0.42 |
| C4 | 0.72 | 0.62 | 1.06 | 2.66 (0.55–8.01) |
| C6 | 0.90 | 0.88 | 1.27 | 2.71 |
| C7 | 10.59 | 10.84 | 9.14 | 14.28 |
| C8 (subset: 53/67/136/20) | 3.92 | 2.76 | 4.36 | 5.36 |
| C9 | 4.02 | 3.31 | 3.79 | 4.37 |

**Answer.** The anchored check takes 241 ms on a laptop (200 ms of it waiting for a second frame) and adds 1.0 s per step at a 5% event rate, against 6.5 s for the whole-screen check as published, which re-plans on every pair because a moving page always differs. Model checks cost 3.7–10.0 s per step, of which look time is 1.7 s (Haiku), 2.5 s (Opus) and 4.1 s (Qwen 4B on a T4) (`cost_ladder_parts.csv`). Slow checks pay a second price: while Opus 5.5 looks (2.3 s median), the page moves the target away in 62 of every 1,000 steps (8% of its go and re-aim clicks); for Qwen 4B alone, 29 per 1,000. At p = 0.05 no check costs less than not checking (0.65 s); the anchored check breaks even with C0 at an event rate of 12% (Table 4).

## Q2: how often can the check re-aim instead of re-planning?

**Table 2.** Tier 1 test. Moved pairs: `correct_action` at offset 0 is re-aim (130; 93 in C8's subset). Relative to C3 on the same pairs.

| Cond | Re-aim recovery (CI) | Re-aims | Wrong re-aims (Wilson CI) | `moved_lookalike`: wrong / re-aims | Re-plans avoided per 1,000 vs C3 | s/step saved vs C3 |
|---|---|---|---|---|---|---|
| C4 | 21% | 29 | 2 = 7% (2–22%) | 0 / 1 | 60 | 0.02 |
| C5 | 28% | 82 | 45 = 55% (44–65%) | 2 / 4 | 171 | −0.14 |
| C6 | 30% | 82 | 43 = 52% (42–63%) | 2 / 4 | 171 | −0.18 |
| C7 | 1% | 90 | 89 = 99% (94–100%) | 18 / 19 | 283 | −9.02 |
| C8 | 54% | 75 | 25 = 33% (24–45%) | 8 / 33 | 210 | −2.89 |
| C9 | 12% | 76 | 60 = 79% (69–87%) | 14 / 16 | 198 | −2.72 |
| oracle | 99% | 130 | 1 (scoring artifact, see note) | 0 / 70 | 37 | 0.80 |

Recovery CIs (cluster bootstrap) are in `table2_q2.csv`. On `moved_lookalike` pairs C4 rarely re-aims: an identical element sits at the old spot and passes the in-place test, so it goes, and 635 per 1,000 of those clicks are stale.

Re-aim trade-off (`fig_reaim_tradeoff.png`, `tradeoff_c4_dev.csv`, `tradeoff_c6_dev.csv`, Tier 1 dev): as the uniqueness margin m falls from 0.3 to 0, C4's recovery rises from 21% to 40% and its wrong share from 7% to 58%. C6 sits at 54–63% wrong at every margin.

**Answer.** Pixels alone re-aimed 21% of moved targets, with 2 of 29 re-aims wrong (upper bound 22%). Re-aiming saves little over re-planning only (0.02 s per step), because most moved targets either have a look-alike or moved during the check. A small-model tie-break did not make re-aiming safer: it re-aimed more (28–30%) but more than half of its re-aims were wrong, and it cost more per step than pixels alone. The frontier model re-aimed best (54%) but a third of its re-aims were wrong and each look takes 2.3 s.

## Q3: which check can tell a failed action from a successful one?

**Table 3.** Worked test set, 200 pairs (100 failed, 100 succeeded). Thresholds frozen on dev at ≤ 2% false alarms. Recall on failures (Wilson CI) and the flag rate per outcome type.

| Check | Recall on failures | False alarms | `failed_error` | `failed_silent` | `success_clear` flagged | `success_small` flagged | Median time |
|---|---|---|---|---|---|---|---|
| Pixel (changed area in the clicked control's region, motion masked) | 0% (0–4%) | 0% | 0% | 0% | 0% | 0% | laptop |
| Qwen3-VL 2B | 89% (81–94%) | 0% | 88% | 90% | 0% | 0% | 1.6 s (T4) |
| Qwen3-VL 4B | 100% (96–100%) | 0% | 100% | 100% | 0% | 0% | 2.8 s (T4) |
| Haiku 5.5 | 100% (96–100%) | 0% | 100% | 100% | 0% | 0% | 1.4 s (API) |
| Opus 5.5 | 100% (96–100%) | 0% | 100% | 100% | 0% | 0% | 2.2 s (API) |

No pixel threshold reached 2% false alarms on dev: the dashboard's small success effect appears outside the clicked control, so those successes look like failures in the region. The frozen pixel threshold therefore flags nothing.

**Answer.** On these pages, reading the expected effect takes a model. Pixels around the clicked control catch none of the failures at 2% false alarms, `failed_silent` included. Qwen3-VL 4B, Haiku 5.5 and Opus 5.5 each caught every failure with no false alarms; Qwen3-VL 2B caught 89%.

## Table 4: sensitivity and break-even

Tier 1 test, seconds per step. Break-even = event rate p at which the condition costs the same as C0.

| Cond | p = 0.01 | p = 0.05 | p = 0.20 | Stale 1× / 2× / 5× (p = 0.05) | Wrong 1× / 2× / 5× (p = 0.05) | Break-even p vs C0 |
|---|---|---|---|---|---|---|
| C0 | 0.13 | 0.65 | 2.60 | 0.33 / 0.65 / 1.63 | 0.65 / 0.65 / 0.65 | – |
| C1 | 6.51 | 6.51 | 6.51 | 6.51 / 6.51 / 6.51 | 6.51 / 6.51 / 6.51 | 0.50 |
| C2 | 0.40 | 0.74 | 2.04 | 0.62 / 0.74 / 1.11 | 0.74 / 0.74 / 0.74 | 0.07 |
| C3 | 0.69 | 1.02 | 2.24 | 0.86 / 1.02 / 1.49 | 1.02 / 1.02 / 1.02 | 0.13 |
| C4 | 0.69 | 1.00 | 2.16 | 0.84 / 1.00 / 1.48 | 0.99 / 1.00 / 1.00 | 0.12 |
| C5 | 0.79 | 1.15 | 2.52 | 0.99 / 1.15 / 1.63 | 1.08 / 1.11 / 1.23 | 0.18 |
| C6 | 0.84 | 1.20 | 2.54 | 1.04 / 1.20 / 1.68 | 1.12 / 1.16 / 1.27 | 0.19 |
| C7 | 9.78 | 10.04 | 11.01 | 9.24 / 10.04 / 12.45 | 7.47 / 8.76 / 12.61 | none in [0, 1] |
| C8 | 3.72 | 4.00 | 5.06 | 3.48 / 4.00 / 5.56 | 3.92 / 3.96 / 4.09 | 0.61 |
| C9 | 3.37 | 3.73 | 5.12 | 3.32 / 3.73 / 4.99 | 3.51 / 3.62 / 3.95 | 0.86 |

The ordering C2 < C4 < C5 < C6 < C9 < C8 < C7 holds in every column except p = 0.20, where C8 (5.06 s) and C9 (5.12 s) swap. C2 is cheaper than C4 in every column although it lets through more stale actions (292 vs 244 per 1,000); its check takes 2 ms instead of 241 ms, and the check-time difference alone is 0.24 s per step (`cost_ladder_parts.csv`).

## Robustness

- **Leave one page out** (`lopo_test.csv`). Re-tuning C4 on dev without one page and scoring that page on test moves seconds per step by at most 0.01 s (live_dashboard 1.234 → 1.234, live_doc 0.570 → 0.563, live_feed 1.604 → 1.613, live_news 0.799 → 0.803). C6's escalation settings re-tune to the frozen values for every held-out page.
- **Parse failures**: 0 of 620 pairs for C5, C6, C7 and C9, and 0 of 300 for C8; no missing model answers (`parse_rates.csv`). Dev prompt development fixed three format problems before the freeze (prose instead of JSON, mixed box units, unlabelled tie-break images; `docs/PREREG_PILOT_W3.md`).
- **Tier 0 control** (`tier0.csv`): false re-plans on the static page C1 33%, C2 14%, C3–C6 17%, C7 0%, C8 0% (24 pairs), C9 10%.

## Predictions

| | Prediction (frozen before test) | Result | |
|---|---|---|---|
| P1 | C4 adds less than half of C1's s/step at p = 0.05 | 1.00 vs 6.51 s | **held** |
| P2 | C4 re-aims ≥ 70% of moved targets; wrong re-aims upper bound ≤ 3% | 21%; 7%, upper bound 22% | **refuted** |
| P3 | Tier 0: C1 and C4 within 2 points on false re-plans | 33% vs 17% | **refuted** |
| P4 | Tier 1 high motion: C8 more stale actions per 1,000 than C4 | 200 vs 154 (20 and 39 pairs; CIs overlap; on C8's 20 pairs C4 also has 200) | **held**, narrowly |
| P5 | C6 fewer wrong re-aims than C4 on `moved_lookalike`, ≤ 300 ms added | 2 of 4 vs 0 of 1; +140 ms | **refuted** |
| P6 | Pixels ≤ half the failures at 2% false alarms; Qwen 4B within 10 points of the frontier | 0%; 100% vs 100% | **held** |

## Spend

API: $5.93 of the $25 cap (`results/pilot/api_spend.jsonl`): C8 test $2.65, Q3 Opus test $1.67, C9 and Q3 Haiku test $0.18, dev prompt work and confirmation $1.44. Colab: about 6 compute units on a T4 (about 1.07 units per hour), including one lost run.

Known scoring artifact (frozen metric): one Tier 1 oracle re-aim scores as wrong because the target extends past the bottom of the 800 px viewport (`live_news-low-moved-s09`).

---

# Post-hoc checks (not preregistered)

Requested after the preregistered results were reported, run 2026-10-23 after commit 9c1674c. Nothing above this line changed. Code: `harness/posthoc.py`, `generator/effect_boxes.py`; outputs in `results/pilot/posthoc/`. New spend: $1.71 API (hosted Q3 rerun), about 0.6 Colab compute units (T4).

**Before and after**

| Check | Preregistered | Post-hoc |
|---|---|---|
| Model inputs carrying a worked ID or the outcome | not audited | none found (see 1) |
| Q3 recall on failures, Qwen 2B / Qwen 4B / Haiku / Opus | 89% / 100% / 100% / 100% | same, with opaque IDs and shuffled order; 200 of 200 answers identical for each model |
| Q3 pixel baseline, recall at 2% false alarms (test) | 0% (CI 0–4%), region = clicked control | 90% (CI 83–95%), 0% false alarms, region = where the expected effect appears |
| P3 | refuted | refuted in C4's favour: C4 17% vs C1 33% false re-plans on the static page |
| Tier 1 `none` pairs whose correct action at offset 0 is not go | not reported | 25% on test (CI 17–35%); live_feed 71% |
| C5 / C6 tuning rule | no re-find cap: τ_low 0.95, cover band 0 | Wave 2 cap: tie-break off, cover band 0.1 |
| C5 / C6 s/step at p = 0.05 (test) | 1.15 / 1.20 | 1.01 / 1.01 (C4 1.00) |
| C5 / C6 wrong re-aims (test) | 45 of 82 / 43 of 82 | 2 of 29 / 2 of 29 (same re-aims as C4) |

## 1. Did any model input reveal a worked-pair ID or the outcome?

No.
- **Prompts and image labels**: none of the Qwen job prompts or labels (dev and test worked, test locate, test escalation) contains a worked or pair ID, a page name, a seed, or the words failed, success, silent or error. Hosted prompts are built from the same templates.
- **File names**: never sent. The Qwen runner opens each image and passes the in-memory image; hosted calls send base64 images and the prompt text only (`models/frontier.content`). The job ID is used only to log the answer.
- **Image metadata**: no PNG text chunks in any image given to a model (500 checked).
- **Expected-effect sentence**: it names the success the planner expected, not the outcome. Each sentence type appears for both successes and failures on test: the panel sentence for 50 clear successes and 58 failures, the small-effect sentences for 50 small successes and 42 failures.
- **Caveat**: the worked IDs and the frame file names on disk do contain the outcome type (a Wave 1 naming choice), so a model that could read file names would see it. None did.

**Rerun.** Q3 test with opaque random IDs (map kept in `private/`), opaque image file names and shuffled order: Qwen 2B and 4B on a Colab T4, Haiku 5.5 and Opus 5.5 through the API (Opus rerun cost $1.67). Every model gave the same answer as in the preregistered run on all 200 pairs, so recall, false alarms and per-outcome rates are unchanged (`q3_opaque.csv`).

## 2. Pixel Q3 over the region where the expected effect appears

Same pixel score as before (changed fraction, > 20 gray levels, background motion masked, 24 px padding), but the region is where the expected effect appears instead of the clicked control. The region follows from the expected-effect sentence and the page layout before the click, both known to the planner: the confirmation panel's rectangle (placed by the page script relative to the button), the dashboard's "Updated" label, or the button itself (`data/pilot/worked_effect_boxes.json`). Threshold set on dev at ≤ 2% false alarms (θ = 0.988), then applied to test.

| Split | Recall on failures (Wilson CI) | False alarms | `failed_error` flagged | `failed_silent` flagged | `success_clear` flagged | `success_small` flagged |
|---|---|---|---|---|---|---|
| dev | 90% (79–96%) | 0% | 92% | 88% | 0% | 0% |
| test | 90% (83–95%) | 0% | 92% | 88% | 0% | 0% |

With the right region, pixels catch most failures. The preregistered 0% came from the region choice, not from pixels as such. The models still catch more (100% for Qwen 4B, Haiku and Opus), and the pixel region needs to know where the effect will appear, which a planner states only in words.

## 3. P3: which direction it failed, and C4's false re-plans on Tier 0

P3 predicted C1 and C4 within 2 points on the static page. C4 re-planned *less*: 17% of pairs where the click was still good, against C1's 33%. So C4 is not the worse check on a still page, but its false re-plans there are not zero, and they do not come from motion.

All 7 Tier 0 test pairs where C4 re-planned and go was correct at offset 0 (`tier0_c4_false_replans.csv`):

| Pair | Seeded event | C4 reason | In-place NCC (τ_in 0.5) | Best search peak (τ_match 0.85), shift | Target's true shift (px) |
|---|---|---|---|---|---|
| tier0_booking-none-moved-s13 | moved | weak_match | 0.025 | 0.529 at (−791, 12) | (10.1, −10.5) |
| tier0_booking-none-moved-s17 | moved | weak_match | 0.023 | 0.485 at (−856, 12) | (9.4, −10.5) |
| tier0_booking-none-moved-s21 | moved | weak_match | 0.026 | 0.545 at (−786, 12) | (9.1, −10.5) |
| tier0_booking-none-moved-s28 | moved | weak_match | 0.043 | 0.534 at (−780, 12) | (7.8, −10.5) |
| tier0_booking-none-moved-s30 | moved | weak_match | 0.024 | 0.538 at (−787, 12) | (9.3, −10.5) |
| tier0_booking-none-moved-s35 | moved | weak_match | 0.058 | 0.529 at (−777, 12) | (7.1, −10.5) |
| tier0_booking-none-moved-s38 | moved | weak_match | 0.027 | 0.532 at (−783, 12) | (8.5, −10.5) |

Reason for each: the seeded move shifted the target by 7–10 px right and 10.5 px up, small enough that the planned click still landed (go correct), but outside the ±3 px in-place window, so the in-place score fell to about 0.03. The search then did not find the shifted target: its best peak, 0.49–0.55 and 777–856 px to the left, was below τ_match, so C4 re-planned (`weak_match`). The search missing a 10–14 px shift on a static page is a defect to look at before the full study.

## 4. Tier 1 `none` pairs whose correct action at offset 0 is not go

`none` means no event was seeded; the page still moves on its own. Wilson 95% CIs (`none_not_go_share.csv`).

| Page | Test: not go / n | Share (CI) | All splits: not go / n | Share (CI) | of which re-aim / re-plan (all) |
|---|---|---|---|---|---|
| live_dashboard | 1 / 24 | 4% (1–20%) | 3 / 36 | 8% (3–22%) | 3 / 0 |
| live_doc | 6 / 24 | 25% (12–45%) | 7 / 36 | 19% (10–35%) | 6 / 1 |
| live_feed | 17 / 24 | 71% (51–85%) | 24 / 36 | 67% (50–80%) | 5 / 19 |
| live_news | 0 / 24 | 0% (0–14%) | 0 / 36 | 0% (0–10%) | 0 / 0 |
| all pages | 24 / 96 | 25% (17–35%) | 34 / 144 | 24% (17–31%) | 14 / 20 |

On the feed, the page's own motion (new posts pushing content down) moves or covers the target in two of three `none` pairs. "No event" does not mean "no relevant change" on these pages; the cost model already treats a pair as relevant by `go_ok` at offset 0, not by the seeded event.

## 5. C5 and C6 with Wave 2's 1% re-find-error cap

Retuned on Tier 1 dev with Wave 2's `objective()` (expected s/step at p = 0.05, infeasible if re-find errors exceed 1% of re-aims), over the same grid plus τ_low = 1.01 (tie-break never fires), excluding settings that never escalate. No setting with tie-breaks is feasible on dev. The best feasible setting for both C5 and C6 is **tie-break off, cover band 0.1** (dev 0.728 s for both; C4 0.616 s) (`cap_tuning_dev.csv`, `frozen_cap.json`). The test run had not asked 10 of the cover questions this setting needs for each model size; they were run on the T4 with the opaque Q3 rerun.

| Tier 1 test | C4 | C5 prereg | C5 capped | C6 prereg | C6 capped |
|---|---|---|---|---|---|
| s/step, p = 0.05 | 1.00 | 1.15 | 1.01 | 1.20 | 1.01 |
| escalated | 0% | 11% | 1.3% | 11% | 1.3% |
| re-aim recovery | 21% | 28% | 21% | 30% | 21% |
| wrong re-aims | 2 / 29 | 45 / 82 | 2 / 29 | 43 / 82 | 2 / 29 |
| `moved_lookalike` wrong / re-aims | 0 / 1 | 2 / 4 | 0 / 1 | 2 / 4 | 0 / 1 |
| mean check time (ms) | 241 | 331 | 252 | 381 | 253 |

Under the cap, the small model only answers cover questions; it re-aims exactly where C4 does and adds about 11 ms per step on average. P5 ("C6 has fewer wrong re-aims than C4 on look-alikes") stays refuted under either rule: capped C6 ties C4 (0 of 1).
