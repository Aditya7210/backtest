"""Zerodha historical data fetcher with interval-aware chunking."""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
import re
from typing import Any, Callable, Iterator

from kiteconnect import KiteConnect

from backend.config import settings

_INTERVAL_CHUNK_DAYS: dict[str, int] = {
    "minute": 30,
    "3minute": 45,
    "5minute": 60,
    "10minute": 90,
    "15minute": 120,
    "30minute": 180,
    "60minute": 365,
    "day": 3650,
}
_DATE_ONLY_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_SAFE_ISO_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}[T ][0-2]\d:[0-5]\d:[0-5]\d(?:\.\d{1,6})?(?:Z|[+-][0-2]\d:[0-5]\d)?$")
_MIN_SUPPORTED_YEAR = 2000


def build_kite_client() -> KiteConnect:
    kite = KiteConnect(api_key=settings.ZERODHA_API_KEY)
    kite.set_access_token(settings.ZERODHA_ACCESS_TOKEN)
    return kite


def _parse_date(value: str, *, end_of_day: bool = False) -> datetime:
    raw = value.strip()
    parsed: datetime
    if _DATE_ONLY_PATTERN.match(raw):
        parsed = datetime.strptime(raw, "%Y-%m-%d")
    elif _SAFE_ISO_PATTERN.match(raw):
        safe = raw.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(safe)
    else:
        raise ValueError(f"Invalid date format: {value}. Use YYYY-MM-DD or full ISO datetime.")

    max_supported_year = datetime.now().year + 1
    if parsed.year < _MIN_SUPPORTED_YEAR or parsed.year > max_supported_year:
        raise ValueError(
            f"Invalid year {parsed.year}. Supported range is {_MIN_SUPPORTED_YEAR}..{max_supported_year}."
        )

    if end_of_day and parsed.hour == 0 and parsed.minute == 0 and parsed.second == 0 and parsed.microsecond == 0:
        return parsed.replace(hour=23, minute=59, second=59, microsecond=0)
    return parsed


def _build_chunks(from_date: str, to_date: str, interval: str) -> list[tuple[datetime, datetime]]:
    start = _parse_date(from_date, end_of_day=False)
    end = _parse_date(to_date, end_of_day=True)
    if start > end:
        raise ValueError("from_date must be <= to_date")
    chunk_days = _INTERVAL_CHUNK_DAYS.get(interval, 60)
    chunks: list[tuple[datetime, datetime]] = []
    cursor = start
    while cursor <= end:
        chunk_end = min(cursor + timedelta(days=chunk_days - 1), end)
        chunks.append((cursor, chunk_end))
        cursor = chunk_end + timedelta(days=1)
    return chunks


def _fetch_chunk_with_retry(
    kite: KiteConnect,
    instrument_token: int,
    chunk_from: datetime,
    chunk_to: datetime,
    interval: str,
    *,
    retries: int = 2,
) -> list[dict[str, Any]]:
    last_error: Exception | None = None
    for attempt in range(retries + 1):
        try:
            part = kite.historical_data(
                instrument_token=instrument_token,
                from_date=chunk_from,
                to_date=chunk_to,
                interval=interval,
            )
            # Explicitly clear stale retry state on success.
            last_error = None
            return part or []
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            if attempt >= retries:
                break
            time.sleep(0.8 * (attempt + 1))
    if last_error is not None:
        raise last_error
    return []


def iter_historical_chunks(
    kite: KiteConnect,
    instrument_token: int,
    from_date: str,
    to_date: str,
    interval: str = "5minute",
    *,
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
) -> Iterator[dict[str, Any]]:
    """Yield fetched candles chunk-by-chunk, with retry handling per chunk."""
    chunks = _build_chunks(from_date, to_date, interval)
    total = len(chunks)
    rows_fetched = 0
    fetch_concurrency = max(1, min(3, int(settings.ZERODHA_HISTORICAL_FETCH_CONCURRENCY or 1)))

    if fetch_concurrency == 1 or total <= 1:
        for idx, (chunk_from, chunk_to) in enumerate(chunks, start=1):
            rows = _fetch_chunk_with_retry(
                kite,
                instrument_token=instrument_token,
                chunk_from=chunk_from,
                chunk_to=chunk_to,
                interval=interval,
            )
            rows_fetched += len(rows)
            if progress_callback:
                progress_callback(
                    {
                        "phase": "FETCHING",
                        "current_chunk": idx,
                        "total_chunks": total,
                        "rows": rows_fetched,
                        "rows_fetched": rows_fetched,
                        "fetched_in_chunk": len(rows),
                    }
                )
            yield {
                "current_chunk": idx,
                "total_chunks": total,
                "chunk_from": chunk_from,
                "chunk_to": chunk_to,
                "rows": rows,
                "rows_fetched": rows_fetched,
            }
        return

    def _fetch_one(chunk_window: tuple[datetime, datetime]) -> list[dict[str, Any]]:
        chunk_from, chunk_to = chunk_window
        return _fetch_chunk_with_retry(
            kite,
            instrument_token=instrument_token,
            chunk_from=chunk_from,
            chunk_to=chunk_to,
            interval=interval,
        )

    with ThreadPoolExecutor(max_workers=fetch_concurrency) as pool:
        for idx, rows in enumerate(pool.map(_fetch_one, chunks), start=1):
            chunk_from, chunk_to = chunks[idx - 1]
            rows_fetched += len(rows)
            if progress_callback:
                progress_callback(
                    {
                        "phase": "FETCHING",
                        "current_chunk": idx,
                        "total_chunks": total,
                        "rows": rows_fetched,
                        "rows_fetched": rows_fetched,
                        "fetched_in_chunk": len(rows),
                    }
                )
            yield {
                "current_chunk": idx,
                "total_chunks": total,
                "chunk_from": chunk_from,
                "chunk_to": chunk_to,
                "rows": rows,
                "rows_fetched": rows_fetched,
            }


def fetch_historical(
    kite: KiteConnect,
    instrument_token: int,
    from_date: str,
    to_date: str,
    interval: str = "5minute",
    *,
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Fetch historical candles using interval-aware chunking."""
    all_rows: list[dict[str, Any]] = []
    current_chunk = 0
    total_chunks = 0
    for chunk in iter_historical_chunks(
        kite,
        instrument_token,
        from_date,
        to_date,
        interval,
        progress_callback=progress_callback,
    ):
        current_chunk = int(chunk.get("current_chunk", 0))
        total_chunks = int(chunk.get("total_chunks", 0))
        all_rows.extend(chunk.get("rows") or [])

    # De-duplicate on candle timestamp while preserving last seen row.
    by_ts: dict[str, dict[str, Any]] = {}
    for row in all_rows:
        ts = row.get("date")
        key = str(ts)
        by_ts[key] = row
    ordered = sorted(by_ts.values(), key=lambda x: str(x.get("date")))
    return ordered, {"current_chunk": current_chunk, "total_chunks": total_chunks}
