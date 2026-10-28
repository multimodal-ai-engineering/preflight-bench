-- Step 2a. One row per selected page: page timings and every layout shift (time and score).
WITH
{{SELECTION}},
picked AS (
  SELECT * FROM sel
  WHERE is_book OR is_media OR is_study
     OR (is_gov AND h < {{GOV_PERMILLE}})
     OR (has_ecom AND h < {{ECOM_PERMILLE}})
     OR (has_ads AND h < {{ADS_PERMILLE}})
)
SELECT
  page, domain, host, rank, is_book, is_media, is_study, is_gov, has_ecom, has_ads, h,
  LAX_INT64(payload._result) AS wpt_result,
  LAX_INT64(summary.reqTotal) AS req_total,
  LAX_INT64(summary.bytesTotal) AS bytes_total,
  LAX_FLOAT64(payload._TTFB) AS ttfb_ms,
  LAX_FLOAT64(payload._render) AS render_ms,
  LAX_FLOAT64(payload._domContentLoadedEventStart) AS dcl_start_ms,
  LAX_FLOAT64(payload._domContentLoadedEventEnd) AS dcl_end_ms,
  LAX_FLOAT64(payload._docTime) AS load_ms,
  LAX_FLOAT64(payload._fullyLoaded) AS fully_loaded_ms,
  LAX_FLOAT64(payload._lastVisualChange) AS last_visual_change_ms,
  LAX_FLOAT64(JSON_QUERY(payload, '$."_chromeUserTiming.CumulativeLayoutShift"')) AS cls,
  TO_JSON_STRING(payload._viewport) AS viewport,
  JSON_QUERY(payload, '$.{{SHIFTS_KEY}}') IS NULL AS shifts_missing,
  (SELECT STRING_AGG(FORMAT('%.1f:%.6f',
                            IFNULL(LAX_FLOAT64(JSON_QUERY(s, '$.{{SHIFT_TIME}}')), -1),
                            IFNULL(LAX_FLOAT64(JSON_QUERY(s, '$.{{SHIFT_SCORE}}')), -1)), ';'
                     ORDER BY LAX_FLOAT64(JSON_QUERY(s, '$.{{SHIFT_TIME}}')))
   FROM UNNEST(JSON_QUERY_ARRAY(payload, '$.{{SHIFTS_KEY}}')) AS s) AS shifts
FROM picked
