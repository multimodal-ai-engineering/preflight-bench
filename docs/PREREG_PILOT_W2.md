# Pre-registration, Wave 2 (pixel checks). PILOT

Frozen 2026-10-22, before any Wave 2 check touched the test split. Tag: `pilot-prereg-w2`.
Thresholds: `results/pilot/frozen_w2.json`. Code: `anchored/check.py`, `anchored/whole_screen.py`, `harness/run_checks.py`, `harness/metrics.py`.
All data are pilot data. Tuning hardware: Apple M3, 8 GB unified memory, macOS (Darwin 25.5.0). Pixel checks run on this laptop only.

## Conditions and frozen thresholds

| Cond | What | Frozen settings |
|---|---|---|
| C0 | no check, always go | none, δ = 0 |
| C1 | whole-screen check, PUSV as published (reimplemented) | SSIM < 0.92 on 160×160 patch, or > 0.2% of outside pixels differ by > 20/255 → re-plan |
| C2 | whole-screen check, tuned | ssim_min = 0.8727, frac_max = 0.10822, diff 20/255 |
| C3 | anchored, re-plan only | mask_thr 12, mask_dilate 3, τ_in 0.50, τ_target 0.70, b 6.0, d 50.0 (τ_match, m_unique unused) |
| C4 | anchored with re-aim, pixels only | mask_thr 12, mask_dilate 3, τ_in 0.50, τ_match 0.85, m_unique 0.15, τ_target 0.70, b 6.0, d 25.0 |
| oracle | `correct_action` at offset 0, δ = 0 | reference |
| always re-plan | δ = 0 | reference |

Check time δ: measured compute time per pair on the laptop; anchored modes (C3, C4) add the 200 ms frame wait. C1/C2 take one pre-action frame, as every condition does, so no wait is charged (see `docs/THIRD_PARTY.md`).

## Tuning (done on Tier 1 dev, 240 pairs)

- Objective: expected seconds per step at p = 0.05 (cost model below).
- C3 and C4 grid: mask (thr, dilate) ∈ {(8,9),(12,9),(20,9),(12,5),(12,15)}, τ_in, τ_match, m_unique, τ_target, b, d (full grid in `results/pilot/tuning_w2_anchored.csv`). The winning values sat on grid edges (τ_in, b, mask dilation), so the grid was extended twice past those edges (`tuning_w2_anchored_ext.csv`, `_ext2.csv`). Final τ_in = 0.50 is interior. C3 was tuned separately from C4.
- C2: every observed (ssim, frac) pair as candidate thresholds, constrained to ≤ 2% false alarms on Tier 1 dev pairs with no relevant change; minimize seconds per step at p = 0.05 (`tuning_w2_c2.csv`).
- Dev objective values (s/step at p = 0.05): C2 0.432, C3 0.642, C4 0.617; C0 is 0.651.
- m_unique trade-off curve on dev: `results/pilot/tradeoff_c4_dev.csv`.

### Deviation from the prompt (recorded before test)

The prompt's tuning constraint was "wrong re-aims at or below 1% of re-aims on dev". Dev has only 13–60 re-aims per config, and one dev pair (`live_news-med-moved-s01`) is re-aimed correctly at offset 0 but the ticker moves the target during the ~240 ms check. That single pair made **every** config with any re-aim infeasible. The constraint was therefore applied to **re-find errors**: wrong re-aims that already miss at offset 0. Wrong re-aims caused by movement during the check are still counted in every reported metric, in Table 2, and in P2's upper bound.

## Cost model and constants

- C_plan = 6.51 s (W. Xu 2026, arXiv 2604.18860). C_stale = 2 × C_plan, C_wrong = 3 × C_plan (sensitivity 1×, 2×, 5×).
- Expected seconds per step = mean δ + (1 − p) · mean cost over pairs with no relevant change + p · mean cost over pairs with one. A pair has a relevant change when `go_ok` is false at offset 0. p ∈ {0.01, 0.05, 0.20}.
- "Seconds added per step" = this expected value (a successful step costs 0 beyond the check).

## Metrics (definitions)

- Each decision is scored against the first truth snapshot at or after δ.
- **False alarm rate** = share of pairs with no relevant change on which the check re-plans.
- **False re-plans per 1,000 steps** = re-plans where `go_ok` is true in the scored snapshot.
- **Stale actions per 1,000** = go decisions where `go_ok` is false in the scored snapshot; "during the check" = `go_ok` was true at offset 0.
- **Re-aim recovery** = among pairs whose `correct_action` at offset 0 is `reaim` ("moved pairs"), the share where the check re-aimed and landed on a hit cell (±2 px of a 4 px grid point) in the scored snapshot.
- **Wrong re-aims** = re-aims that do not land on a hit cell; reported as a share of re-aims, Wilson 95% interval.
- Motion bins from measured `motion_200ms`: static ≤ 1e-4, low ≤ 0.003, med ≤ 0.008, high above.
- CIs: cluster bootstrap over (page, seed), 2,000 resamples; Wilson for rates near zero.

## Predictions (frozen)

- **P1:** on Tier 1 test, C4 adds less than half of C1's seconds per step at p = 0.05.
- **P2:** on Tier 1 test, C4 re-aims at least 70% of moved targets, and the upper 95% Wilson bound on wrong re-aims (share of re-aims) is at most 3%.
- **P3:** on Tier 0 test, C1 and C4 are within 2 percentage points on false re-plans (false alarm rate), so any Tier 1 difference comes from motion.

Dev already suggests P2's recovery part will not hold (C4 re-aims 25% of moved dev targets; many moved targets have identical look-alikes in the context patch). The prediction is kept as written; a refuted prediction is reported as a finding.

## Test procedure

`python -m harness.run_checks test` (refuses to run without this tag), then `TALK_NUMBERS.md` v1 and the slide 6 and 7 figures. No threshold changes after this tag.
