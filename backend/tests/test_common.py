"""Unit tests for the shared parsing helpers."""
from __future__ import annotations

from app.ingest.normalizers.common import normalize_campaign, parse_date, parse_int

META_FORMATS = ["%m/%d/%Y", "%Y-%m-%d"]


def test_normalize_campaign_trims_collapses_lowercases():
    assert normalize_campaign("  Brand   Awareness  Q2 ") == "brand awareness q2"
    assert normalize_campaign("Retargeting - US") == "retargeting - us"


def test_normalize_campaign_handles_none_and_empty():
    assert normalize_campaign(None) == ""
    assert normalize_campaign("   ") == ""


def test_parse_date_accepts_both_formats():
    assert parse_date("06/02/2026", META_FORMATS) == ("2026-06-02", None)
    assert parse_date("2026-06-02", META_FORMATS) == ("2026-06-02", None)


def test_parse_date_rejects_impossible_calendar_date():
    iso, err = parse_date("06/31/2026", META_FORMATS)
    assert iso is None and err is not None


def test_parse_date_rejects_empty():
    assert parse_date("", META_FORMATS) == (None, "empty date")
    assert parse_date(None, META_FORMATS) == (None, "empty date")


def test_parse_int_variants():
    assert parse_int(" 574 ") == (574, None)
    assert parse_int("")[0] is None
    assert parse_int(None)[0] is None
    assert parse_int("12.5")[0] is None       # not an integer
    assert parse_int("abc")[0] is None
