"""The user's local calendar day (D-111). Timestamps are stored in UTC; "today", streaks and the
calendar use the IANA zone from the profile (unknown zone -> UTC). Day bounds are local midnight
converted to UTC, so a DST day of 23 or 25 hours is correct."""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def zone_for(name: str | None) -> ZoneInfo:
    try:
        return ZoneInfo(name or "UTC")
    except (ZoneInfoNotFoundError, ValueError, OSError):
        return ZoneInfo("UTC")


def user_zone(user: Any) -> ZoneInfo:
    profile = getattr(user, "profile", None)
    return zone_for(getattr(profile, "timezone", None))


def local_date(zone: ZoneInfo, moment: datetime) -> date:
    return moment.astimezone(zone).date()


def day_start_utc(zone: ZoneInfo, day: date) -> datetime:
    return datetime.combine(day, time.min, tzinfo=zone).astimezone(UTC)


def day_bounds(zone: ZoneInfo, moment: datetime) -> tuple[datetime, datetime]:
    """[start, end) of the local day containing `moment`, both in UTC."""
    today = local_date(zone, moment)
    return day_start_utc(zone, today), day_start_utc(zone, today + timedelta(days=1))
