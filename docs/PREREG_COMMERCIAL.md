# Preregistration addendum: commercial pages (HTTP Archive, no new site visits)

Status: **frozen 2026-10-27, tag `prereg-com-v1`** (see Freeze record). It was frozen once the author approves it and the schema probe (Step 1) has been reviewed, and before Step 2 reads any row for the analysis groups. Freezing records:

- the tag `prereg-com-v1`;
- the date;
- the SHA-256 of this file, `analyze.py`, `run.py`, `validate_proxy.py`, every file in `sql/`, `domains.csv`, `study31.csv`, `probe_domains.txt`, and `config.json` as completed after the probe.

It adds to `docs/PREREGISTRATION.md`, `docs/PREREG_EXTENSION.md` and `docs/PREREG_ADDITIONS.md`, which stay unchanged. Every result is labelled "commercial" and lives in `commercial/results/`. Any change after freezing is a deviation and gets its own section.

## Why

The real-page study measured 31 public, non-commercial pages whose terms permit automated access. On them, a screenshot taken after network idle left 0.46% of planned clicks stale. Agents book, buy and pay on commercial pages, and those pages' terms of use usually prohibit automated access, so we do not visit them.

Instead we use the HTTP Archive's public monthly crawl. It loads about 13 million desktop sites with WebPageTest and records, for each page:

- the time and score of every layout shift;
- DOM-ready and load times;
- the start and end of every network request.

The claim concerns **home pages**. Inner pages (search results, checkout) are exploratory.

## What was seen before this was written

- Every result of the earlier registrations, including the 31-page numbers.
- **The layout-shift validation below.** It was computed on Addition 1's visits on 2026-10-27, before this document was written, so it is exploratory. It fixes the calibration used here.
- Informal observations on 2026-10-27 of two commercial pages, a weather site and an airline home page: content was inserted several seconds after DOM ready, and network activity never stopped. These motivated the study and are not used in any result.
- No HTTP Archive data. Step 1 reads ten home pages listed in `probe_domains.txt`, chosen outside every analysis group, to confirm field names. They are excluded from every result.

## Validation: a layout shift after the screenshot predicts stale clicks (31 pages, exploratory)

- **Shift:** in an Addition 1 visit (664 visits, 31 sites), a shift means the page's cumulative layout shift rose by more than 0.0001 between the planning screenshot and the end of tracking at 6.5 s. Cumulative layout shift here is the raw sum of `layout-shift` entries without recent input.
- **Stale:** a tracked target is stale if `go_ok` was false at 0.5, 1, 2 or 6.5 s.

| Visits | Tracked clicks | Stale | Share stale (site-bootstrap 95% CI) |
|---|---|---|---|
| a shift after the screenshot | 1,357 | 313 | b = 23.1% (14.7–33.4) |
| no shift | 7,752 | 69 | a = 0.89% (0.16–2.0) |

Of all stale clicks, 82% (60–96) occurred in visits with a shift. The other 18% come from content that covers or swaps a target without registering a shift, so the estimates below are expected to run low on pages with pop-ups.

Two features limit the calibration:

1. **It differs by rule.** In visits with a shift, the share of stale clicks was 38% after the DOM-ready screenshot and 15% across S1–S5. In the 9 network-idle visits with a shift, no click was stale (0 of 72).
2. **It does not rise steadily with shift size.** By the size of the rise in layout shift, the stale share was 8.5% up to 0.01, 39% from 0.01 to 0.05, 56% from 0.05 to 0.1, and 15% above 0.1.

The **primary crawl outcome is therefore the share of pages that shift after the screenshot**, which is measured directly. Stale-click estimates are reported with two calibrations, and no hypothesis rests on them.

Code: `validate_proxy.py`. Data: `inputs/validation_visits.csv`.

## Data

- **Source:** `httparchive.crawl.pages` and `httparchive.crawl.requests`, from the latest complete monthly crawl when Step 1 runs: the newest crawl with at least 95% of a typical month's desktop root pages. The date is recorded in `config.json`.
- **Client:** desktop is primary; mobile is exploratory. Desktop means WebPageTest desktop Chrome at 1376×768, a cable connection (5/1 Mbps, 28 ms), US test locations, an empty cache and no login.
- **Pages:** root pages (home pages) of origins with a CrUX rank of at most 1,000,000.
- **Excluded pages, counted per group and rule:**
  - the final main document did not return status 200;
  - fewer than 10 requests (when a count is known), which marks an error or bot-challenge page;
  - no DOM-ready time.
- **Probe domains:** removed before grouping; their number is reported.
- **Completeness check:** pages whose request rows differ from the page's own request count by more than 10% are counted and reported.

## Groups

- **BOOK** (primary): booking and buying sites. The 69 registered domains in `domains.csv` cover six categories: airlines; lodging and travel agencies; car, rail and bus; restaurants and food delivery; tickets, movies and events; retail. The author wrote the list before seeing any data, as well-known US consumer brands per category; no outcome was used to choose it. Each domain contributes one page: its apex or `www.` root page, and otherwise the root page with the best rank.
- **GOV** (primary baseline): root pages whose host ends in `.gov`.
- **SHOP** (secondary, population scale): pages where HTTP Archive's technology detection (Wappalyzer) reports a technology in the e-commerce category, excluding BOOK, MEDIA, GOV and STUDY31. Sampled by deterministic hash, `h < 40` per mille.
- **ADS** (exploratory): pages with a technology in the advertising category, with the same exclusions, `h < 15` per mille.
- **MEDIA** (exploratory): the 10 news, sports and weather domains in `domains.csv`.
- **STUDY31** (transfer check): the root pages of the 31 study pages' hosts that appear in the crawl. For 13 of the 31, the study page is an inner page, so the comparison is with the origin's home page.

GOV, SHOP and ADS are capped at 5,000 pages each, keeping the lowest hash values. Here `h = fingerprint(page) mod 1000`, made non-negative.

## Wait rules

Times are milliseconds from navigation start, WebPageTest's time base, which the probe confirms. Let t0 be the end of the DOMContentLoaded event (`_domContentLoadedEventEnd`, or the event's start if the end is missing). Each rule's screenshot time T is:

- **S0** t0 (DOM ready; two of the ten agents in the paper use this);
- **S1** t0 + 0.5 s;
- **S2** t0 + 1 s;
- **S4** the load event (`_docTime`);
- **S5** network idle with a 3 s cap (the paper's rule 1):
  - Find the first window of 500 ms, starting at or after t0, with no request in flight.
  - The screenshot is at the end of that window, which is when a network-idle wait returns.
  - If that is later than t0 + 3 s, the screenshot is at t0 + 3 s.
  - A request is in flight from `_all_start` to `_all_end`. If either value is missing or negative, `_load_start` or `_load_end` is used instead. A request that never finished stays in flight. If a request has no start time, S5 is missing for that page.
- **S5u** (exploratory) network idle without the cap, as in Addition 1. A page that never goes quiet is screenshot at the last recorded moment, as a timed-out wait would be, and counts as censored.

S3 and S3b from Addition 1 need a live page and cannot be reproduced from the crawl.

## Outcome

- **Shift after the screenshot**, per page and rule: the layout-shift scores with times in (T, T + 6.5 s] sum to more than 0.0001. This is the same quantity and threshold as in the validation.
- **Missing data:**
  - If the crawl lists no shifts for a page and its CLS is 0, the page has no shifts.
  - If it lists none and its CLS is above 0 or unknown, the page is excluded from shift outcomes.
  - All exclusions are counted per group and rule.
- **Observation end:** WebPageTest stops recording once the page is fully loaded. The observation end is the latest of fully loaded, the load event, the last request end and the last shift.
  - If it comes before T + 6.5 s, the unobserved remainder counts as having no shifts. This is a conservative assumption.
  - Because pages that go quiet early are watched for less time, a pre-specified sensitivity analysis drops these page-rule pairs. C1 must hold in both analyses.
- **Estimated stale-click share** (reported, no hypothesis): p̂ = a + (b − a) × π, where π is the group's shift share.
  - a and b come from two calibrations: all Addition 1 visits pooled, and S1–S5 visits only.
  - Each p̂ has a 95% interval that combines a bootstrap over pages (2,000 resamples) with a bootstrap over the 31 validation sites.

## Hypotheses (desktop, home pages)

- **C1.** After the network-idle screenshot (S5), BOOK pages shift within 6.5 s more often than GOV pages. The 95% interval of the difference must lie above 0, both in the primary analysis and with censored page-rule pairs dropped. If fewer than 30 pages of either group remain once censored pairs are dropped, that check is reported as untestable and C1 rests on the primary analysis.
- **C2.** BOOK pages reach 500 ms of network quiet within 3 s of DOM ready less often than GOV pages. The 95% interval of the difference must lie above 0.
- **C3 (transfer check).** On the STUDY31 pages, a crawl shift after DOM ready (S0) goes with a larger post-navigation burst in the study, measured as the share of clicks stale within 2 s at S0 (`settle_cls_by_page.csv`).
  - The test is Spearman ρ, with a bootstrap 95% interval above 0. Resamples where every page has the same crawl value count as ρ = 0, and their number is reported.
  - A level check sets the crawl estimate for STUDY31 beside the stale share the study measured, rule by rule (the crawl's S5u against the study's uncapped S5).
  - If C3 fails, the crawl results are reported as an unvalidated proxy.

Each hypothesis is reported as held, refuted or untestable, with its estimate and interval. A test is untestable if either group has fewer than 30 pages (10 for C3).

**Secondary analyses (pre-specified):**

- C1 with GOV reweighted to BOOK's mix of rank buckets (top 1k, 10k, 100k, 1M), using the buckets present in both groups, in the primary analysis;
- C1 and C2 with SHOP in place of BOOK.

## Decision analysis (no hypothesis)

For each group and rule, p̂ is set against the pixel check's break-even point from the paper (82% detection, 4% false alarms, 0.31 s, 6.5 s planner):

- p* ≈ 10% for an ordinary click (k = 2);
- p* ≈ 1.2% for an irreversible one (k = 10).

The table shows whether the check pays under each calibration.

## Exploratory (labelled as such)

- per BOOK category;
- ADS and MEDIA against GOV;
- rank strata;
- time of the last shift after DOM ready, and time to network quiet without the cap;
- the share of pages whose last visual change in the video comes after each rule's screenshot (an upper bound that also counts pop-ups and carousels);
- mobile;
- inner pages.

## Procedure and cost

- **Step 1** (`python3 run.py probe --project …`): table metadata (partitioning, clustering, sizes), the available crawl months, the schema probe, and dry-run estimates for Step 2. The probe may change only the payload field names and the two technology category names. Each change is logged before Step 2.
- **Step 2** (`python3 run.py main --project …`): the pages query and the requests query.
- **Cost control:** every query runs with a hard byte limit (`--maximum_bytes_billed`, `config.json`), so it fails without charge rather than exceed it.
  - Dry-run estimates on clustered tables are upper bounds, and both are recorded.
  - The requests query must read the request payload column for the whole month, because the crawl cannot be narrowed to the selected pages. It may exceed BigQuery's free monthly allowance, so its estimate is shown after Step 1. It runs only after the author sets `requests_approved` in `config.json`, and run.py enforces this.
- **Reporting:** the paper reports groups and categories and names no individual site. Per-page rows from the public crawl go in the repository.
- **Analysis code:** `analyze.py`, tested by `tests/test_analyze.py` on inputs with known answers.

## Freeze record

- **Date:** 2026-10-27. **Tag:** `prereg-com-v1`. Crawl: 2026-10-01, desktop.
- **Author's decisions at STOP 1:** the requests probe (`02_probe_requests`, refused under its 150 GB cap at an estimate of 1,712 GB) is skipped; the request field names were checked instead by an extra query on HTTP Archive's 10k-page sample (`sql/03_check_request_fields.sql`, 7.9 GB). `requests_approved` = true and `cap_gb["11"]` = 4,500 GB (estimate 4,466 GB); the other caps are unchanged.
- **Changes made before the freeze, approved by the author:** `run.py` passes each query to `bq` with a leading newline (`bq` read a query starting with a `--` comment as a flag), and passes `summary` as well as `payload` into the pages query's selection (`10_pages.sql` reads `summary.reqTotal`). `config.json`: `crawl_date`, `probe_reviewed`, `requests_approved`, `cap_gb["11"]`. Details in `results/RESULTS_COM.md`.
- **SHA-256.** The hash of this file is of its text with this section reading "(filled in at freezing)"; a file cannot contain its own hash.

| File | SHA-256 |
|---|---|
| `PREREG_COMMERCIAL.md` | `97264f51055030dfb1f258d095a88917e4c5b4b6a78ac9ddf2894db45381e425` |
| `analyze.py` | `efad749e99efa6871944aa8d8289040f5a7737da7c1c29f6331ad23af5ad339f` |
| `run.py` | `bdd85fde108a719f144840408a88450c95b3a1063da66f564d10c735d0fb382b` |
| `validate_proxy.py` | `f6d22ad892e5a2a418d27618be594f992d17a3f3d1cd8a999b3367d525c026df` |
| `sql/00_crawl_dates.sql` | `4b658ab0762f8db4585ca210c9856e2d2c8dafa301eb4bd6383b4b9857cb5f12` |
| `sql/01_probe_pages.sql` | `ece938a7288e1adba525aac70233875578ade84fee37c20cbcb5d9b3003f2d6d` |
| `sql/02_probe_requests.sql` | `990d3fa709a613e8ebfbc96446b4772f10b079535a302d8f848d3e0ad327e297` |
| `sql/03_check_request_fields.sql` | `f52ef19594eed36b844ad65e57bc7fe5879f1a6ac536430e0acef11a0f926a24` |
| `sql/10_pages.sql` | `51bfdb1c4917871efc401254c165f17aca9fc1d7f12814f3e2376c6ebc9d7c90` |
| `sql/11_requests.sql` | `51041ad21713108e3b778b444986171bf0df067d306e45a502847b8b80b1d804` |
| `sql/_selection.sql` | `c4cd6312b2b201d9529de21a2073ac311c37666d67f4330cc09f931804d0a820` |
| `domains.csv` | `998e3f3fcc09f7da0c7dbe46b4425c9acf73aa8fdf21ad7c5410607bef09704d` |
| `study31.csv` | `c5596c11ecb9985be7cd5b1f47473644bed7033c90d5a379e1d2f0564d76a2ad` |
| `probe_domains.txt` | `a26e58255ff8dba49b86769dd5025cf5ccf5804835cb3c90160f0922d12806f7` |
| `config.json` | `06628d9bf7e01c1b0c92c78d0558a2dae5506d972e7fe87dec3a48ab9d5313ec` |
