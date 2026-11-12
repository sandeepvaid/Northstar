"""Read SQL for the API. Filters use named params with an IS NULL guard so an unset
filter is a no-op. Column lists are explicit (no SELECT *)."""

# Shared WHERE for metrics filters (platform + date range), all optional.
_METRIC_FILTER = (
    "WHERE (:platform IS NULL OR platform = :platform) "
    "AND (:date_from IS NULL OR date >= :date_from) "
    "AND (:date_to IS NULL OR date <= :date_to)"
)

SELECT_METRICS = (
    "SELECT platform, campaign, date, spend_usd, impressions, clicks "
    f"FROM metrics {_METRIC_FILTER} "
    "ORDER BY date, platform, campaign"
)

SELECT_METRICS_TOTALS = (
    "SELECT COUNT(*) AS rows, SUM(spend_usd) AS spend_usd, "
    "SUM(impressions) AS impressions, SUM(clicks) AS clicks, "
    "MIN(date) AS date_min, MAX(date) AS date_max "
    f"FROM metrics {_METRIC_FILTER}"
)

# group_column is a validated identifier (never user free-text) injected by the router.
SELECT_METRICS_SUMMARY = (
    "SELECT {group_select} "
    "SUM(spend_usd) AS spend_usd, SUM(impressions) AS impressions, "
    "SUM(clicks) AS clicks, COUNT(*) AS rows "
    f"FROM metrics {_METRIC_FILTER} "
    "GROUP BY {group_by}"
)

SELECT_DELIVERIES = (
    "SELECT d.id, d.platform, d.week_start, d.filename, d.status, d.health, "
    "d.row_count, d.ingested_at, "
    "COUNT(i.id) AS issue_count, "
    "COALESCE(SUM(CASE WHEN i.severity = 'fail' THEN 1 ELSE 0 END), 0) AS fail_count, "
    "COALESCE(SUM(CASE WHEN i.severity = 'warn' THEN 1 ELSE 0 END), 0) AS warn_count "
    "FROM deliveries d LEFT JOIN data_issues i ON i.delivery_id = d.id "
    "GROUP BY d.id "
    "ORDER BY d.week_start, d.platform"
)

SELECT_DELIVERY = (
    "SELECT id, platform, week_start, filename, status, health, row_count, ingested_at "
    "FROM deliveries WHERE id = ?"
)

SELECT_DELIVERY_ISSUES = (
    "SELECT id, level, check_name, severity, field, raw_value, raw_row, campaign, date, message "
    "FROM data_issues WHERE delivery_id = ? "
    "ORDER BY CASE level WHEN 'delivery' THEN 0 WHEN 'file' THEN 1 ELSE 2 END, "
    "CASE severity WHEN 'fail' THEN 0 ELSE 1 END, id"
)
