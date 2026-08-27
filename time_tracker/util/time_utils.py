from __future__ import annotations

from datetime import datetime, timedelta
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


def parse_local_datetime(value: str) -> datetime:
    """Parse 'YYYY-MM-DD HH:MM[:SS]' to timezone-aware datetime."""
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            parsed = datetime.strptime(value.strip(), fmt)
            return parsed.astimezone()
        except ValueError:
            continue
    raise ValueError("Use date/time format YYYY-MM-DD HH:MM[:SS].")


def format_datetime(value: str | None) -> str:
    """Format ISO string to 'YYYY-MM-DD HH:MM:SS', or empty string if None."""
    if not value:
        return ""
    return parse_iso(value).strftime("%Y-%m-%d %H:%M:%S")


def seconds_between(start_at: str, end_at: str | None, fallback: datetime | None = None) -> int:
    """Calculate seconds between two ISO timestamps. Uses current time if end_at is None."""
    start = parse_iso(start_at)
    end = parse_iso(end_at) if end_at else fallback or now_local()
    return max(0, int((end - start).total_seconds()))


def human_duration(seconds: int) -> str:
    """Format seconds as 'H:MM:SS'."""
    sign = "-" if seconds < 0 else ""
    seconds = abs(int(seconds))
    hours, rem = divmod(seconds, 3600)
    minutes, secs = divmod(rem, 60)
    return f"{sign}{hours}:{minutes:02d}:{secs:02d}"


def decimal_hours(seconds: int | float) -> str:
    """Convert seconds to decimal hours with one decimal place (e.g., '1.2')."""
    hours = Decimal(str(seconds)) / Decimal("3600")
    return str(hours.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))


def round_seconds(seconds: float, increment_minutes: int, mode: str = "nearest") -> int:
    """Round seconds to the nearest increment. Modes: 'nearest', 'up', 'down'."""
    increment = max(1, int(increment_minutes)) * 60
    if mode == "up":
        return int(((seconds + increment - 1) // increment) * increment)
    if mode == "down":
        return int((seconds // increment) * increment)
    return int(round(seconds / increment) * increment)


def week_bounds(day: datetime) -> tuple[str, str]:
    """Get Monday-Sunday bounds for the week containing the given date."""
    start = day.date() - timedelta(days=day.weekday())
    end = start + timedelta(days=6)
    return start.isoformat(), end.isoformat()
