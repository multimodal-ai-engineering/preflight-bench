"""Shared helpers for model checks: prompts, crops, JSON parsing."""
import json, re
from pathlib import Path

from PIL import Image

PROMPTS = Path(__file__).parent / "prompts"


def prompt(name, **kw):
    return (PROMPTS / f"{name}.txt").read_text().strip().format(**kw)


def parse_json(text):
    """First {...} object in the output, or None (a parse failure counts as re-plan)."""
    if not text:
        return None
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None


def plan_crop(img: Image.Image, box, size=(448, 336)):
    """448x336 crop of the planning frame centered on the target. Returns crop and target box inside it."""
    x, y, w, h = box
    cw, ch = size
    left = int(round(min(max(0, x + w / 2 - cw / 2), img.width - cw)))
    top = int(round(min(max(0, y + h / 2 - ch / 2), img.height - ch)))
    return img.crop((left, top, left + cw, top + ch)), (round(x - left), round(y - top), round(w), round(h))


def locate_decision(parsed, planned_box, scale):
    """C7/C8/C9 rule. scale converts the model's box units to pixels: (sx, sy)."""
    if not isinstance(parsed, dict) or not parsed.get("present") or parsed.get("covered"):
        return "replan", None
    b = parsed.get("box")
    try:
        x1, y1, x2, y2 = [float(v) for v in b]
    except Exception:
        return "replan", None
    x1, x2 = sorted((x1 * scale[0], x2 * scale[0]))
    y1, y2 = sorted((y1 * scale[1], y2 * scale[1]))
    px, py, pw, ph = planned_box
    ix = max(0, min(x2, px + pw) - max(x1, px))
    iy = max(0, min(y2, py + ph) - max(y1, py))
    inter = ix * iy
    union = (x2 - x1) * (y2 - y1) + pw * ph - inter
    iou = inter / union if union > 0 else 0
    if iou > 0.5:
        return "go", None
    return "reaim", ((x1 + x2) / 2, (y1 + y2) / 2)
