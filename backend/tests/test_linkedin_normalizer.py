"""LinkedIn normalizer unit tests + delivery-level missing-delivery check."""
from __future__ import annotations

from datetime import date

import pytest

from app.config import DELIVERIES_DIR
from app.db import get_connection
from app.ingest.normalizers.base import IngestContext
from app.ingest.normalizers.linkedin import LinkedInNormalizer
from app.ingest.pipeline import run_ingest

CTX = IngestContext(week_start=date(2026, 6, 1), exchange_rates={"USD": 1.0, "EUR": 1.08})


def _row(**over):
    base = {"campaign": "ABM Tier 1", "date_ts": 1780272000000,
            "spend": {"amount": "92.37", "currency": "EUR"}, "impressions": 41097, "clicks": 1283}
    base.update(over)
    return base


def test_epoch_ms_converts_to_utc_date():
    assert LinkedInNormalizer().normalize_row(_row(), CTX).row.date == "2026-06-01"


def test_eur_converts_and_keeps_raw():
    res = LinkedInNormalizer().normalize_row(_row(), CTX)
    assert res.row.spend_usd == round(92.37 * 1.08, 4)  # 99.7596
    assert res.row.raw_amount == "92.37" and res.row.raw_currency == "EUR"


def test_missing_clicks_field_nulls_but_keeps_row():
    raw = _row()
    del raw["clicks"]
    res = LinkedInNormalizer().normalize_row(raw, CTX)
    assert res.row is not None
    assert res.row.clicks is None
    assert res.row.spend_usd is not None           # spend still computed
    assert any(i.check_name == "missing_clicks" for i in res.issues)


def test_missing_date_ts_quarantines_row():
    raw = _row()
    del raw["date_ts"]
    res = LinkedInNormalizer().normalize_row(raw, CTX)
    assert res.row is None
    assert any(i.check_name == "invalid_date" for i in res.issues)


def test_campaign_normalized():
    assert LinkedInNormalizer().normalize_row(_row(campaign="ABM Tier 1 "), CTX).row.campaign == "abm tier 1"


@pytest.mark.skipif(not DELIVERIES_DIR.exists(), reason="sample data not present")
def test_missing_linkedin_0622_is_flagged(tmp_path):
    db = tmp_path / "t.sqlite3"
    run_ingest(db_path=db)
    conn = get_connection(db)
    try:
        row = conn.execute(
            "SELECT status, health FROM deliveries WHERE platform='linkedin' AND week_start='2026-06-22'"
        ).fetchone()
        issue = conn.execute(
            "SELECT COUNT(*) n FROM data_issues WHERE check_name='missing_delivery'"
        ).fetchone()
    finally:
        conn.close()
    assert row["status"] == "missing" and row["health"] == "fail"
    assert issue["n"] == 1
