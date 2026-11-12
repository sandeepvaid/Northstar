"""Tests for delivery-file discovery and content hashing."""
from __future__ import annotations

from datetime import date

from app.ingest.discover import content_hash, discover


def _make_deliveries(tmp_path):
    d = tmp_path / "deliveries"
    d.mkdir()
    (d / "meta_ads_2026-06-01.csv").write_text("x")
    (d / "google_ads_2026-06-15.csv").write_text("y")
    (d / "google_ads_2026-06-15_resend.csv").write_text("y")
    (d / "linkedin_ads_2026-06-29.json").write_text("[]")
    (d / "notes.txt").write_text("ignore me")          # unrecognized -> skipped
    (d / "exchange_rates.json").write_text("{}")         # wrong pattern -> skipped
    return d


def test_discover_parses_platform_and_week(tmp_path):
    files = discover(_make_deliveries(tmp_path))
    by_name = {f.filename: f for f in files}
    assert by_name["meta_ads_2026-06-01.csv"].platform == "meta"
    assert by_name["meta_ads_2026-06-01.csv"].week_start == date(2026, 6, 1)
    assert by_name["linkedin_ads_2026-06-29.json"].platform == "linkedin"


def test_discover_ignores_unrecognized_files(tmp_path):
    names = {f.filename for f in discover(_make_deliveries(tmp_path))}
    assert "notes.txt" not in names
    assert "exchange_rates.json" not in names
    assert len(names) == 4


def test_discover_sorts_original_before_resend(tmp_path):
    names = [f.filename for f in discover(_make_deliveries(tmp_path))]
    assert names.index("google_ads_2026-06-15.csv") < names.index("google_ads_2026-06-15_resend.csv")


def test_content_hash_is_deterministic_and_content_sensitive(tmp_path):
    a = tmp_path / "a"; a.write_text("same")
    b = tmp_path / "b"; b.write_text("same")
    c = tmp_path / "c"; c.write_text("different")
    assert content_hash(a) == content_hash(b)
    assert content_hash(a) != content_hash(c)
