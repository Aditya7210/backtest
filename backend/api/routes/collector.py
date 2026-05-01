"""Collector/calculator control REST routes (subprocess approach per E-12)."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.database.connection import get_db
from backend.process_manager.collector_process import (
    start_collector,
    stop_collector,
)
from backend.process_manager.calculator_process import (
    start_calculator,
    stop_calculator,
)

router = APIRouter(tags=["collector"])


@router.get("/collector/status")
async def get_status():
    """Get collector and calculator status from MongoDB singleton."""
    db = get_db()
    doc = await db.collector_status.find_one({"_id": "singleton"})
    if doc is None:
        return {"collector": {"status": "stopped"}, "calculator": {"status": "stopped"}}
    doc.pop("_id", None)
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
