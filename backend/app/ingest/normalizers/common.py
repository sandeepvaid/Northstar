"""Parsing helpers shared across platform normalizers.

Extracted once a second platform needed them; kept deliberately small.
All parsers are strict and return (value, error) so callers decide how to record failures.
"""
from __future__ import annotations

from datetime import datetime


def normalize_campaign(value: str | None) -> str:
    # trim, collapse internal whitespace, lowercase -> one canonical case
    return " ".join((value or "").split()).lower()


def parse_date(value: str | None, formats: list[str]) -> tuple[str | None, str | None]:
    """Strict parse against an ordered format list. strptime rejects impossible calendar
    dates (e.g. 06/31). Returns (iso_date, error)."""
    v = (value or "").strip()
    if not v:
        return None, "empty date"
    for fmt in formats:
        try:
            return datetime.strptime(v, fmt).date().isoformat(), None
        except ValueError:
            continue
    return None, f"invalid date {value!r} (expected one of {formats})"


def parse_int(value: str | None) -> tuple[int | None, str | None]:
    v = (value or "").strip()
    if v == "":
        return None, "missing value"
    try:
        return int(v), None
    except ValueError:
        return None, f"not an integer: {value!r}"
