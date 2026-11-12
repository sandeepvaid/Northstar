"""Delivery file discovery: filename -> (platform, week_start), plus content hashing."""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

# e.g. meta_ads_2026-06-01.csv, google_ads_2026-06-15_resend.csv, linkedin_ads_2026-06-29.json
_FILENAME_RE = re.compile(
    r"^(?P<prefix>meta_ads|google_ads|linkedin_ads)_"
    r"(?P<week>\d{4}-\d{2}-\d{2})(?P<suffix>_\w+)?\.(?P<ext>csv|json)$"
)

_PLATFORM_BY_PREFIX = {"meta_ads": "meta", "google_ads": "google", "linkedin_ads": "linkedin"}


@dataclass
class DeliveryFile:
    path: Path
    platform: str
    week_start: date
    filename: str


def content_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def discover(deliveries_dir: Path) -> list[DeliveryFile]:
    """Return recognized delivery files, sorted so originals sort before their *_resend copies."""
    found: list[DeliveryFile] = []
    for path in sorted(deliveries_dir.iterdir()):
        if not path.is_file():
            continue
        m = _FILENAME_RE.match(path.name)
        if not m:
            continue
        found.append(DeliveryFile(
            path=path,
            platform=_PLATFORM_BY_PREFIX[m.group("prefix")],
            week_start=date.fromisoformat(m.group("week")),
            filename=path.name,
        ))
    return found
