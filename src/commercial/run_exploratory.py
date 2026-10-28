"""Exploratory runs from the preregistration (added after the freeze; the frozen files are unchanged):
mobile home pages, and desktop inner pages (is_root_page false). Uses run.py's dry run, hard byte cap and
run_log.json. The caps for the two requests queries were approved by the author on 2026-10-27.

  python run_exploratory.py --project PROJECT_ID mobile   # -> results/pages_mobile.csv, results/requests_mobile.csv
  python run_exploratory.py --project PROJECT_ID inner    # -> results/pages_desktop_inner.csv, results/requests_desktop_inner.csv

Then: python analyze.py --client mobile   /   python analyze.py --client desktop_inner
"""
import argparse, json

import run

CAPS = {"10m": 700, "11m": 5500, "10i": 700, "11i": 8300}


def inner(sql):
    """The frozen SQL with the root-page filters flipped to inner pages."""
    n = sql.count("AND is_root_page") + sql.count("AND r.is_root_page")
    if n == 0:
        raise SystemExit("no root-page filter found to flip")
    return sql.replace("AND is_root_page", "AND NOT is_root_page").replace("AND r.is_root_page", "AND NOT r.is_root_page")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("which", choices=["mobile", "inner"])
    ap.add_argument("--project", required=True)
    a = ap.parse_args()
    c = run.cfg()
    if not (c.get("probe_reviewed") and c.get("requests_approved") and c.get("crawl_date")):
        raise SystemExit("config.json is not frozen for Step 2")
    c = dict(c, cap_gb=dict(c["cap_gb"], **CAPS))
    log_path = run.RES / "run_log.json"
    log = json.loads(log_path.read_text())
    try:
        if a.which == "mobile":
            for n, key, out in (("10_pages.sql", "10m", "pages_mobile.csv"), ("11_requests.sql", "11m", "requests_mobile.csv")):
                run.run_query(a.project, key, f"{n[:-4]}_mobile", run.render(n, c, "mobile"), run.RES / out, c, log)
        else:
            for n, key, out in (("10_pages.sql", "10i", "pages_desktop_inner.csv"), ("11_requests.sql", "11i", "requests_desktop_inner.csv")):
                run.run_query(a.project, key, f"{n[:-4]}_desktop_inner", inner(run.render(n, c, "desktop")), run.RES / out, c, log)
    finally:
        log_path.write_text(json.dumps(log, indent=2) + "\n")


if __name__ == "__main__":
    main()
