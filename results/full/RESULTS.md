# PreflightBench-Live: full study results (2026-10-23/24)

Preregistration: `docs/PREREGISTRATION.md`, tag `prereg-v1` (commit a9d3cb0), frozen before any data was generated. Dev thresholds frozen in commit 1b68ffd before test labels were read. All numbers below come from logged runs; tables are in `results/full/tables/`, raw decisions in `results/full/raw/`, model answers in `results/full/gpu_out/` and `results/full/hosted/`, live-loop steps in `results/full/live/loop.jsonl`. Test labels stay in `private/` (gitignored). Nothing here is public.

PUSV (W. Xu 2026, arXiv 2604.18860) is a security defense designed for adversarial change between screenshot and action. Here its checks (reimplemented from the paper's text) are run on ordinary moving pages, a workload it was not built for. Its "re-plan on any change" behaviour is the intended, conservative choice for its threat model.

## Scope as run

| Item | Preregistered | Run |
|---|---|---|
| Templates | 6 kinds x 4 variants; v0-1 dev, v2-3 test | as planned; all pass `generator/check_page.py` |
| Action pairs | Tier 0/1 per-kind counts + 1,200 Tier 2 | 4,608 (2,316 dev, 2,292 test), 0 generation errors |
| Worked pairs | 125 per template + 600 Tier 2 | 3,600 (1,818 dev, 1,782 test), 0 errors |
| Positives per question | >= 1,500 | settled 3,414; dialog 1,625; worked (last action failed) 1,802 |
| Pixel checks C0, C1, C2, C4, C7 | all test pairs | all test pairs |
| Qwen3-VL 2B / 4B, SmolVLM2, Florence-2 | stratified subsets | 12,478 GPU jobs, 0 errors (subsets: per tier up to 600 action / 300 worked test pairs; Tier 0 test has 284 action pairs) |
| Haiku 5.5 | every test pair | every test pair (Batch API) plus all dev pairs for thresholds |
| Opus 5.5 | every test pair | every test pair (Batch API) plus 300 dev pairs |
| Live loop | 6 cells x 400 steps, Haiku planner | 2,391 steps (one no-check episode at 2 s cut short by a crash: 391 steps) |
| Real-site set | 300-500 read-only pairs, separate | 400 pairs from 10 approved public pages |

Spend: Anthropic API **$25.11** of the $100 cap (Opus batch $21.59, Opus duplicate batch answers $0.59, Opus latency calls $1.38, Haiku batch $0.85, live-loop planner $0.66, other $0.04). Colab: T4 for Qwen 2B, then an A100 (switched to finish the same day); units used: see the Colab dashboard (not logged by the runner).

## Deviations from the preregistration

1. **C4 frozen in re-plan-only mode.** On Tier 1 dev no setting of the C4 grid kept re-find errors at or below 1% of re-aims (lowest 13 of 115 = 11.3%). The preregistration did not say what to do when no setting meets the cap; the only settings that meet it are those with zero re-aims, so C4 was frozen in re-plan-only mode (best dev seconds per step among them). The lowest-error re-aim setting is reported as an exploratory row, **C4r**.
2. **C5 and C6 not frozen.** The same cap left no escalation setting on the 150-pair Tier 1 dev subset (lowest: C5 1 of 10 re-aims, C6 1 of 12). Their lowest-error settings are reported as exploratory rows **C5r** and **C6r**. No preregistered model-escalation condition exists in the test results.
3. **H1 cells where Opus has no 2%-false-alarm operating point.** Opus answers yes/no. Where its dev false-alarm rate is above 2%, no threshold gives it a recall at 2% false alarms, so the preregistered metric scores it 0 and the non-inferiority test in that cell is uninformative. Those cells are marked uninformative, not counted as passes. A supplementary comparison at each check's own decision point is added and labelled as such.
4. **H1 tie-break.** On worked Tier 1, several small checks tied at 100% dev recall; the preregistration has no tie-break rule and the code took the first in its list (Qwen 3-VL 2B).
5. **Live-loop harness fixes before the final run.** Two aborted runs were discarded (kept as `results/full/live/loop_aborted_*.jsonl`): (a) steps where the planner missed the named element before the gap were being scored as stale; they are now `planner_miss`, reported apart; (b) tasks could name elements hidden under a toast or dialog left by an earlier step; tasks now name only elements clickable when the task is issued, and leftover overlays are dismissed between tasks. A zero-size planner box is read as a click on that point. Planner calls got retries after a connection error stopped one run (resumed, completed episodes kept).
6. **GPU.** The preregistration named a T4 or L4. Qwen 2B ran on a T4 (fp16). The T4's 762 Qwen 4B answers were lost when the runtime was switched (not yet synced to Drive), and Qwen 4B, most of SmolVLM2 and all of Florence-2 ran on an A100 (bf16). A100 latencies were measured with several processes sharing the GPU and are not clean latencies; Qwen 2B's first ~800 jobs also shared the T4 with SmolVLM2.
7. **Batch submission.** An overlapping resubmission created one duplicate Opus chunk; it was cancelled after 120 of its requests had finished. Each answer is used once; the duplicate answers' cost ($0.59) is in the ledger.

## Table 1. Questions (test, at each check's own decision point; supplementary view)

Recall and false-alarm rate of each check's own yes/no decision (pixel checks: the decision they logged; Florence-2 and the pixel worked score: dev threshold at <= 2% false alarms). Tier 1 shown; all tiers in `tables/table1_questions.csv`. The preregistered recall at 2% false alarms is in the same file (column `recall`); it is 0 for every yes/no check whose false alarms exceed 2% (`no_2pct_point = True`).

| Question (Tier 1 test) | Check | Recall | False alarms |
|---|---|---|---|
| Target settled? (moved/covered/gone; 1,064 positives) | anchored pixels (C4) | 0.818 | 0.042 |
| | PUSV-style tuned (C2) | 0.235 | 0.003 |
| | PUSV as published (C1) | 1.000 | 1.000 |
| | PUSV + anchored (C7) | 0.827 | 0.166 |
| | Qwen3-VL 2B (subset, 447 positives) | 0.002 | 0.000 |
| | Qwen3-VL 4B (subset) | 0.664 | 0.373 |
| | SmolVLM2 2.2B (subset) | 0.000 | 0.000 |
| | Haiku 5.5 | 0.980 | 0.952 |
| | Opus 5.5 | 0.827 | 0.124 |
| Dialog in the way? (500 positives) | anchored dialog detector | 0.724 | 0.012 |
| | PUSV-style tuned | 0.340 | 0.088 |
| | Qwen3-VL 2B (subset, 205 positives) | 0.922 | 0.149 |
| | Qwen3-VL 4B (subset) | 0.946 | 0.142 |
| | SmolVLM2 2.2B (subset) | 0.161 | 0.000 |
| | Haiku 5.5 | 1.000 | 0.152 |
| | Opus 5.5 | 1.000 | 0.070 |
| Did the last action fail? (620 positives) | pixel effect-region score | 0.895 | 0.000 |
| | Qwen3-VL 2B (subset, 139 positives) | 0.971 | 0.012 |
| | Qwen3-VL 4B (subset) | 1.000 | 0.000 |
| | SmolVLM2 2.2B (subset; 73% of answers not JSON) | 1.000 | 0.596 |
| | Florence-2 OCR match (subset) | 0.000 | 0.000 |
| | Haiku 5.5 | 1.000 | 0.056 |
| | Opus 5.5 | 1.000 | 0.000 |

Model behaviour worth stating plainly: Qwen3-VL 2B and SmolVLM2 answered "same place" on nearly every action pair, so they detect almost no moved targets. Haiku 5.5 answered "moved" on about 95% of pairs, including still-valid ones. SmolVLM2 often answered a bare "True." or "False." instead of the requested JSON; under the preregistered parser those are parse failures. Post hoc (not preregistered), reading a bare true/false as the answer gives recall 0.669 / 0.799 / 0.681 and false alarms 0.000 / 0.124 / 0.043 on Tiers 0 / 1 / 2 (`tables/posthoc_smolvlm2_lenient_worked.csv`).

**False re-plans on background motion** (Tier 1 test `settled` negatives with a spinner or caret near or away from the target; Wilson 95% CI; `tables/bg_motion_false_replans.csv`): C1 242/242 (1.000, 0.984-1.000); C2 1/242 (0.004, 0.001-0.023); C4 11/242 (0.045, 0.026-0.080); C7 42/242 (0.174, 0.131-0.226); Opus 32/242 (0.132, 0.095-0.181); Haiku 232/242 (0.959). Tier 2: C1 0.837, C2 0.000, C4 0.043, C7 0.174, Opus 0.141.

Latency per check (median): pixel anchored 316 ms on the laptop (includes the 200 ms second frame); PUSV layers 4 ms compute (one pre-action screenshot, taken by every condition, not charged); Qwen3-VL 2B 1,683 ms (T4); Haiku 5.5 1,276 ms and Opus 5.5 2,366 ms (150 standard API calls each; p90 2,009 and 4,686 ms). Qwen 4B, SmolVLM2 and Florence-2 ran on a shared A100 (medians 1,135 / 1,542 / 6,847 ms under load; not comparable). Cost per 1,000 checks: Haiku $0.21, Opus $9.19 (standard price, from the latency calls); batch price is half.

## H1. Small checks vs Opus at 2% false alarms

| Question | Tier | Small check (best dev recall) | Small recall | Opus recall | Holm p | Cell |
|---|---|---|---|---|---|---|
| settled | 0 | pixel | 0.907 | 0.000 | 0.00 | uninformative (Opus has no 2% FA point) |
| settled | 1 | pixel | 0.000 | 0.000 | 0.00 | uninformative |
| settled | 2 | pixel | 0.000 | 0.000 | 0.00 | uninformative |
| dialog | 0 | pixel | 0.500 | 0.000 | 0.00 | uninformative |
| dialog | 1 | pixel | 0.724 | 0.000 | 0.00 | uninformative |
| dialog | 2 | pixel | 0.660 | 0.000 | 0.00 | uninformative |
| worked | 0 | pixel | 1.000 | 1.000 | 0.00 | non-inferior |
| worked | 1 | Qwen3-VL 2B | 0.971 | 1.000 | 0.63 | not shown |
| worked | 2 | Qwen3-VL 4B | 1.000 | 1.000 | 0.00 | non-inferior |

**H1 is not supported as stated.** It held in 2 of 9 cells (worked, Tiers 0 and 2), was not shown in 1 (worked, Tier 1: Qwen 2B 0.971 vs Opus 1.000, chosen by the tie-break in deviation 4; Qwen 4B, which tied on dev, had 1.000 on test), and could not be tested in 6 because Opus has no operating point at 2% false alarms for settled and dialog. The anchored pixel `settled` score also has no 2% point on Tiers 1 and 2 (the cover check sets the score to 1 for many still-valid pairs), so its preregistered recall there is 0 even though its decision catches 82%.

Supplementary (not preregistered), at each check's own decision on Tier 1: for `settled`, anchored pixels 0.818 recall at 0.042 false alarms vs Opus 0.827 at 0.124; for `dialog`, the pixel detector 0.724 at 0.012 vs Opus 1.000 at 0.070 (Qwen 4B 0.946 at 0.142); for `worked`, Qwen 4B 1.000 at 0.000, equal to Opus. See `figures/full_fig_B_grid.png`.

## H2. Live loop (Haiku 5.5 planner, Tier 1 test pages)

| Gap | Condition | Steps | Planner misses | Stale / planned hits | Stale rate (95% CI) | Re-plans (needed / not) | Added time per step |
|---|---|---|---|---|---|---|---|
| 2 s | no check | 391 | 16.9% | 211 / 325 | 0.649 (0.596-0.699) | 0 | 0 |
| 2 s | preflight (C4) | 400 | 16.5% | 35 / 329 | 0.106 (0.077-0.144) | 195 (180 / 15) | +105% |
| 6.5 s | no check | 400 | 15.3% | 229 / 334 | 0.686 (0.634-0.733) | 0 | 0 |
| 6.5 s | preflight | 400 | 15.5% | 32 / 333 | 0.096 (0.069-0.133) | 200 (195 / 5) | +45% |
| 12 s | no check | 400 | 15.8% | 233 / 336 | 0.693 (0.642-0.740) | 0 | 0 |
| 12 s | preflight | 400 | 14.8% | 30 / 334 | 0.090 (0.064-0.125) | 211 (206 / 5) | +28% |

Added time per step = (check time + re-plans x 6.51 s) / (mean planning time + gap) of the no-check cell. The preflight made no re-aims (re-plan-only C4), so the wrong re-aim criterion is met trivially.

**H2 is not supported.** The preflight cut stale actions by 84% / 86% / 87% (2 / 6.5 / 12 s), past the 50% bar, but added 105% / 45% / 28% time per step, past the 10% bar. Almost all of that time is re-plans that were needed (the planned click would have missed): the benchmark's event mix makes the planned click stale on about two-thirds of planned hits without a check (0.65-0.69), far more than a typical session, and every needed re-plan costs a full planning call. With 5-15 false re-plans per 400 steps, the time cost scales with how often the page actually changes.

The Haiku planner missed the element it was asked to click on 15-17% of steps on these moving pages (98% hits on the static form in its smoke test); those steps are not stale actions and are excluded from the stale rate.

## H3. PUSV + anchored (C7) vs PUSV as published (C1)

| Tier | Dialog recall C1 | Dialog recall C7 | Background-motion re-plans C1 | C7 | Keeps flags (within 2 pts) | Cuts re-plans >= 50% |
|---|---|---|---|---|---|---|
| 1 | 1.000 | 0.724 | 1.000 | 0.166 | no | yes |
| 2 | 1.000 | 0.660 | 0.856 | 0.171 | no | yes |

**H3 is not supported.** The combined check cut re-plans on background-motion pairs by 83% (Tier 1) and 80% (Tier 2), but its dialog recall (0.724 / 0.660) is not within 2 points of C1's, because C1 flags every changed screen (dialog or not) and C7 keeps only flags its dialog detector confirms.

## Table 2. Replay at action time (test, Tier 1; all tiers in `tables/table2_replay.csv`)

| Condition | Stale /1000 | False re-plans /1000 | Re-aims (wrong; Wilson hi) | Median check | s/step p=0.01 | p=0.05 | p=0.20 | Break-even p* observed (predicted from dev) |
|---|---|---|---|---|---|---|---|---|
| C0 no check | 749 | 0 | 0 | 0 ms | 0.130 | 0.651 | 2.604 | - |
| C1 PUSV as published | 0 | 253 | 0 | 4.5 ms | 6.516 | 6.516 | 6.516 | 0.500 (0.500) |
| C2 PUSV-style tuned | 571 | 0.7 | 0 | 4.5 ms | 0.138 | 0.596 | 2.311 | 0.015 (0.030) |
| C4 anchored, re-plan only | 137 | 10.6 | 0 | 312 ms | 0.740 | 1.034 | 2.134 | 0.117 (0.146) |
| C7 PUSV + anchored | 130 | 41.5 | 0 | 317 ms | 1.542 | 1.801 | 2.771 | 0.226 (0.316) |
| C4r exploratory re-aim | 111 | 9.2 | 122 (28; 0.31) | 312 ms | 0.790 | 1.062 | 2.083 | 0.116 (0.154) |
| C5r exploratory, Qwen 2B (subset) | 145 | 13.3 | 50 (15; 0.44) | 296 ms | 0.800 | 1.090 | 2.177 | 0.126 (0.084) |
| C6r exploratory, Qwen 4B (subset) | 135 | 13.3 | 49 (15; 0.45) | 298 ms | 0.846 | 1.133 | 2.210 | 0.133 (0.089) |

Expected seconds per step under the preregistered cost model (C_plan 6.51 s; stale 2 x C_plan; wrong re-aim 3 x C_plan). At a 5% chance of change during the gap, the tuned PUSV-style check (C2) has the lowest expected time of any condition (0.596 s vs 0.651 s for no check) because it re-plans only on large changes and almost never on still-valid pairs; the anchored check catches far more stale actions but pays a re-plan for each, and breaks even with no check at p* = 0.117 (observed) / 0.146 (predicted from dev). Above that rate it has the lower expected time. Predicted and observed break-evens agree within 0.03 for C1, C2 and C4 on Tier 1.

## Real-site set (separate, read-only, never pooled)

400 pairs from 10 approved public pages (`results/full/realsite/`). After 6.5 s the planned click still landed on 398; the target was gone on 2 (nasa.gov, USGS earthquake map). False re-plans on the 398 still-valid pairs (Wilson 95% CI): C1 82 (0.206, 0.169-0.248); C2 0 (0.000, 0.000-0.010); C4 2 (0.005, 0.001-0.018), both on nasa.gov. Each check caught 1 of the 2 changed pairs. With 2 positives, this set measures false alarms only.

## What the study supports

- On moving pages, the anchored pixel check catches most stale clicks (82% on Tier 1 test at 4.2% false alarms; 84-87% fewer stale actions in the live loop) without a model call, at about 0.3 s.
- Whether that pays for itself depends on how often the page changes during the gap: below about 12% of steps, no check (or the tuned PUSV-style check) costs less time under this cost model; above it, the anchored check costs less.
- Re-aiming is not yet safe: no anchored or model-assisted setting kept wrong re-aims near 1% (best about 8-11%).
- "Did it work?" is the question where a small model matches Opus here: Qwen3-VL 4B scored 1.000 recall on the Tier 0, 1 and 2 subsets (false alarms 0.000 / 0.000 / 0.029), against Opus's 1.000 at 0.000.
- Dialogs: the pixel dialog detector is precise (1.2% false alarms) but misses about a quarter of dialogs; Qwen 4B and Opus find nearly all at 7-14% false alarms.

## Files

`tables/table1_questions.csv`, `tables/h1.csv`, `tables/h2.csv`, `tables/h2_live_cells.csv`, `tables/h3.csv`, `tables/table2_replay.csv`, `tables/table2_replay_dev.csv`, `tables/table3_break_even.csv`, `tables/bg_motion_false_replans.csv`, `tables/escalation_refind_dev.csv`, `tables/posthoc_smolvlm2_lenient_worked.csv`, `realsite/summary.csv`; figures `figures/full_fig_A_stale.png`, `full_fig_B_grid.png`, `full_fig_C_example.png`.
