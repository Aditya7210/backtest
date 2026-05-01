"""Zerodha historical data fetcher — pulls OHLCV via kiteconnect API."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from kiteconnect import KiteConnect

from backend.config import settings


def build_kite_client() -> KiteConnect:
    kite = KiteConnect(api_key=settings.ZERODHA_API_KEY)
    kite.set_access_token(settings.ZERODHA_ACCESS_TOKEN)
    return kite


def fetch_historical(
    kite: KiteConnect,
    instrument_token: int,
    from_date: str,
    to_date: str,
    interval: str = "5minute",
) -> list[dict[str, Any]]:
    """Fetch historical candles from Zerodha.

    interval: minute, 3minute, 5minute, 10minute, 15minute, 30minute, 60minute, day
    """
    data = kite.historical_data(
        instrument_token=instrument_token,
        from_date=from_date,
        to_date=to_date,
        interval=interval,
    )
    return data
