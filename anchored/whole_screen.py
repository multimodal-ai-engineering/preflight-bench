"""Whole-screen pre-action check, reimplemented from the PUSV paper's text (W. Xu 2026, arXiv 2604.18860).

PUSV is a security defense built for adversarial change; here it runs on ordinary moving pages,
a workload it was not designed for. Choices the paper leaves open are recorded in docs/THIRD_PARTY.md.

Layer 1: SSIM on a 160x160 grayscale patch at the click point (planned vs current). Flag if < ssim_min.
Layer 2a: flag if more than frac_max of the pixels outside that patch differ by more than 20/255.
Layer 2b (window list) does not apply inside a browser and is omitted.
A flag means re-plan; otherwise go.
"""
import time

import numpy as np
from skimage.metrics import structural_similarity

PUBLISHED = dict(ssim_min=0.92, frac_max=0.002, diff_thr=20)


def patch_bounds(click, shape, size=160):
    h, w = shape
    x0 = int(round(min(max(0, click[0] - size / 2), w - size)))
    y0 = int(round(min(max(0, click[1] - size / 2), h - size)))
    return x0, y0, x0 + size, y0 + size


def scores(planned, current, click):
    x0, y0, x1, y1 = patch_bounds(click, planned.shape)
    a, b = planned[y0:y1, x0:x1], current[y0:y1, x0:x1]
    ssim = structural_similarity(a, b, data_range=255)  # scikit-image defaults otherwise
    diff = np.abs(planned.astype(np.int16) - current.astype(np.int16)) > PUBLISHED["diff_thr"]
    diff[y0:y1, x0:x1] = False
    outside = planned.size - (y1 - y0) * (x1 - x0)
    return dict(ssim=float(ssim), frac_outside=float(diff.sum() / outside))


def check(planned_gray, current_gray, click, cfg=None):
    cfg = {**PUBLISHED, **(cfg or {})}
    t0 = time.perf_counter()
    s = scores(planned_gray, current_gray, click)
    flag1 = s["ssim"] < cfg["ssim_min"]
    flag2 = s["frac_outside"] > cfg["frac_max"]
    ms = (time.perf_counter() - t0) * 1000
    action = "replan" if (flag1 or flag2) else "go"
    reason = "ssim" if flag1 else "outside_change" if flag2 else "unchanged"
    return dict(action=action, click=tuple(click), reason=reason, scores=s, escalated=False, model_calls=[], ms=ms, usd=0.0)
