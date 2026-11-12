"""Pydantic response models for the API."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class Totals(BaseModel):
    row_count: int
    spend_usd: float | None
    impressions: int | None
    clicks: int | None
    ctr: float | None
    cpc: float | None
    date_min: str | None          # earliest date in the (filtered) data shown
    date_max: str | None          # latest date in the (filtered) data shown


class MetricRow(BaseModel):
    platform: str
    campaign: str
    date: str
    spend_usd: float | None
    impressions: int | None
    clicks: int | None
    ctr: float | None
    cpc: float | None


class MetricsResponse(BaseModel):
    items: list[MetricRow]
    totals: Totals


class SummaryRow(BaseModel):
    group: str                 # campaign name or platform name
    platform: str | None       # present when grouping by campaign
    spend_usd: float | None
    impressions: int | None
    clicks: int | None
    ctr: float | None
    cpc: float | None
    rows: int


class SummaryResponse(BaseModel):
    group_by: str
    items: list[SummaryRow]
    totals: Totals


class DeliveryListItem(BaseModel):
    id: int
    platform: str
    week_start: str
    filename: str
    status: str
    health: str | None
    row_count: int | None
    issue_count: int
    fail_count: int
    warn_count: int
    ingested_at: str


class IssueOut(BaseModel):
    id: int
    level: str
    check_name: str
    severity: str
    field: str | None
    raw_value: str | None
    raw_row: dict[str, Any] | None
    campaign: str | None
    date: str | None
    message: str


class DeliveryDetail(BaseModel):
    id: int
    platform: str
    week_start: str
    filename: str
    status: str
    health: str | None
    row_count: int | None
    ingested_at: str
    issues: list[IssueOut]


class IngestResponse(BaseModel):
    files: int
    outcomes: dict[str, int]
    metrics: int
    issues: int
