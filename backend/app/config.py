"""Paths and expected-delivery configuration.

Defaults resolve relative to the repo root so a fresh clone runs with no env setup.
Override DATA_DIR / DB_PATH via environment for tests or alternate datasets.
"""
from __future__ import annotations

import os
from pathlib import Path

from .constants import Platform

# backend/app/config.py -> parents[2] == repo root
REPO_ROOT = Path(__file__).resolve().parents[2]

DATA_DIR = Path(os.environ.get("CDH_DATA_DIR", REPO_ROOT / "assesment-doc" / "campaign-data-hub" / "data"))
DELIVERIES_DIR = DATA_DIR / "deliveries"
EXCHANGE_RATES_PATH = DATA_DIR / "exchange_rates.json"

DB_PATH = Path(os.environ.get("CDH_DB_PATH", REPO_ROOT / "backend" / "campaign_data_hub.sqlite3"))

SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"

# Each platform is expected to deliver one file per week for these week-start dates.
EXPECTED_WEEK_STARTS = ("2026-06-01", "2026-06-08", "2026-06-15", "2026-06-22", "2026-06-29")
EXPECTED_PLATFORMS = (Platform.META, Platform.GOOGLE, Platform.LINKEDIN)

# Cross-delivery spend-plausibility check (relative method + sanity floor).
# A delivery's CPM (spend / impressions * 1000) is compared to the median CPM across
# that platform's other deliveries. It is flagged only when it is BOTH far from the
# peer median (relative) AND independently implausible in absolute terms (floor) -- so
# a delivery that is 5x the median but still a normal $3 CPM is never flagged.
SPEND_PLAUSIBILITY_MIN_DELIVERIES = 3   # need enough peers for a meaningful median
SPEND_PLAUSIBILITY_RATIO = 5.0          # flag if CPM > ratio x median (or < median / ratio)
SPEND_PLAUSIBILITY_CPM_CEILING = 50.0   # sanity floor: absolute CPM ($) above which it is suspect
