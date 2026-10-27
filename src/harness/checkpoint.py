"""Wave 1 checkpoint: contact sheet and counts. Uses dev labels plus private test labels (counts only)."""
import json
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "results" / "figures"


def load_all():
    dev = [json.loads(l) for l in (ROOT / "data/pilot/dev/pairs.jsonl").read_text().splitlines()]
    test = [json.loads(l) for l in (ROOT / "private/test_pairs_labels.jsonl").read_text().splitlines()]
    wd = [json.loads(l) for l in (ROOT / "data/pilot/dev/worked.jsonl").read_text().splitlines()]
    wt = [json.loads(l) for l in (ROOT / "private/test_worked_labels.jsonl").read_text().splitlines()]
    return dev + test, wd + wt


def font(n):
    for f in ["/System/Library/Fonts/Helvetica.ttc", "/System/Library/Fonts/Supplemental/Arial.ttf"]:
        try:
            return ImageFont.truetype(f, n)
        except OSError:
            pass
    return ImageFont.load_default()


def annotate(rec, scale=0.3):
    """planned_a | current_b side by side, planned click (black dot), DOM truth box at offset 0 (green), look-alikes (orange)."""
    a = Image.open(ROOT / rec["frames"]["planned_a"]).convert("RGB")
    b = Image.open(ROOT / rec["frames"]["current_b"]).convert("RGB")
    for im, boxes in ((a, [rec["planned_box"]]), (b, [rec["truth"][0]["target_box"]] if rec["truth"][0]["target_box"] else [])):
        d = ImageDraw.Draw(im)
        for bx in boxes:
            x, y, w, h = bx
            d.rectangle([x - 2, y - 2, x + w + 2, y + h + 2], outline=(20, 160, 70), width=4)
        if im is b:
            for (x, y, w, h) in rec["truth"][0]["lookalike_boxes"]:
                d.rectangle([x - 2, y - 2, x + w + 2, y + h + 2], outline=(230, 120, 20), width=4)
        cx, cy = rec["click"]
        d.ellipse([cx - 9, cy - 9, cx + 9, cy + 9], fill=(10, 10, 10), outline=(255, 255, 255), width=2)
    W, H = int(1280 * scale), int(800 * scale)
    tile = Image.new("RGB", (2 * W + 6, H + 22), "white")
    tile.paste(a.resize((W, H)), (0, 22))
    tile.paste(b.resize((W, H)), (W + 6, 22))
    ImageDraw.Draw(tile).text((2, 3), f"{rec['pair_id']} | {rec['target_id']} | truth: {rec['correct_action']}", fill="black", font=font(13))
    return tile


def contact_sheet(pairs, worked):
    by = {}
    for r in sorted(pairs, key=lambda r: r["pair_id"]):
        if r["motion"] in ("none", "high"):
            by.setdefault((r["page"], r["event"]), []).append(r)
    tiles = []
    for page in ["tier0_booking", "live_feed", "live_dashboard", "live_doc", "live_news"]:
        for ev in ["none", "moved", "covered", "gone", "moved_lookalike"]:
            tiles += [annotate(r) for r in by.get((page, ev), [])[:2]]
    cols = 4
    tw, th = tiles[0].size
    rows = (len(tiles) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * tw, rows * th), "white")
    for i, t in enumerate(tiles):
        sheet.paste(t, ((i % cols) * tw, (i // cols) * th))
    OUT.mkdir(exist_ok=True)
    sheet.save(OUT / "checkpoint_contact_sheet_pairs.png")
    # Worked set: one per outcome (live_feed), before | after.
    wt = []
    for o in ["success_clear", "success_small", "failed_error", "failed_silent"]:
        r = next(r for r in worked if r["page"] == "live_feed" and r["outcome"] == o)
        a = Image.open(ROOT / r["frames"]["before"]).convert("RGB").resize((448, 280))
        b = Image.open(ROOT / r["frames"]["after"]).convert("RGB").resize((448, 280))
        t = Image.new("RGB", (902, 320), "white")
        t.paste(a, (0, 40)); t.paste(b, (454, 40))
        ImageDraw.Draw(t).text((2, 3), f"{r['worked_id']} | {r['label']}\nexpected: {r['expected_effect']}", fill="black", font=font(13))
        wt.append(t)
    ws = Image.new("RGB", (902 * 2, 320 * 2), "white")
    for i, t in enumerate(wt):
        ws.paste(t, ((i % 2) * 902, (i // 2) * 320))
    ws.save(OUT / "checkpoint_contact_sheet_worked.png")


def counts(pairs, worked):
    df = pd.DataFrame([{k: r[k] for k in ["pair_id", "tier", "page", "motion", "event", "split", "correct_action", "motion_200ms", "change_gap"]}
                       | {"ca16": r["truth"][-1]["correct_action"], "flip": len({s["correct_action"] for s in r["truth"]}) > 1,
                          "lookalikes0": len(r["truth"][0]["lookalike_boxes"]), "errors": len(r["page_errors"])} for r in pairs])
    lines = ["## Counts (all splits)", "", "### correct_action at offset 0, by page", "",
             df.pivot_table(index="page", columns="correct_action", values="pair_id", aggfunc="count", fill_value=0).to_markdown(), "",
             "### correct_action by event (DOM label vs event name)", "",
             df.pivot_table(index="event", columns="correct_action", values="pair_id", aggfunc="count", fill_value=0).to_markdown(), "",
             "### by motion level", "",
             df.pivot_table(index="motion", columns="correct_action", values="pair_id", aggfunc="count", fill_value=0).to_markdown(), "",
             "### median motion_200ms and change_gap by motion level (fraction of pixels > 20/255)", "",
             df.groupby("motion")[["motion_200ms", "change_gap"]].median().to_markdown(floatfmt=".4f"), "",
             f"Pairs whose correct action changes during the 16 s after current_b: {int(df.flip.sum())} of {len(df)}", "",
             f"Pairs with look-alikes visible at offset 0: {int((df.lookalikes0 > 0).sum())}", "",
             f"Page JS errors: {int(df.errors.sum())}", "",
             "### split sizes", "", df.groupby(["tier", "split"]).size().to_frame("pairs").to_markdown(), ""]
    w = pd.DataFrame(worked)
    lines += ["### worked set", "", w.pivot_table(index="page", columns="outcome", values="worked_id", aggfunc="count", fill_value=0).to_markdown(), "",
              w.groupby("split").size().to_frame("pairs").to_markdown()]
    return "\n".join(lines)


if __name__ == "__main__":
    pairs, worked = load_all()
    contact_sheet(pairs, worked)
    txt = counts(pairs, worked)
    (ROOT / "results/pilot/checkpoint_counts.md").write_text(txt)
    print(txt)
