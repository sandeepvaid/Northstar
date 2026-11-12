"""Normalizer contract + shared data shapes.

A normalizer turns one platform's raw delivery file into canonical rows plus the
issues found while doing so. Adding a platform = add one Normalizer subclass and
register it in the pipeline's REGISTRY; nothing else changes.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any


@dataclass
class IngestContext:
    """Per-delivery context handed to the normalizer."""
    week_start: date
    exchange_rates: dict[str, float]


@dataclass
class Issue:
    level: str          # row | file | delivery
    check_name: str
    severity: str       # warn | fail
    message: str
    field: str | None = None
    raw_value: str | None = None
    raw_row: dict[str, Any] | None = None
    campaign: str | None = None
    date: str | None = None


@dataclass
class CanonicalRow:
    platform: str
    campaign: str
    date: str                       # ISO YYYY-MM-DD
    spend_usd: float | None
    impressions: int | None
    clicks: int | None
    raw_amount: str | None
    raw_currency: str | None


@dataclass
class RowResult:
    """Outcome of normalizing one raw row.

    row is None when the row is quarantined (a key field could not be trusted,
    so it must not enter metrics). issues is always populated with what we found.
    """
    row: CanonicalRow | None
    issues: list[Issue] = field(default_factory=list)


class Normalizer(ABC):
    platform: str

    @abstractmethod
    def parse(self, path: Path) -> list[dict[str, Any]]:
        """Read the file into raw row dicts. May raise on a corrupt/unreadable file."""

    @abstractmethod
    def normalize_row(self, raw: dict[str, Any], ctx: IngestContext) -> RowResult:
        """Map + validate one raw row into a canonical row (or quarantine it)."""
