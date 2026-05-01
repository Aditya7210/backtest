"""Repository for calculation snapshots — upsert/fetch from MongoDB snapshots collection."""
from __future__ import annotations

from typing import Any

from backend.database.connection import get_db
from backend.utils.time_utils import now_ist_iso


async def upsert_snapshot(snapshot_type: str, trading_date: str, data: dict[str, Any]) -> None:
    """Upsert a snapshot — unique on (snapshot_type, trading_date)."""
    db = get_db()
    await db.snapshots.update_one(
        {"snapshot_type": snapshot_type, "trading_date": trading_date},
        {"$set": {
            "snapshot_type": snapshot_type,
            "trading_date": trading_date,
            "generated_at": now_ist_iso(),
            "data": data,
        }},
        upsert=True,
    )


async def get_latest_snapshot(snapshot_type: str) -> dict[str, Any] | None:
    """Get the most recent snapshot of a given type."""
    db = get_db()
    return await db.snapshots.find_one(
        {"snapshot_type": snapshot_type},
        sort=[("trading_date", -1)],
    )


async def get_snapshot_history(
    snapshot_type: str,
    trading_date: str,
) -> list[dict[str, Any]]:
    """Get all snapshots of a given type for a trading date."""
    db = get_db()
    cursor = db.snapshots.find({
        "snapshot_type": snapshot_type,
        "trading_date": trading_date,
    }).sort("generated_at", -1)
    return await cursor.to_list(length=None)
