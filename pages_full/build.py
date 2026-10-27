"""Build the full-study pages (PreflightBench-Live): inline _common_full.js into every page in src/.

Each built page is one self-contained HTML file with no network loads.
"""
import re
from pathlib import Path

HERE = Path(__file__).parent
COMMON = (HERE / "_common_full.js").read_text()


def build(html: str, name: str) -> str:
    assert "<!--COMMON-->" in html, name
    out = html.replace("<!--COMMON-->", "<script>\n" + COMMON + "\n</script>")
    stripped = re.sub(r'xmlns(:\w+)?=["\']http://www\.w3\.org/[^"\']*["\']', "", out)
    assert not re.search(r'(src|href)=["\']https?:', stripped) and "@import" not in stripped and "url(http" not in stripped, f"network ref in {name}"
    return out


def main():
    for p in sorted((HERE / "src").glob("*.html")):
        (HERE / p.name).write_text(build(p.read_text(), p.name))
        print("built", p.name)


if __name__ == "__main__":
    main()
