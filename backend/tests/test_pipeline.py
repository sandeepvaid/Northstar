"""Pipeline-level guarantees on self-contained synthetic deliveries:
error isolation (NFR-2), duplicate handling, and value-level upsert idempotency (NFR-1).
"""
from __future__ import annotations

import pytest

from app import config
from app.db import get_connection
from app.ingest.normalizers.base import Issue
from app.ingest.pipeline import _health_from_issues, run_ingest

META_HEADER = "campaign_name,date,spend_usd,impressions,clicks\n"


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    """A temp data dir with its own exchange rates, isolated from the provided dataset."""
    data = tmp_path / "data"
    deliveries = data / "deliveries"
    deliveries.mkdir(parents=True)
    (data / "exchange_rates.json").write_text('{"rates": {"USD": 1.0, "EUR": 1.08}}')
    monkeypatch.setattr(config, "EXCHANGE_RATES_PATH", data / "exchange_rates.json")

    def write(name: str, content: str):
        (deliveries / name).write_text(content)

    return data, write


def _metrics(db):
    conn = get_connection(db)
    try:
        return conn.execute(
            "SELECT campaign, date, spend_usd, impressions, clicks FROM metrics "
            "WHERE platform='meta' ORDER BY campaign, date"
        ).fetchall()
    finally:
        conn.close()


# --- NFR-2: error isolation ------------------------------------------------

def test_corrupt_file_does_not_abort_run(workspace, tmp_path):
    data, write = workspace
    write("meta_ads_2026-06-01.csv", META_HEADER + "Summer Sale,06/01/2026,200.08,37215,574\n")
    write("linkedin_ads_2026-06-01.json", "{ this is not valid json ")  # corrupt
    db = tmp_path / "t.sqlite3"

    summary = run_ingest(db_path=db, data_dir=data)

    assert summary["outcomes"].get("processed", 0) == 1   # meta still processed
    assert summary["outcomes"].get("parse_error", 0) == 1  # corrupt file isolated
    conn = get_connection(db)
    try:
        assert conn.execute("SELECT COUNT(*) n FROM metrics").fetchone()["n"] == 1
        bad = conn.execute(
            "SELECT health FROM deliveries WHERE filename='linkedin_ads_2026-06-01.json'"
        ).fetchone()
        assert bad["health"] == "fail"
        assert conn.execute(
            "SELECT COUNT(*) n FROM data_issues WHERE check_name='parse_error'"
        ).fetchone()["n"] == 1
    finally:
        conn.close()


def test_bad_rows_isolated_good_rows_survive(workspace, tmp_path):
    data, write = workspace
    write("meta_ads_2026-06-01.csv", META_HEADER
          + "Good One,06/01/2026,100.00,1000,50\n"
          + "Bad Date,06/31/2026,100.00,1000,50\n"       # quarantined
          + "Neg Spend,06/02/2026,-5.00,1000,50\n"        # spend nulled, row kept
          + "Good Two,06/03/2026,120.00,2000,80\n")
    db = tmp_path / "t.sqlite3"
    run_ingest(db_path=db, data_dir=data)

    rows = {r["campaign"]: r for r in _metrics(db)}
    assert set(rows) == {"good one", "neg spend", "good two"}  # bad date quarantined out
    assert rows["neg spend"]["spend_usd"] is None             # nulled, but present
    assert rows["good one"]["spend_usd"] == 100.0


# --- within-file duplicates ------------------------------------------------

def test_exact_duplicate_row_deduped_as_warn(workspace, tmp_path):
    data, write = workspace
    write("meta_ads_2026-06-01.csv", META_HEADER
          + "Summer Sale,06/01/2026,200.00,1000,50\n"
          + "Summer Sale,06/01/2026,200.00,1000,50\n")
    db = tmp_path / "t.sqlite3"
    run_ingest(db_path=db, data_dir=data)

    assert len(_metrics(db)) == 1
    conn = get_connection(db)
    try:
        assert conn.execute(
            "SELECT severity FROM data_issues WHERE check_name='duplicate_row'"
        ).fetchone()["severity"] == "warn"
    finally:
        conn.close()


def test_conflicting_duplicate_row_is_fail_first_kept(workspace, tmp_path):
    data, write = workspace
    write("meta_ads_2026-06-01.csv", META_HEADER
          + "Summer Sale,06/01/2026,200.00,1000,50\n"
          + "Summer Sale,06/01/2026,999.00,1000,50\n")   # same key, different spend
    db = tmp_path / "t.sqlite3"
    run_ingest(db_path=db, data_dir=data)

    rows = _metrics(db)
    assert len(rows) == 1 and rows[0]["spend_usd"] == 200.0  # first value kept
    conn = get_connection(db)
    try:
        assert conn.execute(
            "SELECT severity FROM data_issues WHERE check_name='conflicting_duplicate_row'"
        ).fetchone()["severity"] == "fail"
    finally:
        conn.close()


# --- NFR-1: idempotency ----------------------------------------------------

def test_reingest_same_file_is_noop(workspace, tmp_path):
    data, write = workspace
    write("meta_ads_2026-06-01.csv", META_HEADER + "Summer Sale,06/01/2026,200.00,1000,50\n")
    db = tmp_path / "t.sqlite3"
    first = run_ingest(db_path=db, data_dir=data)
    second = run_ingest(db_path=db, data_dir=data)
    assert _metrics(db) == _metrics(db)  # stable
    assert first["metrics"] == second["metrics"]
    assert second["outcomes"].get("unchanged", 0) >= 1


def test_changed_file_upserts_by_natural_key(workspace, tmp_path):
    data, write = workspace
    write("meta_ads_2026-06-01.csv", META_HEADER + "Summer Sale,06/01/2026,200.00,1000,50\n")
    db = tmp_path / "t.sqlite3"
    run_ingest(db_path=db, data_dir=data)
    assert _metrics(db)[0]["spend_usd"] == 200.0

    # same natural key, new spend -> upsert overwrites, no duplicate row
    write("meta_ads_2026-06-01.csv", META_HEADER + "Summer Sale,06/01/2026,250.00,1000,50\n")
    run_ingest(db_path=db, data_dir=data)
    rows = _metrics(db)
    assert len(rows) == 1 and rows[0]["spend_usd"] == 250.0


# --- cross-delivery spend plausibility (#1) --------------------------------

def _meta_week(campaign: str, mmdd: str, spend: float, impr: int, clicks: int) -> str:
    return META_HEADER + f"{campaign},06/{mmdd}/2026,{spend},{impr},{clicks}\n"


def _spend_issues(db):
    conn = get_connection(db)
    try:
        return conn.execute(
            "SELECT di.delivery_id, di.level, di.severity, d.week_start, d.health "
            "FROM data_issues di JOIN deliveries d ON d.id = di.delivery_id "
            "WHERE di.check_name = 'spend_implausible'"
        ).fetchall()
    finally:
        conn.close()


def test_spend_plausibility_flags_offscale_delivery(workspace, tmp_path):
    data, write = workspace
    # Three ~$3 CPM weeks + one ~$300 CPM week (spend 100x off, impressions normal).
    write("meta_ads_2026-06-01.csv", _meta_week("Summer Sale", "01", 300.0, 100_000, 500))
    write("meta_ads_2026-06-08.csv", _meta_week("Summer Sale", "08", 30_000.0, 100_000, 500))
    write("meta_ads_2026-06-15.csv", _meta_week("Summer Sale", "15", 300.0, 100_000, 500))
    write("meta_ads_2026-06-22.csv", _meta_week("Summer Sale", "22", 300.0, 100_000, 500))
    db = tmp_path / "t.sqlite3"
    run_ingest(db_path=db, data_dir=data)

    issues = _spend_issues(db)
    assert len(issues) == 1                       # only the off-scale week
    only = issues[0]
    assert only["week_start"] == "2026-06-08"     # the inflated one
    assert only["level"] == "delivery" and only["severity"] == "warn"
    assert only["health"] == "warn"               # health reflects the delivery-level warning

    # the three normal deliveries stay pass (raw spend still present -- not corrected)
    conn = get_connection(db)
    try:
        passes = conn.execute(
            "SELECT COUNT(*) n FROM deliveries WHERE status='processed' AND health='pass'"
        ).fetchone()["n"]
        assert passes == 3
        kept = conn.execute(
            "SELECT spend_usd FROM metrics WHERE date='2026-06-08'"
        ).fetchone()["spend_usd"]
        assert kept == 30_000.0                    # flagged, never auto-corrected
    finally:
        conn.close()


def test_spend_plausibility_is_idempotent(workspace, tmp_path):
    data, write = workspace
    write("meta_ads_2026-06-01.csv", _meta_week("Summer Sale", "01", 300.0, 100_000, 500))
    write("meta_ads_2026-06-08.csv", _meta_week("Summer Sale", "08", 30_000.0, 100_000, 500))
    write("meta_ads_2026-06-15.csv", _meta_week("Summer Sale", "15", 300.0, 100_000, 500))
    db = tmp_path / "t.sqlite3"
    run_ingest(db_path=db, data_dir=data)
    run_ingest(db_path=db, data_dir=data)
    assert len(_spend_issues(db)) == 1            # not accumulated across runs


def test_spend_plausibility_needs_enough_peers(workspace, tmp_path):
    data, write = workspace
    # Only two deliveries -> below the min-peers threshold -> no baseline, nothing flagged.
    write("meta_ads_2026-06-01.csv", _meta_week("Summer Sale", "01", 300.0, 100_000, 500))
    write("meta_ads_2026-06-08.csv", _meta_week("Summer Sale", "08", 30_000.0, 100_000, 500))
    db = tmp_path / "t.sqlite3"
    run_ingest(db_path=db, data_dir=data)
    assert _spend_issues(db) == []


def test_spend_plausibility_sanity_floor_blocks_small_cpms(workspace, tmp_path):
    data, write = workspace
    # One delivery is 8x the median CPM but still only ~$8 CPM (< $50 ceiling) -> not flagged.
    write("meta_ads_2026-06-01.csv", _meta_week("Summer Sale", "01", 100.0, 100_000, 500))  # $1
    write("meta_ads_2026-06-08.csv", _meta_week("Summer Sale", "08", 800.0, 100_000, 500))  # $8
    write("meta_ads_2026-06-15.csv", _meta_week("Summer Sale", "15", 100.0, 100_000, 500))  # $1
    db = tmp_path / "t.sqlite3"
    run_ingest(db_path=db, data_dir=data)
    assert _spend_issues(db) == []


# --- health rollup ---------------------------------------------------------

def test_health_rollup_precedence():
    warn = [Issue(level="row", check_name="x", severity="warn", message="")]
    fail = [Issue(level="row", check_name="y", severity="fail", message="")]
    assert _health_from_issues([], "processed") == "pass"
    assert _health_from_issues(warn, "processed") == "warn"
    assert _health_from_issues(warn + fail, "processed") == "fail"
    assert _health_from_issues([], "parse_error") == "fail"
