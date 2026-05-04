"""Live WebSocket payload builder.

Builds a single coherent WS payload for Market Pulse / Live Market:
- collector + calculator status
- status health
- snapshot freshness
- latest snapshot data
- market view (spot/futures lens)
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from backend.database.repositories.live_market_view_repository import get_live_market_view
from backend.utils.time_utils import now_ist, now_ist_iso


def _parse_iso(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        dt = datetime.fromisoformat(value)
    except Exception:
        return None
    if dt.tzinfo is None:
        return None
    return dt


def _is_recent(value: Any, max_age_seconds: int) -> tuple[bool, float | None]:
    dt = _parse_iso(value)
    if dt is None:
        return False, None
    age = (now_ist() - dt).total_seconds()
    return age <= float(max_age_seconds), max(0.0, float(age))


async def _snapshot_health(db: Any, snapshot_type: str) -> dict[str, Any]:
    doc = await db.snapshots.find_one({"snapshot_type": snapshot_type}, sort=[("trading_date", -1)])
    if not doc:
        return {"available": False, "generated_at": None, "stale": True, "age_seconds": None}
    generated_at = doc.get("generated_at")
    recent, age = _is_recent(generated_at, 180)
    return {
        "available": True,
        "generated_at": generated_at,
        "stale": not recent,
        "age_seconds": age,
    }


async def _latest_snapshot_data(db: Any, snapshot_type: str) -> dict[str, Any]:
    doc = await db.snapshots.find_one({"snapshot_type": snapshot_type}, sort=[("trading_date", -1)])
    if not doc:
        return {}
    data = doc.get("data")
    return data if isinstance(data, dict) else {}


async def build_live_stream_payload(db: Any) -> dict[str, Any]:
    status_doc = await db.collector_status.find_one({"_id": "singleton"})
    collector = {}
    calculator = {}
    if isinstance(status_doc, dict):
        collector = status_doc.get("collector") if isinstance(status_doc.get("collector"), dict) else {}
        calculator = status_doc.get("calculator") if isinstance(status_doc.get("calculator"), dict) else {}

    collector_recent, collector_age = _is_recent(collector.get("heartbeat_at") or collector.get("last_tick_at"), 30)
    calculator_recent, calculator_age = _is_recent(calculator.get("heartbeat_at") or calculator.get("last_cycle_at"), 45)
    tick_recent, tick_age = _is_recent(collector.get("last_tick_at"), 45)
    bar_recent, bar_age = _is_recent(collector.get("last_bar_at"), 90)

    snapshot_health = {
        "vwap": await _snapshot_health(db, "vwap"),
        "ad": await _snapshot_health(db, "ad"),
        "pcr": await _snapshot_health(db, "pcr"),
        "atm_oi": await _snapshot_health(db, "atm_oi"),
        "vix": await _snapshot_health(db, "vix"),
    }
    snapshots_stale = any(item.get("stale", True) for item in snapshot_health.values())

    market_view = await get_live_market_view()

    return {
        "type": "live_update",
        "generated_at": now_ist_iso(),
        "collector": collector,
        "calculator": calculator,
        "collector_file_status": {
            "bars_written": collector.get("bars_written", 0),
            "tokens_subscribed": collector.get("tokens_subscribed", 0),
            "last_tick_at": collector.get("last_tick_at"),
            "last_bar_at": collector.get("last_bar_at"),
            "heartbeat_at": collector.get("heartbeat_at"),
        },
        "collector_status_health": {
            "status_recent": collector_recent,
            "tick_recent": tick_recent,
            "bar_recent": bar_recent,
            "collector_stale": str(collector.get("status", "")).lower() == "running" and not collector_recent,
            "calculator_stale": str(calculator.get("status", "")).lower() == "running" and not calculator_recent,
            "snapshots_stale": snapshots_stale,
            "collector_age_seconds": collector_age,
            "calculator_age_seconds": calculator_age,
            "tick_age_seconds": tick_age,
            "bar_age_seconds": bar_age,
        },
        "snapshot_health": snapshot_health,
        "market_view": market_view.get("market_view", {}),
        "pcr": await _latest_snapshot_data(db, "pcr"),
        "vix": await _latest_snapshot_data(db, "vix"),
        "atm_oi": await _latest_snapshot_data(db, "atm_oi"),
    }
