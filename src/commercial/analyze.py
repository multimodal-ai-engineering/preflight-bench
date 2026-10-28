"""Commercial-page analysis (PREREG_COMMERCIAL.md). Reads the Step 2 query results and the 31-page validation,
computes each wait rule's screenshot time per page, whether the page shifted in the 6.5 s after it, the estimated
share of stale clicks per group, and hypotheses C1-C3.

  python3 analyze.py [--client desktop] [--boot 2000]

Inputs:  results/pages_<client>.csv, results/requests_<client>.csv (run.py main)
         inputs/validation_visits.csv (validate_proxy.py), inputs/settle_cls_by_page.csv (Addition 1 table)
         domains.csv, study31.csv, probe_domains.txt
Outputs: results/analysis_<client>/
"""
import argparse, csv, json, math, random
from collections import defaultdict
from pathlib import Path
from urllib.parse import urlparse

HERE = Path(__file__).resolve().parent
SHIFT_EPS = 1e-4            # the validation's threshold: summed layout-shift score after the screenshot
WINDOW_MS = 6500.0          # the planner's thinking time
QUIET_MS, CAP_MS = 500.0, 3000.0
RULES = ("S0", "S1", "S2", "S4", "S5", "S5u")
RULE_NAME = {"S0": "DOM ready", "S1": "+0.5 s", "S2": "+1 s", "S4": "load event", "S5": "network idle, 3 s cap",
             "S5u": "network idle, no cap"}
RANK_BUCKETS = (1000, 10000, 100000, 1000000)
GROUP_CAP = 5000
MIN_REQUESTS = 10           # fewer requests than this on a home page: treated as an error or bot-challenge page
MIN_N_TEST = 30             # a group needs at least this many pages for a test to be decided
PIX = dict(r=0.82, f=0.04, delta_s=0.312, C_s=6.5)   # pixel check from the paper; planner 6.5 s
CALIBRATIONS = {"pooled": None, "S1toS5": {"S1", "S2", "S3", "S3b", "S4", "S5"}}


# ---------- parsing ----------
def fnum(x):
    try:
        v = float(x)
        return v if math.isfinite(v) else None
    except (TypeError, ValueError):
        return None


def parse_shifts(s):
    out = []
    for part in (s or "").split(";"):
        if ":" not in part:
            continue
        t, sc = (fnum(v) for v in part.split(":", 1))
        if t is not None and sc is not None and t >= 0 and sc >= 0:
            out.append((t, sc))
    return sorted(out)


def parse_intervals(s):
    """'start,end;start,end;...' with -1 for missing. Returns [(start, end or None)]; end None = never finished."""
    out = []
    for part in (s or "").split(";"):
        if part.count(",") != 1:
            continue
        a, b = (fnum(v) for v in part.split(","))
        if a is None or a < 0:
            continue                      # no start time: cannot be placed (counted via n_open)
        out.append((a, b if (b is not None and b > 0 and b >= a) else None))
    return out


def truthy(x):
    return str(x).strip().lower() in ("true", "1")


# ---------- per-page quantities ----------
def network_idle(intervals, t0, quiet=QUIET_MS):
    """Start of the first window (t, t + quiet), t >= t0, with no request in flight. A request [s, e] is in flight
    on (s, e); one that never finished (e None) stays in flight from s on. None if no such window exists."""
    iv = [(s, e if e is not None else float("inf")) for s, e in intervals]
    cands = sorted({t0} | {e for _, e in iv if t0 <= e < float("inf")})
    for t in cands:
        if not any(s < t + quiet and e > t for s, e in iv):
            return t
    return None


def page_record(row, req):
    """Screenshot time per rule, outcome per rule, observation end; None if the page lacks DOM-ready."""
    dcl_end, dcl_start = fnum(row.get("dcl_end_ms")), fnum(row.get("dcl_start_ms"))
    t0 = dcl_end if dcl_end and dcl_end > 0 else (dcl_start if dcl_start and dcl_start > 0 else None)
    if t0 is None:
        return None
    cls = fnum(row.get("cls"))
    shifts = parse_shifts(row.get("shifts"))
    shifts_ok = bool(shifts) or cls == 0          # no shift entries: valid only if the page's CLS is 0
    load = fnum(row.get("load_ms"))
    full = fnum(row.get("fully_loaded_ms")) or 0.0
    lvc = fnum(row.get("last_visual_change_ms"))
    intervals = req["intervals"] if req else None
    ends = [e for _, e in (intervals or []) if e is not None]
    end = max([full, load or 0.0] + ends + [t for t, _ in shifts])
    T = {"S0": t0, "S1": t0 + 500, "S2": t0 + 1000, "S4": load if load and load >= t0 else None, "S5": None, "S5u": None}
    idle = capped = None
    req_ok = bool(req) and bool(intervals) and req.get("n_parsed") == req.get("n_requests")
    if req_ok:
        idle = network_idle(intervals, t0)
        quiet_at = (idle + QUIET_MS) if idle is not None else None        # a network-idle wait returns at the end
        capped = quiet_at is None or quiet_at > t0 + CAP_MS               # of its quiet window
        T["S5"] = t0 + CAP_MS if capped else quiet_at
        T["S5u"] = quiet_at if quiet_at is not None else end   # never quiet: the wait times out at the last recorded moment
    rec = dict(t0=t0, load=load, fully_loaded=full, last_visual_change=lvc, cls=cls, shifts_ok=shifts_ok,
               n_shifts=len(shifts), req_ok=req_ok, idle_start=idle, idle_capped=capped, obs_end=end)
    sig = [t for t, sc in shifts if sc > 0]
    rec["last_shift_after_t0"] = (max(sig) - t0) if sig and max(sig) > t0 else None
    for r, t in T.items():
        rec[f"T_{r}"] = t
        if t is None or not shifts_ok:
            rec[f"y_{r}"] = rec[f"cens_{r}"] = rec[f"lvc_{r}"] = None
            continue
        score = sum(sc for ts, sc in shifts if t < ts <= t + WINDOW_MS)
        rec[f"y_{r}"] = int(score > SHIFT_EPS)
        rec[f"score_{r}"] = score
        rec[f"cens_{r}"] = int(end < t + WINDOW_MS)
        rec[f"lvc_{r}"] = None if lvc is None else int(lvc > t)
    return rec


# ---------- inputs and groups ----------
def load_pages(client):
    seen, pages = set(), []
    for p in csv.DictReader(open(HERE / "results" / f"pages_{client}.csv")):
        if p["page"] not in seen:
            seen.add(p["page"])
            pages.append(p)
    req = {}
    rp = HERE / "results" / f"requests_{client}.csv"
    if rp.exists():
        for r in csv.DictReader(open(rp)):
            iv = parse_intervals(r["intervals"])
            req[r["page"]] = dict(intervals=iv, n_parsed=len(iv), n_requests=int(r["n_requests"] or 0),
                                  n_open=int(r["n_open"] or 0), main_status=fnum(r.get("main_status")))
    return pages, req


def assign_groups(pages):
    doms = {d["domain"]: d for d in csv.DictReader(open(HERE / "domains.csv"))}
    study = {urlparse(r["url"]).hostname: r["site"] for r in csv.DictReader(open(HERE / "study31.csv"))}
    probe = {l.strip() for l in open(HERE / "probe_domains.txt") if l.strip()}
    n_probe = sum(1 for p in pages if p["domain"] in probe)
    pages = [p for p in pages if p["domain"] not in probe]
    rank = lambda p: int(fnum(p["rank"]) or 10**9)
    groups = defaultdict(list)
    # BOOK / MEDIA: one page per registered domain; the apex or www host first, then the best rank
    best = {}
    for p in pages:
        d = p["domain"]
        if d in doms:
            key = (0 if p["host"] in (d, "www." + d) else 1, rank(p), p["page"])
            if d not in best or key < best[d][0]:
                best[d] = (key, p)
    for d, (_, p) in sorted(best.items()):
        g = doms[d]["group"]
        groups[g].append(p)
        groups[f"{g}:{doms[d]['category']}"].append(p)
    sbest = {}
    for p in pages:
        if p["host"] in study:
            key = (rank(p), p["page"])
            if p["host"] not in sbest or key < sbest[p["host"]][0]:
                sbest[p["host"]] = (key, p)
    groups["STUDY31"] = [p for _, p in sorted(sbest.values(), key=lambda x: x[0])]
    by_h = lambda xs: sorted(xs, key=lambda p: (int(p["h"]), p["page"]))[:GROUP_CAP]
    groups["GOV"] = by_h([p for p in pages if truthy(p["is_gov"])])
    excl = lambda p: truthy(p["is_gov"]) or p["host"] in study or p["domain"] in doms
    groups["SHOP"] = by_h([p for p in pages if truthy(p["has_ecom"]) and not excl(p)])
    groups["ADS"] = by_h([p for p in pages if truthy(p["has_ads"]) and not excl(p)])
    for b in RANK_BUCKETS:
        for g in ("BOOK", "GOV", "SHOP"):
            groups[f"{g}@rank<={b}"] = [p for p in groups[g] if rank(p) <= b and (b == RANK_BUCKETS[0] or rank(p) > RANK_BUCKETS[RANK_BUCKETS.index(b) - 1])]
    groups["_probe_pages_removed"] = n_probe
    return groups, study


def load_validation():
    rows = list(csv.DictReader(open(HERE / "inputs" / "validation_visits.csv")))
    for r in rows:
        r["shift"], r["tracks"], r["stale"] = int(r["shift"]), int(r["tracks"]), int(r["stale"])
    return rows


def calib(rows, rules=None):
    sel = [r for r in rows if rules is None or r["rule"] in rules]
    n1 = sum(r["tracks"] for r in sel if r["shift"]); i1 = sum(r["stale"] for r in sel if r["shift"])
    n0 = sum(r["tracks"] for r in sel if not r["shift"]); i0 = sum(r["stale"] for r in sel if not r["shift"])
    return (i0 / n0 if n0 else float("nan")), (i1 / n1 if n1 else float("nan"))


def site_boot(rows, rnd):
    by = defaultdict(list)
    for r in rows:
        by[r["site"]].append(r)
    ks = sorted(by)
    out = []
    for _ in ks:
        out += by[rnd.choice(ks)]
    return out


# ---------- statistics ----------
def mean(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else float("nan")


def pct(xs, q):
    xs = sorted(x for x in xs if x is not None and not math.isnan(x))
    if not xs:
        return float("nan")
    k = (len(xs) - 1) * q
    lo, hi = math.floor(k), math.ceil(k)
    return xs[lo] + (xs[hi] - xs[lo]) * (k - lo)


def p_star(k, r=PIX["r"], f=PIX["f"], delta_s=PIX["delta_s"], C_s=PIX["C_s"]):
    return (delta_s / C_s + f) / (r * (k - 1) + f)


def spearman(x, y):
    def ranks(v):
        order = sorted(range(len(v)), key=lambda i: v[i])
        rk, i = [0.0] * len(v), 0
        while i < len(v):
            j = i
            while j + 1 < len(v) and v[order[j + 1]] == v[order[i]]:
                j += 1
            for m in range(i, j + 1):
                rk[order[m]] = (i + j) / 2 + 1
            i = j + 1
        return rk
    if len(x) < 3:
        return float("nan")
    rx, ry = ranks(x), ranks(y)
    mx, my = mean(rx), mean(ry)
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    den = math.sqrt(sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry))
    return num / den if den else float("nan")


def rnd4(x):
    return None if x is None or (isinstance(x, float) and math.isnan(x)) else round(float(x), 4)


# ---------- analysis ----------
def analyze(client="desktop", B=2000, seed=20261027, exclude_censored=False):
    import numpy as np
    rng = np.random.default_rng(seed)
    pages, req = load_pages(client)
    groups, study = assign_groups(pages)
    n_probe = groups.pop("_probe_pages_removed")
    recs, page_excl = {}, {}
    for p in pages:
        r = req.get(p["page"])
        if r and r["main_status"] is not None and r["main_status"] != 200:
            page_excl[p["page"]] = "main document not 200"
            continue
        known = [n for n in (fnum(p.get("req_total")), r["n_requests"] if r else None) if n is not None]
        if known and max(known) < MIN_REQUESTS:
            page_excl[p["page"]] = f"fewer than {MIN_REQUESTS} requests"
            continue
        rec = page_record(p, r)
        if rec is None:
            page_excl[p["page"]] = "no DOM ready"
            continue
        recs[p["page"]] = rec
    val = load_validation()
    cal = {}
    vr = random.Random(seed)
    for name, rules in CALIBRATIONS.items():
        a, b = calib(val, rules)
        if math.isnan(a) or math.isnan(b):
            raise SystemExit(f"calibration {name}: an empty cell; check rule labels in validation_visits.csv")
        cal[name] = (a, b, np.array([calib(site_boot(val, vr), rules) for _ in range(B)]))

    def ys(gpages, rule):
        y, why = [], defaultdict(int)
        for p in gpages:
            rec = recs.get(p["page"])
            if rec is None:
                why[page_excl.get(p["page"], "not in data")] += 1
                continue
            v = rec.get(f"y_{rule}")
            if v is None:
                why["shift data missing" if not rec["shifts_ok"] else "rule time unavailable"] += 1
                continue
            if exclude_censored and rec[f"cens_{rule}"]:
                why["censored (sensitivity)"] += 1
                continue
            y.append(v)
        return y, dict(why)

    def boot(x):        # resampling a 0/1 list with replacement: the mean is Binomial(n, mean) / n
        return rng.binomial(len(x), sum(x) / len(x), size=B) / len(x)

    summary, boots, excl_rows = [], {}, []
    names = [g for g in ("BOOK", "MEDIA", "SHOP", "ADS", "GOV", "STUDY31") if groups.get(g)]
    names += sorted(g for g in groups if (":" in g or "@" in g) and groups[g])
    for g in names:
        for r in RULES:
            y, why = ys(groups[g], r)
            excl_rows.append(dict(group=g, rule=r, included=len(y), **{f"excluded: {k}": v for k, v in why.items()}))
            if not y:
                continue
            pi = sum(y) / len(y)
            bs = boot(y)
            boots[(g, r)] = bs
            gp = [recs[p["page"]] for p in groups[g] if p["page"] in recs and recs[p["page"]].get(f"y_{r}") is not None]
            row = dict(group=g, rule=r, rule_name=RULE_NAME[r], n_pages=len(y), shift_share=rnd4(pi),
                       shift_lo=rnd4(np.quantile(bs, .025)), shift_hi=rnd4(np.quantile(bs, .975)),
                       censored_share=rnd4(mean([x[f"cens_{r}"] for x in gp])),
                       visual_change_after_share=rnd4(mean([x[f"lvc_{r}"] for x in gp])))
            for cn, (a, b, AB) in cal.items():
                ph = a + (b - a) * pi
                pb = AB[:, 0] + (AB[:, 1] - AB[:, 0]) * bs
                row.update({f"stale_{cn}": rnd4(ph), f"stale_{cn}_lo": rnd4(np.nanquantile(pb, .025)),
                            f"stale_{cn}_hi": rnd4(np.nanquantile(pb, .975)),
                            f"check_pays_ordinary_{cn}": bool(ph > p_star(2)), f"check_pays_irreversible_{cn}": bool(ph > p_star(10))})
            summary.append(row)
    quiet, qboots = [], {}
    for g in names:
        gp = [recs[p["page"]] for p in groups[g] if p["page"] in recs and recs[p["page"]]["req_ok"]]
        if not gp:
            continue
        q = [0 if x["idle_capped"] else 1 for x in gp]
        qboots[g] = boot(q)
        idle = [x["idle_start"] + QUIET_MS - x["t0"] for x in gp if x["idle_start"] is not None]
        last = [x["last_shift_after_t0"] for x in gp if x["last_shift_after_t0"] is not None]
        quiet.append(dict(group=g, n_pages=len(q), never_quiet=sum(1 for x in gp if x["idle_start"] is None),
                          quiet_within_3s=rnd4(sum(q) / len(q)), lo=rnd4(np.quantile(qboots[g], .025)), hi=rnd4(np.quantile(qboots[g], .975)),
                          idle_after_dcl_median_s=rnd4(pct(idle, .5) / 1000), idle_after_dcl_p90_s=rnd4(pct(idle, .9) / 1000),
                          pages_with_shift_after_dcl=len(last), last_shift_after_dcl_median_s=rnd4(pct(last, .5) / 1000) if last else None,
                          last_shift_after_dcl_p90_s=rnd4(pct(last, .9) / 1000) if last else None))
    get = lambda g, r: next((s for s in summary if s["group"] == g and s["rule"] == r), None)

    def diff_test(ga, gb, r, label):
        na = get(ga, r)["n_pages"] if get(ga, r) else 0
        nb = get(gb, r)["n_pages"] if get(gb, r) else 0
        if min(na, nb) < MIN_N_TEST:
            return dict(test=label, testable=False, n_pages=(na, nb), ci_above_0=None)
        d = boots[(ga, r)] - boots[(gb, r)]
        return dict(test=label, testable=True, n_pages=(na, nb), estimate=rnd4(get(ga, r)["shift_share"] - get(gb, r)["shift_share"]),
                    lo=rnd4(np.quantile(d, .025)), hi=rnd4(np.quantile(d, .975)), ci_above_0=bool(np.quantile(d, .025) > 0),
                    censored_share=(get(ga, r)["censored_share"], get(gb, r)["censored_share"]))

    def quiet_test(ga, gb, label):
        qn = {q["group"]: q["n_pages"] for q in quiet}
        if min(qn.get(ga, 0), qn.get(gb, 0)) < MIN_N_TEST:
            return dict(test=label, testable=False, n_pages=(qn.get(ga, 0), qn.get(gb, 0)), ci_above_0=None)
        d = qboots[gb] - qboots[ga]
        qv = {q["group"]: q["quiet_within_3s"] for q in quiet}
        return dict(test=label, testable=True, n_pages=(qn[ga], qn[gb]), estimate=rnd4(qv[gb] - qv[ga]), lo=rnd4(np.quantile(d, .025)), hi=rnd4(np.quantile(d, .975)),
                    ci_above_0=bool(np.quantile(d, .025) > 0))

    def reweighted(ga, gb, r):
        """ga against gb reweighted to ga's mix of rank buckets, both restricted to buckets present in both."""
        parts = []
        for b in RANK_BUCKETS:
            ya = ys(groups.get(f"{ga}@rank<={b}", []), r)[0]
            yb = ys(groups.get(f"{gb}@rank<={b}", []), r)[0]
            if ya and yb:
                parts.append((ya, yb))
        if not parts:
            return None
        tot = sum(len(ya) for ya, _ in parts)
        if tot < MIN_N_TEST or sum(len(yb) for _, yb in parts) < MIN_N_TEST:
            return None
        est_a = sum(sum(ya) for ya, _ in parts) / tot
        est_b = sum(len(ya) / tot * mean(yb) for ya, yb in parts)
        bs_a = sum(len(ya) / tot * boot(ya) for ya, _ in parts)
        bs_b = sum(len(ya) / tot * boot(yb) for ya, yb in parts)
        return est_a - est_b, bs_a - bs_b, tot

    hyp = {}
    hyp["C1"] = diff_test("BOOK", "GOV", "S5", "after the network-idle screenshot (3 s cap), BOOK pages shift within 6.5 s more often than GOV pages")
    hyp["C2"] = quiet_test("BOOK", "GOV", "BOOK pages reach 500 ms of network quiet within 3 s of DOM ready less often than GOV pages")
    rw = reweighted("BOOK", "GOV", "S5")
    if rw:
        est, d, n = rw
        hyp["C1_rank_reweighted"] = dict(test="secondary: C1 with GOV reweighted to BOOK's rank buckets (buckets present in both)",
                                         n_book_pages=n, estimate=rnd4(est), lo=rnd4(np.quantile(d, .025)), hi=rnd4(np.quantile(d, .975)),
                                         ci_above_0=bool(np.quantile(d, .025) > 0))
    hyp["C1_SHOP"] = diff_test("SHOP", "GOV", "S5", "secondary: C1 with SHOP in place of BOOK")
    hyp["C2_SHOP"] = quiet_test("SHOP", "GOV", "secondary: C2 with SHOP in place of BOOK")
    # C3 transfer check
    burst = {r["site"]: fnum(r["burst_2s"]) for r in csv.DictReader(open(HERE / "inputs" / "settle_cls_by_page.csv"))}
    xs, ys_ = [], []
    for p in groups.get("STUDY31", []):
        site, rec = study.get(p["host"]), recs.get(p["page"])
        if site in burst and burst[site] is not None and rec and rec.get("y_S0") is not None:
            xs.append(rec["y_S0"]); ys_.append(burst[site])
    rho, rb, degen = spearman(xs, ys_), [], 0
    for _ in range(B if len(xs) >= 3 else 0):
        idx = rng.integers(0, len(xs), len(xs))
        v = spearman([xs[i] for i in idx], [ys_[i] for i in idx])
        if math.isnan(v):
            degen += 1
            v = 0.0
        rb.append(v)
    hyp["C3"] = dict(test="transfer: on the study's own sites, a crawl shift after DOM ready goes with the burst the study measured (Spearman rho > 0)",
                     n_pages=len(xs), estimate=rnd4(rho), lo=rnd4(pct(rb, .025)) if rb else None, hi=rnd4(pct(rb, .975)) if rb else None,
                     degenerate_resamples_scored_0=degen, testable=len(xs) >= 10, ci_above_0=bool(rb) and pct(rb, .025) > 0)
    # level check: crawl-based estimate for the study's sites vs what the study measured, per rule
    level = []
    meas = defaultdict(lambda: [0, 0])
    for v in val:
        meas[v["rule"]][0] += v["tracks"]; meas[v["rule"]][1] += v["stale"]
    for r, mr in (("S0", "S0"), ("S1", "S1"), ("S2", "S2"), ("S4", "S4"), ("S5u", "S5")):  # the study's S5 had no cap
        s = get("STUDY31", r)
        if s:
            level.append(dict(crawl_rule=r, study_rule=mr, crawl_shift_share=s["shift_share"], crawl_stale_pooled=s["stale_pooled"],
                              study_measured_stale=rnd4(meas[mr][1] / meas[mr][0]) if meas[mr][0] else None, n_pages=s["n_pages"]))
    from collections import Counter
    pairs = [(fnum(p.get("req_total")), req[p["page"]]["n_requests"]) for p in pages if p["page"] in req and fnum(p.get("req_total"))]
    mismatch = sum(1 for a_, b_ in pairs if abs(a_ - b_) > 0.1 * a_)
    meta = dict(client=client, n_page_rows=len(pages), probe_pages_removed=n_probe, pages_excluded=dict(Counter(page_excl.values())),
                requests_vs_reqTotal=dict(pages_compared=len(pairs), off_by_more_than_10pct=mismatch),
                pages_without_request_rows=sum(1 for p in pages if p["page"] not in req),
                calibration={k: dict(a=rnd4(v[0]), b=rnd4(v[1])) for k, v in cal.items()},
                p_star_ordinary=rnd4(p_star(2)), p_star_irreversible=rnd4(p_star(10)), boot=B, seed=seed,
                exclude_censored=exclude_censored, group_sizes={g: len(v) for g, v in sorted(groups.items())})
    return dict(summary=summary, quiet=quiet, hyp=hyp, level=level, exclusions=excl_rows, meta=meta)


def write_csv(path, rows):
    if not rows:
        return
    keys = []
    for r in rows:
        keys += [k for k in r if k not in keys]
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows(rows)


def run(client="desktop", B=2000):
    out = HERE / "results" / f"analysis_{client}"
    out.mkdir(parents=True, exist_ok=True)
    main_ = analyze(client, B)
    sens = analyze(client, B, exclude_censored=True)
    h = main_["hyp"]
    # C1 holds only if its interval lies above 0 both with censored pairs counted and with them dropped
    def decide(x):
        return None if not x or not x.get("testable", True) else bool(x["ci_above_0"])
    if h.get("C1"):
        s1 = sens["hyp"].get("C1")
        h["C1"]["drop_censored"] = s1
        if decide(h["C1"]) is None:
            h["C1"]["held"] = None                      # untestable
        elif decide(s1) is None:                        # too few pages left once censored pairs are dropped
            h["C1"]["held"] = decide(h["C1"])
            h["C1"]["note"] = "drop-censored analysis untestable (fewer than 30 pages); decided on the primary analysis"
        else:
            h["C1"]["held"] = decide(h["C1"]) and decide(s1)
    for k in ("C2", "C3"):
        if h.get(k):
            h[k]["held"] = decide(h[k])
    write_csv(out / "shift_and_stale_by_group_rule.csv", main_["summary"])
    write_csv(out / "shift_and_stale_by_group_rule__drop_censored.csv", sens["summary"])
    write_csv(out / "network_quiet.csv", main_["quiet"])
    write_csv(out / "level_check_study31.csv", main_["level"])
    write_csv(out / "exclusions.csv", main_["exclusions"])
    (out / "hypotheses.json").write_text(json.dumps(h, indent=2))
    (out / "meta.json").write_text(json.dumps(main_["meta"], indent=2))
    return main_, sens


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--client", default="desktop")
    ap.add_argument("--boot", type=int, default=2000)
    a = ap.parse_args()
    m, _ = run(a.client, a.boot)
    print(json.dumps(m["hyp"], indent=2))
    print(json.dumps(m["meta"], indent=2))


if __name__ == "__main__":
    main()
