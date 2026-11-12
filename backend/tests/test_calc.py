"""CTR/CPC derivation edge cases, including divide-by-zero (API criterion #4)."""
from __future__ import annotations

from app.api.calc import cpc, ctr


def test_ctr_normal():
    assert ctr(1000, 50) == 0.05


def test_ctr_zero_or_missing_impressions_is_none():
    assert ctr(0, 50) is None
    assert ctr(None, 50) is None


def test_ctr_missing_clicks_is_none():
    assert ctr(1000, None) is None


def test_cpc_normal():
    assert cpc(100.0, 50) == 2.0


def test_cpc_zero_clicks_is_none():
    assert cpc(100.0, 0) is None       # divide-by-zero -> null, documented


def test_cpc_missing_inputs_is_none():
    assert cpc(None, 50) is None
    assert cpc(100.0, None) is None
