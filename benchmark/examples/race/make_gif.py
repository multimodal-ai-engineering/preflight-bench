"""Animated stale click on the race registration page: screenshot as the page opens, a results banner at 0.8 s,
and the click at 4 s landing on a different race. Run render_race.py first (it writes race_meta.json).

  python benchmark/examples/race/make_gif.py      # -> docs/assets/stale-click.gif
"""
import io, json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from playwright.sync_api import sync_playwright

OUT = Path(__file__).resolve().parents[3] / "docs" / "assets"


def gif():
    """Animated stale click on the race page: screenshot at page open, banner at 0.8 s, click at 4 s."""
    race = Path(__file__).resolve().parent
    meta = json.loads((race / "race_meta.json").read_text())
    cx, cy = meta["click"]; sb = meta["sprint_box_at_click"]
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": 1280, "height": 800})
        pg.clock.install(time=0); pg.clock.pause_at(0)
        pg.goto((race / "race.html").as_uri(), wait_until="domcontentloaded")
        before = Image.open(io.BytesIO(pg.screenshot())).convert("RGB")
        pg.clock.run_for(1000)
        after = Image.open(io.BytesIO(pg.screenshot())).convert("RGB")
        b.close()
    box = (0, 58, 930, 512)
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 22)
        small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 20)
    except OSError:
        font = small = ImageFont.load_default()
    def frame(img, caption, clock, ring=True, pulse=0, blue=False):
        im = img.crop(box).copy()
        d = ImageDraw.Draw(im)
        x, y = cx - box[0], cy - box[1]
        if ring:
            r = 34 + pulse
            d.ellipse([x - r, y - r, x + r, y + r], outline="#eb6834", width=6)
            d.ellipse([x - 4, y - 4, x + 4, y + 4], fill="#eb6834")
        if blue:
            d.rectangle([sb["x"] - 8, sb["y"] - box[1] - 8, sb["x"] + sb["width"] + 8, sb["y"] + sb["height"] - box[1] + 8], outline="#2a78d6", width=5)
        bar = Image.new("RGB", (im.width, 64), "#24152f")
        db = ImageDraw.Draw(bar)
        db.text((22, 19), caption, fill="#fdcadb", font=small)
        db.text((im.width - 22, 19), clock, fill="#faa0d0", font=font, anchor="ra")
        out = Image.new("RGB", (im.width, im.height + 64), "white"); out.paste(im, (0, 0)); out.paste(bar, (0, im.height))
        return out.resize((out.width * 3 // 4, out.height * 3 // 4), Image.LANCZOS)
    frames, durs = [], []
    def add(f, ms): frames.append(f); durs.append(ms)
    add(frame(before, "The agent takes its screenshot as the page opens", "0.0 s", ring=False), 1300)
    add(frame(before, "It plans: click Register for the Sprint", "0.4 s"), 1500)
    add(frame(after, "A results banner loads and pushes the list down", "0.8 s"), 1700)
    for i, t in enumerate(("1.5 s", "2.5 s", "3.5 s")):
        add(frame(after, "Still planning on the old screenshot", t), 600)
    for pz in (10, 0, 10, 0):
        add(frame(after, "The click lands: Register for the Olympic", "4.0 s", pulse=pz), 160)
    add(frame(after, "The click lands: Register for the Olympic. Sprint (blue) moved down.", "4.0 s", blue=True), 3200)
    pal = [f.convert("P", palette=Image.ADAPTIVE, colors=128) for f in frames]
    pal[0].save(OUT / "stale-click.gif", save_all=True, append_images=pal[1:], duration=durs, loop=0, optimize=True, disposal=2)


if __name__ == "__main__":
    gif()
