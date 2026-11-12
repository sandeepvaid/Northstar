"""Data-health endpoints (FR-5)."""
from __future__ import annotations

import json
import sqlite3

from fastapi import APIRouter, Depends, HTTPException

from .. import queries as q
from ..deps import get_db
from ..schemas import DeliveryDetail, DeliveryListItem, IssueOut

router = APIRouter(prefix="/deliveries", tags=["deliveries"])


@router.get("", response_model=list[DeliveryListItem])
def list_deliveries(conn: sqlite3.Connection = Depends(get_db)):
    """All deliveries with health classification and issue counts (scannable list)."""
    return [
        DeliveryListItem(
            id=r["id"], platform=r["platform"], week_start=r["week_start"],
            filename=r["filename"], status=r["status"], health=r["health"],
            row_count=r["row_count"], issue_count=r["issue_count"],
            fail_count=r["fail_count"], warn_count=r["warn_count"], ingested_at=r["ingested_at"],
        )
        for r in conn.execute(q.SELECT_DELIVERIES).fetchall()
    ]


@router.get("/{delivery_id}", response_model=DeliveryDetail)
def get_delivery(delivery_id: int, conn: sqlite3.Connection = Depends(get_db)):
    """One delivery plus its full quality report (all recorded issues)."""
    d = conn.execute(q.SELECT_DELIVERY, (delivery_id,)).fetchone()
    if d is None:
        raise HTTPException(status_code=404, detail=f"delivery {delivery_id} not found")

    issues = [
        IssueOut(
            id=i["id"], level=i["level"], check_name=i["check_name"], severity=i["severity"],
            field=i["field"], raw_value=i["raw_value"],
            raw_row=json.loads(i["raw_row"]) if i["raw_row"] else None,
            campaign=i["campaign"], date=i["date"], message=i["message"],
        )
        for i in conn.execute(q.SELECT_DELIVERY_ISSUES, (delivery_id,)).fetchall()
    ]
    return DeliveryDetail(
        id=d["id"], platform=d["platform"], week_start=d["week_start"], filename=d["filename"],
        status=d["status"], health=d["health"], row_count=d["row_count"],
        ingested_at=d["ingested_at"], issues=issues,
    )
