"""Derived-metric helpers, with explicit divide-by-zero handling.

CTR and CPC are never stored; they are computed at read time from (possibly null) sums.
Returning None (rather than 0 or raising) is the documented behavior when the
denominator is zero or a required input is missing.
"""
from __future__ import annotations


def ctr(impressions: int | None, clicks: int | None) -> float | None:
    if not impressions or clicks is None:
        return None
    return round(clicks / impressions, 6)


def cpc(spend_usd: float | None, clicks: int | None) -> float | None:
    if not clicks or spend_usd is None:
        return None
    return round(spend_usd / clicks, 4)
