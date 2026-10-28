# Commercial pages, measured from the HTTP Archive crawl

This folder measures how long commercial home pages keep loading and moving after an agent's wait, without visiting any of them. Commercial sites' terms of use usually prohibit automated access, so all page data comes from the [HTTP Archive](https://httparchive.org)'s public monthly crawl in BigQuery. The preregistration is `docs/PREREG_COMMERCIAL.md` (tag `prereg-com-v1` in the study repository); results are in `results/commercial/RESULTS_COM.md`.

| File | What it is |
|---|---|
| `domains.csv` | BOOK: 69 booking and buying domains in 6 categories, listed before any data was read; MEDIA: 10 news, sports and weather domains |
| `study31.csv` | the 31 real-page study pages, for the transfer check |
| `probe_domains.txt` | the ten domains the schema probe reads; excluded from every result |
| `sql/` | BigQuery templates: crawl dates, two schema probes, a request-field check, pages, requests |
| `run.py` | runs the queries with `bq`: dry run first, a hard byte cap on every query, CSV out, a log in `results/run_log.json` |
| `config.json` | the frozen configuration, including the author's approvals (see below) |
| `analyze.py` | the analysis: wait rules, outcomes, hypotheses C1 to C3, the decision table |
| `tests/test_analyze.py` | checks `analyze.py` on inputs with known answers |
| `validate_proxy.py` | builds `inputs/validation_visits.csv` from the real-page visit logs (the logs are not public; the derived file is included) |
| `spot_check.py` | recomputes every rule by hand for three booking and three .gov pages |
| `fig_airline.py` | the paper's Figure 1: one airline's home page from the crawl |
| `fig_commercial.py` | the paper's Figure 3 |
| `run_exploratory.py` | the exploratory runs: mobile home pages and desktop inner pages |

## Rerun the analysis without BigQuery

The desktop query outputs are in `data/commercial/` (from the HTTP Archive crawl of October 2026). From the repository root:

```bash
mkdir -p src/commercial/results
gunzip -c data/commercial/pages_desktop.csv.gz > src/commercial/results/pages_desktop.csv
gunzip -c data/commercial/requests_desktop.csv.gz > src/commercial/results/requests_desktop.csv
uv run python src/commercial/tests/test_analyze.py
uv run python src/commercial/analyze.py          # writes src/commercial/results/analysis_desktop/
```

With Python 3.12 and numpy 2.5.4, as pinned in `uv.lock`, the output is identical to `results/commercial/analysis_desktop/`. With another numpy version the bootstrap intervals can differ slightly; every point estimate and hypothesis outcome stays the same.

Every frozen file in this folder matches its SHA-256 in the preregistration's freeze record.

## Rerun the queries on your own GCP project

You need the `bq` command-line tool and a GCP project with BigQuery enabled. Every query runs with a dry run first and a hard `--maximum_bytes_billed` cap, so a query that would exceed its cap fails without charge.

1. Set `requests_approved` to `false` in `config.json`. The frozen file carries the author's approval for the requests query; give your own after reading its estimate.
2. `python3 src/commercial/run.py estimate --project YOUR_PROJECT` prints the dry-run estimates. On clustered tables these are upper bounds: in the study, the requests query was estimated at 4,466 GB and processed 128 GB.
3. `python3 src/commercial/run.py main --project YOUR_PROJECT` runs the pages query, and the requests query once you set `requests_approved` to `true`.
4. `python3 src/commercial/analyze.py`.

To measure a later crawl, change `crawl_date` in `config.json`. That run is a new study, not a replication of the preregistered one.

## Data

The per-page rows are derived from the HTTP Archive crawl. The HTTP Archive's maintainers ask for attribution when the data is used. Each row is one home page from one WebPageTest load (desktop Chrome, cable connection, US test locations, empty cache, no login). The paper names no individual site.
