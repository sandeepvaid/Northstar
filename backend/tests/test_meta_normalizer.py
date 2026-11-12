"""Meta normalizer unit tests + an end-to-end idempotency check on the real data."""
from __future__ import annotations

from datetime import date

import pytest

from app.config import DELIVERIES_DIR
from app.ingest.normalizers.base import IngestContext
from app.ingest.normalizers.meta import MetaNormalizer
from app.ingest.pipeline import run_ingest

CTX = IngestContext(week_start=date(2026, 6, 1), exchange_rates={"USD": 1.0})


def _row(**over):
    base = {"campaign_name": "Summer Sale", "date": "06/01/2026",
            "spend_usd": "200.08", "impressions": "37215", "clicks": "574"}
    base.update(over)
    return base


def test_valid_row_normalizes():
    res = MetaNormalizer().normalize_row(_row(), CTX)
    assert res.row is not None
    assert res.row.date == "2026-06-01"
    assert res.row.spend_usd == 200.08
    assert res.issues == []


def test_campaign_is_trimmed_and_lowercased():
    res = MetaNormalizer().normalize_row(_row(campaign_name="  Brand Awareness Q2 "), CTX)
    assert res.row.campaign == "brand awareness q2"


def test_iso_and_us_dates_both_parse():
    assert MetaNormalizer().normalize_row(_row(date="2026-06-03"), CTX).row.date == "2026-06-03"
    assert MetaNormalizer().normalize_row(_row(date="06/03/2026"), CTX).row.date == "2026-06-03"


def test_invalid_calendar_date_quarantines_row():
    res = MetaNormalizer().normalize_row(_row(date="06/31/2026"), CTX)
    assert res.row is None
    assert any(i.check_name == "invalid_date" and i.severity == "fail" for i in res.issues)


def test_negative_spend_nulled_but_row_kept():
    res = MetaNormalizer().normalize_row(_row(spend_usd="-111.41"), CTX)
    assert res.row is not None
    assert res.row.spend_usd is None
    assert res.row.raw_amount == "-111.41"  # raw preserved for traceability
    assert any(i.check_name == "negative_spend" for i in res.issues)


def test_empty_clicks_nulled_but_row_kept():
    res = MetaNormalizer().normalize_row(_row(clicks=""), CTX)
    assert res.row is not None
    assert res.row.clicks is None
    assert any(i.check_name == "missing_clicks" for i in res.issues)


@pytest.mark.skipif(not DELIVERIES_DIR.exists(), reason="sample data not present")
def test_pipeline_is_idempotent(tmp_path):
    db = tmp_path / "test.sqlite3"
    first = run_ingest(db_path=db)
    second = run_ingest(db_path=db)
    assert first["metrics"] == second["metrics"]
    assert first["issues"] == second["issues"]
    assert second["outcomes"].get("unchanged", 0) >= 1  # second run skips unchanged files
