"""Talk assets for the Reverie deck: two charts, a scoreboard card, a QR code and an animated GIF of a stale click.
Numbers come from the paper (real-page survival, Table 2 rates, Equation 1)."""
import io, json, math
from pathlib import Path

import qrcode
from PIL import Image, ImageDraw, ImageFont
from playwright.sync_api import sync_playwright

OUT = Path(__file__).parent

PLUM, PINK, DEEP_PINK, LILAC, BLUE, MUTED, GRID = "#24152f", "#faa0d0", "#c2186b", "#c49edb", "#4f74c8", "#6b6170", "#ece7ee"
HEAD = """<html><head><meta charset="utf-8">
<link href="https://fonts.googleapis.com/css2?family=DM+Sans:opsz,wght@9..40,400;9..40,500;9..40,700&display=block" rel="stylesheet">
<style>*{margin:0;padding:0;box-sizing:border-box} body{width:%dpx;height:%dpx;background:transparent;font-family:'DM Sans',sans-serif;color:#24152f}
.card{width:100%%;height:100%%;background:#fff;border-radius:22px;padding:%s}</style></head><body>"""


def render(name, w, h, body, pad="26px 30px"):
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": w, "height": h}, device_scale_factor=3)
        pg.set_content(HEAD % (w, h, pad) + f'<div class="card">{body}</div></body></html>')
        pg.wait_for_timeout(2000)
        pg.screenshot(path=str(OUT / name), omit_background=True)
        b.close()


def svg_chart(W, H, xs, series, xlog, ylog, xlim, ylim, xticks, yticks, xlabel, ylabel, extra=""):
    L, R, T, B = 74, 16, 14, 52
    def X(v):
        a, b = (math.log10(xlim[0]), math.log10(xlim[1])) if xlog else xlim
        v = math.log10(v) if xlog else v
        return L + (v - a) / (b - a) * (W - L - R)
    def Y(v):
        a, b = (math.log10(ylim[0]), math.log10(ylim[1])) if ylog else ylim
        v = math.log10(v) if ylog else v
        return T + (1 - (v - a) / (b - a)) * (H - T - B)
    g = []
    for t, lab in yticks:
        g.append(f'<line x1="{L}" x2="{W-R}" y1="{Y(t):.1f}" y2="{Y(t):.1f}" stroke="{GRID}" stroke-width="1"/>'
                 f'<text x="{L-10}" y="{Y(t)+5:.1f}" text-anchor="end" font-size="15" fill="{MUTED}">{lab}</text>')
    for t, lab in xticks:
        g.append(f'<text x="{X(t):.1f}" y="{H-B+24}" text-anchor="middle" font-size="15" fill="{MUTED}">{lab}</text>')
    g.append(f'<text x="{(L+W-R)/2:.1f}" y="{H-8}" text-anchor="middle" font-size="15" fill="{MUTED}">{xlabel}</text>')
    g.append(f'<text transform="translate(18,{(T+H-B)/2:.1f}) rotate(-90)" text-anchor="middle" font-size="15" fill="{MUTED}">{ylabel}</text>')
    for s in series:
        pts = " ".join(f"{X(x):.1f},{Y(y):.1f}" for x, y in zip(s["x"], s["y"]))
        dash = ' stroke-dasharray="7 6"' if s.get("dash") else ""
        g.append(f'<polyline points="{pts}" fill="none" stroke="{s["color"]}" stroke-width="{s.get("w",4)}"{dash} stroke-linecap="round" stroke-linejoin="round"/>')
        if s.get("dots"):
            g += [f'<circle cx="{X(x):.1f}" cy="{Y(y):.1f}" r="5" fill="{s["color"]}"/>' for x, y in zip(s["x"], s["y"])]
        if s.get("label"):
            lx, ly, anchor = s["label_at"]
            g.append(f'<text x="{X(lx):.1f}" y="{Y(ly):.1f}" font-size="17" font-weight="700" fill="{s["color"]}" text-anchor="{anchor}">{s["label"]}</text>')
    return f'<svg width="{W}" height="{H}" viewBox="0 0 {W} {H}" font-family="DM Sans">{"".join(g)}{extra(X, Y) if extra else ""}</svg>'


def chart_pageload():
    t = [0.5, 1, 2, 6.5, 12, 30]
    loaded = [99.7, 99.7, 99.6, 99.7, 99.7, 99.6]
    opened = [85.5, 82.8, 82.6, 82.9, 83.0, 82.9]
    W, H = 548 - 60, 274 - 52
    svg = svg_chart(W, H, t, [
        dict(x=t, y=loaded, color=BLUE, dots=True, label="fully loaded page: 0.4% stale", label_at=(0.55, 96.3, "start")),
        dict(x=t, y=opened, color=DEEP_PINK, dots=True, label="page just opened: 17% stale by 1 s", label_at=(0.55, 86.7, "start")),
    ], True, False, (0.42, 36), (80, 101), [(0.5, "0.5"), (1, "1"), (2, "2"), (6.5, "6.5"), (12, "12"), (30, "30 s")],
        [(80, "80%"), (85, "85%"), (90, "90%"), (95, "95%"), (100, "100%")], "seconds after the screenshot", "clicks still on target")
    render("talk-pageload.png", 548, 274, svg)


def pstar(C, r, f, d, k=2):
    return (d / C + f) / (r * (k - 1) + f)


def chart_breakeven():
    Cs = [0.5 * (40 ** (i / 60)) for i in range(61)]
    px = [pstar(c, .818, .042, .312) for c in Cs]
    op = [min(1.0, pstar(c, .827, .124, 2.366)) for c in Cs]
    W, H = 548 - 60, 274 - 52
    def extra(X, Y):
        return (f'<line x1="{X(0.5):.1f}" x2="{X(20):.1f}" y1="{Y(0.171):.1f}" y2="{Y(0.171):.1f}" stroke="{MUTED}" stroke-dasharray="3 5" stroke-width="2"/>'
                f'<text x="{X(0.55):.1f}" y="{Y(0.171)+20:.1f}" text-anchor="start" font-size="14" fill="{MUTED}">page just opened: 17%</text>'
                f'<line x1="{X(0.5):.1f}" x2="{X(20):.1f}" y1="{Y(0.004):.1f}" y2="{Y(0.004):.1f}" stroke="{MUTED}" stroke-dasharray="3 5" stroke-width="2"/>'
                f'<text x="{X(0.55):.1f}" y="{Y(0.004)-8:.1f}" text-anchor="start" font-size="14" fill="{MUTED}">fully loaded page: 0.4%</text>'
                f'<line x1="{X(2.4):.1f}" x2="{X(3.4):.1f}" y1="{Y(0.045):.1f}" y2="{Y(0.045):.1f}" stroke="{DEEP_PINK}" stroke-width="4" stroke-linecap="round"/>'
                f'<text x="{X(3.7):.1f}" y="{Y(0.045)+5:.1f}" font-size="16" font-weight="700" fill="{DEEP_PINK}">frontier model check</text>'
                f'<line x1="{X(2.4):.1f}" x2="{X(3.4):.1f}" y1="{Y(0.02):.1f}" y2="{Y(0.02):.1f}" stroke="{BLUE}" stroke-width="4" stroke-linecap="round"/>'
                f'<text x="{X(3.7):.1f}" y="{Y(0.02)+5:.1f}" font-size="16" font-weight="700" fill="{BLUE}">pixel check</text>')
    svg = svg_chart(W, H, Cs, [
        dict(x=Cs, y=op, color=DEEP_PINK),
        dict(x=Cs, y=px, color=BLUE),
    ], True, True, (0.5, 20), (0.003, 1.0), [(0.5, "0.5"), (1, "1"), (2, "2"), (5, "5"), (10, "10"), (20, "20 s")],
        [(0.01, "1%"), (0.1, "10%"), (1.0, "100%")], "how long the agent plans", "break-even change rate", extra)
    render("talk-breakeven.png", 548, 274, svg)


def scoreboard():
    def row(name, a, b, c, strong=False):
        fw = 700 if strong else 500
        return (f'<tr><td style="padding:7px 0;font-weight:{fw}">{name}</td>'
                f'<td style="text-align:right;font-weight:700;font-size:22px">{a}</td>'
                f'<td style="text-align:right;color:{MUTED}">{b}</td><td style="text-align:right;color:{MUTED}">{c}</td></tr>')
    head = f'<tr style="color:{MUTED};font-size:13px"><td></td><td style="text-align:right">caught</td><td style="text-align:right">false alarms</td><td style="text-align:right">time</td></tr>'
    body = f"""
<div style="font-size:14px;letter-spacing:.12em;color:{DEEP_PINK};font-weight:700">WHERE IS MY TARGET?</div>
<table style="width:100%;font-size:17px;border-collapse:collapse;margin:4px 0 14px">{head}
{row("Pixels", "82%", "4%", "0.3 s", True)}{row("Frontier model", "83%", "12%", "2.4 s")}</table>
<div style="font-size:14px;letter-spacing:.12em;color:{BLUE};font-weight:700">DID THE LAST ACTION WORK?</div>
<table style="width:100%;font-size:17px;border-collapse:collapse;margin-top:4px">{head}
{row("4B open model", "100%", "0%", "2.8 s", True)}{row("Frontier model", "100%", "0%", "2.4 s")}</table>"""
    render("talk-scoreboard.png", 420, 290, body, pad="20px 26px")


def qr():
    q = qrcode.QRCode(border=2, box_size=20, error_correction=qrcode.constants.ERROR_CORRECT_M)
    q.add_data("https://github.com/multimodal-ai-engineering/preflight-bench")
    q.make(fit=True)
    q.make_image(fill_color=PLUM, back_color="white").convert("RGB").save(OUT / "talk-qr.png")


def gif():
    """Animated stale click on the race page: screenshot at page open, banner at 0.8 s, click at 4 s."""
    race = Path(__file__).resolve().parents[3] / "paper" / "race"
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
    pal[0].save(OUT / "talk-stale-click.gif", save_all=True, append_images=pal[1:], duration=durs, loop=0, optimize=True, disposal=2)
    frames[-1].save(OUT / "talk-stale-click-last.png")


if __name__ == "__main__":
    chart_pageload(); chart_breakeven(); scoreboard(); qr(); gif()
    for f in sorted(OUT.iterdir()):
        print(f.name, f.stat().st_size, Image.open(f).size)
