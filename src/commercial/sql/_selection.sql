-- Shared page selection (inlined into 10 and 11 by run.py). Desktop or mobile root pages of one crawl, rank <= 1,000,000.
-- BOOK and MEDIA: registered domains in domains.csv. STUDY31: hosts of the 31 study pages. GOV: hosts ending in .gov.
-- SHOP / ADS: a technology in the e-commerce / advertising category (names confirmed by the probe), deterministic hash samples.
sel AS (
  SELECT
    page, rank{{PAYLOAD}},
    NET.REG_DOMAIN(page) AS domain,
    NET.HOST(page) AS host,
    NET.REG_DOMAIN(page) IN ({{BOOK_DOMAINS}}) AS is_book,
    NET.REG_DOMAIN(page) IN ({{MEDIA_DOMAINS}}) AS is_media,
    NET.HOST(page) IN ({{STUDY_HOSTS}}) AS is_study,
    ENDS_WITH(NET.HOST(page), '.gov') AS is_gov,
    EXISTS(SELECT 1 FROM UNNEST(technologies) AS t, UNNEST(t.categories) AS c WHERE c = '{{CAT_ECOM}}') AS has_ecom,
    EXISTS(SELECT 1 FROM UNNEST(technologies) AS t, UNNEST(t.categories) AS c WHERE c = '{{CAT_ADS}}') AS has_ads,
    MOD(MOD(FARM_FINGERPRINT(page), 1000) + 1000, 1000) AS h
  FROM `httparchive.crawl.pages`
  WHERE date = '{{CRAWL_DATE}}'
    AND client = '{{CLIENT}}'
    AND is_root_page
    AND rank <= 1000000
)
