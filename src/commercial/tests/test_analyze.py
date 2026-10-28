"""Tests for analyze.py on hand-made inputs with known answers.  python3 tests/test_analyze.py"""
import csv, shutil, sys, tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import analyze as A  # noqa: E402


def test_network_idle():
    assert A.network_idle([(0, 100), (50, 1200), (1300, 1400)], 200) == 1400
    assert A.network_idle([(0, 300)], 500) == 500
    assert A.network_idle([(0, 600), (1200, 1300)], 100) == 600           # 600-1100 is quiet before the next request
    assert A.network_idle([(0, 600), (1050, 1300)], 100) == 1300          # 600-1050 is too short
    assert A.network_idle([], 250) == 250
    assert A.network_idle([(0, 600), (400, None)], 100) is None   # an unfinished request never ends
    assert A.network_idle([(0, 600), (5000, None)], 100) == 600   # ...but only from its start


def test_parsers():
    assert A.parse_shifts("120.0:0.01;-1.0:-1.000000;80.5:0.002") == [(80.5, 0.002), (120.0, 0.01)]
    assert A.parse_shifts("") == [] and A.parse_shifts(None) == []
    assert A.parse_intervals("0,100;-1,-1;50,40;200,300;300,-1") == [(0, 100), (50, None), (200, 300), (300, None)]


def row(**kw):
    base = dict(dcl_start_ms="1000", dcl_end_ms="1010", load_ms="2000", fully_loaded_ms="4000",
                last_visual_change_ms="3000", cls="0.2", shifts_missing="false", shifts="")
    base.update({k: str(v) for k, v in kw.items()})
    return base


def req(iv):
    p = A.parse_intervals(iv)
    return dict(intervals=p, n_parsed=len(p), n_requests=len(p), n_open=0, main_status=200)


def test_rules_and_outcomes():
    r = A.page_record(row(shifts="1200:0.05;3500:0.01;9000:0.00001"), req("0,900;950,2600"))
    assert r["t0"] == 1010 and r["T_S1"] == 1510 and r["T_S2"] == 2010 and r["T_S4"] == 2000
    assert r["idle_start"] == 2600 and r["T_S5"] == 3100 and r["idle_capped"] is False   # returns at the end of the quiet window
    assert r["y_S0"] == 1 and r["y_S1"] == 1 and r["y_S4"] == 1 and r["y_S5"] == 1      # 3500 is inside every window
    r2 = A.page_record(row(shifts="1200:0.05"), req("0,900;950,2600"))
    assert r2["y_S0"] == 1 and r2["y_S1"] == 0 and r2["y_S5"] == 0 and r2["last_shift_after_t0"] == 190
    # many tiny shifts add up, as CLS does in the validation
    r3 = A.page_record(row(shifts="5000:0.00004;5100:0.00004;5200:0.00004"), req("0,900"))
    assert r3["y_S5"] == 1
    # never quiet within the cap: the screenshot is taken at the cap
    r4 = A.page_record(row(shifts="5000:0.1"), req("0,3000;2900,6000;5900,8000"))
    assert r4["idle_capped"] is True and r4["T_S5"] == 4010 and r4["y_S5"] == 1 and r4["T_S5u"] == 8500
    assert r4["cens_S5"] == 1      # observation ends at 8000 < 4010 + 6500


def test_missing_data():
    assert A.page_record(row(shifts_missing="true", cls="0"), req("0,10"))["shifts_ok"] is True
    r = A.page_record(row(shifts_missing="true", cls="0.3"), req("0,10"))
    assert r["shifts_ok"] is False and r["y_S0"] is None
    assert A.page_record(row(shifts_missing="false", shifts="", cls="0.3"), req("0,10"))["shifts_ok"] is False   # empty list, CLS > 0
    assert A.page_record(row(dcl_start_ms="0", dcl_end_ms=""), None) is None
    assert A.page_record(row(shifts="1200:0.05"), None)["T_S5"] is None
    bad = req("0,10;20,30"); bad["n_requests"] = 3                                 # a request without a start time
    assert A.page_record(row(shifts="1200:0.05"), bad)["T_S5"] is None


def test_p_star_matches_paper():
    assert abs(A.p_star(2) - 0.1023) < 0.001
    assert abs(A.p_star(10) - 0.0119) < 0.0005


def write(path, header, rows):
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=header); w.writeheader(); w.writerows(rows)


def test_end_to_end_synthetic():
    tmp = Path(tempfile.mkdtemp())
    here = Path(__file__).resolve().parents[1]
    for f in ("domains.csv", "study31.csv", "probe_domains.txt"):
        shutil.copy(here / f, tmp / f)
    (tmp / "results").mkdir(); (tmp / "inputs").mkdir()
    hdr = ["page", "domain", "host", "rank", "is_book", "is_media", "is_study", "is_gov", "has_ecom", "has_ads", "h", "wpt_result",
           "req_total", "bytes_total", "ttfb_ms", "render_ms", "dcl_start_ms", "dcl_end_ms", "load_ms", "fully_loaded_ms",
           "last_visual_change_ms", "cls", "viewport", "shifts_missing", "shifts"]
    rows, reqs = [], []
    book = [d["domain"] for d in csv.DictReader(open(here / "domains.csv")) if d["group"] == "BOOK"][:40]
    for i, d in enumerate(book):                          # 24 of 40 never go quiet and shift at 6 s
        late = i < 24
        rows.append(dict(page=f"https://www.{d}/", domain=d, host=f"www.{d}", rank=1000, is_book="true", is_media="false",
                         is_study="false", is_gov="false", has_ecom="true", has_ads="true", h=i, wpt_result=0, req_total=80,
                         bytes_total=3_000_000, ttfb_ms=200, render_ms=500, dcl_start_ms=1000, dcl_end_ms=1000, load_ms=2000,
                         fully_loaded_ms=9000, last_visual_change_ms=8000, cls=0.2 if late else 0, viewport="{}",
                         shifts_missing="false" if late else "true", shifts="6000:0.05" if late else ""))
        reqs.append(dict(page=f"https://www.{d}/", n_requests=3 if late else 2, n_open=0, main_status=200,
                         intervals="0,500;400,2200;2100,9000" if late else "0,500;400,1200"))
    # a decoy: the same airline on a subdomain with a better rank must not replace the www page
    rows.append(dict(rows[0], page="https://careers.united.com/", host="careers.united.com", rank=1, shifts="", cls=0, shifts_missing="true"))
    for i in range(40):                                   # GOV: quiet by 1.2 s, no shifts
        h = f"www.agency{i}.gov"
        rows.append(dict(page=f"https://{h}/", domain=f"agency{i}.gov", host=h, rank=1000, is_book="false", is_media="false",
                         is_study="false", is_gov="true", has_ecom="false", has_ads="false", h=i, wpt_result=0, req_total=40,
                         bytes_total=900_000, ttfb_ms=200, render_ms=500, dcl_start_ms=800, dcl_end_ms=800, load_ms=1200,
                         fully_loaded_ms=2500, last_visual_change_ms=900, cls=0, viewport="{}", shifts_missing="true", shifts=""))
        reqs.append(dict(page=f"https://{h}/", n_requests=2, n_open=0, main_status=200, intervals="0,400;300,1200"))
    # a bot-challenge page is excluded
    rows.append(dict(rows[-1], page="https://www.blocked.gov/", host="www.blocked.gov", domain="blocked.gov", h=999))
    reqs.append(dict(page="https://www.blocked.gov/", n_requests=2, n_open=0, main_status=403, intervals="0,100;50,200"))
    write(tmp / "results" / "pages_desktop.csv", hdr, rows)
    write(tmp / "results" / "requests_desktop.csv", ["page", "n_requests", "n_open", "main_status", "intervals"], reqs)
    vrows = []
    for s in ("x", "y"):
        vrows += [dict(site=s, rule="S0", round=0, shift=1, tracks=100, stale=20), dict(site=s, rule="S5", round=0, shift=0, tracks=100, stale=1),
                  dict(site=s, rule="S2", round=0, shift=1, tracks=100, stale=10), dict(site=s, rule="S2", round=1, shift=0, tracks=100, stale=1)]
    write(tmp / "inputs" / "validation_visits.csv", ["site", "rule", "round", "shift", "tracks", "stale"], vrows)
    write(tmp / "inputs" / "settle_cls_by_page.csv", ["site", "kind", "burst_2s", "tracks", "cls_s0", "cls_s5"], [])
    old = A.HERE
    A.HERE = tmp
    try:
        m, sens = A.run("desktop", B=300)
    finally:
        A.HERE = old
    get = lambda g, r: next(s for s in m["summary"] if s["group"] == g and s["rule"] == r)
    assert get("BOOK", "S5")["n_pages"] == 40 and get("BOOK", "S5")["shift_share"] == 0.6
    assert get("GOV", "S5")["shift_share"] == 0.0 and get("GOV", "S5")["n_pages"] == 40      # the 403 page is out
    a, b = 4 / 400, 60 / 400                                                                  # pooled over S0, S2, S5
    assert abs(get("BOOK", "S5")["stale_pooled"] - (a + (b - a) * 0.6)) < 1e-4
    a2, b2 = 4 / 400, 20 / 200                                                                # S1-S5 only (S2, S5 rows)
    assert abs(get("BOOK", "S5")["stale_S1toS5"] - (a2 + (b2 - a2) * 0.6)) < 1e-4
    qv = {q["group"]: q["quiet_within_3s"] for q in m["quiet"]}
    assert qv["BOOK"] == 0.4 and qv["GOV"] == 1.0
    h = m["hyp"]
    assert h["C2"]["held"] is True
    # every GOV page goes quiet early, so all its pairs are censored and the drop-censored test is untestable:
    assert h["C1"]["drop_censored"]["testable"] is False and h["C1"]["held"] is True and "note" in h["C1"]
    assert h["C3"]["testable"] is False and h["C3"]["held"] is None          # no study pages in this fixture
    assert m["meta"]["pages_excluded"].get("main document not 200") == 1
    assert m["meta"]["group_sizes"]["BOOK"] == 40


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
