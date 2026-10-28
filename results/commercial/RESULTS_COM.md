# Results: commercial pages from the HTTP Archive

Public copy. Paths refer to the study's original layout: `commercial/` is now `src/commercial/`, its `results/` outputs are in `results/commercial/`, and the per-page query outputs for the desktop run are in `data/commercial/`.

Preregistration: `commercial/PREREG_COMMERCIAL.md`, frozen 2026-10-27 as `prereg-com-v1` (copy in `docs/PREREG_COMMERCIAL.md`). Run on the author's own GCP project. No commercial site was visited; all commercial-page data comes from HTTP Archive tables in BigQuery.

## Step 0 checks

- `bq` 2.1.31 and `gcloud auth list` work; the active account is the author's.
- `commercial/tests/test_analyze.py`: all six tests pass.
- `validate_proxy.py private/realsite_add/visits.jsonl`: b = 0.2307, a = 0.0089, 0.819, matching the preregistration.
- Commits: `commercial/` as it stood (3267453); `paper/` as it stood (92ca964).

## Probe (Step 1)

Table metadata: `results/table_meta.json`. Crawl months found (desktop root pages): 2026-10-01 (11,650,352), 2026-09-01 (11,359,325), 2026-08-01 (11,276,122), 2026-07-01 (11,628,397), 2026-06-01 (11,991,791). The rule picks **2026-10-01** (at least 95% of the median month), written to `config.json` as `crawl_date`.

Queries run (`results/run_log.json`):

| Query | Dry run | Processed | Billed | Rows |
|---|---|---|---|---|
| 00_crawl_dates | 1.0 GB | 1.04 GB | 1.04 GB | 5 |
| 01_probe_pages | 1.8 GB | 1.78 GB | 1.78 GB | 67 |
| 02_probe_requests | 1,711.7 GB (accuracy not reported) | refused | 0 | — |

`01_probe_pages` returned 67 root pages, not 10: the query selects every root page whose registered domain is one of the ten probe domains (39 on yahoo.com, 18 on pinterest.com, 5 on microsoft.com, 2 on linkedin.com, 1 each on github.com, imdb.com and craigslist.org; zillow.com, reddit.com and stackoverflow.com returned none). All are outside every analysis group. 63 of 67 have a WebPageTest payload.

**`02_probe_requests` was refused by BigQuery under its 150 GB cap** ("Query exceeded limit for bytes billed: 150000000000. 1711749988352 or higher required"). Nothing was billed. Per the instructions the cap was not raised, and the probe stopped there. **Author's decision:** skip the requests probe; check the request fields instead with an extra query on HTTP Archive's 10k-page sample of the same crawl (`sql/03_check_request_fields.sql`; dry run 7.9 GB, cap 20 GB; logged in `run_log.json`). Its first run billed 7.05 GB but returned nothing, because `bq` cannot print array columns as CSV; the rerun with scalar columns returned 17 rows (`results/check_request_fields.csv`).

Confirmed from the pages probe:

- **a. Layout shifts.** `_LayoutShifts` exists: it is present (non-null) on all 49 probe pages with CLS above 0. Each entry has `time` (ms), `score`, `cumulative_score`, `window_score`, `shift_window_num` and `rects`. `shift_time` = `time` and `shift_score` = `score`, as in the default `config.json`; no change. On 5 pages the probe's 3,000-character excerpt was truncated; this affects only the probe display, not the Step 2 query, which reads the full array.
- **b. Time base.** DOM ready (`_domContentLoadedEventEnd`) comes after TTFB on 63 of 63 pages. All 71 parsed shift times fall between start render (`_render`) and the end of the test (the later of `_fullyLoaded` and `_lastVisualChange`). From the sample check: the main document's `_all_start` has median 1 ms (min −27, max 9,153 ms over 5,997 sample pages), so times are measured from navigation start. On 1,080 of those main documents `_all_start` is slightly negative; `11_requests.sql` then uses `_load_start`, as written.
- **c. Technology categories.** `Ecommerce` and `Advertising` occur exactly so; `cat_ecom` and `cat_ads` unchanged.
- **d. Requests** (from the sample check, desktop root pages, all 1.97 M requests). `_all_start` and `_all_end` are present on every request; `req_start` = `_all_start`, `req_end` = `_all_end`, unchanged. An unfinished request has `_all_end` = 0 (the minimum for every type); start below 0 or end at or below 0 occurs on 0–2% of requests depending on type, and `11_requests.sql` counts these as open. `response.status` is present on every request and equals `summary.status` on all but 24; `req_status` = `response.status`, unchanged.
- **e. Clustering.** `pages`: client, is_root_page, rank, page. `requests`: client, is_root_page, type, rank. `requests` is **not** clustered on `page`, so the requests query cannot be narrowed to the selected pages by clustering.

Config changes: `crawl_date` = 2026-10-01 (written by the probe); at the author's approval `probe_reviewed` = true, `requests_approved` = true, `cap_gb["11"]` = 4,500 (estimate 4,466 GB). No field name changed.

## Deviations

1. **`run.py` passes each query to `bq` with a leading newline** (two lines changed). Every SQL file starts with a `--` comment, and `bq` read the query argument as an unknown command-line flag, so no query could run. `bq` does not accept `--` as an end-of-flags marker; a leading newline does work. The SQL text and its logged SHA-256 are unchanged. Made before the freeze; approved by the author.
2. **`10_pages.sql` could not run (fixed before the freeze, approved by the author).** It reads `summary.reqTotal` and `summary.bytesTotal`, but the shared selection (`_selection.sql`, via `{{PAYLOAD}}` in `run.py`) passes only `payload` through, not `summary`, so BigQuery rejects the query ("Unrecognized name: summary"). Fix: `run.py` passes `, payload, summary` for the pages query. Dry runs after the fix: pages 87.4 GB, requests 4,465.9 GB (accuracy not reported for either; clustered tables give an upper bound).
3. **The requests probe was skipped** (author's decision at STOP 1, to avoid a 1.7 TB probe). Items b and d were confirmed on HTTP Archive's 10k-page sample of the same crawl instead of on the ten probe pages. The extra query billed 7.05 GB twice (once with no output, see above).

## Data (Step 3)

- **Crawl:** 2026-10-01, desktop, root pages with CrUX rank ≤ 1,000,000.
- **Queries** (`results/run_log.json`):

| Query | Dry run | Processed | Billed | Rows | Job |
|---|---|---|---|---|---|
| 10_pages_desktop | 87.4 GB | 77.8 GB | 77.8 GB | 12,597 | `preflight_com_10_20261027_234137` |
| 11_requests_desktop | 4,465.9 GB (upper bound) | 127.8 GB | 127.8 GB | 12,597 | `preflight_com_11_20261027_234155` |

  The requests query billed 2.9% of its dry-run estimate: clustering pruned what the dry run could not. All queries in this study together billed 222.6 GB (0.20 TiB).
- **Rows:** 12,597 selected pages, each with one row of requests; **no page lacks request rows**. One probe-domain page was in the selection and was removed before grouping.
- **BOOK:** 66 of 69 domains found. Missing: allegiantair.com, spirit.com, tripadvisor.com (no desktop root page in this crawl's selection). By category: airline 8, car/rail/bus 10, lodging/travel 13, restaurants/food 10, retail 15, tickets/events 10.
- **Group sizes** (before page exclusions): BOOK 66, GOV 3,406 (every .gov root page in the selection, below the 5,000 cap), SHOP 5,000 (capped, of 7,210 sampled), ADS 3,867 (of 4,246 sampled, after excluding BOOK, MEDIA, GOV and STUDY31), MEDIA 10 of 10, STUDY31 21 of 31 hosts. The 10 study hosts not in the crawl selection: dashboard.waterdata.usgs.gov, earthquake.usgs.gov, en.wikinews.org, hydra.nixos.org, status.python.org, volcanoes.usgs.gov, www.caiso.com, www.seismicportal.eu, www.swpc.noaa.gov, www.wikimediastatus.net.
- **Request-count consistency:** on all 12,597 pages the request rows were compared with the page's own `summary.reqTotal`; 1 page differs by more than 10%.
- **Main document status:** 200 on all 12,597 pages.
- **Page exclusions** (all selected rows): 422 with fewer than 10 requests; 165 with no DOM-ready time (these are the 165 pages with no WebPageTest result); 0 with a non-200 main document. By group: GOV 377 (fewer than 10 requests) + 1 (no DOM ready); SHOP 10 + 18; ADS 4 + 106; BOOK 1 (fewer than 10 requests); MEDIA 1 (no DOM ready). Per-rule exclusions (missing shift data, rule time unavailable) are reported with the analysis.
- **Requests never finished:** 1,074 pages have at least one request with a missing or non-positive end time; these stay in flight for the network-idle rule, as preregistered.

## Spot checks (Step 4.2)

`commercial/spot_check.py` draws 3 BOOK and 3 GOV pages (seed 20261027) among pages with usable shift data and recomputes every rule from the preregistered definitions. It finds network idle independently, by sweeping forward past merged in-flight spans, where `analyze.py` tests candidate points. For each page it prints DOM ready, load, fully loaded, CLS, the request count, the in-flight spans after DOM ready, the network-idle window, the shift list and each rule's screenshot time and outcome.

- **All 36 page-rule outcomes and screenshot times agree** with `analyze.py`. No bug was found, so no code was changed.
- Checked by hand against the definitions:
  - On one BOOK page (DOM ready 960 ms), the first 500 ms gap after DOM ready starts at 13,108 ms. So S5 screenshots at the 3 s cap (3,960 ms), and the 0.027 shift at 4,049 ms counts. S5u screenshots at 13,608 ms and sees no shift. The test ended at 14,530 ms, so that pair is censored.
  - On another BOOK page, one request never finished (in flight from 3,018 ms on). The page never goes quiet, S5 ends at the cap, and S5u falls back to the last recorded moment (12,099 ms), as preregistered.
  - Shift sums below and above the 0.0001 threshold were handled correctly. For example, a page's two shifts of 0.0001 and 0.0002 after DOM ready count as a shift at S0.
  - On all three GOV pages the network went quiet for good. The recording ended with the last request, 0.5 s **before** the network-idle screenshot, so the whole 6.5 s window after it is unobserved. Their S5 pairs are censored and count as no shift (see Limitations).

## Scope as run

- Desktop home pages in the 2026-10-01 crawl, CrUX rank ≤ 1,000,000. One WebPageTest load per page: desktop Chrome, cable profile, US locations, empty cache.
- Pages analysed, after exclusions:
  - BOOK 65 (66 domains found; 1 excluded with fewer than 10 requests);
  - GOV 3,028;
  - SHOP 4,972;
  - ADS 3,757;
  - MEDIA 9;
  - STUDY31 21.
- **Rule S4 has fewer pages:** it is unavailable where the load event comes before DOM ready (SHOP 19, ADS 49, GOV 3, MEDIA 2 pages).
- Mobile and inner pages, listed as exploratory, were not run.
- Analysis: `commercial/analyze.py` as frozen, B = 2,000, seed 20261027. Output in `results/analysis_desktop/`.

## Hypotheses

| | Test | Estimate (95% interval) | Pages | Result |
|---|---|---|---|---|
| **C1** | BOOK shift share minus GOV, after the network-idle screenshot (S5, 3 s cap) | +44.5 points (32.4 to 56.9). BOOK 52.3% (40.0–64.6), GOV 7.8% (6.8–8.7) | 65 / 3,028 | **held** |
| | C1 with censored page-rule pairs dropped | +35.1 points (19.8 to 50.1). BOOK 61.0% (46.3–75.6), GOV 25.9% (21.0–31.1) | 41 / 286 | held in both analyses |
| **C2** | GOV share reaching 500 ms of network quiet within 3 s of DOM ready, minus BOOK | +48.1 points (38.5 to 56.4). BOOK 15.4% (7.7–24.6), GOV 63.4% (61.8–65.1) | 65 / 3,028 | **held** |
| **C3** | Spearman ρ, crawl shift after DOM ready (S0) vs the study's 2 s stale share at S0, on STUDY31 | ρ = −0.12 (−0.56 to 0.32); no degenerate resamples | 20 | **refuted** |

**C3 refuted.** On the study's own sites, the crawl's layout-shift signal did not track the post-navigation burst the study measured. As preregistered, the crawl results are therefore an **unvalidated proxy** for stale clicks on these pages. The shift shares in C1 and C2 are measured directly. The stale-click estimates below rest on a calibration that this check did not confirm on the crawl.

**Level check (STUDY31, 21 pages).** Crawl estimate (pooled calibration) against the stale share the study measured, rule by rule:

| Rule | Crawl estimate | Study measured |
|---|---|---|
| S0 | 12.5% | 14.2% |
| S1 | 7.2% | 2.6% |
| S2 | 6.2% | 3.1% |
| S4 | 4.1% | 4.3% |
| crawl S5u / study S5 | 1.95% | 0.45% |

The crawl estimate matches at DOM ready and the load event. It runs 2.0–2.8 times higher than measured after the timed sleeps, and 4.3 times higher after network idle.

## Secondary analyses (pre-specified)

- **C1 with GOV reweighted to BOOK's rank mix:** +43.4 points (29.8 to 56.3). The interval is above 0.
- **C1 with SHOP in place of BOOK:** SHOP 22.0% (20.9–23.1) against GOV 7.8%, +14.2 points (12.7 to 15.7). The interval is above 0.
- **C2 with SHOP in place of BOOK:** SHOP 19.4% (18.3–20.5) reach quiet within 3 s, against GOV 63.4%, a difference of 44.1 points (42.1 to 46.0). The interval is above 0.

## Decision table (no hypothesis)

Estimated stale-click share p̂ = a + (b − a) × π, under two calibrations (pooled: a = 0.89%, b = 23.1%; S1–S5 only: a = 0.83%, b = 15.4%). The pixel check pays when p̂ exceeds p* = 10.2% for an ordinary click (k = 2) or 1.19% for an irreversible one (k = 10). "Pays" compares the point estimate with p*. These estimates inherit the C3 caveat and, per the level check, run high after network idle.

| Group | Rule | p̂ pooled (95%) | p̂ S1–S5 (95%) | Ordinary click: pays? (pooled / S1–S5) | Irreversible: pays? |
|---|---|---|---|---|---|
| BOOK | S0 DOM ready | 18.6% (12.0–28.7) | 12.5% (5.6–23.5) | yes / yes | yes / yes |
| BOOK | S4 load | 11.5% (7.2–17.9) | 7.8% (3.5–14.9) | yes / no | yes / yes |
| BOOK | S5 network idle, 3 s cap | 12.5% (7.8–19.2) | 8.4% (3.9–16.4) | yes / no | yes / yes |
| SHOP | S0 | 14.6% (9.7–21.9) | 9.8% (4.5–18.4) | yes / no | yes / yes |
| SHOP | S4 | 6.3% (4.3–9.4) | 4.4% (2.2–8.1) | no / no | yes / yes |
| SHOP | S5 | 5.8% (3.9–8.6) | 4.0% (2.0–7.4) | no / no | yes / yes |
| GOV | S0 | 15.5% (10.3–23.3) | 10.4% (4.8–19.6) | yes / yes | yes / yes |
| GOV | S4 | 5.6% (3.8–8.5) | 3.9% (2.0–7.1) | no / no | yes / yes |
| GOV | S5 | 2.6% (1.7–4.0) | 1.95% (0.92–3.5) | no / no | yes / yes |

Full table for every group and rule: `results/analysis_desktop/shift_and_stale_by_group_rule.csv`.

## Exploratory (labelled as such)

- **Network quiet** (`network_quiet.csv`):
  - **Time from DOM ready to 500 ms quiet, with no cap:** median 7.4 s (p90 16.1 s) on BOOK, 6.4 s on SHOP and 2.1 s (p90 7.3 s) on GOV.
  - **Pages that never went quiet:** BOOK 6 of 65, SHOP 308 of 4,972, GOV 106 of 3,028.
  - **Last layout shift after DOM ready:** median 5.1 s on BOOK, 2.2 s on SHOP and 0.65 s on GOV.
- **BOOK by category** (S5 shift share; quiet within 3 s). Groups have 8–14 pages, so the intervals are wide.

  | Category | Pages | S5 shift share | Quiet within 3 s |
  |---|---|---|---|
  | airline | 8 | 75% | 12.5% |
  | car, rail and bus | 10 | 80% | 0% |
  | lodging and travel | 13 | 54% | 0% |
  | restaurants and food | 10 | 50% | 20% |
  | tickets and events | 10 | 40% | 10% |
  | retail | 14 | 29% | 43% |

- **ADS and MEDIA against GOV** (S5 shift share): ADS 23.3% (22.1–24.7), MEDIA 56% (n = 9), GOV 7.8%.
- **Rank strata** (S5 shift share):
  - BOOK: 50% in the top 1k (n = 10), 46% in 1k–10k (26) and 68% in 10k–100k (25).
  - GOV: 90% of its pages are ranked 100k–1M, where the share is 7.8%.
- **Last visual change after the S5 screenshot** (an upper bound that also counts pop-ups and carousels): BOOK 89%, SHOP 78%, ADS 76%, GOV 35%.
- **The drop-censored analysis raises every group's shift share** (BOOK S5 61%, SHOP 30%, GOV 26%). The pages still recording after T + 6.5 s are the ones still loading.

## Limitations

- **Calibration transfer.** The layout-shift-to-stale calibration comes from a live, unthrottled browser on 31 public pages. Here it is applied to WebPageTest's throttled desktop profile, and the transfer check (C3) failed.
- **Home pages only.** Search results, product pages and checkout were not measured.
- **One load per page,** from one crawl month and one test location type.
- **Shifts miss some stale clicks.** In the validation, 18% of stale clicks did not register as a layout shift (content that covers or swaps a target). Pages with pop-ups may run higher than the estimates.
- **Censoring.** WebPageTest stops recording once a page is fully loaded, and unobserved time counts as no shift. When a page's network goes quiet and stays quiet, the recording ends at its last request, before the network-idle screenshot, so none of the 6.5 s window after that screenshot is observed. This applies to 91% of GOV, 52% of SHOP and 37% of BOOK pairs at S5, so GOV's 7.8% is mostly an assumption about unrecorded time. With censored pairs dropped, C1 still holds (BOOK 61% against GOV 26%), but that subset is the pages still loading.

## Deviations (continued)

4. **Two helper scripts added after the freeze:** `commercial/spot_check.py` (the Step 4.2 spot checks) and `commercial/fig_commercial.py` (the Step 4.3 figure). Neither changes the frozen analysis; `analyze.py` ran as frozen.
5. **Mobile and inner pages** (exploratory in the preregistration) were run afterwards, at the author's request, through a new script, `commercial/run_exploratory.py`. It reuses run.py's capped, logged query function and the frozen SQL; for inner pages it flips the root-page filters (`AND is_root_page` to `AND NOT is_root_page`, in the selection and in the requests join). The author approved caps of 5,500 GB (mobile requests) and 8,300 GB (inner-page requests), held in that script so the frozen `config.json` is unchanged. Results below.
6. **Rounding correction (paper step).** C1's difference was first written as +44.6 points by rounding the stored estimate 0.4455; the exact difference is 34/65 − 235/3,028 = 0.44547, so +44.5 points. No other number changed.
7. **Post hoc check of the BOOK pages (paper step).** The preregistered rule takes each domain's apex or `www.` root page and otherwise its best-ranked root page. For 8 of the 66 BOOK domains the selection held no apex or `www.` root page, so the rule took a subdomain: support.axs.com, stores.bestbuy.com, help.etsy.com, careers.hyatt.com, cruises.priceline.com, help.ticketmaster.com, partners.wayfair.com and business.yelp.com. These are mostly help, careers and partner pages. None of the 8 shifted after the capped wait, and 4 of 8 went quiet within 3 s. On the 57 BOOK pages on the main host: S5 shift share 59.6% (47.4–71.9), quiet within 3 s 10.5% (3.5–19.3), median time to quiet 7.8 s, median last shift 5.8 s, fully recorded subset 64.1% (n = 39). The preregistered result therefore understates the difference. Post hoc, reported in the paper as such; the preregistered numbers are unchanged.

## Exploratory: mobile home pages and desktop inner pages

Run after Step 4 at the author's request (`run_exploratory.py`, then `analyze.py --client mobile` and `--client desktop_inner`; output in `results/analysis_mobile/` and `results/analysis_desktop_inner/`). These are exploratory. The C1–C3 tests below are the same computations applied to these data. They are not the preregistered hypotheses, which are desktop home pages only.

**Data.**

| Query | Dry run | Billed | Rows |
|---|---|---|---|
| 10_pages_mobile | 112.5 GB | 99.0 GB | 12,688 |
| 11_requests_mobile | 5,398.5 GB | 152.4 GB | 12,688 |
| 10_pages_desktop_inner | 167.6 GB | 150.0 GB | 11,313 |
| 11_requests_desktop_inner | 8,230.3 GB | 265.7 GB | 11,313 |

All queries in this study together billed 889.6 GB (0.81 TiB).

- **Mobile:**
  - Groups: BOOK 68 of 69 domains, GOV 3,248, SHOP 5,000, ADS 3,977, MEDIA 10, STUDY31 20.
  - Excluded: 385 pages with fewer than 10 requests, 48 with no DOM ready.
  - Request counts are off by more than 10% on 2 pages.
- **Desktop inner pages:**
  - Groups: BOOK 64, GOV 2,615, SHOP 5,000, ADS 3,712, MEDIA 10, STUDY31 19.
  - Excluded: 106 pages with fewer than 10 requests, 152 with no DOM ready.
  - Request counts are off by more than 10% on 0 pages.
  - An inner page here is whichever non-home page HTTP Archive crawled for that site. BOOK keeps one per domain (the apex or `www.` host first, then the best rank). GOV, SHOP and ADS may hold several pages from one site.
- No page lacks request rows in either run.

**Shift share after the network-idle screenshot (S5, 3 s cap).** Bracketed: with censored page-rule pairs dropped.

| | BOOK | SHOP | GOV |
|---|---|---|---|
| Desktop home (primary) | 52.3% [61.0%, n = 41] | 22.0% [30.4%] | 7.8% [25.9%, n = 286] |
| Mobile home | 26.5% (16.2–36.8) [27.1%, n = 59] | 22.3% [26.7%] | 13.6% (12.3–14.8) [28.2%, n = 575] |
| Desktop inner | 39.1% (28.1–51.6) [55.2%, n = 29] | 20.2% [32.3%] | 5.0% (4.2–5.9) [16.9%, n = 130] |

**Network quiet within 3 s of DOM ready.**

| | BOOK | SHOP | GOV |
|---|---|---|---|
| Desktop home | 15.4% | 19.4% | 63.4% |
| Mobile home | 41.2% (29.4–54.4) | 27.4% | 51.4% |
| Desktop inner | 18.8% (9.4–28.1) | 26.6% | 73.4% |

Median time to quiet: mobile BOOK 3.9 s, GOV 2.9 s; inner BOOK 6.1 s, GOV 1.8 s.

**The same tests on these data:**

| | Mobile home | Desktop inner |
|---|---|---|
| C1 (BOOK − GOV, S5 shift) | +12.9 points (2.9 to 23.2). Censored dropped: −1.1 (−12.6 to 11.2). Would **not** hold. | +34.0 points (22.4 to 46.4). The censored-dropped check is untestable: 29 BOOK pages remain, below 30. Would hold on the primary analysis. |
| C1 rank-reweighted | +11.5 (−1.2 to 24.9) | +33.2 (20.7 to 45.0) |
| C2 (GOV − BOOK, quiet within 3 s) | +10.2 points (−2.3 to 21.4). Would **not** hold. | +54.7 points (44.7 to 64.5). Would hold. |
| C1 with SHOP | +8.7 (7.0 to 10.4) | +15.2 (13.8 to 16.6) |
| C2 with SHOP | +24.0 (21.8 to 26.3) | +46.8 (44.8 to 48.9) |
| C3 (transfer, ρ) | 0.23 (−0.30 to 0.68), n = 19. Would not hold. | 0.31 (−0.21 to 0.69), n = 17; 4 degenerate resamples. Would not hold. |

**Reading.**
- **Inner pages** follow the desktop home-page pattern. Booking pages rarely go quiet within 3 s (19%), and 39% still shift after the capped wait.
- **On mobile the booking-vs-.gov gap mostly disappears.**
  - The booking home pages in the mobile crawl go quiet within 3 s far more often than on desktop (41% against 15%). They shift after the capped wait about half as often (26.5% against 52.3%).
  - With censored pairs dropped, BOOK and GOV are about equal on mobile (27% and 28%).
- **SHOP stays at 20–22% after the capped wait** in all three runs.
- So the desktop home-page result (C1, C2) did not replicate on mobile home pages. The paper should keep the claim to desktop and report the mobile result beside it.
