"""Resolve analytics time windows (today, week, ISO ranges)."""

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from app import config


def _local_tz() -> ZoneInfo:
    return ZoneInfo(config.TIMEZONE)


def parse_iso(ts: str) -> datetime:
    if ts.endswith("Z"):
        ts = ts[:-1] + "+00:00"
    return datetime.fromisoformat(ts)


def to_utc_iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


SUPPORTED_PERIODS = ("today", "yesterday", "week", "month")


def resolve_period(period: str, now: datetime | None = None) -> tuple[str, str]:
    """Return (from_iso, to_iso) in UTC for a named period preset."""
    tz = _local_tz()
    if now is None:
        now = datetime.now(tz)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=tz)
    else:
        now = now.astimezone(tz)

    if period == "today":
        start_local = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end_local = now
    elif period == "yesterday":
        yesterday = (now - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        start_local = yesterday
        end_local = yesterday.replace(hour=23, minute=59, second=59)
    elif period == "week":
        start_local = (now - timedelta(days=now.weekday())).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        end_local = now
    elif period == "month":
        start_local = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        end_local = now
    else:
        raise ValueError(f"unsupported period: {period}")

    return to_utc_iso(start_local), to_utc_iso(end_local)


def resolve_range(
    from_value: str | None,
    to_value: str | None,
    now: datetime | None = None,
) -> tuple[str | None, str | None]:
    """Resolve from/to query params; supports today/week shorthands."""
    from_iso: str | None
    to_iso: str | None

    if from_value in SUPPORTED_PERIODS:
        from_iso, to_iso = resolve_period(from_value, now=now)
    elif from_value:
        from_iso = to_utc_iso(parse_iso(from_value))
        to_iso = to_utc_iso(parse_iso(to_value)) if to_value else None
    else:
        from_iso = None
        to_iso = to_utc_iso(parse_iso(to_value)) if to_value else None

    return from_iso, to_iso


def overlap_seconds(
    seg_start: str,
    seg_end: str,
    range_start: str,
    range_end: str,
) -> int:
    start = max(parse_iso(seg_start), parse_iso(range_start))
    end = min(parse_iso(seg_end), parse_iso(range_end))
    if end <= start:
        return 0
    return int((end - start).total_seconds())
