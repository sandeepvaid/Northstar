"""Google normalizer unit tests + duplicate-handling checks via the pipeline."""
from __future__ import annotations

from datetime import date

import pytest

from app.config import DELIVERIES_DIR
from app.db import get_connection
from app.ingest.normalizers.base import IngestContext
from app.ingest.normalizers.google import GoogleNormalizer
from app.ingest.pipeline import run_ingest

CTX = IngestContext(week_start=date(2026, 6, 1), exchange_rates={"USD": 1.0, "EUR": 1.08})


def _row(**over):
    base = {"Campaign": "Search - Brand", "Day": "2026-06-07",
            "Cost (micros)": "117410000", "Currency": "USD", "Impr.": "37355", "Clicks": "779"}
    base.update(over)
    return base


def test_micros_to_usd_is_lossless():
    res = GoogleNormalizer().normalize_row(_row(), CTX)
    assert res.row.spend_usd == 117.41            # 117410000 / 1e6
    assert res.row.raw_amount == "117410000"       # raw micros preserved
    assert res.issues == []


def test_non_usd_currency_converts_via_rate():
    res = GoogleNormalizer().normalize_row(_row(**{"Cost (micros)": "100000000", "Currency": "EUR"}), CTX)
    assert res.row.spend_usd == 108.0              # 100 EUR * 1.08
    assert res.row.raw_currency == "EUR"


def test_unknown_currency_nulls_spend():
    res = GoogleNormalizer().normalize_row(_row(Currency="GBP"), CTX)
    assert res.row is not None
    assert res.row.spend_usd is None
    assert any(i.check_name == "unknown_currency" for i in res.issues)


def test_campaign_normalized():
    assert GoogleNormalizer().normalize_row(_row(Campaign="Search - BRAND "), CTX).row.campaign == "search - brand"


@pytest.mark.skipif(not DELIVERIES_DIR.exists(), reason="sample data not present")
def test_resend_is_detected_as_duplicate_delivery(tmp_path):
    db = tmp_path / "t.sqlite3"
    run_ingest(db_path=db)
    conn = get_connection(db)
    try:
        dup = conn.execute(
            "SELECT status, health FROM deliveries WHERE filename = 'google_ads_2026-06-15_resend.csv'"
        ).fetchone()
        issue = conn.execute(
            "SELECT COUNT(*) n FROM data_issues WHERE check_name = 'duplicate_delivery'"
        ).fetchone()
    finally:
        conn.close()
    assert dup["status"] == "skipped_duplicate"
    assert issue["n"] == 1


@pytest.mark.skipif(not DELIVERIES_DIR.exists(), reason="sample data not present")
def test_within_file_exact_duplicates_are_deduped(tmp_path):
    db = tmp_path / "t.sqlite3"
    run_ingest(db_path=db)
    conn = get_connection(db)
    try:
        dups = conn.execute(
            "SELECT COUNT(*) n FROM data_issues d JOIN deliveries dv ON d.delivery_id=dv.id "
            "WHERE dv.filename='google_ads_2026-06-01.csv' AND d.check_name='duplicate_row'"
        ).fetchone()
    finally:
        conn.close()
    assert dups["n"] == 8  # eight exact-duplicate rows collapsed, each flagged
