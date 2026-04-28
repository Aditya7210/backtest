from __future__ import annotations

from datetime import date, datetime, time
import json
from pathlib import Path

from LiveMarket import HOLIDAYS_PATH


_MARKET_OPEN = time(9, 15)
_MARKET_CLOSE = time(15, 30)


def _load_holidays(holidays_path: Path) -> dict[str, list[str]]:
    if not holidays_path.is_file():
        print(f"[trading_calendar] Holidays file missing: {holidays_path}. Assuming trading day.")
        return {}
    try:
        payload = json.loads(holidays_path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"[trading_calendar] Failed to parse holidays file: {exc}. Assuming trading day.")
        return {}
    if not isinstance(payload, dict):
        print("[trading_calendar] Holidays payload is invalid. Assuming trading day.")
        return {}
    normalized: dict[str, list[str]] = {}
    for key, value in payload.items():
        if not isinstance(key, str):
            continue
        if not isinstance(value, list):
            continue
        normalized[key] = [str(item) for item in value if isinstance(item, str)]
    return normalized


def is_trading_day(check_date: date, holidays_path: Path = HOLIDAYS_PATH) -> bool:
    if check_date.weekday() >= 5:
        return False

    holiday_map = _load_holidays(holidays_path)
    year_key = str(check_date.year)
    year_holidays = holiday_map.get(year_key)
    if year_holidays is None:
        if holiday_map:
            print(
                f"[trading_calendar] Year {year_key} not present in holidays file. "
                "Assuming trading day."
            )
        return True
    if check_date.isoformat() in year_holidays:
        return False
    return True


def get_market_open(check_date: date) -> time:
    _ = check_date
    return _MARKET_OPEN


def get_market_close(check_date: date) -> time:
    _ = check_date
    return _MARKET_CLOSE


def minutes_until_market_open(now: datetime) -> int:
    open_dt = datetime.combine(now.date(), _MARKET_OPEN, tzinfo=now.tzinfo)
    delta_minutes = int((open_dt - now).total_seconds() // 60)
    return max(0, delta_minutes)


__all__ = [
    "get_market_close",
    "get_market_open",
    "is_trading_day",
    "minutes_until_market_open",
]

