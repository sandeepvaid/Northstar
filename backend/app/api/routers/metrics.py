"""Campaign metrics endpoints (FR-4)."""
from __future__ import annotations

import sqlite3
from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, Query

from .. import queries as q
from ..calc import cpc, ctr
from ..deps import get_db
from ..schemas import MetricRow, MetricsResponse, SummaryResponse, SummaryRow, Totals

router = APIRouter(prefix="/metrics", tags=["metrics"])

# Maps the validated group_by choice to safe SQL fragments (never user free-text).
_GROUP_SQL = {
    "campaign": ('campaign AS "group", platform AS platform, ', "platform, campaign"),
    "platform": ('platform AS "group", NULL AS platform, ', "platform"),
}
_SORT_ATTR = {"spend": "spend_usd", "ctr": "ctr", "cpc": "cpc",
              "impressions": "impressions", "clicks": "clicks", "group": "group"}


def _filters(platform: str | None, date_from: date | None, date_to: date | None) -> dict:
    return {
        "platform": platform,
        "date_from": date_from.isoformat() if date_from else None,
        "date_to": date_to.isoformat() if date_to else None,
    }


def _totals(conn: sqlite3.Connection, params: dict) -> Totals:
    r = conn.execute(q.SELECT_METRICS_TOTALS, params).fetchone()
    return Totals(
        row_count=r["rows"], spend_usd=r["spend_usd"],
        impressions=r["impressions"], clicks=r["clicks"],
        ctr=ctr(r["impressions"], r["clicks"]), cpc=cpc(r["spend_usd"], r["clicks"]),
        date_min=r["date_min"], date_max=r["date_max"],
    )


@router.get("", response_model=MetricsResponse)
def list_metrics(
    conn: sqlite3.Connection = Depends(get_db),
    platform: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
):
    """Daily normalized rows with filters, plus filter-aware totals (traceability base)."""
    params = _filters(platform, date_from, date_to)
    items = [
        MetricRow(
            platform=r["platform"], campaign=r["campaign"], date=r["date"],
            spend_usd=r["spend_usd"], impressions=r["impressions"], clicks=r["clicks"],
            ctr=ctr(r["impressions"], r["clicks"]), cpc=cpc(r["spend_usd"], r["clicks"]),
        )
        for r in conn.execute(q.SELECT_METRICS, params).fetchall()
    ]
    return MetricsResponse(items=items, totals=_totals(conn, params))


@router.get("/summary", response_model=SummaryResponse)
def metrics_summary(
    conn: sqlite3.Connection = Depends(get_db),
    group_by: Literal["campaign", "platform"] = "campaign",
    platform: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    sort_by: Literal["spend", "ctr", "cpc", "impressions", "clicks", "group"] = "spend",
    order: Literal["asc", "desc"] = "desc",
):
    """Aggregates grouped by campaign or platform, with derived CTR/CPC and totals."""
    params = _filters(platform, date_from, date_to)
    group_select, group_clause = _GROUP_SQL[group_by]
    sql = q.SELECT_METRICS_SUMMARY.format(group_select=group_select, group_by=group_clause)

    items = [
        SummaryRow(
            group=r["group"], platform=r["platform"],
            spend_usd=r["spend_usd"], impressions=r["impressions"], clicks=r["clicks"],
            ctr=ctr(r["impressions"], r["clicks"]), cpc=cpc(r["spend_usd"], r["clicks"]),
            rows=r["rows"],
        )
        for r in conn.execute(sql, params).fetchall()
    ]

    # Sort in Python so derived CTR/CPC are sortable; Nones always sort last.
    attr = _SORT_ATTR[sort_by]
    present = [r for r in items if getattr(r, attr) is not None]
    absent = [r for r in items if getattr(r, attr) is None]
    present.sort(key=lambda r: getattr(r, attr), reverse=(order == "desc"))
    items = present + absent

    return SummaryResponse(group_by=group_by, items=items, totals=_totals(conn, params))
