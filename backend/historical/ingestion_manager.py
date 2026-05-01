"""Historical data ingestion manager — fetch + store in MongoDB."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

from backend.database.sync_connection import get_sync_db
from backend.historical.zerodha_fetcher import build_kite_client, fetch_historical


_INTERVAL_TO_TIMEFRAME = {
    "minute": "1min",
    "3minute": "3min",
    "5minute": "5min",
    "10minute": "10min",
    "15minute": "15min",
    "30minute": "30min",
    "60minute": "60min",
    "day": "1day",
}
IST_TZ = ZoneInfo("Asia/Kolkata")


def ingest(
    instrument_token: int,
    tradingsymbol: str,
    from_date: str,
    to_date: str,
    interval: str = "5minute",
) -> dict[str, Any]:
    """Fetch historical data from Zerodha and store in MongoDB."""
    from pymongo import UpdateOne

    kite = build_kite_client()
    candles = fetch_historical(kite, instrument_token, from_date, to_date, interval)

    if not candles:
        return {"status": "no_data", "rows": 0}

    timeframe = _INTERVAL_TO_TIMEFRAME.get(interval, interval)
    db = get_sync_db()
    operations = []

    for candle in candles:
        ts = candle.get("date")
        if isinstance(ts, datetime):
            if ts.tzinfo is None:
                # Zerodha historical candles represent Indian market sessions.
                ts = ts.replace(tzinfo=IST_TZ)
            ts_ist = ts.astimezone(IST_TZ)
            ts_utc = ts_ist.astimezone(timezone.utc)
        else:
            continue

        trading_date = ts_ist.strftime("%Y-%m-%d")

        doc = {
            "timestamp": ts_utc,
            "trading_date": trading_date,
            "timeframe": timeframe,
            "instrument_type": "equity",
            "instrument_token": instrument_token,
            "tradingsymbol": tradingsymbol,
            "open": float(candle.get("open", 0)),
            "high": float(candle.get("high", 0)),
            "low": float(candle.get("low", 0)),
            "close": float(candle.get("close", 0)),
            "volume": float(candle.get("volume", 0)),
        }

        filt = {
            "instrument_token": instrument_token,
            "timeframe": timeframe,
            "timestamp": ts_utc,
        }
        operations.append(UpdateOne(
            filt,
            {"$set": doc, "$setOnInsert": {"data_source": "historical"}},
            upsert=True,
        ))

    if operations:
        result = db.bars.bulk_write(operations, ordered=False)
        inserted = result.upserted_count + result.modified_count
    else:
        inserted = 0

    return {"status": "ok", "rows": len(candles), "inserted": inserted}
