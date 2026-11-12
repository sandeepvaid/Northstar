"""Ingestion orchestration.

Flow per file: content-hash dedupe -> parse -> normalize+validate -> within-file dedupe
-> persist (upsert metrics by natural key, rewrite this delivery's issues) -> roll up health.

Idempotent: an identical re-run of a file is skipped by content hash; metrics upsert on
(platform, campaign, date) so re-processing converges to the same values.
"""
from __future__ import annotations

import json
import logging
import sqlite3
from datetime import date, datetime, timezone
from pathlib import Path
from statistics import median
from typing import Any

from .. import config
from ..constants import Check, DeliveryStatus, Health, IssueLevel, Outcome, Severity
from ..db import get_connection, init_db
from . import queries as q
from .discover import DeliveryFile, content_hash, discover
from .normalizers.base import CanonicalRow, IngestContext, Issue, Normalizer
from .normalizers.google import GoogleNormalizer
from .normalizers.linkedin import LinkedInNormalizer
from .normalizers.meta import MetaNormalizer

logger = logging.getLogger("cdh.ingest")

# Register a platform here to light it up end-to-end.
REGISTRY: dict[str, Normalizer] = {
    n.platform: n for n in (MetaNormalizer(), GoogleNormalizer(), LinkedInNormalizer())
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_exchange_rates() -> dict[str, float]:
    if not config.EXCHANGE_RATES_PATH.exists():
        return {}
    return json.loads(config.EXCHANGE_RATES_PATH.read_text()).get("rates", {})


def _health_from_issues(issues: list[Issue], status: str) -> str:
    if status == DeliveryStatus.PARSE_ERROR:
        return Health.FAIL
    if any(i.severity == Severity.FAIL for i in issues):
        return Health.FAIL
    if issues:
        return Health.WARN
    return Health.PASS


def _insert_delivery(conn: sqlite3.Connection, df: DeliveryFile, c_hash: str, status: str) -> int:
    cur = conn.execute(
        q.INSERT_DELIVERY,
        (df.platform, df.week_start.isoformat(), df.filename, c_hash, status, _now()),
    )
    return cur.lastrowid


def _write_issues(conn: sqlite3.Connection, delivery_id: int, issues: list[Issue]) -> None:
    # Rewrite semantics keep re-ingest idempotent (never accumulate).
    conn.execute(q.DELETE_ISSUES_FOR_DELIVERY, (delivery_id,))
    conn.executemany(
        q.INSERT_ISSUE,
        [
            (
                delivery_id, i.level, i.check_name, i.severity, i.field, i.raw_value,
                json.dumps(i.raw_row) if i.raw_row is not None else None,
                i.campaign, i.date, i.message, _now(),
            )
            for i in issues
        ],
    )


def _upsert_metric(conn: sqlite3.Connection, row: CanonicalRow, delivery_id: int) -> None:
    conn.execute(
        q.UPSERT_METRIC,
        (
            row.platform, row.campaign, row.date, row.spend_usd, row.impressions, row.clicks,
            row.raw_amount, row.raw_currency, delivery_id, _now(),
        ),
    )


def _process_file(conn: sqlite3.Connection, df: DeliveryFile, ctx_rates: dict[str, float]) -> str:
    c_hash = content_hash(df.path)
    existing = conn.execute(q.SELECT_DELIVERY_BY_HASH, (c_hash,)).fetchone()

    if existing is not None:
        if existing["filename"] == df.filename:
            logger.info("skip %s (already ingested, unchanged)", df.filename)
            return Outcome.UNCHANGED
        # Same bytes under a different name == duplicate delivery (e.g. *_resend).
        # Record it under a synthetic hash; guard the insert so re-runs stay idempotent.
        synthetic_hash = f"{c_hash}:dup:{df.filename}"
        if conn.execute(q.EXISTS_DELIVERY_BY_HASH, (synthetic_hash,)).fetchone():
            logger.info("skip %s (duplicate already recorded)", df.filename)
            return Outcome.DUPLICATE
        delivery_id = _insert_delivery(conn, df, synthetic_hash, DeliveryStatus.SKIPPED_DUPLICATE)
        _write_issues(conn, delivery_id, [Issue(
            level=IssueLevel.FILE, check_name=Check.DUPLICATE_DELIVERY, severity=Severity.WARN,
            message=f"identical content to already-ingested delivery '{existing['filename']}'",
        )])
        conn.execute(q.UPDATE_DELIVERY_RESULT, (Health.WARN, 0, delivery_id))
        conn.commit()
        logger.info("skip %s (duplicate of %s)", df.filename, existing["filename"])
        return Outcome.DUPLICATE

    normalizer = REGISTRY.get(df.platform)
    if normalizer is None:
        logger.info("skip %s (no normalizer registered for %s)", df.filename, df.platform)
        return Outcome.NO_NORMALIZER

    logger.info("ingest %s", df.filename)
    try:
        raw_rows = normalizer.parse(df.path)
    except Exception as exc:  # noqa: BLE001 - a corrupt file must not abort the run
        delivery_id = _insert_delivery(conn, df, c_hash, DeliveryStatus.PARSE_ERROR)
        _write_issues(conn, delivery_id, [Issue(
            level=IssueLevel.FILE, check_name=Check.PARSE_ERROR, severity=Severity.FAIL,
            message=f"could not parse delivery: {exc}",
        )])
        conn.execute(q.UPDATE_DELIVERY_RESULT, (Health.FAIL, 0, delivery_id))
        conn.commit()
        logger.warning("parse_error %s: %s", df.filename, exc)
        return Outcome.PARSE_ERROR

    ctx = IngestContext(week_start=df.week_start, exchange_rates=ctx_rates)
    delivery_id = _insert_delivery(conn, df, c_hash, DeliveryStatus.PROCESSED)

    issues: list[Issue] = []
    seen: dict[tuple[str, str], CanonicalRow] = {}
    persisted = 0

    for raw in raw_rows:
        try:
            result = normalizer.normalize_row(raw, ctx)
        except Exception as exc:  # noqa: BLE001 - one bad row never aborts the file
            issues.append(Issue(
                level=IssueLevel.ROW, check_name=Check.ROW_ERROR, severity=Severity.FAIL,
                raw_row=raw, message=f"unexpected error normalizing row: {exc}",
            ))
            continue

        issues.extend(result.issues)
        row = result.row
        if row is None:
            continue

        key = (row.campaign, row.date)
        if key in seen:
            prev = seen[key]
            same = (prev.spend_usd, prev.impressions, prev.clicks) == (row.spend_usd, row.impressions, row.clicks)
            issues.append(Issue(
                level=IssueLevel.FILE,
                check_name=Check.DUPLICATE_ROW if same else Check.CONFLICTING_DUPLICATE_ROW,
                severity=Severity.WARN if same else Severity.FAIL,
                campaign=row.campaign, date=row.date,
                message=("exact duplicate row within file; kept first"
                         if same else "same campaign/date with different values; kept first"),
            ))
            continue
        seen[key] = row
        _upsert_metric(conn, row, delivery_id)
        persisted += 1

    _write_issues(conn, delivery_id, issues)
    health = _health_from_issues(issues, DeliveryStatus.PROCESSED)
    conn.execute(q.UPDATE_DELIVERY_RESULT, (health, persisted, delivery_id))
    conn.commit()
    logger.info("done %s: %d rows, %d issues, health=%s", df.filename, persisted, len(issues), health)
    return Outcome.PROCESSED


def _check_missing_deliveries(conn: sqlite3.Connection) -> int:
    """Delivery-level cadence check: every registered platform should have delivered one
    file per expected week. A gap is recorded as a 'missing' placeholder delivery (health=fail)
    so it shows up in the health view. Rebuilt each run -> idempotent and self-correcting.
    """
    conn.execute(q.DELETE_MISSING_ISSUES)
    conn.execute(q.DELETE_MISSING_DELIVERIES)

    present = {
        (r["platform"], r["week_start"])
        for r in conn.execute(q.SELECT_PROCESSED_DELIVERY_KEYS).fetchall()
    }

    missing = 0
    for platform in (p for p in config.EXPECTED_PLATFORMS if p in REGISTRY):
        for week in config.EXPECTED_WEEK_STARTS:
            if (platform, week) in present:
                continue
            delivery_id = conn.execute(
                q.INSERT_MISSING_DELIVERY,
                (platform, week, f"(missing) {platform}_{week}", f"missing:{platform}:{week}", _now()),
            ).lastrowid
            conn.execute(
                q.INSERT_MISSING_DELIVERY_ISSUE,
                (delivery_id, f"no {platform} delivery for week {week}", _now()),
            )
            missing += 1
    conn.commit()
    return missing


def _check_spend_plausibility(conn: sqlite3.Connection) -> int:
    """Cross-delivery spend-plausibility check (relative method + sanity floor).

    Each row/value in an inflated delivery is individually valid (positive, parses fine),
    so no row-level rule catches a whole delivery whose spend is off-scale. Here each
    processed delivery's CPM (spend / impressions x 1000) is compared to the *median* CPM
    of its platform's other deliveries -- median so the outlier can't pull its own baseline.

    A delivery is flagged only when its CPM is BOTH far above the peer median (relative:
    > ratio x median) AND independently implausible in absolute terms (sanity floor:
    > CPM ceiling). Requiring both means a delivery that is e.g. 5x the median but still a
    normal $3 CPM is never flagged. We flag, never correct: raw spend stays in metrics
    (traceability) and the issue tells a reviewer to investigate.

    Rebuilt each run (prior issues cleared first) -> idempotent. Health is recomputed from
    issues afterwards so the new delivery-level warning is reflected in the health view.
    """
    conn.execute(q.DELETE_SPEND_ISSUES)

    by_platform: dict[str, list[sqlite3.Row]] = {}
    for r in conn.execute(q.SELECT_DELIVERY_SPEND_AGG).fetchall():
        by_platform.setdefault(r["platform"], []).append(r)

    ratio = config.SPEND_PLAUSIBILITY_RATIO
    ceiling = config.SPEND_PLAUSIBILITY_CPM_CEILING
    flagged = 0

    for platform, deliveries in by_platform.items():
        if len(deliveries) < config.SPEND_PLAUSIBILITY_MIN_DELIVERIES:
            continue  # too few peers for a meaningful baseline
        cpm = {r["delivery_id"]: r["spend"] / r["impressions"] * 1000 for r in deliveries}
        baseline = median(cpm.values())
        if baseline <= 0:
            continue
        for r in deliveries:
            value = cpm[r["delivery_id"]]
            if not (value > ratio * baseline and value > ceiling):
                continue
            cpc = (r["spend"] / r["clicks"]) if r["clicks"] else None
            cpc_txt = f", CPC ${cpc:.2f}" if cpc is not None else ""
            message = (
                f"delivery CPM ${value:.2f} is implausible vs the {platform} median "
                f"${baseline:.2f} (> {ratio:g}x median and > ${ceiling:g} ceiling)"
                f"{cpc_txt}; raw spend kept, needs review"
            )
            conn.execute(q.INSERT_SPEND_ISSUE, (r["delivery_id"], f"{value:.2f}", message, _now()))
            logger.warning("spend_implausible %s week %s: CPM $%.2f (median $%.2f)",
                           platform, r["week_start"], value, baseline)
            flagged += 1

    conn.execute(q.RECOMPUTE_PROCESSED_HEALTH)
    conn.commit()
    return flagged


def run_ingest(db_path: Path | str | None = None, data_dir: Path | None = None) -> dict[str, Any]:
    """Run the full pipeline. Returns a per-file summary."""
    deliveries_dir = (data_dir / "deliveries") if data_dir else config.DELIVERIES_DIR
    rates = _load_exchange_rates()

    conn = get_connection(db_path)
    try:
        init_db(conn)
        files = discover(deliveries_dir)
        summary: dict[str, int] = {}
        for df in files:
            outcome = _process_file(conn, df, rates)
            summary[outcome] = summary.get(outcome, 0) + 1
        missing = _check_missing_deliveries(conn)
        if missing:
            summary[Outcome.MISSING] = missing
        _check_spend_plausibility(conn)
        total_metrics = conn.execute(q.COUNT_METRICS).fetchone()["n"]
        total_issues = conn.execute(q.COUNT_ISSUES).fetchone()["n"]
    finally:
        conn.close()

    return {"files": len(files), "outcomes": summary, "metrics": total_metrics, "issues": total_issues}
