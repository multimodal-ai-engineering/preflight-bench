"""Dialog detector for the anchored preflight (full study): a dimmed backdrop, or a new bounded panel.

Both are measured outside the motion mask, between the second planning frame and the current frame:
  drop       median brightness drop of unmasked pixels (a modal backdrop darkens most of the page)
  panel      the largest connected region of changed pixels (> 20 gray levels, on a 4x downsampled grid):
             its bounding-box area as a share of the frame and how fully it fills that box (a dialog or a
             cookie banner is a filled rectangle; reflowed text is a sparse, ragged region)
Thresholds are tuned on dev (harness/full_checks.py); this module only computes the scores.
"""
import numpy as np
from scipy import ndimage


def dialog_features(pb, cb, mask, step=4):
    keep = ~mask
    drop = float(np.median(pb[keep]) - np.median(cb[keep])) if keep.any() else 0.0
    ch = (np.abs(pb.astype(np.int16) - cb.astype(np.int16)) > 20) & keep
    small = ch[::step, ::step]
    lab, n = ndimage.label(small)
    if n == 0:
        return dict(drop=drop, panel_area=0.0, panel_fill=0.0, changed=float(ch.mean()))
    sizes = ndimage.sum(small, lab, index=np.arange(1, n + 1))
    k = int(np.argmax(sizes)) + 1
    sl = ndimage.find_objects(lab, max_label=k)[k - 1]
    box_area = (sl[0].stop - sl[0].start) * (sl[1].stop - sl[1].start)
    return dict(drop=drop, panel_area=box_area / small.size, panel_fill=float(sizes[k - 1] / max(box_area, 1)), changed=float(ch.mean()))


def dialog_flag(f, cfg):
    return f["drop"] >= cfg["dlg_drop"] or (f["panel_area"] >= cfg["dlg_area"] and f["panel_fill"] >= cfg["dlg_fill"])
