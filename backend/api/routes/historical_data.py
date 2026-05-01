"""Historical data REST routes - catalog, instrument search, ingestion jobs."""
from __future__ import annotations

import asyncio
import uuid
from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from pydantic import BaseModel, Field

from backend.database.connection import get_db
from backend.database.repositories import bar_repository, instrument_repository
from backend.historical import ingestion_manager
from backend.utils.time_utils import now_ist_iso

router = APIRouter(tags=["historical-data"])

_ALLOWED_INTERVALS = {"minute", "3minute", "5minute", "10minute", "15minute", "30minute", "60minute", "day"}


class HistoricalIngestRequest(BaseModel):
    instrument_token: int
    tradingsymbol: str
    from_date: str
    to_date: str
    interval: str = Field(default="day")


def _map_ingest_error(exc: Exception) -> str:
    message = f"{type(exc).__name__}: {exc}"
    low = message.lower()
    if "token" in low and ("expired" in low or "invalid" in low or "incorrect" in low):
        return "Zerodha session expired. Login again and refresh access token."
    if "permission" in low or "forbidden" in low:
        return "Zerodha rejected this request. Verify API access and instrument permissions."
    return message


@router.get("/historical/catalog")
async def get_catalog():
    """Return available instruments + timeframes + date ranges in MongoDB."""
    catalog = await bar_repository.get_available_catalog()
    return {"catalog": catalog}


@router.get("/historical/bars/{instrument_token}")
async def get_historical_bars(
    instrument_token: int,
    timeframe: str = "5min",
    date_from: str | None = None,
    date_to: str | None = None,
):
    """Fetch historical bars for a given instrument, timeframe, and date range."""
    bars = await bar_repository.get_bars(
        token=instrument_token,
        timeframe=timeframe,
        date_from=date_from,
        date_to=date_to,
    )
    for bar in bars:
        bar.pop("_id", None)
        ts = bar.get("timestamp")
        if ts:
            import calendar
            bar["time"] = int(calendar.timegm(ts.timetuple()))
    return {"bars": bars, "total": len(bars)}


@router.get("/instruments/search")
async def search_instruments(
    q: str = Query(default="", min_length=1),
    limit: int = Query(default=20, ge=1, le=200),
):
    """Search instrument master by symbol/name with Mongo-first and CSV fallback."""
    if len(q.strip()) < 2:
        return {"items": [], "source": "none", "warning": "Type at least 2 characters to search."}
    return await instrument_repository.search_with_fallback(q.strip(), limit)


@router.get("/historical/instruments/search")
async def search_historical_instruments(
    q: str = Query(default="", min_length=1),
    limit: int = Query(default=20, ge=1, le=200),
):
    """Alias endpoint for historical workflow compatibility."""
    return await search_instruments(q=q, limit=limit)


@router.post("/historical/ingest")
async def start_historical_ingest(request: HistoricalIngestRequest, background_tasks: BackgroundTasks):
    """Create and run a historical ingestion job in background."""
    if request.interval not in _ALLOWED_INTERVALS:
        raise HTTPException(status_code=422, detail=f"Unsupported interval: {request.interval}")
    if request.from_date > request.to_date:
        raise HTTPException(status_code=422, detail="from_date must be <= to_date")

    job_id = str(uuid.uuid4())
    db = get_db()
    await db.historical_ingest_jobs.insert_one({
        "job_id": job_id,
        "status": "PENDING",
        "request": request.model_dump(),
        "rows": 0,
        "inserted": 0,
        "error_message": None,
        "started_at": None,
        "completed_at": None,
        "updated_at": now_ist_iso(),
    })
    background_tasks.add_task(_run_ingest_job, job_id, request.model_dump())
    return {"job_id": job_id, "status": "PENDING"}


@router.get("/historical/ingest/{job_id}")
async def get_historical_ingest_job(job_id: str):
    db = get_db()
    doc = await db.historical_ingest_jobs.find_one({"job_id": job_id})
    if doc is None:
        raise HTTPException(status_code=404, detail="Historical ingest job not found")
    doc.pop("_id", None)
    return doc


async def _run_ingest_job(job_id: str, payload: dict[str, Any]) -> None:
    db = get_db()
    await db.historical_ingest_jobs.update_one(
        {"job_id": job_id},
        {"$set": {"status": "RUNNING", "started_at": now_ist_iso(), "updated_at": now_ist_iso()}},
    )
    try:
        result = await asyncio.to_thread(
            ingestion_manager.ingest,
            instrument_token=int(payload["instrument_token"]),
            tradingsymbol=str(payload["tradingsymbol"]),
            from_date=str(payload["from_date"]),
            to_date=str(payload["to_date"]),
            interval=str(payload["interval"]),
        )
        raw_status = str(result.get("status", "ok")).lower()
        if raw_status == "no_data":
            status = "NO_DATA"
        else:
            status = "COMPLETED"

        await db.historical_ingest_jobs.update_one(
            {"job_id": job_id},
            {"$set": {
                "status": status,
                "rows": int(result.get("rows", 0)),
                "inserted": int(result.get("inserted", 0)),
                "error_message": None,
                "completed_at": now_ist_iso(),
                "updated_at": now_ist_iso(),
            }},
        )
    except Exception as exc:  # noqa: BLE001
        await db.historical_ingest_jobs.update_one(
            {"job_id": job_id},
            {"$set": {
                "status": "FAILED",
                "error_message": _map_ingest_error(exc),
                "completed_at": now_ist_iso(),
                "updated_at": now_ist_iso(),
            }},
        )
