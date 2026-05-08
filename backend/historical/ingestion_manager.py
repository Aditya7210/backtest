"""Historical data ingestion manager: fetch chunk-by-chunk and store in MongoDB."""
from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Callable
from zoneinfo import ZoneInfo

from pymongo import UpdateOne

from backend.config import settings
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


class IngestCancelled(RuntimeError):
    """Raised when a historical ingest job is cancelled."""

    def __init__(self, message: str, *, stats: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.stats = stats or {}


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
    job_id: str | None,
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
        "ingest_job_id": job_id,
        "ingest_status": "pending" if job_id else "committed",
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
    should_cancel: Callable[[], bool] | None = None,
    event_callback: Callable[[str], None] | None = None,
    job_id: str | None = None,
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
    write_batch_size = max(200, int(settings.HISTORICAL_WRITE_BATCH_SIZE))
    cancel_check_seconds = max(0.1, float(settings.HISTORICAL_CANCEL_CHECK_SECONDS))
    ingest_started_at = time.perf_counter()

    rows_fetched = 0
    rows_saved = 0
    inserted = 0
    modified = 0
    first_saved_trading_date: str | None = None
    last_saved_trading_date: str | None = None
    current_chunk = 0
    total_chunks = 0
    fetch_seconds = 0.0
    normalize_seconds = 0.0
    write_seconds = 0.0
    cancel_probe = {"last_check": 0.0, "value": False}

    def _emit(message: str) -> None:
        if event_callback:
            event_callback(message)

    def _stats_snapshot() -> dict[str, Any]:
        return {
            "rows": rows_fetched,
            "rows_fetched": rows_fetched,
            "saved_rows": rows_saved,
            "inserted": inserted,
            "modified": modified,
            "current_chunk": current_chunk,
            "total_chunks": total_chunks,
            "requested_from_date": from_date,
            "requested_to_date": to_date,
            "first_saved_trading_date": first_saved_trading_date,
            "last_saved_trading_date": last_saved_trading_date,
            "fetch_seconds": fetch_seconds,
            "normalize_seconds": normalize_seconds,
            "write_seconds": write_seconds,
        }

    def _raise_if_cancelled(checkpoint: str) -> None:
        if not should_cancel:
            return
        now_tick = time.monotonic()
        if (now_tick - cancel_probe["last_check"]) < cancel_check_seconds:
            if cancel_probe["value"]:
                _emit(f"Cancellation detected at {checkpoint}.")
                raise IngestCancelled("Cancellation requested", stats=_stats_snapshot())
            return
        cancel_probe["last_check"] = now_tick
        cancel_probe["value"] = bool(should_cancel())
        if cancel_probe["value"]:
            _emit(f"Cancellation detected at {checkpoint}.")
            raise IngestCancelled("Cancellation requested", stats=_stats_snapshot())

    def _throughput() -> tuple[float, float]:
        elapsed = max(0.001, time.perf_counter() - ingest_started_at)
        rows_per_second = float(rows_saved) / elapsed
        chunks_per_second = float(current_chunk) / elapsed if current_chunk > 0 else 0.0
        return rows_per_second, chunks_per_second

    _raise_if_cancelled("start")

    chunk_stream = iter_historical_chunks(
        kite=kite,
        instrument_token=instrument_token,
        from_date=from_date,
        to_date=to_date,
        interval=interval,
    )
    while True:
        _raise_if_cancelled("before_chunk_fetch")
        fetch_started = time.perf_counter()
        try:
            chunk = next(chunk_stream)
        except StopIteration:
            break
        fetch_seconds += max(0.0, time.perf_counter() - fetch_started)

        _raise_if_cancelled("before_chunk")
        current_chunk = int(chunk.get("current_chunk", 0))
        total_chunks = int(chunk.get("total_chunks", 0))
        candles = chunk.get("rows") or []
        rows_fetched += len(candles)
        rows_per_second, chunks_per_second = _throughput()

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
                    "fetch_seconds": fetch_seconds,
                    "normalize_seconds": normalize_seconds,
                    "write_seconds": write_seconds,
                    "rows_per_second": rows_per_second,
                    "chunks_per_second": chunks_per_second,
                }
            )

        normalize_started = time.perf_counter()
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
                job_id=job_id,
            )
            if operation is None:
                continue
            deduped_by_ts[str(candle.get("date"))] = operation

        normalize_seconds += max(0.0, time.perf_counter() - normalize_started)
        rows_per_second, chunks_per_second = _throughput()
        operations = list(deduped_by_ts.values())
        if not operations:
            continue

        if progress_callback:
            progress_callback(
                {
                    "phase": "NORMALIZING",
                    "current_chunk": current_chunk,
                    "total_chunks": total_chunks,
                    "rows": rows_fetched,
                    "rows_fetched": rows_fetched,
                    "saved_rows": rows_saved,
                    "inserted": inserted,
                    "modified": modified,
                    "fetch_seconds": fetch_seconds,
                    "normalize_seconds": normalize_seconds,
                    "write_seconds": write_seconds,
                    "rows_per_second": rows_per_second,
                    "chunks_per_second": chunks_per_second,
                }
            )

        for offset in range(0, len(operations), write_batch_size):
            _raise_if_cancelled("before_write_batch")
            batch = operations[offset: offset + write_batch_size]
            write_started = time.perf_counter()
            result = db.bars.bulk_write(batch, ordered=False)
            write_seconds += max(0.0, time.perf_counter() - write_started)
            inserted += int(result.upserted_count)
            modified += int(result.modified_count)
            rows_saved += len(batch)
            _raise_if_cancelled("after_write_batch")
            rows_per_second, chunks_per_second = _throughput()
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
                        "fetch_seconds": fetch_seconds,
                        "normalize_seconds": normalize_seconds,
                        "write_seconds": write_seconds,
                        "rows_per_second": rows_per_second,
                        "chunks_per_second": chunks_per_second,
                    }
                )

    _raise_if_cancelled("after_all_chunks")

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
            "fetch_seconds": fetch_seconds,
            "normalize_seconds": normalize_seconds,
            "write_seconds": write_seconds,
            "rows_per_second": 0.0,
            "chunks_per_second": 0.0,
        }
    rows_per_second, chunks_per_second = _throughput()
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
        "fetch_seconds": fetch_seconds,
        "normalize_seconds": normalize_seconds,
        "write_seconds": write_seconds,
        "rows_per_second": rows_per_second,
        "chunks_per_second": chunks_per_second,
    }
