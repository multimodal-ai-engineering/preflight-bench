-- Step 1a. Which monthly crawls are available, and how complete each is (desktop root pages).
-- Reads only the date, client and is_root_page columns.
SELECT date, COUNT(*) AS root_pages
FROM `httparchive.crawl.pages`
WHERE date >= DATE_SUB(CURRENT_DATE(), INTERVAL 150 DAY)
  AND client = 'desktop'
  AND is_root_page
GROUP BY date
ORDER BY date DESC
