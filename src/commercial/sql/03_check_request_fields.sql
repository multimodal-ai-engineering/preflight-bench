-- Extra check (Step 1d substitute): request payload field names and encodings, read from HTTP Archive's 10k-page sample
-- instead of the full crawl (the requests probe was skipped by the author's decision). No analysis-group page is used.
SELECT
  date, type, is_main_document,
  COUNT(*) AS n,
  COUNTIF(LAX_FLOAT64(payload._all_start) IS NOT NULL) AS has_all_start,
  COUNTIF(LAX_FLOAT64(payload._all_end) IS NOT NULL) AS has_all_end,
  COUNTIF(LAX_FLOAT64(payload._all_start) < 0 OR LAX_FLOAT64(payload._all_end) <= 0) AS start_neg_or_end_nonpos,
  COUNTIF(LAX_FLOAT64(payload._load_start) IS NOT NULL) AS has_load_start,
  COUNTIF(LAX_INT64(JSON_QUERY(payload, '$.response.status')) IS NOT NULL) AS has_response_status,
  COUNTIF(LAX_INT64(JSON_QUERY(payload, '$.response.status')) = LAX_INT64(summary.status)) AS status_matches_summary,
  MIN(LAX_FLOAT64(payload._all_start)) AS min_all_start, APPROX_QUANTILES(LAX_FLOAT64(payload._all_start), 2)[OFFSET(1)] AS med_all_start, MAX(LAX_FLOAT64(payload._all_start)) AS max_all_start,
  MIN(LAX_FLOAT64(payload._all_end)) AS min_all_end, APPROX_QUANTILES(LAX_FLOAT64(payload._all_end), 2)[OFFSET(1)] AS med_all_end, MAX(LAX_FLOAT64(payload._all_end)) AS max_all_end,
  ANY_VALUE(ARRAY_TO_STRING(ARRAY(SELECT DISTINCT k FROM UNNEST(REGEXP_EXTRACT_ALL(TO_JSON_STRING(payload), r'"(_[A-Za-z][A-Za-z0-9_]*)":')) AS k ORDER BY k), '|')) AS payload_keys_example
FROM `httparchive.sample_data.requests_10k`
WHERE client = 'desktop' AND is_root_page
GROUP BY date, type, is_main_document
ORDER BY date DESC, n DESC
