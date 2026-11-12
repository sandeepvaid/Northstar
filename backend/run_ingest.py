"""CLI entry point: run the ingestion pipeline.

    python run_ingest.py            # ingest into the default sqlite db
    python run_ingest.py --reset    # delete the db first, then ingest
"""
from __future__ import annotations

import argparse
import logging

from app import config
from app.ingest.pipeline import run_ingest


def main() -> None:
    parser = argparse.ArgumentParser(description="Campaign Data Hub ingestion")
    parser.add_argument("--reset", action="store_true", help="delete the database before ingesting")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    if args.reset and config.DB_PATH.exists():
        config.DB_PATH.unlink()

    summary = run_ingest()
    print("\nIngestion summary:")
    print(f"  files seen : {summary['files']}")
    print(f"  outcomes   : {summary['outcomes']}")
    print(f"  metrics    : {summary['metrics']}")
    print(f"  issues     : {summary['issues']}")


if __name__ == "__main__":
    main()
