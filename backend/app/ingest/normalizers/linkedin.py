"""LinkedIn Ads normalizer.

Source schema (JSON array): each record has
  campaign, date_ts (epoch milliseconds), spend {amount (string), currency}, impressions, clicks
- spend is a string amount in a foreign currency (EUR) -> convert via fixed rates, keep raw
- dates are epoch-ms integers
- some records omit the clicks field entirely
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from ...constants import Check, IssueLevel, Platform, Severity
from .base import CanonicalRow, IngestContext, Issue, Normalizer, RowResult
from .common import normalize_campaign

MS_PER_SECOND = 1000


def _coerce_count(value: Any) -> tuple[int | None, str | None]:
    """LinkedIn counts arrive as JSON numbers; a missing field is None."""
    if value is None:
        return None, "missing value"
    if isinstance(value, bool):  # guard: bool is an int subclass
        return None, f"not an integer: {value!r}"
    if isinstance(value, int):
        return value, None
    try:
        return int(str(value).strip()), None
    except ValueError:
        return None, f"not an integer: {value!r}"


class LinkedInNormalizer(Normalizer):
    platform = Platform.LINKEDIN

    def parse(self, path: Path) -> list[dict[str, Any]]:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            raise ValueError("expected a JSON array of records")
        return data

    def normalize_row(self, raw: dict[str, Any], ctx: IngestContext) -> RowResult:
        issues: list[Issue] = []

        campaign = normalize_campaign(raw.get("campaign"))

        # --- date_ts (epoch ms) -> ISO date ---
        iso_date: str | None = None
        ts = raw.get("date_ts")
        if isinstance(ts, (int, float)) and not isinstance(ts, bool):
            try:
                iso_date = datetime.fromtimestamp(ts / MS_PER_SECOND, tz=timezone.utc).date().isoformat()
            except (OverflowError, OSError, ValueError):
                iso_date = None

        # --- Key-field validation -> quarantine ---
        if not campaign:
            issues.append(Issue(
                level=IssueLevel.ROW, check_name=Check.MISSING_CAMPAIGN, severity=Severity.FAIL,
                field="campaign", raw_value=str(raw.get("campaign")), raw_row=raw,
                message="campaign name is empty; row quarantined",
            ))
        if iso_date is None:
            issues.append(Issue(
                level=IssueLevel.ROW, check_name=Check.INVALID_DATE, severity=Severity.FAIL,
                field="date_ts", raw_value=str(ts), raw_row=raw,
                campaign=campaign, message="date_ts missing/invalid; row quarantined",
            ))
        if not campaign or iso_date is None:
            return RowResult(row=None, issues=issues)

        # --- Spend: string amount in a foreign currency -> USD (keep raw) ---
        spend = raw.get("spend") or {}
        amount_raw = spend.get("amount") if isinstance(spend, dict) else None
        currency = (spend.get("currency") if isinstance(spend, dict) else None) or ""
        currency = currency.strip().upper()
        spend_usd: float | None = None

        if amount_raw is None or str(amount_raw).strip() == "":
            issues.append(Issue(
                level=IssueLevel.ROW, check_name=Check.MISSING_SPEND, severity=Severity.FAIL,
                field="spend.amount", raw_value=None, campaign=campaign, date=iso_date,
                message="spend amount missing; stored null",
            ))
        else:
            try:
                amount = float(str(amount_raw))
                if amount < 0:
                    issues.append(Issue(
                        level=IssueLevel.ROW, check_name=Check.NEGATIVE_SPEND, severity=Severity.FAIL,
                        field="spend.amount", raw_value=str(amount_raw),
                        campaign=campaign, date=iso_date, message="spend is negative; stored null",
                    ))
                elif currency not in ctx.exchange_rates:
                    issues.append(Issue(
                        level=IssueLevel.ROW, check_name=Check.UNKNOWN_CURRENCY, severity=Severity.FAIL,
                        field="spend.currency", raw_value=currency or None,
                        campaign=campaign, date=iso_date,
                        message=f"no exchange rate for currency {currency!r}; spend stored null",
                    ))
                else:
                    spend_usd = round(amount * ctx.exchange_rates[currency], 4)
            except ValueError:
                issues.append(Issue(
                    level=IssueLevel.ROW, check_name=Check.INVALID_SPEND, severity=Severity.FAIL,
                    field="spend.amount", raw_value=str(amount_raw),
                    campaign=campaign, date=iso_date, message="spend not numeric; stored null",
                ))

        impressions, imp_err = _coerce_count(raw.get("impressions"))
        if imp_err:
            issues.append(Issue(
                level=IssueLevel.ROW, check_name=Check.INVALID_IMPRESSIONS, severity=Severity.FAIL,
                field="impressions", raw_value=str(raw.get("impressions")),
                campaign=campaign, date=iso_date, message=f"impressions {imp_err}; stored null",
            ))
        elif impressions < 0:
            issues.append(Issue(
                level=IssueLevel.ROW, check_name=Check.NEGATIVE_IMPRESSIONS, severity=Severity.FAIL,
                field="impressions", raw_value=str(raw.get("impressions")),
                campaign=campaign, date=iso_date, message="impressions negative; stored null",
            ))
            impressions = None

        clicks, clk_err = _coerce_count(raw.get("clicks"))
        if clk_err:
            issues.append(Issue(
                level=IssueLevel.ROW, check_name=Check.MISSING_CLICKS, severity=Severity.FAIL,
                field="clicks", raw_value=str(raw.get("clicks")),
                campaign=campaign, date=iso_date, message=f"clicks {clk_err}; stored null",
            ))
        elif clicks < 0:
            issues.append(Issue(
                level=IssueLevel.ROW, check_name=Check.NEGATIVE_CLICKS, severity=Severity.FAIL,
                field="clicks", raw_value=str(raw.get("clicks")),
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
                field="date_ts", raw_value=iso_date, campaign=campaign, date=iso_date,
                message=f"date {iso_date} outside delivery week "
                        f"{ctx.week_start.isoformat()}..{window_end.isoformat()}",
            ))

        row = CanonicalRow(
            platform=Platform.LINKEDIN, campaign=campaign, date=iso_date,
            spend_usd=spend_usd, impressions=impressions, clicks=clicks,
            raw_amount=str(amount_raw) if amount_raw is not None else None,
            raw_currency=currency or None,
        )
        return RowResult(row=row, issues=issues)
