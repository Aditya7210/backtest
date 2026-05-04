"""Live tick persistence feature for collector."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pymongo import UpdateOne

_INDEX_READY = False


def _ensure_live_tick_index(db: Any) -> None:
    global _INDEX_READY
    if _INDEX_READY:
        return
    db.live_ticks.create_index([("instrument_token", 1)], unique=True, background=True, name="ix_live_ticks_token_unique")
    _INDEX_READY = True


def flush_latest_ticks_to_mongo(db: Any, ticks_by_token: dict[int, dict[str, Any]]) -> int:
    if not ticks_by_token:
        return 0
    _ensure_live_tick_index(db)
    operations: list[UpdateOne] = []
    for token, payload in ticks_by_token.items():
        ts = payload.get("timestamp")
        if isinstance(ts, datetime):
            ts_utc = ts if ts.tzinfo is not None else ts.replace(tzinfo=timezone.utc)
            ts_utc = ts_utc.astimezone(timezone.utc)
        else:
            ts_utc = datetime.now(tz=timezone.utc)
        document = {
            "instrument_token": int(token),
            "last_price": float(payload.get("last_price") or 0.0),
            "volume_traded": float(payload.get("volume_traded") or 0.0),
            "oi": float(payload.get("oi") or 0.0),
            "timestamp": ts_utc,
            "trading_date": str(payload.get("trading_date") or ""),
            "tradingsymbol": str(payload.get("tradingsymbol") or f"TOKEN_{token}"),
            "instrument_type": str(payload.get("instrument_type") or "unknown"),
            "exchange": str(payload.get("exchange") or ""),
            "segment": str(payload.get("segment") or ""),
            "underlying": payload.get("underlying"),
            "expiry": payload.get("expiry"),
            "strike": payload.get("strike"),
            "option_type": payload.get("option_type"),
            "updated_at": datetime.now(tz=timezone.utc),
        }
        operations.append(
            UpdateOne(
                {"instrument_token": int(token)},
                {"$set": document},
                upsert=True,
            )
        )
    if not operations:
        return 0
    result = db.live_ticks.bulk_write(operations, ordered=False)
    return int((result.modified_count or 0) + (result.upserted_count or 0))
