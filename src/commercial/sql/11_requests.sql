-- Step 2b. Request start and end times for the same pages, for the network-idle rule, and the main document's status.
-- One row per page: "start,end;start,end;..." in ms from navigation start, in request order; -1 marks a missing value.
WITH
{{SELECTION}},
picked AS (
  SELECT page FROM sel
  WHERE is_book OR is_media OR is_study
     OR (is_gov AND h < {{GOV_PERMILLE}})
     OR (has_ecom AND h < {{ECOM_PERMILLE}})
     OR (has_ads AND h < {{ADS_PERMILLE}})
),
req AS (
  SELECT
    r.page, r.`index`, r.is_main_document,
    SAFE_CAST(IF(LAX_FLOAT64(r.payload.{{REQ_START}}) IS NULL OR LAX_FLOAT64(r.payload.{{REQ_START}}) < 0,
                 LAX_FLOAT64(r.payload._load_start), LAX_FLOAT64(r.payload.{{REQ_START}})) AS INT64) AS s,
    SAFE_CAST(IF(LAX_FLOAT64(r.payload.{{REQ_END}}) IS NULL OR LAX_FLOAT64(r.payload.{{REQ_END}}) <= 0,
                 LAX_FLOAT64(r.payload._load_end), LAX_FLOAT64(r.payload.{{REQ_END}})) AS INT64) AS e,
    LAX_INT64(JSON_QUERY(r.payload, '$.{{REQ_STATUS}}')) AS status
  FROM `httparchive.crawl.requests` AS r
  JOIN picked USING (page)
  WHERE r.date = '{{CRAWL_DATE}}'
    AND r.client = '{{CLIENT}}'
    AND r.is_root_page
)
SELECT
  page,
  COUNT(*) AS n_requests,
  COUNTIF(s IS NULL OR s < 0 OR e IS NULL OR e <= 0 OR e < s) AS n_open,
  ARRAY_AGG(IF(is_main_document, status, NULL) IGNORE NULLS ORDER BY `index` DESC LIMIT 1)[SAFE_OFFSET(0)] AS main_status,
  STRING_AGG(FORMAT('%d,%d', IFNULL(s, -1), IFNULL(e, -1)), ';' ORDER BY `index`) AS intervals
FROM req
GROUP BY page
