"""Trigger (re-)ingestion (FR-6)."""
from __future__ import annotations

from fastapi import APIRouter

from ...ingest.pipeline import run_ingest
from ..schemas import IngestResponse

router = APIRouter(tags=["ingest"])


@router.post("/ingest", response_model=IngestResponse)
def trigger_ingest():
    """Run the full ingestion pipeline. Idempotent: re-running does not duplicate data."""
    summary = run_ingest()
    return IngestResponse(**summary)
