"""SQL used by the ingestion pipeline, kept in one place so pipeline.py reads as orchestration.

Column lists are spelled out (no SELECT *), statements are parameterized, and the metric
upsert leans on the UNIQUE(platform, campaign, date) natural key for idempotency.
"""

# --- deliveries -----------------------------------------------------------

SELECT_DELIVERY_BY_HASH = "SELECT id, filename FROM deliveries WHERE content_hash = ?"

EXISTS_DELIVERY_BY_HASH = "SELECT 1 FROM deliveries WHERE content_hash = ?"

INSERT_DELIVERY = (
    "INSERT INTO deliveries (platform, week_start, filename, content_hash, status, ingested_at) "
    "VALUES (?, ?, ?, ?, ?, ?)"
)

UPDATE_DELIVERY_RESULT = "UPDATE deliveries SET health = ?, row_count = ? WHERE id = ?"

# --- data_issues ----------------------------------------------------------

DELETE_ISSUES_FOR_DELIVERY = "DELETE FROM data_issues WHERE delivery_id = ?"

INSERT_ISSUE = (
    "INSERT INTO data_issues "
    "(delivery_id, level, check_name, severity, field, raw_value, raw_row, campaign, date, message, created_at) "
    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
)

# --- metrics (upsert on natural key) --------------------------------------

UPSERT_METRIC = (
    "INSERT INTO metrics "
    "(platform, campaign, date, spend_usd, impressions, clicks, raw_amount, raw_currency, "
    " source_delivery_id, updated_at) "
    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
    "ON CONFLICT(platform, campaign, date) DO UPDATE SET "
    "  spend_usd=excluded.spend_usd, impressions=excluded.impressions, clicks=excluded.clicks, "
    "  raw_amount=excluded.raw_amount, raw_currency=excluded.raw_currency, "
    "  source_delivery_id=excluded.source_delivery_id, updated_at=excluded.updated_at"
)

# --- delivery-level cadence (missing-delivery placeholders) ----------------

DELETE_MISSING_ISSUES = (
    "DELETE FROM data_issues WHERE delivery_id IN (SELECT id FROM deliveries WHERE status = 'missing')"
)

DELETE_MISSING_DELIVERIES = "DELETE FROM deliveries WHERE status = 'missing'"

SELECT_PROCESSED_DELIVERY_KEYS = (
    "SELECT platform, week_start FROM deliveries WHERE status = 'processed'"
)

INSERT_MISSING_DELIVERY = (
    "INSERT INTO deliveries (platform, week_start, filename, content_hash, row_count, "
    "status, health, ingested_at) VALUES (?, ?, ?, ?, 0, 'missing', 'fail', ?)"
)

INSERT_MISSING_DELIVERY_ISSUE = (
    "INSERT INTO data_issues (delivery_id, level, check_name, severity, message, created_at) "
    "VALUES (?, 'delivery', 'missing_delivery', 'fail', ?, ?)"
)

# --- cross-delivery spend plausibility ------------------------------------

# Per processed delivery: aggregate spend/impressions/clicks of the rows it owns
# (metrics carry source_delivery_id lineage). Impressions > 0 so CPM is well-defined.
SELECT_DELIVERY_SPEND_AGG = (
    "SELECT d.id AS delivery_id, d.platform AS platform, d.week_start AS week_start, "
    "       SUM(m.spend_usd) AS spend, SUM(m.impressions) AS impressions, SUM(m.clicks) AS clicks "
    "FROM deliveries d JOIN metrics m ON m.source_delivery_id = d.id "
    "WHERE d.status = 'processed' "
    "GROUP BY d.id, d.platform, d.week_start "
    "HAVING SUM(m.impressions) > 0 AND SUM(m.spend_usd) IS NOT NULL"
)

# Rewrite semantics: clear prior plausibility issues before recomputing -> idempotent.
DELETE_SPEND_ISSUES = "DELETE FROM data_issues WHERE check_name = 'spend_implausible'"

INSERT_SPEND_ISSUE = (
    "INSERT INTO data_issues (delivery_id, level, check_name, severity, field, raw_value, "
    "message, created_at) VALUES (?, 'delivery', 'spend_implausible', 'warn', 'spend_usd', ?, ?, ?)"
)

# Health is fully derived from issues: fail if any fail-severity issue, warn if any issue,
# else pass. Recomputed after the post-pass so a newly added delivery-level issue is reflected.
RECOMPUTE_PROCESSED_HEALTH = (
    "UPDATE deliveries SET health = CASE "
    "  WHEN EXISTS (SELECT 1 FROM data_issues i "
    "              WHERE i.delivery_id = deliveries.id AND i.severity = 'fail') THEN 'fail' "
    "  WHEN EXISTS (SELECT 1 FROM data_issues i WHERE i.delivery_id = deliveries.id) THEN 'warn' "
    "  ELSE 'pass' END "
    "WHERE status = 'processed'"
)

# --- summary counts -------------------------------------------------------

COUNT_METRICS = "SELECT COUNT(*) AS n FROM metrics"
COUNT_ISSUES = "SELECT COUNT(*) AS n FROM data_issues"
