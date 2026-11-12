"""Enumerated string values used across the app.

Kept as plain-string class attributes (not Enum) so the values go straight into SQLite
and JSON without conversion, while code refers to them by name to avoid typos.
"""


class Platform:
    META = "meta"
    GOOGLE = "google"
    LINKEDIN = "linkedin"


class DeliveryStatus:
    PROCESSED = "processed"
    SKIPPED_DUPLICATE = "skipped_duplicate"
    PARSE_ERROR = "parse_error"
    MISSING = "missing"


class Health:
    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"


class IssueLevel:
    ROW = "row"
    FILE = "file"
    DELIVERY = "delivery"


class Severity:
    WARN = "warn"
    FAIL = "fail"


class Outcome:
    """Per-file result returned by the pipeline, tallied into the run summary."""
    PROCESSED = "processed"
    UNCHANGED = "unchanged"
    DUPLICATE = "duplicate"
    PARSE_ERROR = "parse_error"
    NO_NORMALIZER = "no_normalizer"
    MISSING = "missing"


class Check:
    """check_name values recorded in data_issues."""
    # row-level
    MISSING_CAMPAIGN = "missing_campaign"
    INVALID_DATE = "invalid_date"
    MISSING_SPEND = "missing_spend"
    INVALID_SPEND = "invalid_spend"
    NEGATIVE_SPEND = "negative_spend"
    UNKNOWN_CURRENCY = "unknown_currency"
    INVALID_IMPRESSIONS = "invalid_impressions"
    NEGATIVE_IMPRESSIONS = "negative_impressions"
    MISSING_CLICKS = "missing_clicks"
    NEGATIVE_CLICKS = "negative_clicks"
    CLICKS_GT_IMPRESSIONS = "clicks_gt_impressions"
    DATE_OUT_OF_WINDOW = "date_out_of_window"
    ROW_ERROR = "row_error"
    # file-level
    DUPLICATE_DELIVERY = "duplicate_delivery"
    DUPLICATE_ROW = "duplicate_row"
    CONFLICTING_DUPLICATE_ROW = "conflicting_duplicate_row"
    PARSE_ERROR = "parse_error"
    # delivery-level
    MISSING_DELIVERY = "missing_delivery"
    SPEND_IMPLAUSIBLE = "spend_implausible"


class Currency:
    USD = "USD"
