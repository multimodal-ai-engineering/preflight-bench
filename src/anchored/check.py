"""Anchored preflight: mask what moves, re-find the target, decide go / re-aim / re-plan.

check(planned_frames, current_frames, target_box, *, mode, config=None) -> Decision

modes:
  "replan_only"  C3  any "not in place" result becomes a re-plan
  "reaim"        C4  pixels only, re-aim when the re-find is unique
  "escalate"     C5/C6 as C4, but ambiguous re-finds and uncertain covers go to a small model
                 (pass config["model"] = a models.qwen.Qwen instance)

Run `python -m anchored.check --demo` for a decision on a dev pair, with and without escalation.
"""
import argparse, json, time
from dataclasses import dataclass, field, asdict
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

DEFAULTS = dict(
    mask_thr=12,       # grayscale diff (0-255) that counts as self-motion
    mask_dilate=9,     # px, dilation kernel for the motion mask
    tau_in=0.90,       # masked NCC at the planned spot (+-3 px) for "in place"
    tau_match=0.85,    # best search peak needed to re-aim
    m_unique=0.05,     # best - second needed to re-aim
    tau_target=0.80,   # tight target crop NCC at the final spot
    b=18.0,            # max change of the target crop's mean brightness
    d=25.0,            # max drop of median brightness outside the mask
    # escalation (C5/C6)
    tau_low=0.60,      # ambiguous re-find band: tau_low <= best and (best < tau_match or margin < m_unique)
    cover_band=0.5,    # fraction of b / d / (1-tau_target) around each threshold that counts as uncertain
)
FRAME_WAIT_MS = 200.0  # second current frame; anchored modes wait for it


@dataclass
class Decision:
    action: str
    click: tuple
    reason: str
    scores: dict = field(default_factory=dict)
    escalated: bool = False
    model_calls: list = field(default_factory=list)
    ms: float = 0.0
    usd: float = 0.0


def gray(im):
    if isinstance(im, (str, Path)):
        im = Image.open(im)
    if isinstance(im, Image.Image):
        return np.asarray(im.convert("L"), dtype=np.uint8)
    return im


def motion_mask(pa, pb, ca, cb, thr, dil):
    m = (cv2.absdiff(pa, pb) > thr) | (cv2.absdiff(ca, cb) > thr)
    if dil > 0:
        m = cv2.dilate(m.astype(np.uint8), np.ones((dil, dil), np.uint8)) > 0
    return m


def context_rect(box, shape, min_wh=(96, 64), max_wh=(256, 192)):
    x, y, w, h = box
    W = int(min(max(w + 16, min_wh[0]), max_wh[0]))
    H = int(min(max(h + 16, min_wh[1]), max_wh[1]))
    cx, cy = x + w / 2, y + h / 2
    x0 = int(round(min(max(0, cx - W / 2), shape[1] - W)))
    y0 = int(round(min(max(0, cy - H / 2), shape[0] - H)))
    return x0, y0, W, H


def masked_ncc(t, wmask, img, x0, y0):
    """NCC of template t (with weight mask) against img at top-left (x0, y0). -1 when out of frame."""
    h, w = t.shape
    if x0 < 0 or y0 < 0 or y0 + h > img.shape[0] or x0 + w > img.shape[1]:
        return -1.0
    a = t[wmask].astype(np.float32)
    b = img[y0:y0 + h, x0:x0 + w][wmask].astype(np.float32)
    if a.size < 20:
        return -1.0
    a -= a.mean(); b -= b.mean()
    den = np.sqrt((a * a).sum() * (b * b).sum())
    if den < 1e-6:
        # Both flat: similar if their levels match.
        return 1.0 if abs(float(t[wmask].mean()) - float(img[y0:y0 + h, x0:x0 + w][wmask].mean())) < 4 else 0.0
    return float((a * b).sum() / den)


def local_best(t, wmask, img, x0, y0, r=3):
    best, bx, by = -1.0, x0, y0
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            s = masked_ncc(t, wmask, img, x0 + dx, y0 + dy)
            if s > best:
                best, bx, by = s, x0 + dx, y0 + dy
    return best, bx, by


def search(t, wmask, img, k=3):
    """Coarse search at half scale, then refine. Returns up to k peaks [(score, x, y)] after NMS."""
    ts = cv2.resize(t, (max(8, t.shape[1] // 2), max(8, t.shape[0] // 2)), interpolation=cv2.INTER_AREA)
    ms = cv2.resize(wmask.astype(np.uint8), (ts.shape[1], ts.shape[0]), interpolation=cv2.INTER_NEAREST)
    im = cv2.resize(img, (img.shape[1] // 2, img.shape[0] // 2), interpolation=cv2.INTER_AREA)
    if ms.sum() < 20:
        return []
    res = cv2.matchTemplate(im.astype(np.float32), ts.astype(np.float32), cv2.TM_CCOEFF_NORMED, mask=ms.astype(np.float32))
    res = np.nan_to_num(res, nan=-1.0, posinf=-1.0, neginf=-1.0)
    peaks = []
    r = res.copy()
    sx, sy = max(2, ts.shape[1] // 2), max(2, ts.shape[0] // 2)
    for _ in range(k + 3):
        _, mx, _, loc = cv2.minMaxLoc(r)
        if mx <= -0.5:
            break
        cx, cy = loc
        peaks.append((cx * 2, cy * 2))
        r[max(0, cy - sy):cy + sy + 1, max(0, cx - sx):cx + sx + 1] = -1.0
    refined = []
    for (x, y) in peaks:
        s, bx, by = local_best(t, wmask, img, x, y, r=3)
        refined.append((s, bx, by))
    # NMS again at full resolution, keep top k.
    refined.sort(key=lambda p: -p[0])
    out = []
    for p in refined:
        if all(abs(p[1] - q[1]) > t.shape[1] // 2 or abs(p[2] - q[2]) > t.shape[0] // 2 for q in out):
            out.append(p)
        if len(out) == k:
            break
    return out


def target_ncc(planned, current, box, dx, dy):
    x, y, w, h = [int(round(v)) for v in box]
    a = planned[y:y + h, x:x + w]
    X, Y = x + dx, y + dy
    if X < 0 or Y < 0 or Y + h > current.shape[0] or X + w > current.shape[1] or a.size == 0:
        return -1.0, 999.0
    b = current[Y:Y + h, X:X + w]
    s = masked_ncc(a, np.ones_like(a, bool), current, X, Y)
    return s, abs(float(b.mean()) - float(a.mean()))


def outside_drop(planned, current, mask):
    keep = ~mask
    if keep.sum() < 100:
        return 0.0
    return float(np.median(planned[keep])) - float(np.median(current[keep]))


def features(pa, pb, ca, cb, target_box, cfg):
    """Threshold-free scores. Depends only on mask_thr and mask_dilate, so tuning can reuse it."""
    x, y, w, h = target_box
    M = motion_mask(pa, pb, ca, cb, cfg["mask_thr"], cfg["mask_dilate"])
    X0, Y0, W, H = context_rect(target_box, pa.shape)
    tpl = pa[Y0:Y0 + H, X0:X0 + W]
    wm = ~M[Y0:Y0 + H, X0:X0 + W]
    # Always keep the target's own pixels, so a target inside a moving region can still be found.
    tx0, ty0 = int(x - X0), int(y - Y0)
    wm[max(0, ty0):ty0 + int(h), max(0, tx0):tx0 + int(w)] = True
    drop = outside_drop(pa, cb, M)
    s_in, bx, by = local_best(tpl, wm, cb, X0, Y0, r=3)
    F = dict(mask_frac=float(M.mean()), ctx=(X0, Y0, W, H), in_place=s_in, outside_drop=drop)
    tn, bs = target_ncc(pa, cb, target_box, bx - X0, by - Y0)
    F["at_in"] = dict(dx=bx - X0, dy=by - Y0, target_ncc=tn, bright_shift=bs)
    peaks = search(tpl, wm, cb, k=3)
    F["peaks"] = []
    for (sc, px, py) in peaks:
        tn, bs = target_ncc(pa, cb, target_box, px - X0, py - Y0)
        F["peaks"].append(dict(score=sc, dx=px - X0, dy=py - Y0, target_ncc=tn, bright_shift=bs))
    return F


def _cover_state(spot, drop, cfg):
    tn, bs = spot["target_ncc"], spot["bright_shift"]
    ok = tn >= cfg["tau_target"] and bs <= cfg["b"] and drop <= cfg["d"]
    unc = (abs(tn - cfg["tau_target"]) <= cfg["cover_band"] * (1 - cfg["tau_target"]) or
           abs(bs - cfg["b"]) <= cfg["cover_band"] * cfg["b"] or
           abs(drop - cfg["d"]) <= cfg["cover_band"] * cfg["d"])
    return ok, unc


def decide(F, target_box, cfg, mode, ask=None):
    """Pure decision from features. ask(kind, spot_or_peaks) -> parsed model answer, used only in escalate mode.
    Returns (action, click, reason, escalated)."""
    x, y, w, h = target_box
    click = (x + w / 2, y + h / 2)
    esc = [False]

    def usable(spot):
        ok, unc = _cover_state(spot, F["outside_drop"], cfg)
        if mode == "escalate" and ask is not None and unc:
            esc[0] = True
            j = ask("cover", spot)
            return isinstance(j, dict) and "covered" in j and not bool(j["covered"])
        return ok

    if F["in_place"] >= cfg["tau_in"]:
        if usable(F["at_in"]):
            return "go", click, "in_place", esc[0]
        return "replan", click, "covered_or_changed", esc[0]
    if mode == "replan_only":
        return "replan", click, "not_in_place", False
    P = F["peaks"]
    if not P:
        return "replan", click, "no_match", False
    best = P[0]["score"]
    second = P[1]["score"] if len(P) > 1 else -1.0
    chosen = None
    if best >= cfg["tau_match"] and best - second >= cfg["m_unique"]:
        chosen = P[0]
    elif mode == "escalate" and ask is not None and best >= cfg["tau_low"]:
        esc[0] = True
        # Candidates: top peaks at or above cand_min (0.5 for C5/C6, so packed model answers stay valid as tau_low moves).
        cands = [p for p in P if p["score"] >= cfg.get("cand_min", cfg["tau_low"])][:3]
        j = ask("tiebreak", cands)
        ch = j.get("choice") if isinstance(j, dict) else None
        if isinstance(ch, bool) or not isinstance(ch, int) or not (1 <= ch <= len(cands)):
            return "replan", click, ("model_null" if isinstance(j, dict) else "parse_fail"), True
        chosen = cands[ch - 1]
    if chosen is None:
        return "replan", click, ("ambiguous" if best >= cfg["tau_match"] else "weak_match"), esc[0]
    if usable(chosen):
        return "reaim", (click[0] + chosen["dx"], click[1] + chosen["dy"]), "unique_match", esc[0]
    return "replan", click, "match_covered_or_changed", esc[0]


def make_asker(model, pa, cb, target_box, F, calls):
    """Builds the small-model escalation callback, logging every raw output into calls."""
    from models.common import prompt, parse_json
    x, y, w, h = [int(round(v)) for v in target_box]
    X0, Y0, W, H = F["ctx"]

    def ask(kind, arg):
        if kind == "cover":
            a = Image.fromarray(pa[y:y + h, x:x + w])
            X, Y = x + arg["dx"], y + arg["dy"]
            b = Image.fromarray(cb[max(0, Y):Y + h, max(0, X):X + w])
            txt, ms = model.ask([_padded(a), _padded(b)], prompt("cover"), max_tokens=32)
        else:
            tpl = Image.fromarray(pa[Y0:Y0 + H, X0:X0 + W])
            crops = [Image.fromarray(cb[Y0 + p["dy"]:Y0 + p["dy"] + H, X0 + p["dx"]:X0 + p["dx"] + W]) for p in arg]
            n = len(crops)
            txt, ms = model.ask([tpl] + crops, prompt("tiebreak", n=n, choices="|".join(str(i + 1) for i in range(n))), max_tokens=32)
        j = parse_json(txt)
        calls.append(dict(kind=kind, raw=txt, ms=ms, parsed=j))
        return j
    return ask


def check(planned_frames, current_frames, target_box, *, mode="reaim", config=None):
    cfg = {**DEFAULTS, **(config or {})}
    model = cfg.get("model")
    t0 = time.perf_counter()
    pa, pb = (gray(f) for f in planned_frames)
    ca, cb = (gray(f) for f in current_frames)
    F = features(pa, pb, ca, cb, target_box, cfg)
    calls = []
    ask = make_asker(model, pa, cb, target_box, F, calls) if (mode == "escalate" and model is not None) else None
    action, click, reason, esc = decide(F, target_box, cfg, mode, ask)
    compute_ms = (time.perf_counter() - t0) * 1000 - sum(c["ms"] for c in calls)
    ms = compute_ms + FRAME_WAIT_MS + sum(c["ms"] for c in calls)
    scores = {k: v for k, v in F.items() if k != "ctx"}
    return Decision(action, tuple(float(v) for v in click), reason, scores, esc, calls, ms, 0.0)


def _padded(im, min_side=64):
    """Small crops get padded to a minimum size; tiny images break some vision encoders."""
    w, h = im.size
    if w >= min_side and h >= min_side:
        return im
    c = Image.new("L", (max(w, min_side), max(h, min_side)), 255)
    c.paste(im, ((c.width - w) // 2, (c.height - h) // 2))
    return c


def _demo():
    root = Path(__file__).resolve().parents[2]
    recs = [json.loads(l) for l in (root / "data/pilot/dev/pairs.jsonl").read_text().splitlines()]
    frozen = root / "results/pilot/frozen_w2.json"
    cfg = json.loads(frozen.read_text())["C4"] if frozen.exists() else {}
    r = next(r for r in recs if r["tier"] == 1 and r["correct_action"] == "reaim" and r["event"] == "moved")
    fr = {k: root / v for k, v in r["frames"].items()}
    args = ((fr["planned_a"], fr["planned_b"]), (fr["current_a"], fr["current_b"]), r["planned_box"])
    print(f"pair {r['pair_id']}  target {r['target_id']}  truth at offset 0: {r['correct_action']}")
    d = check(*args, mode="reaim", config=cfg)
    print(f"  pixels only   -> {d.action:6s} click=({d.click[0]:.0f},{d.click[1]:.0f}) reason={d.reason} {d.ms:.0f} ms")
    try:
        from models.qwen import Qwen
        frozen3 = root / "results/pilot/frozen_w3.json"
        cfg6 = {**cfg, **json.loads(frozen3.read_text())["C6"]} if frozen3.exists() else cfg
        d2 = check(*args, mode="escalate", config={**cfg6, "model": Qwen("4b"), "tau_match": 1.01})
        print(f"  + Qwen3-VL 4B -> {d2.action:6s} click=({d2.click[0]:.0f},{d2.click[1]:.0f}) reason={d2.reason} "
              f"escalated={d2.escalated} {d2.ms:.0f} ms  (tau_match forced above 1 so the demo escalates)")
        for c in d2.model_calls:
            print("     model said:", c["raw"].strip()[:120])
    except Exception as e:  # model optional for the demo
        print("  escalation unavailable:", e)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--demo", action="store_true")
    if ap.parse_args().demo:
        _demo()
