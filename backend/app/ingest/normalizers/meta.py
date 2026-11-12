"""Meta Ads normalizer.

Source schema (CSV): campaign_name, date, spend_usd, impressions, clicks
- spend is already USD
- dates arrive in mixed formats (MM/DD/YYYY and ISO), distinguished by separator
- campaign names arrive in inconsistent casing
"""
from __future__ import annotations

import csv
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from ...constants import Check, Currency, IssueLevel, Platform, Severity
from .base import CanonicalRow, IngestContext, Issue, Normalizer, RowResult
from .common import normalize_campaign, parse_date, parse_int

# Meta dates arrive mixed; both formats are unambiguous by separator, so order is safe.
DATE_FORMATS = ["%m/%d/%Y", "%Y-%m-%d"]


class MetaNormalizer(Normalizer):
    platform = Platform.META

    def parse(self, path: Path) -> list[dict[str, Any]]:
        with path.open(newline="", encoding="utf-8") as fh:
            return list(csv.DictReader(fh))

    def normalize_row(self, raw: dict[str, Any], ctx: IngestContext) -> RowResult:
        issues: list[Issue] = []

        campaign_raw = raw.get("campaign_name", "") or ""
        campaign = normalize_campaign(campaign_raw)

        iso_date, date_err = parse_date(raw.get("date", ""), DATE_FORMATS)

        # --- Key-field validation: a bad key means the row cannot be keyed -> quarantine ---
        if not campaign:
            issues.append(Issue(
                level=IssueLevel.ROW, check_name=Check.MISSING_CAMPAIGN, severity=Severity.FAIL,
                field="campaign_name", raw_value=campaign_raw, raw_row=raw,
                message="campaign name is empty; row quarantined",
            ))
        if date_err:
            issues.append(Issue(
                level=IssueLevel.ROW, check_name=Check.INVALID_DATE, severity=Severity.FAIL,
                field="date", raw_value=raw.get("date"), raw_row=raw,
                campaign=campaign, message=f"{date_err}; row quarantined",
            ))
        if not campaign or date_err:
            return RowResult(row=None, issues=issues)

        # --- Metric-field validation: bad value -> null that field, keep the row ---
        spend_raw = (raw.get("spend_usd", "") or "").strip()
        spend_usd: float | None
        try:
            spend_usd = float(spend_raw) if spend_raw != "" else None
            if spend_usd is None:
                issues.append(Issue(
                    level=IssueLevel.ROW, check_name=Check.MISSING_SPEND, severity=Severity.FAIL,
                    field="spend_usd", raw_value=spend_raw, campaign=campaign, date=iso_date,
                    message="spend missing; stored null",
                ))
            elif spend_usd < 0:
                issues.append(Issue(
                    level=IssueLevel.ROW, check_name=Check.NEGATIVE_SPEND, severity=Severity.FAIL,
                    field="spend_usd", raw_value=spend_raw, campaign=campaign, date=iso_date,
                    message="spend is negative; stored null",
                ))
                spend_usd = None
        except ValueError:
            spend_usd = None
            issues.append(Issue(
                level=IssueLevel.ROW, check_name=Check.INVALID_SPEND, severity=Severity.FAIL,
                field="spend_usd", raw_value=spend_raw, campaign=campaign, date=iso_date,
                message="spend not numeric; stored null",
            ))

        impressions, imp_err = parse_int(raw.get("impressions", ""))
        if imp_err:
            issues.append(Issue(
                level=IssueLevel.ROW, check_name=Check.INVALID_IMPRESSIONS, severity=Severity.FAIL,
                field="impressions", raw_value=raw.get("impressions"),
                campaign=campaign, date=iso_date, message=f"impressions {imp_err}; stored null",
            ))
        elif impressions < 0:
            issues.append(Issue(
                level=IssueLevel.ROW, check_name=Check.NEGATIVE_IMPRESSIONS, severity=Severity.FAIL,
                field="impressions", raw_value=raw.get("impressions"),
                campaign=campaign, date=iso_date, message="impressions negative; stored null",
            ))
            impressions = None

        clicks, clk_err = parse_int(raw.get("clicks", ""))
        if clk_err:
            issues.append(Issue(
                level=IssueLevel.ROW, check_name=Check.MISSING_CLICKS, severity=Severity.FAIL,
                field="clicks", raw_value=raw.get("clicks"),
                campaign=campaign, date=iso_date, message=f"clicks {clk_err}; stored null",
            ))
        elif clicks < 0:
            issues.append(Issue(
                level=IssueLevel.ROW, check_name=Check.NEGATIVE_CLICKS, severity=Severity.FAIL,
                field="clicks", raw_value=raw.get("clicks"),
                campaign=campaign, date=iso_date, message="clicks negative; stored null",
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
                field="date", raw_value=iso_date, campaign=campaign, date=iso_date,
                message=f"date {iso_date} outside delivery week "
                        f"{ctx.week_start.isoformat()}..{window_end.isoformat()}",
            ))

        row = CanonicalRow(
            platform=Platform.META, campaign=campaign, date=iso_date,
            spend_usd=spend_usd, impressions=impressions, clicks=clicks,
            raw_amount=spend_raw or None, raw_currency=Currency.USD,
        )
        return RowResult(row=row, issues=issues)
