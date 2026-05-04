"""Historical data ingestion manager: fetch chunk-by-chunk and store in MongoDB."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable
from zoneinfo import ZoneInfo

from pymongo import UpdateOne

from backend.database.sync_connection import get_sync_db
from backend.historical.zerodha_fetcher import build_kite_client, iter_historical_chunks


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
WRITE_BATCH_SIZE = 1000


def _infer_instrument_type(tradingsymbol: str) -> str:
    symbol = str(tradingsymbol or "").upper()
    if "ETF" in symbol:
        return "etf"
    if "NIFTY" in symbol or "VIX" in symbol or "SENSEX" in symbol or "BANKEX" in symbol:
        return "index"
    return "equity"


def _build_operation(
    *,
    candle: dict[str, Any],
    instrument_token: int,
    tradingsymbol: str,
    timeframe: str,
    instrument_type: str,
) -> UpdateOne | None:
    ts = candle.get("date")
    if not isinstance(ts, datetime):
        return None
    if ts.tzinfo is None:
        # Zerodha historical candles represent Indian market sessions.
        ts = ts.replace(tzinfo=IST_TZ)
    ts_ist = ts.astimezone(IST_TZ)
    ts_utc = ts_ist.astimezone(timezone.utc)
    trading_date = ts_ist.strftime("%Y-%m-%d")

    doc = {
        "timestamp": ts_utc,
        "trading_date": trading_date,
        "timeframe": timeframe,
        "instrument_type": instrument_type,
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
    return UpdateOne(
        filt,
        {"$set": doc, "$setOnInsert": {"data_source": "historical"}},
        upsert=True,
    )


def ingest(
    instrument_token: int,
    tradingsymbol: str,
    from_date: str,
    to_date: str,
    interval: str = "5minute",
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """Fetch historical data from Zerodha and persist incrementally in MongoDB."""
    kite = build_kite_client()
    timeframe = _INTERVAL_TO_TIMEFRAME.get(interval, interval)
    instrument_type = _infer_instrument_type(tradingsymbol)
    db = get_sync_db()
    requested_from = datetime.strptime(from_date, "%Y-%m-%d")
    requested_to = datetime.strptime(to_date, "%Y-%m-%d")
    requested_years = set(range(requested_from.year, requested_to.year + 1))
    max_supported_year = datetime.now(tz=IST_TZ).year + 1

    rows_fetched = 0
    rows_saved = 0
    inserted = 0
    modified = 0
    first_saved_trading_date: str | None = None
    last_saved_trading_date: str | None = None
    current_chunk = 0
    total_chunks = 0

    for chunk in iter_historical_chunks(
        kite,
        instrument_token,
        from_date,
        to_date,
        interval,
    ):
        current_chunk = int(chunk.get("current_chunk", 0))
        total_chunks = int(chunk.get("total_chunks", 0))
        candles = chunk.get("rows") or []
        rows_fetched += len(candles)

        if progress_callback:
            progress_callback(
                {
                    "phase": "FETCHING",
                    "current_chunk": current_chunk,
                    "total_chunks": total_chunks,
                    "rows": rows_fetched,
                    "rows_fetched": rows_fetched,
                    "saved_rows": rows_saved,
                    "inserted": inserted,
                    "modified": modified,
                }
            )

        deduped_by_ts: dict[str, UpdateOne] = {}
        for candle in candles:
            ts = candle.get("date")
            if isinstance(ts, datetime):
                ts_ist = (ts.replace(tzinfo=IST_TZ) if ts.tzinfo is None else ts.astimezone(IST_TZ))
                trading_date = ts_ist.strftime("%Y-%m-%d")
                trading_year = int(trading_date[:4])
                if trading_year < 2000 or trading_year > max_supported_year:
                    raise ValueError(f"Refusing to ingest candle with out-of-range year {trading_year} ({trading_date}).")
                if trading_year not in requested_years:
                    raise ValueError(
                        f"Refusing to ingest candle outside requested year range: requested={from_date}..{to_date}, got {trading_date}."
                    )
                if first_saved_trading_date is None or trading_date < first_saved_trading_date:
                    first_saved_trading_date = trading_date
                if last_saved_trading_date is None or trading_date > last_saved_trading_date:
                    last_saved_trading_date = trading_date

            operation = _build_operation(
                candle=candle,
                instrument_token=instrument_token,
                tradingsymbol=tradingsymbol,
                timeframe=timeframe,
                instrument_type=instrument_type,
            )
            if operation is None:
                continue
            deduped_by_ts[str(candle.get("date"))] = operation

        operations = list(deduped_by_ts.values())
        if not operations:
            continue

        if progress_callback:
            progress_callback(
                {
                    "phase": "SAVING",
                    "current_chunk": current_chunk,
                    "total_chunks": total_chunks,
                    "rows": rows_fetched,
                    "rows_fetched": rows_fetched,
                    "saved_rows": rows_saved,
                    "inserted": inserted,
                    "modified": modified,
                }
            )

        for offset in range(0, len(operations), WRITE_BATCH_SIZE):
            batch = operations[offset: offset + WRITE_BATCH_SIZE]
            result = db.bars.bulk_write(batch, ordered=False)
            inserted += int(result.upserted_count)
            modified += int(result.modified_count)
            rows_saved += len(batch)
            if progress_callback:
                progress_callback(
                    {
                        "phase": "SAVING",
                        "current_chunk": current_chunk,
                        "total_chunks": total_chunks,
                        "rows": rows_fetched,
                        "rows_fetched": rows_fetched,
                        "saved_rows": rows_saved,
                        "inserted": inserted,
                        "modified": modified,
                    }
                )

    if rows_fetched == 0:
        return {
            "status": "no_data",
            "rows": 0,
            "rows_fetched": 0,
            "saved_rows": 0,
            "inserted": 0,
            "modified": 0,
            "requested_from_date": from_date,
            "requested_to_date": to_date,
            "first_saved_trading_date": None,
            "last_saved_trading_date": None,
            "current_chunk": current_chunk,
            "total_chunks": total_chunks,
        }
    return {
        "status": "ok",
        "rows": rows_fetched,
        "rows_fetched": rows_fetched,
        "saved_rows": rows_saved,
        "inserted": inserted,
        "modified": modified,
        "requested_from_date": from_date,
        "requested_to_date": to_date,
        "first_saved_trading_date": first_saved_trading_date,
        "last_saved_trading_date": last_saved_trading_date,
        "current_chunk": current_chunk,
        "total_chunks": total_chunks,
    }
