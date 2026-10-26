"""Shared, dependency-free helpers (dates, numbers, formatting, sanitising)."""

from __future__ import annotations

import json
import math
import re
from datetime import date, datetime, timedelta, timezone
from typing import Any, Iterable

DATE_FMT = "%Y-%m-%d"

#: Characters that spreadsheet applications interpret as a formula start.
_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def utcnow_iso() -> str:
    return utcnow().isoformat(timespec="seconds")


def to_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not text:
        return None
    for fmt in (DATE_FMT, "%d-%m-%Y", "%m/%d/%Y", "%d/%m/%Y", "%Y/%m/%d", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(text[:19] if "T" in fmt else text, fmt).date()
        except ValueError:
            continue
    try:  # last resort: ISO parsing (handles timezone suffixes)
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def date_iso(value: date | datetime | str) -> str:
    converted = to_date(value)
    return (converted or utcnow().date()).isoformat()


def parse_iso_date(value: str | None) -> date | None:
    if not value:
        return None
    return to_date(value)


def daterange(start: date, end: date) -> Iterable[date]:
    current = start
    while current <= end:
        yield current
        current += timedelta(days=1)


def is_blank(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, float) and math.isnan(value):
        return True
    return str(value).strip() == ""


def safe_float(value: Any) -> float | None:
    """Parse a numeric cell. Returns None when the value is not numeric."""
    if is_blank(value):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(",", "").replace("\u20b9", "").replace("$", "")
    if text.startswith("(") and text.endswith(")"):
        text = "-" + text[1:-1]
    try:
        return float(text)
    except ValueError:
        return None


def safe_int(value: Any) -> int | None:
    parsed = safe_float(value)
    return None if parsed is None else int(round(parsed))


def round2(value: float | None) -> float | None:
    if value is None or (isinstance(value, float) and (math.isnan(value) or math.isinf(value))):
        return None
    return round(float(value), 2)


def pct(value: float | None) -> float | None:
    return None if value is None else round(float(value) * 100, 2)


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def ceil_units(value: float) -> int:
    """Round a quantity up to whole units, allowing for float noise."""
    if value <= 0:
        return 0
    return int(math.ceil(round(value, 6)))


def json_dumps(value: Any) -> str:
    return json.dumps(value, default=str, separators=(",", ":"))


def json_loads(value: Any, default: Any = None) -> Any:
    if value in (None, ""):
        return default
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return default


def sanitize_text(value: Any, max_length: int = 200) -> str | None:
    """Trim, collapse whitespace and strip control characters."""
    if is_blank(value):
        return None
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", str(value)).strip()
    text = re.sub(r"\s+", " ", text)
    return text[:max_length] or None


def sanitize_spreadsheet_cell(value: Any) -> Any:
    """Neutralise CSV/Excel formula injection for exported cells."""
    if isinstance(value, str) and value.startswith(_FORMULA_PREFIXES):
        return "'" + value
    return value


def slugify_sku(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "-", value.strip().upper()).strip("-")
    return slug[:40] or "SKU"


def human_period(start: str | None, end: str | None) -> str:
    if start and end:
        return f"{start} to {end}"
    if start:
        return f"from {start}"
    if end:
        return f"until {end}"
    return "all recorded history"


def safe_divide(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator in (None, 0):
        return None
    return numerator / denominator
