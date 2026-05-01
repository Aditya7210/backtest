"""Repository for OHLCV bars — insert/query from MongoDB bars collection."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from backend.database.connection import get_db


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
    """Query bars for a specific instrument + timeframe + date range."""
    db = get_db()
    query: dict[str, Any] = {
        "instrument_token": token,
        "timeframe": timeframe,
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

    cursor = db.bars.find(query).sort("timestamp", 1)
    return await cursor.to_list(length=None)


async def get_latest_bar(token: int, timeframe: str) -> dict[str, Any] | None:
    """Get the most recent bar for an instrument."""
    db = get_db()
    return await db.bars.find_one(
        {"instrument_token": token, "timeframe": timeframe},
        sort=[("timestamp", -1)],
    )


async def get_bars_by_type(
    instrument_type: str,
    timeframe: str,
    trading_date: str,
) -> list[dict[str, Any]]:
    """Get all bars of a specific instrument type for a trading date."""
    db = get_db()
    cursor = db.bars.find({
        "instrument_type": instrument_type,
        "timeframe": timeframe,
        "trading_date": trading_date,
    }).sort("timestamp", 1)
    return await cursor.to_list(length=None)


async def get_available_catalog() -> list[dict[str, Any]]:
    """Returns distinct instruments + date ranges + timeframes available for backtesting."""
    db = get_db()
    pipeline = [
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
        {"$group": {
            "_id": {
                "instrument_token": "$_id.instrument_token",
                "tradingsymbol": "$symbol_fallback",
            },
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
            "tradingsymbol": "$_id.tradingsymbol",
            "timeframes_available": "$timeframes",
        }},
        {"$sort": {"tradingsymbol": 1}},
    ]
    cursor = db.bars.aggregate(pipeline)
    return await cursor.to_list(length=None)


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
    result = await db.bars.delete_many({
        "instrument_token": token,
        "timeframe": timeframe,
        "trading_date": {"$gte": date_from, "$lte": date_to},
    })
    return result.deleted_count
