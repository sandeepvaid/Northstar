-- Campaign Data Hub — canonical storage schema (SQLite)
-- Three tables: deliveries (one row per file seen), metrics (daily canonical grain),
-- data_issues (quality report + quarantine of untrusted/raw values).

CREATE TABLE IF NOT EXISTS deliveries (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    platform      TEXT    NOT NULL,
    week_start    TEXT    NOT NULL,              -- ISO date parsed from filename
    filename      TEXT    NOT NULL,
    content_hash  TEXT    NOT NULL UNIQUE,       -- sha256 of file bytes -> dedupe + idempotency
    row_count     INTEGER,                       -- canonical rows persisted from this delivery
    status        TEXT    NOT NULL,              -- processed | skipped_duplicate | parse_error
    health        TEXT,                          -- pass | warn | fail
    ingested_at   TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS metrics (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    platform           TEXT    NOT NULL,
    campaign           TEXT    NOT NULL,         -- normalized: trimmed + lowercased
    date               TEXT    NOT NULL,         -- ISO YYYY-MM-DD
    spend_usd          REAL,                     -- nullable: null when untrusted (see data_issues)
    impressions        INTEGER,
    clicks             INTEGER,
    raw_amount         TEXT,                      -- original spend string (keeps transform reversible)
    raw_currency       TEXT,
    source_delivery_id INTEGER NOT NULL REFERENCES deliveries(id),
    updated_at         TEXT    NOT NULL,
    UNIQUE(platform, campaign, date)             -- natural key -> upsert = idempotent
);

CREATE TABLE IF NOT EXISTS data_issues (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    delivery_id INTEGER NOT NULL REFERENCES deliveries(id),
    level       TEXT    NOT NULL,                -- row | file | delivery
    check_name  TEXT    NOT NULL,
    severity    TEXT    NOT NULL,                -- warn | fail
    field       TEXT,                            -- offending field, when row-level
    raw_value   TEXT,                            -- the actual data point we could not trust
    raw_row     TEXT,                            -- full raw row as JSON (for quarantined rows)
    campaign    TEXT,
    date        TEXT,
    message     TEXT    NOT NULL,
    created_at  TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_metrics_platform_date ON metrics(platform, date);
CREATE INDEX IF NOT EXISTS idx_issues_delivery       ON data_issues(delivery_id);
