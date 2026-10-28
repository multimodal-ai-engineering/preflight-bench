"""Run the commercial-page queries on HTTP Archive (BigQuery), with a dry run and a byte cap on every query.

  python3 run.py probe --project PROJECT_ID     # Step 1: crawl dates, schema probe, cost estimates for Step 2
  python3 run.py estimate --project PROJECT_ID  # dry-run cost of Step 2 with the current config.json (reads no data)
  python3 run.py main  --project PROJECT_ID     # Step 2: the two data queries (only after the probe is reviewed)
  python3 run.py render                         # print the rendered SQL without running anything

Needs the bq command-line tool, already authenticated. Every query is dry-run first and then runs with a hard byte
limit (--maximum_bytes_billed = cap_gb in config.json): BigQuery fails it without charge rather than exceed the
limit. An exact (PRECISE) estimate above the cap stops the script before running; on clustered tables the dry run
gives only an upper bound, which is recorded. The requests query also needs requests_approved = true in
config.json, set after its cost estimate has been seen. Results go to results/ as CSV; run_log.json records each job
id, bytes processed and billed, and the SHA-256 of the exact SQL that ran.
"""
import argparse, csv, datetime as dt, hashlib, json, re, subprocess, sys
from pathlib import Path
from urllib.parse import urlparse

HERE = Path(__file__).resolve().parent
SQL, RES = HERE / "sql", HERE / "results"
CFG_PATH = HERE / "config.json"
DEFAULTS = {
    "crawl_date": None,            # set by the probe: the latest complete monthly crawl
    "client": "desktop",
    "cat_ecom": "Ecommerce",       # technology category names; the probe confirms them
    "cat_ads": "Advertising",
    "shifts_key": "_LayoutShifts", # payload field names; the probe confirms them
    "shift_time": "time",
    "shift_score": "score",
    "req_start": "_all_start",
    "req_end": "_all_end",
    "req_status": "response.status", # path to the HTTP status in the request payload; the probe confirms it
    "gov_permille": 1000,          # deterministic hash samples (h = fingerprint(page) mod 1000, made non-negative; kept if h < permille)
    "ecom_permille": 40,
    "ads_permille": 15,
    "cap_gb": {"00": 20, "01": 60, "02": 150, "10": 700, "11": 1500},
    "probe_reviewed": False,       # set to true only after the probe output has been checked
    "requests_approved": False,    # set to true only after the requests query's cost estimate has been approved
}


def cfg():
    c = dict(DEFAULTS)
    if CFG_PATH.exists():
        c.update(json.loads(CFG_PATH.read_text()))
    return c


def save_cfg(c):
    CFG_PATH.write_text(json.dumps(c, indent=2) + "\n")


def quoted(xs):
    xs = sorted(set(xs))
    if not xs:
        raise SystemExit("empty list")
    for x in xs:
        if not re.fullmatch(r"[a-z0-9.-]+", x):
            raise SystemExit(f"unexpected characters in {x!r}")
    return ", ".join(f"'{x}'" for x in xs)


KEY_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def render(name, c, client=None, req_probe_filter="is_main_document"):
    for k in ("shifts_key", "shift_time", "shift_score", "req_start", "req_end", "req_status"):
        if not all(KEY_RE.fullmatch(part) for part in str(c[k]).split(".")):
            raise SystemExit(f"config.json: {k} = {c[k]!r} is not a plain field name")
    for k in ("cat_ecom", "cat_ads"):
        if not re.fullmatch(r"[A-Za-z][A-Za-z &-]*", str(c[k])):
            raise SystemExit(f"config.json: {k} = {c[k]!r} has unexpected characters")
    doms = list(csv.DictReader(open(HERE / "domains.csv")))
    probe = [l.strip() for l in open(HERE / "probe_domains.txt") if l.strip()]
    study_hosts = [urlparse(r["url"]).hostname for r in csv.DictReader(open(HERE / "study31.csv"))]
    sql = (SQL / name).read_text()
    if "{{SELECTION}}" in sql:
        sel = (SQL / "_selection.sql").read_text()
        sel = "\n".join(l for l in sel.splitlines() if not l.startswith("--"))
        sql = sql.replace("{{SELECTION}}", sel).replace("{{PAYLOAD}}", ", payload, summary" if name.startswith("10") else "")
    rep = {
        "CRAWL_DATE": c["crawl_date"] or "YYYY-MM-DD",
        "CLIENT": client or c["client"],
        "BOOK_DOMAINS": quoted(d["domain"] for d in doms if d["group"] == "BOOK"),
        "MEDIA_DOMAINS": quoted(d["domain"] for d in doms if d["group"] == "MEDIA"),
        "STUDY_HOSTS": quoted(study_hosts),
        "PROBE_DOMAINS": quoted(probe),
        "REQ_PROBE_FILTER": req_probe_filter,
        "CAT_ECOM": c["cat_ecom"], "CAT_ADS": c["cat_ads"],
        "SHIFTS_KEY": c["shifts_key"], "SHIFT_TIME": c["shift_time"], "SHIFT_SCORE": c["shift_score"],
        "REQ_START": c["req_start"], "REQ_END": c["req_end"], "REQ_STATUS": c["req_status"],
        "GOV_PERMILLE": str(int(c["gov_permille"])), "ECOM_PERMILLE": str(int(c["ecom_permille"])),
        "ADS_PERMILLE": str(int(c["ads_permille"])),
    }
    for k, v in rep.items():
        sql = sql.replace("{{" + k + "}}", v)
    left = re.findall(r"\{\{[A-Z_]+\}\}", sql)
    if left:
        raise SystemExit(f"unfilled placeholders in {name}: {left}")
    return sql


def bq(project, args, check=True):
    cmd = ["bq", "--quiet", "--headless", f"--project_id={project}"] + args
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0 and check:
        sys.stderr.write(p.stdout + p.stderr)
        raise SystemExit(f"bq failed: {' '.join(cmd[:6])} ...")
    return p.stdout if check else p


def dry_run(project, sql):
    """Bytes the query would process, and whether BigQuery calls that exact (PRECISE) or an upper bound
    (clustered tables: the dry run cannot apply cluster pruning)."""
    out = bq(project, ["query", "--use_legacy_sql=false", "--dry_run", "--format=json", "\n" + sql])
    try:
        st = json.loads(out)["statistics"]
        return int(st["totalBytesProcessed"]), st.get("totalBytesProcessedAccuracy", "UNKNOWN")
    except (ValueError, KeyError, TypeError):
        m = re.search(r"process (upper bound of )?(\d+) bytes", out)
        if not m:
            raise SystemExit(f"could not read the dry-run estimate:\n{out}")
        return int(m.group(2)), ("UPPER_BOUND" if m.group(1) else "UNKNOWN")


def run_query(project, key, name, sql, out_csv, c, log):
    cap = int(c["cap_gb"][key] * 1e9)
    est, acc = dry_run(project, sql)
    print(f"{name}: dry run {est / 1e9:.1f} GB ({acc}); hard cap {cap / 1e9:.0f} GB")
    if acc == "PRECISE" and est > cap:
        raise SystemExit(f"{name}: exact estimate above the cap; nothing was run. Raise cap_gb['{key}'] only deliberately.")
    job = f"preflight_com_{key}_{dt.datetime.now(dt.timezone.utc):%Y%m%d_%H%M%S}"
    p = bq(project, ["query", "--use_legacy_sql=false", "--format=csv", "--max_rows=100000000",
                     f"--maximum_bytes_billed={cap}", f"--job_id={job}", "\n" + sql], check=False)  # leading newline: bq reads an argument starting with "--" as a flag
    if p.returncode != 0:
        msg = (p.stdout + p.stderr).strip()
        log.append(dict(query=name, job_id=job, failed=True, dry_run_bytes=est, dry_run_accuracy=acc, cap_bytes=cap, error=msg[-2000:]))
        if "bytes billed" in msg.lower() or "maximum bytes" in msg.lower():
            raise SystemExit(f"{name}: BigQuery refused to run it under the {cap / 1e9:.0f} GB cap; nothing was billed.\n{msg[-600:]}")
        raise SystemExit(f"{name}: query failed.\n{msg[-1200:]}")
    data = p.stdout
    out_csv.write_text(data)
    stats = json.loads(bq(project, ["show", "--format=json", "-j", job])).get("statistics", {})
    rows = max(0, data.count("\n") - 1)
    log.append(dict(query=name, job_id=job, rows=rows, dry_run_bytes=est, dry_run_accuracy=acc, cap_bytes=cap,
                    bytes_processed=int(stats.get("totalBytesProcessed", 0) or 0),
                    bytes_billed=int(stats.get("query", {}).get("totalBytesBilled", 0) or 0),
                    sql_sha256=hashlib.sha256(sql.encode()).hexdigest(), at=dt.datetime.now(dt.timezone.utc).isoformat(),
                    output=str(out_csv.relative_to(HERE))))
    print(f"{name}: {rows} rows -> {out_csv.relative_to(HERE)}")


def pick_crawl_date(csv_text):
    rows = [(r["date"], int(r["root_pages"])) for r in csv.DictReader(csv_text.splitlines())]
    rows.sort(reverse=True)
    if not rows:
        raise SystemExit("no crawls found")
    counts = [n for _, n in rows]
    ref = sorted(counts)[len(counts) // 2]  # median month
    for d, n in rows:  # newest first: the latest crawl that is at least 95% of a typical month is complete
        if n >= 0.95 * ref:
            return d, rows
    return rows[0][0], rows


def estimate(project, c):
    est = {n: dry_run(project, render(n, c)) for n in ("10_pages.sql", "11_requests.sql")}
    (RES / "step2_cost_estimate.json").write_text(json.dumps({k: {"bytes": v[0], "GB": round(v[0] / 1e9, 1), "accuracy": v[1]}
                                                               for k, v in est.items()}, indent=2))
    print("Step 2 estimates (dry run only):", {k: f"{v[0] / 1e9:.1f} GB ({v[1]})" for k, v in est.items()})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("step", choices=["probe", "estimate", "main", "render"])
    ap.add_argument("--project")
    ap.add_argument("--client", default=None, help="desktop (primary) or mobile (exploratory)")
    a = ap.parse_args()
    c = cfg()
    RES.mkdir(exist_ok=True)
    if a.step == "render":
        for n in ("00_crawl_dates.sql", "01_probe_pages.sql", "02_probe_requests.sql", "10_pages.sql", "11_requests.sql"):
            print(f"-- ===== {n} =====\n{render(n, c, a.client)}\n")
        return
    if not a.project:
        raise SystemExit("--project is required")
    log_path = RES / "run_log.json"
    log = json.loads(log_path.read_text()) if log_path.exists() else []
    try:
        if a.step == "probe":
            meta = {t: json.loads(bq(a.project, ["show", "--format=json", f"httparchive:crawl.{t}"])) for t in ("pages", "requests")}
            keep = lambda m: {k: m.get(k) for k in ("numBytes", "numRows", "timePartitioning", "clustering", "lastModifiedTime")}
            (RES / "table_meta.json").write_text(json.dumps({t: keep(m) for t, m in meta.items()}, indent=2))
            req_cluster = (meta["requests"].get("clustering") or {}).get("fields", [])
            print("pages clustered on", (meta["pages"].get("clustering") or {}).get("fields"), "| requests clustered on", req_cluster)
            run_query(a.project, "00", "00_crawl_dates", render("00_crawl_dates.sql", c), RES / "crawl_dates.csv", c, log)
            c["crawl_date"], rows = pick_crawl_date((RES / "crawl_dates.csv").read_text())
            save_cfg(c)
            print("crawl months:", ", ".join(f"{d} ({n:,})" for d, n in rows), "\nusing", c["crawl_date"])
            run_query(a.project, "01", "01_probe_pages", render("01_probe_pages.sql", c), RES / "probe_pages.csv", c, log)
            rpf = "is_main_document OR type IN ('font', 'other')" if "type" in req_cluster else "is_main_document"
            run_query(a.project, "02", "02_probe_requests", render("02_probe_requests.sql", c, req_probe_filter=rpf), RES / "probe_requests.csv", c, log)
            estimate(a.project, c)
            print("Probe done. Only the ten probe home pages were read; none is in an analysis group.")
        elif a.step == "estimate":
            if not c.get("crawl_date"):
                raise SystemExit("config.json has no crawl_date; run the probe first.")
            estimate(a.project, c)
        else:
            if not c.get("crawl_date"):
                raise SystemExit("config.json has no crawl_date; run the probe first.")
            if not c.get("probe_reviewed"):
                raise SystemExit("config.json: probe_reviewed is false. The probe output must be checked first.")
            client = a.client or c["client"]
            run_query(a.project, "10", f"10_pages_{client}", render("10_pages.sql", c, client), RES / f"pages_{client}.csv", c, log)
            if not c.get("requests_approved"):
                est = json.loads((RES / "step2_cost_estimate.json").read_text()).get("11_requests.sql", {}) if (RES / "step2_cost_estimate.json").exists() else {}
                raise SystemExit(f"Pages query done. The requests query is not approved yet (estimate {est.get('GB')} GB, {est.get('accuracy')}); "
                                 "set requests_approved and cap_gb['11'] in config.json to run it.")
            run_query(a.project, "11", f"11_requests_{client}", render("11_requests.sql", c, client), RES / f"requests_{client}.csv", c, log)
    finally:
        log_path.write_text(json.dumps(log, indent=2) + "\n")


if __name__ == "__main__":
    main()
