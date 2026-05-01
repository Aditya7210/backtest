"""Repository for backtest results (E-06: data_selection not data_file)."""
from __future__ import annotations

from typing import Any

from backend.database.connection import get_db
from backend.utils.time_utils import now_ist_iso


async def create(task_id: str, config: dict[str, Any]) -> None:
    db = get_db()
    await db.backtest_results.insert_one({
        "task_id": task_id,
        "strategy_name": config.get("strategy_name", ""),
        "symbol": config.get("symbol", ""),
        "data_selection": config.get("data_selection"),
        "config": config,
        "status": "PENDING",
        "started_at": now_ist_iso(),
        "completed_at": None,
        "final_value": None,
        "metrics": {},
        "trades": [],
        "data_gaps": None,
        "error_message": None,
        "log_lines": [],
    })


async def update_result(task_id: str, result: dict[str, Any]) -> None:
    db = get_db()
    status = result.get("status", "COMPLETED")
    update_doc: dict[str, Any] = {
        "status": status,
        "final_value": result.get("final_value"),
        "metrics": result.get("metrics", {}),
        "trades": result.get("trades", []),
        "error_message": result.get("error_message"),
    }
    if status in ("COMPLETED", "FAILED"):
        update_doc["completed_at"] = now_ist_iso()
    await db.backtest_results.update_one({"task_id": task_id}, {"$set": update_doc})


async def set_status(task_id: str, status: str, *, error_message: str | None = None) -> None:
    db = get_db()
    update_doc: dict[str, Any] = {"status": status}
    if error_message is not None:
        update_doc["error_message"] = error_message
    if status in ("COMPLETED", "FAILED"):
        update_doc["completed_at"] = now_ist_iso()
    await db.backtest_results.update_one({"task_id": task_id}, {"$set": update_doc})


async def append_log(task_id: str, message: str, level: str = "INFO") -> None:
    db = get_db()
    line = f"[{now_ist_iso()}] [{level}] {message}"
    await db.backtest_results.update_one(
        {"task_id": task_id},
        {"$push": {"log_lines": {"$each": [line], "$slice": -600}}},
    )


async def get_all() -> list[dict[str, Any]]:
    db = get_db()
    cursor = db.backtest_results.find().sort("started_at", -1)
    results = await cursor.to_list(length=None)
    for r in results:
        r["_id"] = str(r["_id"])
    return results


async def get_by_id(task_id: str) -> dict[str, Any] | None:
    db = get_db()
    result = await db.backtest_results.find_one({"task_id": task_id})
    if result:
        result["_id"] = str(result["_id"])
    return result
