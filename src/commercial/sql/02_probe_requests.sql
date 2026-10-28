-- Step 1c. Schema probe on request timing for the same ten probe home pages: the main document of each page, plus
-- (if the requests table is clustered on type) every font and 'other' request, to see how ordinary and unfinished requests are
-- encoded. Confirms the per-request start/end fields and that times are measured from navigation start.
SELECT
  page,
  `index`,
  type,
  is_main_document,
  SUBSTR(url, 1, 200) AS url,
  ARRAY_TO_STRING(ARRAY(SELECT DISTINCT k FROM UNNEST(REGEXP_EXTRACT_ALL(TO_JSON_STRING(payload), r'"(_[A-Za-z][A-Za-z0-9_]*)":')) AS k ORDER BY k), '|') AS payload_keys,
  LAX_FLOAT64(payload._all_start) AS all_start_ms,
  LAX_FLOAT64(payload._all_end) AS all_end_ms,
  LAX_FLOAT64(payload._all_ms) AS all_ms,
  LAX_FLOAT64(payload._load_start) AS load_start_ms,
  LAX_FLOAT64(payload._load_end) AS load_end_ms,
  LAX_FLOAT64(payload._ttfb_start) AS ttfb_start_ms,
  LAX_FLOAT64(JSON_QUERY(payload, '$.time')) AS time_ms,
  LAX_INT64(JSON_QUERY(payload, '$.response.status')) AS response_status,
  LAX_INT64(JSON_QUERY(payload, '$.responseCode')) AS response_code,
  LAX_INT64(summary.status) AS summary_status
FROM `httparchive.crawl.requests`
WHERE date = '{{CRAWL_DATE}}'
  AND client = 'desktop'
  AND is_root_page
  AND ({{REQ_PROBE_FILTER}})
  AND NET.REG_DOMAIN(page) IN ({{PROBE_DOMAINS}})
ORDER BY page, `index`
LIMIT 400
