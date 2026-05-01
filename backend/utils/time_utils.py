"""IST timezone utilities — migrated from LiveMarket/time_utils.py."""
from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo


IST_ZONE_NAME = "Asia/Kolkata"
IST = ZoneInfo(IST_ZONE_NAME)


def now_ist() -> datetime:
    return datetime.now(tz=IST)


def now_ist_iso(*, timespec: str = "seconds") -> str:
    return now_ist().isoformat(timespec=timespec)


def today_ist() -> date:
    return now_ist().date()


def coerce_to_ist(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=IST)
    return value.astimezone(IST)
