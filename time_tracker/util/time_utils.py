from __future__ import annotations

from datetime import datetime, timedelta


def now_local() -> datetime:
    return datetime.now().astimezone()


def iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.astimezone()
    return dt.isoformat(timespec="seconds")


def parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value)


def parse_local_datetime(value: str) -> datetime:
    parsed = datetime.strptime(value.strip(), "%Y-%m-%d %H:%M")
    return parsed.astimezone()


def format_datetime(value: str | None) -> str:
    if not value:
        return ""
    return parse_iso(value).strftime("%Y-%m-%d %H:%M")


def seconds_between(start_at: str, end_at: str | None, fallback: datetime | None = None) -> int:
    start = parse_iso(start_at)
    end = parse_iso(end_at) if end_at else fallback or now_local()
    return max(0, int((end - start).total_seconds()))


def human_duration(seconds: int) -> str:
    sign = "-" if seconds < 0 else ""
    seconds = abs(int(seconds))
    hours, rem = divmod(seconds, 3600)
    minutes, secs = divmod(rem, 60)
    if secs:
        return f"{sign}{hours}:{minutes:02d}:{secs:02d}"
    return f"{sign}{hours}:{minutes:02d}"


def round_seconds(seconds: float, increment_minutes: int, mode: str = "nearest") -> int:
    increment = max(1, int(increment_minutes)) * 60
    if mode == "up":
        return int(((seconds + increment - 1) // increment) * increment)
    if mode == "down":
        return int((seconds // increment) * increment)
    return int(round(seconds / increment) * increment)


def week_bounds(day: datetime) -> tuple[str, str]:
    start = day.date() - timedelta(days=day.weekday())
    end = start + timedelta(days=6)
    return start.isoformat(), end.isoformat()
