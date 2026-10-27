"""Render the race-registration illustration: screenshot at DOM-ready (t = 0), then 4 s of planning, then read
which element sits under the planned click point. Deterministic: Playwright's clock controls the page's timers."""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

HERE = Path(__file__).parent
with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width": 1280, "height": 800})
    pg.clock.install(time=0)
    pg.clock.pause_at(0)
    pg.goto((HERE / "race.html").as_uri(), wait_until="domcontentloaded")
    box = pg.locator('button[data-race="sprint"]').bounding_box()
    click = (box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    pg.screenshot(path=str(HERE / "planned.png"))
    pg.clock.run_for(4000)                       # the agent plans for 4 s; the banner arrives at 0.8 s
    pg.screenshot(path=str(HERE / "clicked.png"))
    hit = pg.evaluate("([x, y]) => { const e = document.elementFromPoint(x, y); return e.closest('[data-race]')?.dataset.race || e.tagName }", list(click))
    now = pg.locator('button[data-race="sprint"]').bounding_box()
    hit_box = pg.locator(f'button[data-race="{hit}"]').bounding_box()
    meta = dict(click=click, planned_box=box, sprint_box_at_click=now, element_at_click=hit, hit_box=hit_box)
    (HERE / "race_meta.json").write_text(json.dumps(meta, indent=1))
    print(json.dumps(meta))
    b.close()
