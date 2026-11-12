"""End-to-end API tests against the real ingested dataset."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import config
from app.config import DELIVERIES_DIR
from app.ingest.pipeline import run_ingest

pytestmark = pytest.mark.skipif(not DELIVERIES_DIR.exists(), reason="sample data not present")


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    db = tmp_path_factory.mktemp("api") / "api.sqlite3"
    original = config.DB_PATH
    config.DB_PATH = db                 # get_db()/run_ingest() resolve this at call time
    run_ingest(db_path=db)
    from app.api.main import app
    with TestClient(app) as c:
        yield c
    config.DB_PATH = original


def test_metrics_returns_items_and_totals(client):
    body = client.get("/metrics").json()
    assert len(body["items"]) == 368
    assert body["totals"]["row_count"] == 368
    assert body["totals"]["spend_usd"] > 0
    assert set(body["items"][0]) >= {"platform", "campaign", "date", "ctr", "cpc"}


def test_metrics_platform_filter(client):
    body = client.get("/metrics", params={"platform": "google"}).json()
    assert body["items"]
    assert all(r["platform"] == "google" for r in body["items"])


def test_metrics_date_range_filter(client):
    body = client.get("/metrics", params={"date_from": "2026-06-08", "date_to": "2026-06-14"}).json()
    assert all("2026-06-08" <= r["date"] <= "2026-06-14" for r in body["items"])


def test_summary_by_platform(client):
    body = client.get("/metrics/summary", params={"group_by": "platform"}).json()
    groups = {r["group"] for r in body["items"]}
    assert groups == {"meta", "google", "linkedin"}


def test_summary_by_campaign_sorted_by_spend_desc(client):
    items = client.get("/metrics/summary", params={"group_by": "campaign"}).json()["items"]
    spends = [r["spend_usd"] for r in items if r["spend_usd"] is not None]
    assert spends == sorted(spends, reverse=True)
    assert items[0]["platform"] is not None     # campaign grouping carries platform


def test_summary_invalid_group_by_is_422(client):
    assert client.get("/metrics/summary", params={"group_by": "nope"}).status_code == 422


def test_deliveries_list_includes_missing_and_duplicate(client):
    body = client.get("/deliveries").json()
    statuses = {r["status"] for r in body}
    assert "missing" in statuses and "skipped_duplicate" in statuses
    assert any(r["health"] == "fail" for r in body)


def test_delivery_detail_has_issues(client):
    deliveries = client.get("/deliveries").json()
    failing = next(r for r in deliveries if r["fail_count"] > 0)
    detail = client.get(f"/deliveries/{failing['id']}").json()
    assert detail["id"] == failing["id"]
    assert len(detail["issues"]) >= 1


def test_delivery_not_found_is_404(client):
    assert client.get("/deliveries/999999").status_code == 404


def test_ingest_is_idempotent_over_http(client):
    first = client.post("/ingest").json()
    second = client.post("/ingest").json()
    assert first["metrics"] == second["metrics"] == 368
