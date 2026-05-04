"""Live timeframe aggregation feature.

Provides on-demand aggregation from stored 1min bars for intraday and daily views.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from backend.database.connection import get_db

IST = ZoneInfo("Asia/Kolkata")
SESSION_OPEN_HOUR = 9
SESSION_OPEN_MINUTE = 15

SUPPORTED_LIVE_TIMEFRAMES: dict[str, int | str] = {
    "1min": 1,
    "3min": 3,
    "5min": 5,
    "10min": 10,
    "15min": 15,
    "20min": 20,
    "30min": 30,
    "45min": 45,
    "60min": 60,
    "1day": "day",
}


def _to_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _bucket_start_ist(ts_utc: datetime, minutes: int) -> datetime:
    ts_ist = _to_utc(ts_utc).astimezone(IST)
    session_anchor = ts_ist.replace(
        hour=SESSION_OPEN_HOUR,
        minute=SESSION_OPEN_MINUTE,
        second=0,
        microsecond=0,
    )
    delta_minutes = int((ts_ist - session_anchor).total_seconds() // 60)
    if delta_minutes < 0:
        delta_minutes = 0
    bucket_offset = (delta_minutes // minutes) * minutes
    bucket_ist = session_anchor.replace() + timedelta(minutes=bucket_offset)
    return bucket_ist.astimezone(timezone.utc)


def _bucket_key_day(ts_utc: datetime) -> tuple[str, datetime]:
    ts_ist = _to_utc(ts_utc).astimezone(IST)
    trading_date = ts_ist.date().isoformat()
    day_start_ist = ts_ist.replace(
        hour=SESSION_OPEN_HOUR,
        minute=SESSION_OPEN_MINUTE,
        second=0,
        microsecond=0,
    )
    return trading_date, day_start_ist.astimezone(timezone.utc)


def _merge_bucket_row(existing: dict[str, Any] | None, row: dict[str, Any], *, bucket_ts: datetime) -> dict[str, Any]:
    if existing is None:
        return {
            "timestamp": bucket_ts,
            "trading_date": row.get("trading_date", ""),
            "instrument_token": row.get("instrument_token"),
            "tradingsymbol": row.get("tradingsymbol"),
            "instrument_type": row.get("instrument_type"),
            "exchange": row.get("exchange"),
            "segment": row.get("segment"),
            "underlying": row.get("underlying"),
            "expiry": row.get("expiry"),
            "strike": row.get("strike"),
            "option_type": row.get("option_type"),
            "data_source": row.get("data_source", "live"),
            "open": float(row.get("open") or 0.0),
            "high": float(row.get("high") or 0.0),
            "low": float(row.get("low") or 0.0),
            "close": float(row.get("close") or 0.0),
            "volume": float(row.get("volume") or 0.0),
            "oi": row.get("oi"),
        }
    existing["high"] = max(float(existing.get("high") or 0.0), float(row.get("high") or 0.0))
    existing["low"] = min(float(existing.get("low") or 0.0), float(row.get("low") or 0.0))
    existing["close"] = float(row.get("close") or existing.get("close") or 0.0)
    existing["volume"] = float(existing.get("volume") or 0.0) + float(row.get("volume") or 0.0)
    if row.get("oi") is not None:
        existing["oi"] = row.get("oi")
    return existing


async def get_live_bars(
    *,
    token: int,
    timeframe: str,
    trading_date: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if timeframe not in SUPPORTED_LIVE_TIMEFRAMES:
        raise ValueError(f"Unsupported timeframe: {timeframe}")

    db = get_db()
    base_query: dict[str, Any] = {
        "instrument_token": int(token),
        "timeframe": "1min",
    }
    if trading_date:
        base_query["trading_date"] = trading_date
    elif date_from or date_to:
        date_filter: dict[str, str] = {}
        if date_from:
            date_filter["$gte"] = date_from
        if date_to:
            date_filter["$lte"] = date_to
        base_query["trading_date"] = date_filter

    one_minute = await db.bars.find(base_query).sort("timestamp", 1).to_list(length=None)
    if timeframe == "1min":
        return one_minute, {"derived": False, "source_timeframe": "1min", "target_timeframe": timeframe}

    if timeframe == "1day":
        buckets: dict[str, dict[str, Any]] = {}
        bucket_start_by_day: dict[str, datetime] = {}
        for row in one_minute:
            ts = row.get("timestamp")
            if not isinstance(ts, datetime):
                continue
            day_key, bucket_ts = _bucket_key_day(ts)
            bucket_start_by_day[day_key] = bucket_ts
            buckets[day_key] = _merge_bucket_row(buckets.get(day_key), row, bucket_ts=bucket_ts)
        out = []
        for day_key in sorted(buckets.keys()):
            merged = buckets[day_key]
            merged["trading_date"] = day_key
            merged["timestamp"] = bucket_start_by_day[day_key]
            merged["timeframe"] = "1day"
            out.append(merged)
        return out, {"derived": True, "source_timeframe": "1min", "target_timeframe": timeframe}

    interval = int(SUPPORTED_LIVE_TIMEFRAMES[timeframe])  # type: ignore[arg-type]
    by_bucket: dict[datetime, dict[str, Any]] = {}
    for row in one_minute:
        ts = row.get("timestamp")
        if not isinstance(ts, datetime):
            continue
        bucket_ts = _bucket_start_ist(ts, interval)
        by_bucket[bucket_ts] = _merge_bucket_row(by_bucket.get(bucket_ts), row, bucket_ts=bucket_ts)

    out: list[dict[str, Any]] = []
    for bucket_ts in sorted(by_bucket.keys()):
        merged = by_bucket[bucket_ts]
        merged["timestamp"] = bucket_ts
        merged["timeframe"] = timeframe
        out.append(merged)
    return out, {"derived": True, "source_timeframe": "1min", "target_timeframe": timeframe}
