from __future__ import annotations

from datetime import date
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
LIVE_MARKET_ROOT = PROJECT_ROOT / "Data" / "live_market"
DAILY_ROOT = LIVE_MARKET_ROOT / "daily"
SNAPSHOTS_ROOT = LIVE_MARKET_ROOT / "snapshots"
COLLECTOR_STATUS_PATH = LIVE_MARKET_ROOT / "collector_status.json"
HOLIDAYS_PATH = LIVE_MARKET_ROOT / "nse_holidays.json"


def ensure_live_market_dirs(*, trading_date: date | None = None) -> Path:
    LIVE_MARKET_ROOT.mkdir(parents=True, exist_ok=True)
    DAILY_ROOT.mkdir(parents=True, exist_ok=True)
    SNAPSHOTS_ROOT.mkdir(parents=True, exist_ok=True)

    if trading_date is None:
        from datetime import date as _date

        trading_date = _date.today()
    day_dir = DAILY_ROOT / trading_date.isoformat()
    day_dir.mkdir(parents=True, exist_ok=True)
    return day_dir


__all__ = [
    "COLLECTOR_STATUS_PATH",
    "DAILY_ROOT",
    "HOLIDAYS_PATH",
    "LIVE_MARKET_ROOT",
    "PROJECT_ROOT",
    "SNAPSHOTS_ROOT",
    "ensure_live_market_dirs",
]

