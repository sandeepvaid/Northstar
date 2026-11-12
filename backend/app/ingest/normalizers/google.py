"""Google Ads normalizer.

Source schema (CSV): Campaign, Day, Cost (micros), Currency, Impr., Clicks
- spend arrives as integer micros (millionths of the currency unit) -> /1e6 is lossless
- dates are ISO
- files contain exact duplicate rows (handled by the pipeline's within-file dedupe)
"""
from __future__ import annotations

import csv
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from ...constants import Check, IssueLevel, Platform, Severity
from .base import CanonicalRow, IngestContext, Issue, Normalizer, RowResult
from .common import normalize_campaign, parse_date, parse_int

DATE_FORMATS = ["%Y-%m-%d"]
MICROS_PER_UNIT = 1_000_000


class GoogleNormalizer(Normalizer):
    platform = Platform.GOOGLE

    def parse(self, path: Path) -> list[dict[str, Any]]:
        with path.open(newline="", encoding="utf-8") as fh:
            return list(csv.DictReader(fh))

    def normalize_row(self, raw: dict[str, Any], ctx: IngestContext) -> RowResult:
        issues: list[Issue] = []

        campaign_raw = raw.get("Campaign", "") or ""
        campaign = normalize_campaign(campaign_raw)
        iso_date, date_err = parse_date(raw.get("Day", ""), DATE_FORMATS)

        # --- Key-field validation -> quarantine whole row ---
        if not campaign:
            issues.append(Issue(
                level=IssueLevel.ROW, check_name=Check.MISSING_CAMPAIGN, severity=Severity.FAIL,
                field="Campaign", raw_value=campaign_raw, raw_row=raw,
                message="campaign name is empty; row quarantined",
            ))
        if date_err:
            issues.append(Issue(
                level=IssueLevel.ROW, check_name=Check.INVALID_DATE, severity=Severity.FAIL,
                field="Day", raw_value=raw.get("Day"), raw_row=raw,
                campaign=campaign, message=f"{date_err}; row quarantined",
            ))
        if not campaign or date_err:
            return RowResult(row=None, issues=issues)

        # --- Spend: micros -> currency amount (lossless) -> USD (via fixed rate) ---
        micros_raw = (raw.get("Cost (micros)", "") or "").strip()
        currency = (raw.get("Currency", "") or "").strip().upper()
        spend_usd: float | None = None
        micros, micros_err = parse_int(micros_raw)

        if micros_err:
            issues.append(Issue(
                level=IssueLevel.ROW, check_name=Check.INVALID_SPEND, severity=Severity.FAIL,
                field="Cost (micros)", raw_value=micros_raw, campaign=campaign, date=iso_date,
                message=f"cost micros {micros_err}; stored null",
            ))
        elif micros < 0:
            issues.append(Issue(
                level=IssueLevel.ROW, check_name=Check.NEGATIVE_SPEND, severity=Severity.FAIL,
                field="Cost (micros)", raw_value=micros_raw, campaign=campaign, date=iso_date,
                message="cost is negative; stored null",
            ))
        elif currency not in ctx.exchange_rates:
            issues.append(Issue(
                level=IssueLevel.ROW, check_name=Check.UNKNOWN_CURRENCY, severity=Severity.FAIL,
                field="Currency", raw_value=currency or None, campaign=campaign, date=iso_date,
                message=f"no exchange rate for currency {currency!r}; spend stored null",
            ))
        else:
            spend_usd = round(micros / MICROS_PER_UNIT * ctx.exchange_rates[currency], 4)

        impressions, imp_err = parse_int(raw.get("Impr.", ""))
        if imp_err:
            issues.append(Issue(
                level=IssueLevel.ROW, check_name=Check.INVALID_IMPRESSIONS, severity=Severity.FAIL,
                field="Impr.", raw_value=raw.get("Impr."), campaign=campaign, date=iso_date,
                message=f"impressions {imp_err}; stored null",
            ))
        elif impressions < 0:
            issues.append(Issue(
                level=IssueLevel.ROW, check_name=Check.NEGATIVE_IMPRESSIONS, severity=Severity.FAIL,
                field="Impr.", raw_value=raw.get("Impr."), campaign=campaign, date=iso_date,
                message="impressions negative; stored null",
            ))
            impressions = None

        clicks, clk_err = parse_int(raw.get("Clicks", ""))
        if clk_err:
            issues.append(Issue(
                level=IssueLevel.ROW, check_name=Check.MISSING_CLICKS, severity=Severity.FAIL,
                field="Clicks", raw_value=raw.get("Clicks"), campaign=campaign, date=iso_date,
                message=f"clicks {clk_err}; stored null",
            ))
        elif clicks < 0:
            issues.append(Issue(
                level=IssueLevel.ROW, check_name=Check.NEGATIVE_CLICKS, severity=Severity.FAIL,
                field="Clicks", raw_value=raw.get("Clicks"), campaign=campaign, date=iso_date,
                message="clicks negative; stored null",
            ))
            clicks = None

        # --- Sanity / cadence (warn: row kept) ---
        if clicks is not None and impressions is not None and clicks > impressions:
            issues.append(Issue(
                level=IssueLevel.ROW, check_name=Check.CLICKS_GT_IMPRESSIONS, severity=Severity.WARN,
                campaign=campaign, date=iso_date,
                message=f"clicks ({clicks}) exceed impressions ({impressions})",
            ))

        window_end = ctx.week_start + timedelta(days=6)
        parsed = date.fromisoformat(iso_date)
        if not (ctx.week_start <= parsed <= window_end):
            issues.append(Issue(
                level=IssueLevel.ROW, check_name=Check.DATE_OUT_OF_WINDOW, severity=Severity.WARN,
                field="Day", raw_value=iso_date, campaign=campaign, date=iso_date,
                message=f"date {iso_date} outside delivery week "
                        f"{ctx.week_start.isoformat()}..{window_end.isoformat()}",
            ))

        row = CanonicalRow(
            platform=Platform.GOOGLE, campaign=campaign, date=iso_date,
            spend_usd=spend_usd, impressions=impressions, clicks=clicks,
            raw_amount=micros_raw or None, raw_currency=currency or None,
        )
        return RowResult(row=row, issues=issues)
