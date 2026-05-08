"""Repository for OHLCV bars — insert/query from MongoDB bars collection."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from backend.database.connection import get_db
from backend.utils.time_utils import now_ist_iso, today_ist

IST = ZoneInfo("Asia/Kolkata")
SESSION_OPEN_HOUR = 9
SESSION_OPEN_MINUTE = 15
SUPPORTED_DERIVED_TIMEFRAMES: dict[str, int | str] = {
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
_TIMEFRAME_ALIASES: dict[str, str] = {
    "minute": "1min",
    "1m": "1min",
    "3minute": "3min",
    "5minute": "5min",
    "10minute": "10min",
    "15minute": "15min",
    "20minute": "20min",
    "30minute": "30min",
    "45minute": "45min",
    "60minute": "60min",
    "hour": "60min",
    "day": "1day",
    "d": "1day",
}


def _normalize_timeframe(value: str) -> str:
    raw = str(value or "").strip().lower()
    if not raw:
        return "1day"
    return _TIMEFRAME_ALIASES.get(raw, raw)


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
    return (session_anchor + timedelta(minutes=bucket_offset)).astimezone(timezone.utc)


def _bucket_key_day(ts_utc: datetime) -> tuple[str, datetime]:
    ts_ist = _to_utc(ts_utc).astimezone(IST)
    trading_date = ts_ist.date().isoformat()
    bucket_ts = ts_ist.replace(
        hour=SESSION_OPEN_HOUR,
        minute=SESSION_OPEN_MINUTE,
        second=0,
        microsecond=0,
    ).astimezone(timezone.utc)
    return trading_date, bucket_ts


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
            "open": float(row.get("open") or 0.0),
            "high": float(row.get("high") or 0.0),
            "low": float(row.get("low") or 0.0),
            "close": float(row.get("close") or 0.0),
            "volume": float(row.get("volume") or 0.0),
            "ingest_status": "derived",
            "data_source": "derived_from_1min",
            "derived_from_timeframe": "1min",
        }
    existing["high"] = max(float(existing.get("high") or 0.0), float(row.get("high") or 0.0))
    existing["low"] = min(float(existing.get("low") or 0.0), float(row.get("low") or 0.0))
    existing["close"] = float(row.get("close") or existing.get("close") or 0.0)
    existing["volume"] = float(existing.get("volume") or 0.0) + float(row.get("volume") or 0.0)
    return existing


def _derive_from_one_minute(rows: list[dict[str, Any]], target_timeframe: str) -> list[dict[str, Any]]:
    if target_timeframe == "1min":
        return rows
    if target_timeframe not in SUPPORTED_DERIVED_TIMEFRAMES:
        return []
    if target_timeframe == "1day":
        by_day: dict[str, dict[str, Any]] = {}
        bucket_ts_by_day: dict[str, datetime] = {}
        for row in rows:
            ts = row.get("timestamp")
            if not isinstance(ts, datetime):
                continue
            day_key, bucket_ts = _bucket_key_day(ts)
            bucket_ts_by_day[day_key] = bucket_ts
            by_day[day_key] = _merge_bucket_row(by_day.get(day_key), row, bucket_ts=bucket_ts)
        out: list[dict[str, Any]] = []
        for day_key in sorted(by_day.keys()):
            merged = by_day[day_key]
            merged["trading_date"] = day_key
            merged["timestamp"] = bucket_ts_by_day[day_key]
            merged["timeframe"] = "1day"
            out.append(merged)
        return out

    minutes = int(SUPPORTED_DERIVED_TIMEFRAMES[target_timeframe])  # type: ignore[arg-type]
    by_bucket: dict[datetime, dict[str, Any]] = {}
    for row in rows:
        ts = row.get("timestamp")
        if not isinstance(ts, datetime):
            continue
        bucket_ts = _bucket_start_ist(ts, minutes)
        by_bucket[bucket_ts] = _merge_bucket_row(by_bucket.get(bucket_ts), row, bucket_ts=bucket_ts)

    out: list[dict[str, Any]] = []
    for bucket_ts in sorted(by_bucket.keys()):
        merged = by_bucket[bucket_ts]
        merged["timestamp"] = bucket_ts
        merged["timeframe"] = target_timeframe
        out.append(merged)
    return out


async def insert_bars(bars: list[dict[str, Any]]) -> int:
    """Insert bars with upsert on (instrument_token, timeframe, timestamp).
    Uses $setOnInsert for data_source per E-10."""
    db = get_db()
    from pymongo import UpdateOne

    operations = []
    for bar in bars:
        filt = {
            "instrument_token": bar["instrument_token"],
            "timeframe": bar["timeframe"],
            "timestamp": bar["timestamp"],
        }
        operations.append(
            UpdateOne(
                filt,
                {
                    "$set": {
                        k: v for k, v in bar.items()
                        if k not in ("data_source",)
                    },
                    "$setOnInsert": {"data_source": bar.get("data_source", "live")},
                },
                upsert=True,
            )
        )

    if not operations:
        return 0

    result = await db.bars.bulk_write(operations, ordered=False)
    return result.upserted_count + result.modified_count


async def get_bars(
    token: int,
    timeframe: str,
    date_from: str | None = None,
    date_to: str | None = None,
    trading_date: str | None = None,
) -> list[dict[str, Any]]:
    """Query bars for instrument/timeframe/date range, with on-demand derived TF fallback."""
    db = get_db()
    normalized_tf = _normalize_timeframe(timeframe)
    query: dict[str, Any] = {
        "instrument_token": token,
        "timeframe": normalized_tf,
    }
    if trading_date:
        query["trading_date"] = trading_date
    elif date_from or date_to:
        date_filter: dict[str, str] = {}
        if date_from:
            date_filter["$gte"] = date_from
        if date_to:
            date_filter["$lte"] = date_to
        query["trading_date"] = date_filter

    bars = await db.bars.find(query).sort("timestamp", 1).to_list(length=None)
    if bars or normalized_tf == "1min":
        return bars

    if normalized_tf not in SUPPORTED_DERIVED_TIMEFRAMES:
        return []

    one_min_query = dict(query)
    one_min_query["timeframe"] = "1min"
    one_minute_rows = await db.bars.find(one_min_query).sort("timestamp", 1).to_list(length=None)
    if not one_minute_rows:
        return []
    return _derive_from_one_minute(one_minute_rows, normalized_tf)


async def get_latest_bar(token: int, timeframe: str) -> dict[str, Any] | None:
    """Get the most recent bar for an instrument."""
    db = get_db()
    normalized_tf = _normalize_timeframe(timeframe)
    return await db.bars.find_one(
        {"instrument_token": token, "timeframe": normalized_tf},
        sort=[("timestamp", -1)],
    )


async def get_bars_by_type(
    instrument_type: str,
    timeframe: str,
    trading_date: str,
) -> list[dict[str, Any]]:
    """Get all bars of a specific instrument type for a trading date."""
    db = get_db()
    normalized_tf = _normalize_timeframe(timeframe)
    cursor = db.bars.find({
        "instrument_type": instrument_type,
        "timeframe": normalized_tf,
        "trading_date": trading_date,
    }).sort("timestamp", 1)
    return await cursor.to_list(length=None)


def _catalog_pipeline(match: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    pipeline: list[dict[str, Any]] = []
    if match:
        pipeline.append({"$match": match})
    pipeline.extend([
        {"$group": {
            "_id": {
                "instrument_token": "$instrument_token",
                "tradingsymbol": "$tradingsymbol",
                "timeframe": "$timeframe",
            },
            "date_from": {"$min": "$trading_date"},
            "date_to": {"$max": "$trading_date"},
            "total_bars": {"$sum": 1},
            "data_sources": {"$addToSet": "$data_source"},
        }},
        {"$addFields": {
            "symbol_fallback": {
                "$ifNull": ["$_id.tradingsymbol", {"$toString": "$_id.instrument_token"}],
            },
        }},
        {"$sort": {"symbol_fallback": 1}},
        {"$group": {
            "_id": {
                "instrument_token": "$_id.instrument_token",
            },
            "tradingsymbol": {"$first": "$symbol_fallback"},
            "timeframes": {"$push": {
                "timeframe": "$_id.timeframe",
                "date_from": "$date_from",
                "date_to": "$date_to",
                "total_bars": "$total_bars",
                "data_source": {
                    "$cond": [
                        {"$gt": [{"$size": "$data_sources"}, 1]},
                        "mixed",
                        {"$ifNull": [{"$arrayElemAt": ["$data_sources", 0]}, "historical"]},
                    ],
                },
            }},
        }},
        {"$project": {
            "_id": 0,
            "instrument_token": "$_id.instrument_token",
            "tradingsymbol": "$tradingsymbol",
            "timeframes_available": "$timeframes",
        }},
        {"$sort": {"tradingsymbol": 1}},
    ])
    return pipeline


async def get_available_catalog(*, use_cache: bool = True) -> list[dict[str, Any]]:
    """Returns distinct instruments + date ranges + timeframes available for backtesting."""
    db = get_db()
    if use_cache:
        cached_docs = await db.historical_catalog.find({}, {"_id": 0}).sort("tradingsymbol", 1).to_list(length=None)
        if cached_docs:
            return cached_docs

    pipeline = _catalog_pipeline()
    cursor = db.bars.aggregate(pipeline)
    docs = [{k: v for k, v in row.items() if k != "_id"} for row in await cursor.to_list(length=None)]
    if use_cache and docs:
        await db.historical_catalog.delete_many({})
        await db.historical_catalog.insert_many([dict(doc) for doc in docs], ordered=False)
    return docs


async def rebuild_catalog_cache() -> int:
    """Rebuild full materialized historical catalog cache from bars collection."""
    db = get_db()
    docs = [{k: v for k, v in row.items() if k != "_id"} for row in await db.bars.aggregate(_catalog_pipeline()).to_list(length=None)]
    await db.historical_catalog.delete_many({})
    if docs:
        await db.historical_catalog.insert_many([dict(doc) for doc in docs], ordered=False)
    return len(docs)


async def refresh_catalog_for_instrument(token: int) -> None:
    """Refresh a single instrument entry in materialized catalog cache."""
    db = get_db()
    docs = [
        {k: v for k, v in row.items() if k != "_id"}
        for row in await db.bars.aggregate(_catalog_pipeline({"instrument_token": token})).to_list(length=None)
    ]
    await db.historical_catalog.delete_many({"instrument_token": token})
    if docs:
        await db.historical_catalog.insert_many([dict(doc) for doc in docs], ordered=False)


async def get_symbol_for_token(token: int) -> str | None:
    """Resolve a token to its latest tradingsymbol from stored bars."""
    db = get_db()
    doc = await db.bars.find_one(
        {"instrument_token": token},
        projection={"_id": 0, "tradingsymbol": 1},
        sort=[("timestamp", -1)],
    )
    if not doc:
        return None
    value = doc.get("tradingsymbol")
    return str(value) if value else None


async def delete_bars(
    token: int,
    timeframe: str,
    date_from: str,
    date_to: str,
) -> int:
    """Delete bars in a date range (for re-ingestion)."""
    db = get_db()
    normalized_tf = _normalize_timeframe(timeframe)
    result = await db.bars.delete_many({
        "instrument_token": token,
        "timeframe": normalized_tf,
        "trading_date": {"$gte": date_from, "$lte": date_to},
    })
    return result.deleted_count


async def delete_bars_by_ingest_job(ingest_job_id: str) -> int:
    """Delete bars linked to a specific historical ingest job lineage id."""
    db = get_db()
    result = await db.bars.delete_many({"ingest_job_id": ingest_job_id})
    return result.deleted_count


async def get_existing_trading_dates(
    *,
    token: int,
    timeframe: str,
    date_from: str,
    date_to: str,
) -> set[str]:
    """Return existing trading_date values for token/timeframe within requested range."""
    db = get_db()
    normalized_tf = _normalize_timeframe(timeframe)
    values = await db.bars.distinct(
        "trading_date",
        {
            "instrument_token": token,
            "timeframe": normalized_tf,
            "trading_date": {"$gte": date_from, "$lte": date_to},
        },
    )
    return {str(v) for v in values if v}


def compute_missing_date_spans(
    *,
    date_from: str,
    date_to: str,
    existing_trading_dates: set[str],
) -> list[tuple[str, str]]:
    """
    Compute missing weekday spans in [date_from, date_to].

    Note: this is date-level completeness, not candle-count completeness.
    """
    start = datetime.strptime(date_from, "%Y-%m-%d").date()
    end = datetime.strptime(date_to, "%Y-%m-%d").date()
    if start > end:
        return []

    missing_days: list[date] = []
    cursor = start
    while cursor <= end:
        iso = cursor.isoformat()
        if cursor.weekday() < 5 and iso not in existing_trading_dates:
            missing_days.append(cursor)
        cursor += timedelta(days=1)

    if not missing_days:
        return []

    spans: list[tuple[str, str]] = []
    span_start = missing_days[0]
    prev = missing_days[0]
    for day in missing_days[1:]:
        if (day - prev).days > 1:
            spans.append((span_start.isoformat(), prev.isoformat()))
            span_start = day
        prev = day
    spans.append((span_start.isoformat(), prev.isoformat()))
    return spans


def _coerce_int(value: Any) -> int | None:
    try:
        return int(value)
    except Exception:
        return None


def _infer_underlying(symbol: str) -> str:
    up = str(symbol or "").strip().upper()
    if up.startswith("BANKNIFTY"):
        return "BANKNIFTY"
    if up.startswith("NIFTY"):
        return "NIFTY"
    return ""


def _infer_option_type(symbol: str) -> str:
    up = str(symbol or "").strip().upper()
    if up.endswith("CE"):
        return "CE"
    if up.endswith("PE"):
        return "PE"
    return ""


def _utc_seconds_from_datetime(value: Any) -> int | None:
    if not isinstance(value, datetime):
        return None
    dt = value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    return int(dt.timestamp())


def _coerce_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except Exception:
        return None


async def _build_live_tick_inventory_items(
    *,
    db: Any,
    now_utc: datetime,
    search: str,
    instrument_type: str,
    universe: str,
    underlying: str,
    expiry: str,
    timeframe: str,
    trading_date: str,
    stale_threshold_seconds: int,
    active_only: bool,
) -> list[dict[str, Any]]:
    tick_match: dict[str, Any] = {}
    if instrument_type and instrument_type != "all":
        tick_match["instrument_type"] = instrument_type
    if underlying and underlying != "all":
        tick_match["underlying"] = underlying.upper()
    if expiry and expiry != "all":
        tick_match["expiry"] = expiry

    tick_docs = await db.live_ticks.find(tick_match, {"_id": 0}).to_list(length=None)
    fallback_items: list[dict[str, Any]] = []
    for row in tick_docs:
        token_int = _coerce_int(row.get("instrument_token"))
        if token_int is None:
            continue
        symbol = str(row.get("tradingsymbol") or token_int).strip()
        if search:
            q = search.lower().strip()
            hay = f"{symbol} {token_int} {row.get('instrument_type') or ''} {row.get('underlying') or ''} {row.get('expiry') or ''}".lower()
            if q not in hay:
                continue

        ts = row.get("timestamp")
        last_dt = ts if isinstance(ts, datetime) else None
        stale_seconds = None
        if last_dt is not None:
            dt = last_dt if last_dt.tzinfo is not None else last_dt.replace(tzinfo=timezone.utc)
            stale_seconds = int((now_utc - dt).total_seconds())
        is_active = stale_seconds is not None and stale_seconds <= stale_threshold_seconds
        if active_only and not is_active:
            continue

        inferred_underlying = str(row.get("underlying") or "").strip().upper()
        if not inferred_underlying and str(row.get("instrument_type") or "") == "option":
            inferred_underlying = _infer_underlying(symbol)
        inferred_option_type = str(row.get("option_type") or "").strip().upper()
        if not inferred_option_type and str(row.get("instrument_type") or "") == "option":
            inferred_option_type = _infer_option_type(symbol)

        candidate = {
            "instrument_token": token_int,
            "tradingsymbol": symbol,
            "instrument_type": str(row.get("instrument_type") or "unknown"),
            "data_source": "live",
            "timeframe": timeframe,
            "trading_date": trading_date,
            "first_bar_at": None,
            "last_bar_at": last_dt.isoformat() if isinstance(last_dt, datetime) else None,
            "first_bar_time": None,
            "last_bar_time": _utc_seconds_from_datetime(last_dt),
            "total_bars": 0,
            "last_close": _coerce_float(row.get("last_price")),
            "exchange": str(row.get("exchange") or ""),
            "segment": str(row.get("segment") or ""),
            "underlying": inferred_underlying,
            "expiry": str(row.get("expiry") or ""),
            "strike": float(row.get("strike")) if row.get("strike") is not None else None,
            "option_type": inferred_option_type,
            "is_active": bool(is_active),
            "stale_seconds": stale_seconds,
        }
        u = universe.upper().strip()
        usym = candidate["tradingsymbol"].upper()
        if u == "NIFTY 50":
            if usym not in {"NIFTY 50", "NIFTY"}:
                continue
        elif u == "NIFTY BANK":
            if usym not in {"NIFTY BANK", "BANKNIFTY"}:
                continue
        elif u == "NIFTY OPTIONS":
            if not (candidate["instrument_type"] == "option" and candidate["underlying"] == "NIFTY"):
                continue
        elif u == "BANKNIFTY OPTIONS":
            if not (candidate["instrument_type"] == "option" and candidate["underlying"] == "BANKNIFTY"):
                continue
        fallback_items.append(candidate)

    fallback_items.sort(key=lambda x: (str(x.get("tradingsymbol") or ""), str(x.get("instrument_type") or "")))
    return fallback_items


async def get_live_instruments_inventory(
    *,
    search: str = "",
    instrument_type: str = "all",
    universe: str = "all",
    underlying: str = "all",
    expiry: str = "all",
    timeframe: str = "1min",
    trading_date: str | None = None,
    data_source: str = "all",
    active_only: bool = False,
    stale_threshold_seconds: int = 180,
    limit: int = 500,
) -> dict[str, Any]:
    db = get_db()
    now_utc = datetime.now(tz=timezone.utc)
    effective_trading_date = trading_date
    if not effective_trading_date or str(effective_trading_date).strip().lower() in {"all", ""}:
        effective_trading_date = today_ist().isoformat()

    base_match: dict[str, Any] = {}
    if timeframe and timeframe != "all":
        base_match["timeframe"] = timeframe
    if effective_trading_date and effective_trading_date != "all":
        base_match["trading_date"] = effective_trading_date
    if data_source and data_source != "all":
        base_match["data_source"] = data_source
    if instrument_type and instrument_type != "all":
        base_match["instrument_type"] = instrument_type
    if underlying and underlying != "all":
        base_match["underlying"] = underlying.upper()
    if expiry and expiry != "all":
        base_match["expiry"] = expiry

    pipeline: list[dict[str, Any]] = []
    if base_match:
        pipeline.append({"$match": base_match})
    pipeline.extend(
        [
            {"$sort": {"timestamp": -1}},
            {
                "$group": {
                    "_id": {
                        "instrument_token": "$instrument_token",
                        "timeframe": "$timeframe",
                        "trading_date": "$trading_date",
                    },
                    "instrument_token": {"$first": "$instrument_token"},
                    "tradingsymbol": {"$first": "$tradingsymbol"},
                    "instrument_type": {"$first": "$instrument_type"},
                    "timeframe": {"$first": "$timeframe"},
                    "trading_date": {"$first": "$trading_date"},
                    "last_bar_at": {"$first": "$timestamp"},
                    "first_bar_at": {"$min": "$timestamp"},
                    "total_bars": {"$sum": 1},
                    "data_sources": {"$addToSet": "$data_source"},
                    "exchange": {"$first": "$exchange"},
                    "segment": {"$first": "$segment"},
                    "underlying": {"$first": "$underlying"},
                    "expiry": {"$first": "$expiry"},
                    "strike": {"$first": "$strike"},
                    "option_type": {"$first": "$option_type"},
                    "last_close": {"$first": "$close"},
                }
            },
            {"$sort": {"tradingsymbol": 1, "timeframe": 1}},
        ]
    )
    raw = await db.bars.aggregate(pipeline).to_list(length=None)

    items: list[dict[str, Any]] = []
    for row in raw:
        symbol = str(row.get("tradingsymbol") or row.get("instrument_token") or "").strip()
        token_int = _coerce_int(row.get("instrument_token"))
        if token_int is None:
            continue
        if search:
            q = search.lower().strip()
            hay = f"{symbol} {token_int} {row.get('instrument_type') or ''} {row.get('underlying') or ''} {row.get('expiry') or ''}".lower()
            if q not in hay:
                continue
        sources = [str(x) for x in (row.get("data_sources") or []) if x]
        source = "mixed" if len(set(sources)) > 1 else (sources[0] if sources else "historical")
        last_bar_at = row.get("last_bar_at")
        last_dt = last_bar_at if isinstance(last_bar_at, datetime) else None
        stale_seconds = None
        if last_dt is not None:
            dt = last_dt if last_dt.tzinfo is not None else last_dt.replace(tzinfo=timezone.utc)
            stale_seconds = int((now_utc - dt).total_seconds())
        is_active = stale_seconds is not None and stale_seconds <= stale_threshold_seconds
        if active_only and not is_active:
            continue

        inferred_underlying = str(row.get("underlying") or "").strip().upper()
        if not inferred_underlying and str(row.get("instrument_type") or "") == "option":
            inferred_underlying = _infer_underlying(symbol)
        inferred_option_type = str(row.get("option_type") or "").strip().upper()
        if not inferred_option_type and str(row.get("instrument_type") or "") == "option":
            inferred_option_type = _infer_option_type(symbol)

        candidate = {
            "instrument_token": token_int,
            "tradingsymbol": symbol or str(token_int),
            "instrument_type": str(row.get("instrument_type") or "unknown"),
            "data_source": source,
            "timeframe": str(row.get("timeframe") or ""),
            "trading_date": str(row.get("trading_date") or ""),
            "first_bar_at": row.get("first_bar_at").isoformat() if isinstance(row.get("first_bar_at"), datetime) else None,
            "last_bar_at": last_dt.isoformat() if isinstance(last_dt, datetime) else None,
            "first_bar_time": _utc_seconds_from_datetime(row.get("first_bar_at")),
            "last_bar_time": _utc_seconds_from_datetime(last_dt),
            "total_bars": int(row.get("total_bars") or 0),
            "last_close": float(row.get("last_close")) if row.get("last_close") is not None else None,
            "exchange": str(row.get("exchange") or ""),
            "segment": str(row.get("segment") or ""),
            "underlying": inferred_underlying,
            "expiry": str(row.get("expiry") or ""),
            "strike": float(row.get("strike")) if row.get("strike") is not None else None,
            "option_type": inferred_option_type,
            "is_active": bool(is_active),
            "stale_seconds": stale_seconds,
        }
        u = universe.upper().strip()
        usym = candidate["tradingsymbol"].upper()
        if u == "NIFTY 50":
            if usym not in {"NIFTY 50", "NIFTY"}:
                continue
        elif u == "NIFTY BANK":
            if usym not in {"NIFTY BANK", "BANKNIFTY"}:
                continue
        elif u == "NIFTY OPTIONS":
            if not (candidate["instrument_type"] == "option" and candidate["underlying"] == "NIFTY"):
                continue
        elif u == "BANKNIFTY OPTIONS":
            if not (candidate["instrument_type"] == "option" and candidate["underlying"] == "BANKNIFTY"):
                continue
        items.append(candidate)

    if not items:
        items = await _build_live_tick_inventory_items(
            db=db,
            now_utc=now_utc,
            search=search,
            instrument_type=instrument_type,
            universe=universe,
            underlying=underlying,
            expiry=expiry,
            timeframe=str(timeframe or "1min"),
            trading_date=effective_trading_date,
            stale_threshold_seconds=stale_threshold_seconds,
            active_only=active_only,
        )

    instrument_types = sorted({str(x.get("instrument_type") or "") for x in items if x.get("instrument_type")})
    underlyings = sorted({str(x.get("underlying") or "") for x in items if x.get("underlying")})
    expiries = sorted({str(x.get("expiry") or "") for x in items if x.get("expiry")})
    timeframes = sorted({str(x.get("timeframe") or "") for x in items if x.get("timeframe")})
    trading_dates = sorted({str(x.get("trading_date") or "") for x in items if x.get("trading_date")}, reverse=True)

    capped_items = items[: max(1, int(limit))]

    return {
        "items": capped_items,
        "generated_at": now_ist_iso(),
        "trading_date": effective_trading_date,
        "stale_threshold_seconds": stale_threshold_seconds,
        "filters": {
            "instrument_types": instrument_types,
            "underlyings": underlyings,
            "expiries": expiries,
            "timeframes": timeframes,
            "trading_dates": trading_dates,
        },
    }


async def get_live_universe_health(
    *,
    trading_date: str | None = None,
    timeframe: str = "1min",
    stale_threshold_seconds: int = 180,
) -> dict[str, Any]:
    inventory = await get_live_instruments_inventory(
        timeframe=timeframe,
        trading_date=trading_date,
        stale_threshold_seconds=stale_threshold_seconds,
        limit=5000,
    )
    items = inventory.get("items", [])
    nifty_spot_present = any(str(x.get("tradingsymbol", "")).upper() in {"NIFTY 50", "NIFTY"} for x in items)
    bank_spot_present = any(str(x.get("tradingsymbol", "")).upper() in {"NIFTY BANK", "BANKNIFTY"} for x in items)
    nifty_opts = [x for x in items if x.get("instrument_type") == "option" and str(x.get("underlying") or "").upper() == "NIFTY"]
    bank_opts = [x for x in items if x.get("instrument_type") == "option" and str(x.get("underlying") or "").upper() == "BANKNIFTY"]
    nifty_futs = [x for x in items if x.get("instrument_type") == "future" and str(x.get("underlying") or "").upper() == "NIFTY"]
    bank_futs = [x for x in items if x.get("instrument_type") == "future" and str(x.get("underlying") or "").upper() == "BANKNIFTY"]
    return {
        "generated_at": now_ist_iso(),
        "trading_date": inventory.get("trading_date"),
        "stale_threshold_seconds": stale_threshold_seconds,
        "timeframe": timeframe,
        "nifty_spot_present": nifty_spot_present,
        "banknifty_spot_present": bank_spot_present,
        "nifty_option_tokens": len({x["instrument_token"] for x in nifty_opts}),
        "banknifty_option_tokens": len({x["instrument_token"] for x in bank_opts}),
        "nifty_ce_count": sum(1 for x in nifty_opts if str(x.get("option_type") or "").upper() == "CE"),
        "nifty_pe_count": sum(1 for x in nifty_opts if str(x.get("option_type") or "").upper() == "PE"),
        "banknifty_ce_count": sum(1 for x in bank_opts if str(x.get("option_type") or "").upper() == "CE"),
        "banknifty_pe_count": sum(1 for x in bank_opts if str(x.get("option_type") or "").upper() == "PE"),
        "nifty_futures_count": len(nifty_futs),
        "banknifty_futures_count": len(bank_futs),
        "active_instruments": sum(1 for x in items if x.get("is_active")),
        "stale_instruments": sum(1 for x in items if not x.get("is_active")),
        "total_instruments": len(items),
        "filters": inventory.get("filters", {}),
    }
