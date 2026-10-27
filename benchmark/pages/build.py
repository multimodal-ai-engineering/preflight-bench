"""Build the self-contained pilot pages.

Inlines _common.js into every page in src/, and derives tier0_booking.html from
../../booking-screenshots/local_booking.html with all network loads removed
(Google Fonts and Wikimedia photos become system fonts and flat color blocks),
so the Tier 0 page renders offline and deterministically.
"""
import re
from pathlib import Path

HERE = Path(__file__).parent
COMMON = (HERE / "_common.js").read_text()
BOOKING = HERE.parent.parent / "booking-screenshots" / "local_booking.html"


def inline(html: str) -> str:
    assert "<!--COMMON-->" in html
    return html.replace("<!--COMMON-->", "<script>\n" + COMMON + "\n</script>")


def tier0(src: str) -> str:
    s = re.sub(r'<link [^>]*fonts\.(googleapis|gstatic)[^>]*>\s*', "", src)
    s = s.replace('Inter, -apple-system', '-apple-system').replace('"Playfair Display", Georgia, serif', 'Georgia, serif')
    colors = iter(["#c9c2b5", "#aebcc6", "#b9c4b8"])
    s = re.sub(r'<img (class="main" )?alt="[^"]*"\s*src="[^"]*">',
               lambda m: f'<div {m.group(1) or ""}style="background:{next(colors)}"></div>', s)
    s = s.replace(".gallery img {", ".gallery div {")
    assert "http" not in re.sub(r'xmlns=\'http://www\.w3\.org/2000/svg\'|xmlns="http://www\.w3\.org/2000/svg"', "", s), "network ref left"
    s = s.replace("* { box-sizing: border-box; }",
                  "* { box-sizing: border-box; caret-color: transparent; }\n  html, body { width: 1280px; height: 800px; overflow: hidden; }")
    s = s.replace("<title>Bay View King | The Ferrow, San Francisco</title>", "<title>Tier 0 booking (fictional hotel)</title>")
    # Targets of mixed size.
    s = s.replace('<a class="signin" href="#">Sign in</a>', '<a class="signin" href="#" data-target-id="signin" data-alt="Signed in">Sign in</a>')
    s = s.replace('<a href="#">Dining</a>', '<a href="#" data-target-id="nav-dining" data-alt="Dining •">Dining</a>')
    s = s.replace('<a href="#">Offers</a>', '<a href="#" data-target-id="nav-offers" data-alt="Offers (3)">Offers</a>')
    s = s.replace('<strong>4.8</strong>',
                  '<strong>4.8</strong><button data-target-id="fav" data-alt="♥" style="width:24px;height:24px;padding:0;border:0;'
                  'background:transparent;font:15px/24px Arial;color:#5d6973">♡</button>')
    s = s.replace('<span class="chip">Bay Bridge view</span>', '<span class="chip"><a href="#" data-target-id="chip-view" data-alt="Bay Bridge view ✓">Bay Bridge view</a></span>')
    s = s.replace('<button class="btn" type="submit">Book</button>',
                  '<button class="btn" type="submit" data-target-id="book" data-alt="Booked" data-action-id="book">Book</button>')
    s = s.replace('<div class="cancel">Free cancellation until Nov 8</div>',
                  '<div class="cancel" data-block>Free cancellation until Nov 8 <a href="#" data-target-id="policy" data-alt="Policy ✓" style="color:#1f4e5f;text-decoration:underline">Policy</a></div>')
    # Replace the network submit with the shared last-action outcomes.
    s = re.sub(r"<script>\s*const form = .*?</script>", """<!--COMMON-->
<script>
  document.getElementById('booking-form').addEventListener('submit', e => e.preventDefault());
  ['first', 'last', 'email', 'phone'].forEach((k, i) => { document.getElementById(k).value = ['Alex', 'Rivera', 'alex@example.com', '(415) 555-0123'][i]; });
  P.action = { id: 'book', smallLabel: 'Booked ✓', panelText: 'Booking confirmed.' };
</script>""", s, flags=re.S)
    return inline(s)


def main():
    for p in sorted((HERE / "src").glob("*.html")):
        (HERE / p.name).write_text(inline(p.read_text()))
        print("built", p.name)
    if BOOKING.exists():
        (HERE / "tier0_booking.html").write_text(tier0(BOOKING.read_text()))
        print("built tier0_booking.html from", BOOKING)


if __name__ == "__main__":
    main()
