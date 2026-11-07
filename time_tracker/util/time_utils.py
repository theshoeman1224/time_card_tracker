from __future__ import annotations

import math
from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP


def now_local() -> datetime:
    """Get current time in the local timezone."""
    return datetime.now().astimezone()


def iso(dt: datetime) -> str:
    """Convert datetime to ISO 8601 string with seconds precision."""
    if dt.tzinfo is None:
        dt = dt.astimezone()
    return dt.isoformat(timespec="seconds")


def parse_iso(value: str) -> datetime:
    """Parse an ISO 8601 string to datetime."""
    return datetime.fromisoformat(value)


# Dates shown to (and typed by) the user. Storage stays ISO 8601.
DATE_FORMAT = "%m-%d-%Y"
DATETIME_FORMAT = f"{DATE_FORMAT} %H:%M:%S"


def parse_local_datetime(value: str) -> datetime:
    """Parse 'MM-DD-YYYY HH:MM[:SS]' to timezone-aware datetime."""
    for fmt in (DATETIME_FORMAT, f"{DATE_FORMAT} %H:%M"):
        try:
            parsed = datetime.strptime(value.strip(), fmt)
            return parsed.astimezone()
        except ValueError:
            continue
    raise ValueError("Use date/time format MM-DD-YYYY HH:MM[:SS].")


def format_datetime(value: str | None) -> str:
    """Format ISO string to 'MM-DD-YYYY HH:MM:SS', or empty string if None."""
    if not value:
        return ""
    return parse_iso(value).strftime(DATETIME_FORMAT)


def format_date(value: str) -> str:
    """Format an ISO date ('YYYY-MM-DD') as 'MM-DD-YYYY'."""
    return date.fromisoformat(value).strftime(DATE_FORMAT)


def parse_date(value: str) -> str:
    """Parse a 'MM-DD-YYYY' date to an ISO date string ('YYYY-MM-DD')."""
    try:
        return datetime.strptime(value.strip(), DATE_FORMAT).date().isoformat()
    except ValueError:
        raise ValueError("Use date format MM-DD-YYYY.") from None


def seconds_between(start_at: str, end_at: str) -> int:
    """Calculate seconds between two ISO timestamps, clamped to zero.

    Pure time math — the "open session ends now" rule lives in the tracking
    module, not here.
    """
    return max(0, int((parse_iso(end_at) - parse_iso(start_at)).total_seconds()))


def human_duration(seconds: int) -> str:
    """Format seconds as 'H:MM:SS'."""
    sign = "-" if seconds < 0 else ""
    seconds = abs(int(seconds))
    hours, rem = divmod(seconds, 3600)
    minutes, secs = divmod(rem, 60)
    return f"{sign}{hours}:{minutes:02d}:{secs:02d}"


def decimal_hours(seconds: int | float, places: int = 1) -> str:
    """Convert seconds to decimal hours with the given decimal places (e.g., '1.2').

    Uses Decimal to avoid float representation errors in the quantize step.
    """
    hours = Decimal(str(seconds)) / Decimal("3600")
    return str(hours.quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP))


def hour_places(increment_minutes: int) -> int:
    """Decimal places needed to show rounded hours for an increment.

    Multiples of 6 minutes are exact tenths of an hour, so one place is enough;
    any other increment (e.g. 15 minutes = 0.25 h) needs two.
    """
    return 1 if max(1, int(increment_minutes)) % 6 == 0 else 2


def round_seconds(seconds: float, increment_minutes: int, mode: str = "nearest") -> int:
    """Round seconds to the nearest increment. Modes: 'nearest', 'up', 'down'."""
    increment = max(1, int(increment_minutes)) * 60
    if mode == "up":
        # Ceiling division to the next whole increment.
        return int(((seconds + increment - 1) // increment) * increment)
    if mode == "down":
        return int((seconds // increment) * increment)
    # Round half up, consistent with decimal_hours (Python's round() is half-to-even).
    return int(math.floor(seconds / increment + 0.5) * increment)


def apportion(total_seconds: int, raw_parts: list[float], unit_seconds: int = 1) -> list[int]:
    """Split a total across parts in whole units (largest remainder).

    Floors each part to the unit, then hands leftover units to the parts with
    the biggest fractional remainder, so the results sum to total_seconds
    exactly. Ties break by part order, so callers should pass parts in a
    deterministic order.
    """
    unit = max(1, int(unit_seconds))
    counts = [int(part // unit) for part in raw_parts]
    remaining = max(0, int(total_seconds) // unit - sum(counts))
    order = sorted(
        range(len(raw_parts)),
        key=lambda i: (-(raw_parts[i] - counts[i] * unit), i),
    )
    for i in order[:remaining]:
        counts[i] += 1
    return [count * unit for count in counts]


def apportion_rounded(rounded_total_seconds: int, raw_parts: list[float], increment_minutes: int) -> list[int]:
    """Split a rounded total across parts in whole rounding increments (see apportion)."""
    return apportion(rounded_total_seconds, raw_parts, max(1, int(increment_minutes)) * 60)


def week_bounds(day: datetime) -> tuple[str, str]:
    """Get Monday-Sunday bounds for the week containing the given date."""
    start = day.date() - timedelta(days=day.weekday())
    end = start + timedelta(days=6)
    return start.isoformat(), end.isoformat()
