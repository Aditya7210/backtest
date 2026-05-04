"""Historical data REST routes: catalog, mapper search, ingestion jobs."""
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timedelta
import re
from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from pydantic import BaseModel, Field, field_validator

from backend.database.connection import get_db
from backend.database.repositories import bar_repository, instrument_repository
from backend.historical import ingestion_manager
from backend.utils.time_utils import now_ist, now_ist_iso

router = APIRouter(tags=["historical-data"])

_ALLOWED_INTERVALS = {"minute", "3minute", "5minute", "10minute", "15minute", "30minute", "60minute", "day"}
_STALE_JOB_TIMEOUT_MINUTES = 20
_DATE_ONLY_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_MIN_SUPPORTED_YEAR = 2000


class HistoricalIngestRequest(BaseModel):
    instrument_token: int
    tradingsymbol: str
    from_date: str
    to_date: str
    interval: str = Field(default="day")

    @field_validator("from_date", "to_date")
    @classmethod
    def _validate_date_only(cls, value: str) -> str:
        raw = value.strip()
        if not _DATE_ONLY_PATTERN.match(raw):
            raise ValueError("Date must be in YYYY-MM-DD format.")
        parsed = datetime.strptime(raw, "%Y-%m-%d")
        max_year = datetime.now().year + 1
        if parsed.year < _MIN_SUPPORTED_YEAR or parsed.year > max_year:
            raise ValueError(f"Year must be between {_MIN_SUPPORTED_YEAR} and {max_year}.")
        return raw

    @field_validator("interval")
    @classmethod
    def _validate_interval(cls, value: str) -> str:
        cleaned = value.strip().lower()
        if cleaned not in _ALLOWED_INTERVALS:
            raise ValueError(f"Unsupported interval: {value}")
        return cleaned


def _map_ingest_error(exc: Exception) -> str:
    message = f"{type(exc).__name__}: {exc}"
    low = message.lower()
    if "token" in low and ("expired" in low or "invalid" in low or "incorrect" in low):
        return "Zerodha session expired. Login again and refresh access token."
    if "permission" in low or "forbidden" in low:
        return "Zerodha rejected this request. Verify API access and instrument permissions."
    return message


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except Exception:  # noqa: BLE001
        return None


async def _maybe_mark_stale_job(doc: dict[str, Any]) -> dict[str, Any]:
    status = str(doc.get("status") or "").upper()
    if status not in {"PENDING", "RUNNING"}:
        return doc
    updated_at = _parse_iso(doc.get("updated_at"))
    if updated_at is None:
        return doc
    if now_ist() - updated_at < timedelta(minutes=_STALE_JOB_TIMEOUT_MINUTES):
        return doc

    db = get_db()
    stale_msg = "Ingest interrupted before completion (stale RUNNING/PENDING job)."
    now_iso = now_ist_iso()
    await db.historical_ingest_jobs.update_one(
        {"job_id": doc["job_id"]},
        {"$set": {
            "status": "FAILED",
            "phase": "STALE",
            "error_message": stale_msg,
            "completed_at": now_iso,
            "updated_at": now_iso,
        }},
    )
    doc.update(
        {
            "status": "FAILED",
            "phase": "STALE",
            "error_message": stale_msg,
            "completed_at": now_iso,
            "updated_at": now_iso,
        }
    )
    return doc


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
            bar["time"] = int(ts.timestamp())
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


@router.get("/instruments/mapper/search")
async def search_instruments_mapper(
    q: str = Query(default="", min_length=1),
    limit: int = Query(default=20, ge=1, le=200),
):
    """Search mapper CSV files (latest + archive), preserving old tokens."""
    return instrument_repository.search_mapper_files(q.strip(), limit)


@router.post("/instruments/mapper/update")
async def update_instruments_mapper():
    """Refresh latest instrument file from Zerodha and merge into archive."""
    try:
        result = await asyncio.to_thread(instrument_repository.update_mapper_from_zerodha)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=422, detail=f"Instrument mapper update failed: {exc}") from exc
    return result


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
    if datetime.strptime(request.from_date, "%Y-%m-%d") > datetime.strptime(request.to_date, "%Y-%m-%d"):
        raise HTTPException(status_code=422, detail="from_date must be <= to_date")

    job_id = str(uuid.uuid4())
    db = get_db()
    now_iso = now_ist_iso()
    await db.historical_ingest_jobs.insert_one(
        {
            "job_id": job_id,
            "status": "PENDING",
            "phase": "PENDING",
            "request": request.model_dump(),
            "rows": 0,
            "rows_fetched": 0,
            "saved_rows": 0,
            "inserted": 0,
            "modified": 0,
            "current_chunk": 0,
            "total_chunks": 0,
            "requested_from_date": request.from_date,
            "requested_to_date": request.to_date,
            "first_saved_trading_date": None,
            "last_saved_trading_date": None,
            "error_message": None,
            "started_at": None,
            "completed_at": None,
            "updated_at": now_iso,
        }
    )
    background_tasks.add_task(_run_ingest_job, job_id, request.model_dump())
    return {"job_id": job_id, "status": "PENDING"}


@router.get("/historical/ingest/{job_id}")
async def get_historical_ingest_job(job_id: str):
    db = get_db()
    doc = await db.historical_ingest_jobs.find_one({"job_id": job_id})
    if doc is None:
        raise HTTPException(status_code=404, detail="Historical ingest job not found")
    doc = await _maybe_mark_stale_job(doc)
    doc.pop("_id", None)
    return doc


async def _run_ingest_job(job_id: str, payload: dict[str, Any]) -> None:
    db = get_db()
    started_iso = now_ist_iso()
    await db.historical_ingest_jobs.update_one(
        {"job_id": job_id},
        {"$set": {"status": "RUNNING", "phase": "FETCHING", "started_at": started_iso, "updated_at": started_iso}},
    )
    try:
        from backend.database.sync_connection import get_sync_db

        sync_db = get_sync_db()

        def _progress_callback(progress: dict[str, Any]) -> None:
            sync_db.historical_ingest_jobs.update_one(
                {"job_id": job_id},
                {"$set": {
                    "status": "RUNNING",
                    "phase": str(progress.get("phase", "RUNNING")),
                    "current_chunk": int(progress.get("current_chunk", 0)),
                    "total_chunks": int(progress.get("total_chunks", 0)),
                    "rows": int(progress.get("rows", 0)),
                    "rows_fetched": int(progress.get("rows_fetched", progress.get("rows", 0))),
                    "saved_rows": int(progress.get("saved_rows", 0)),
                    "inserted": int(progress.get("inserted", 0)),
                    "modified": int(progress.get("modified", 0)),
                    "updated_at": now_ist_iso(),
                }},
            )

        result = await asyncio.to_thread(
            ingestion_manager.ingest,
            instrument_token=int(payload["instrument_token"]),
            tradingsymbol=str(payload["tradingsymbol"]),
            from_date=str(payload["from_date"]),
            to_date=str(payload["to_date"]),
            interval=str(payload["interval"]),
            progress_callback=_progress_callback,
        )

        raw_status = str(result.get("status", "ok")).lower()
        status = "NO_DATA" if raw_status == "no_data" else "COMPLETED"
        completed_iso = now_ist_iso()
        await db.historical_ingest_jobs.update_one(
            {"job_id": job_id},
            {"$set": {
                "status": status,
                "phase": status,
                "rows": int(result.get("rows", 0)),
                "rows_fetched": int(result.get("rows_fetched", result.get("rows", 0))),
                "saved_rows": int(result.get("saved_rows", 0)),
                "inserted": int(result.get("inserted", 0)),
                "modified": int(result.get("modified", 0)),
                "requested_from_date": result.get("requested_from_date", payload.get("from_date")),
                "requested_to_date": result.get("requested_to_date", payload.get("to_date")),
                "first_saved_trading_date": result.get("first_saved_trading_date"),
                "last_saved_trading_date": result.get("last_saved_trading_date"),
                "current_chunk": int(result.get("current_chunk", 0)),
                "total_chunks": int(result.get("total_chunks", 0)),
                "error_message": None,
                "completed_at": completed_iso,
                "updated_at": completed_iso,
            }},
        )
    except Exception as exc:  # noqa: BLE001
        failed_iso = now_ist_iso()
        await db.historical_ingest_jobs.update_one(
            {"job_id": job_id},
            {"$set": {
                "status": "FAILED",
                "phase": "FAILED",
                "error_message": _map_ingest_error(exc),
                "completed_at": failed_iso,
                "updated_at": failed_iso,
            }},
        )
