"""Backfill historical bars trading_date to IST date derived from timestamp.

Usage:
  python scripts/fix_historical_trading_dates.py
"""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from pymongo import UpdateOne

from backend.config import settings
from backend.database.sync_connection import get_sync_db

IST_TZ = ZoneInfo("Asia/Kolkata")


def main() -> None:
    db = get_sync_db()
    cursor = db.bars.find(
        {"data_source": "historical"},
        {"_id": 1, "timestamp": 1, "trading_date": 1},
    )

    ops: list[UpdateOne] = []
    scanned = 0
    mismatched = 0

    for row in cursor:
        scanned += 1
        ts = row.get("timestamp")
        if not isinstance(ts, datetime):
            continue
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=ZoneInfo("UTC"))

        expected = ts.astimezone(IST_TZ).strftime("%Y-%m-%d")
        if row.get("trading_date") != expected:
            mismatched += 1
            ops.append(UpdateOne({"_id": row["_id"]}, {"$set": {"trading_date": expected}}))

    modified = 0
    if ops:
        result = db.bars.bulk_write(ops, ordered=False)
        modified = result.modified_count

    print(
        {
            "mongo_uri": settings.MONGO_URI,
            "scanned": scanned,
            "mismatched": mismatched,
            "modified": modified,
        }
    )


if __name__ == "__main__":
    main()
