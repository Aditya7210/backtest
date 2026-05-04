"""Collector/calculator control REST routes (subprocess approach per E-12)."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException

from backend.database.connection import get_db
from backend.utils.time_utils import now_ist
from backend.process_manager.collector_process import (
    start_collector,
    stop_collector,
)
from backend.process_manager.calculator_process import (
    start_calculator,
    stop_calculator,
)

router = APIRouter(tags=["collector"])


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


@router.get("/collector/status")
async def get_status():
    """Get collector and calculator status from MongoDB singleton."""
    db = get_db()
    doc = await db.collector_status.find_one({"_id": "singleton"})
    if doc is None:
        return {
            "collector": {"status": "stopped"},
            "calculator": {"status": "stopped"},
            "collector_file_status": {
                "bars_written": 0,
                "tokens_subscribed": 0,
                "last_tick_at": None,
                "last_bar_at": None,
            },
            "collector_status_health": {
                "status_recent": False,
                "tick_recent": False,
                "bar_recent": False,
                "collector_stale": True,
                "calculator_stale": True,
                "snapshots_stale": True,
                "collector_age_seconds": None,
                "calculator_age_seconds": None,
            },
            "snapshot_health": {},
        }
    doc.pop("_id", None)
    collector = doc.get("collector") if isinstance(doc.get("collector"), dict) else {}
    calculator = doc.get("calculator") if isinstance(doc.get("calculator"), dict) else {}

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

    doc["collector"] = collector
    doc["calculator"] = calculator
    doc["collector_file_status"] = {
        "bars_written": collector.get("bars_written", 0),
        "tokens_subscribed": collector.get("tokens_subscribed", 0),
        "last_tick_at": collector.get("last_tick_at"),
        "last_bar_at": collector.get("last_bar_at"),
        "heartbeat_at": collector.get("heartbeat_at"),
    }
    doc["collector_status_health"] = {
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
    }
    doc["snapshot_health"] = snapshot_health
    return doc


@router.post("/collector/start")
async def api_start_collector():
    """Start the WebSocket collector subprocess."""
    try:
        result = start_collector()
        return {"status": "starting", **result}
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@router.post("/collector/stop")
async def api_stop_collector():
    """Stop the WebSocket collector subprocess."""
    result = stop_collector()
    return {"status": "stopping", **result}


@router.post("/calculator/start")
async def api_start_calculator():
    """Start the calculation runner subprocess."""
    try:
        result = start_calculator()
        return {"status": "starting", **result}
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@router.post("/calculator/stop")
async def api_stop_calculator():
    """Stop the calculation runner subprocess."""
    result = stop_calculator()
    return {"status": "stopping", **result}
