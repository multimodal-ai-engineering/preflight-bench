-- Step 1b. Schema probe on ten home pages outside every analysis group (probe_domains.txt): confirms the payload
-- field names, the layout-shift entry format, the time base, the technology category names and the summary fields.
-- These domains are excluded from every result.
SELECT
  page,
  rank,
  ARRAY_TO_STRING(ARRAY(SELECT DISTINCT k FROM UNNEST(REGEXP_EXTRACT_ALL(TO_JSON_STRING(payload), r'"(_[A-Za-z][A-Za-z0-9_.]*)":')) AS k ORDER BY k), '|') AS payload_keys,
  SUBSTR(TO_JSON_STRING(payload._LayoutShifts), 1, 3000) AS layout_shifts_json,
  TO_JSON_STRING(payload._viewport) AS viewport,
  LAX_INT64(payload._result) AS wpt_result,
  LAX_FLOAT64(payload._TTFB) AS ttfb_ms,
  LAX_FLOAT64(payload._render) AS render_ms,
  LAX_FLOAT64(payload._domContentLoadedEventStart) AS dcl_start_ms,
  LAX_FLOAT64(payload._domContentLoadedEventEnd) AS dcl_end_ms,
  LAX_FLOAT64(payload._docTime) AS load_ms,
  LAX_FLOAT64(payload._fullyLoaded) AS fully_loaded_ms,
  LAX_FLOAT64(payload._lastVisualChange) AS last_visual_change_ms,
  LAX_FLOAT64(JSON_QUERY(payload, '$."_chromeUserTiming.CumulativeLayoutShift"')) AS cls,
  LAX_INT64(summary.reqTotal) AS req_total,
  LAX_INT64(summary.bytesTotal) AS bytes_total,
  ARRAY_TO_STRING(ARRAY(SELECT DISTINCT k FROM UNNEST(REGEXP_EXTRACT_ALL(TO_JSON_STRING(summary), r'"([A-Za-z_][A-Za-z0-9_]*)":')) AS k ORDER BY k), '|') AS summary_keys,
  ARRAY_TO_STRING(ARRAY(SELECT DISTINCT c FROM UNNEST(technologies) AS t, UNNEST(t.categories) AS c ORDER BY c), '|') AS tech_categories
FROM `httparchive.crawl.pages`
WHERE date = '{{CRAWL_DATE}}'
  AND client = 'desktop'
  AND is_root_page
  AND rank <= 10000
  AND NET.REG_DOMAIN(page) IN ({{PROBE_DOMAINS}})
