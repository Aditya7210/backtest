"""Historical data REST routes: catalog, mapper search, ingestion jobs."""
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timedelta
import re
import time
from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from pydantic import BaseModel, Field, field_validator

from backend.config import settings
from backend.database.connection import get_db
from backend.database.repositories import bar_repository, instrument_repository
from backend.historical import ingestion_manager
from backend.utils.time_utils import now_ist, now_ist_iso

router = APIRouter(tags=["historical-data"])

_ALLOWED_INTERVALS = {"minute", "3minute", "5minute", "10minute", "15minute", "30minute", "60minute", "day"}
_STALE_JOB_TIMEOUT_MINUTES = 20
_DATE_ONLY_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_MIN_SUPPORTED_YEAR = 2000
_JOB_LOG_CAP = 500
_TERMINAL_JOB_STATUSES = {"COMPLETED", "FAILED", "NO_DATA", "CANCELLED"}
_INTERVAL_TO_TIMEFRAME = {
    "minute": "1min",
    "3minute": "3min",
    "5minute": "5min",
    "10minute": "10min",
    "15minute": "15min",
    "30minute": "30min",
    "60minute": "60min",
    "day": "1day",
}


class HistoricalIngestRequest(BaseModel):
    instrument_token: int
    tradingsymbol: str
    from_date: str
    to_date: str
    interval: str = Field(default="day")
    mode: str = Field(default="skip_existing")

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

    @field_validator("mode")
    @classmethod
    def _validate_mode(cls, value: str) -> str:
        cleaned = value.strip().lower()
        if cleaned not in {"skip_existing", "overwrite", "append_only"}:
            raise ValueError("mode must be one of: skip_existing, overwrite, append_only")
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
    if status not in {"PENDING", "RUNNING", "CANCEL_REQUESTED"}:
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
    cleanup = await db.bars.delete_many({"ingest_job_id": doc["job_id"]})
    await db.historical_ingest_jobs.update_one(
        {"job_id": doc["job_id"]},
        {
            "$set": {
                "cleanup_started_at": now_iso,
                "cleanup_completed_at": now_ist_iso(),
            },
            "$push": {
                "log_lines": {
                    "$each": [f"[{now_iso}] Stale job cleanup removed {int(cleanup.deleted_count)} lineage rows."],
                    "$slice": -_JOB_LOG_CAP,
                }
            },
        },
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


@router.post("/historical/catalog/rebuild")
async def rebuild_historical_catalog():
    """Rebuild the materialized historical catalog cache from bars."""
    count = await bar_repository.rebuild_catalog_cache()
    return {"status": "ok", "entries": count}


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
    include_archive: bool = Query(default=False),
):
    """Search mapper CSV files. Default is latest-only; archive is opt-in for debug/history."""
    return instrument_repository.search_mapper_files(q.strip(), limit, include_archive=include_archive)


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

    request_payload = request.model_dump()
    timeframe = _INTERVAL_TO_TIMEFRAME.get(request.interval, request.interval)
    mode = str(request.mode or "skip_existing").lower()
    missing_spans: list[tuple[str, str]] = [(request.from_date, request.to_date)]
    existing_dates_count = 0

    if mode in {"skip_existing", "append_only"}:
        existing_dates = await bar_repository.get_existing_trading_dates(
            token=int(request.instrument_token),
            timeframe=timeframe,
            date_from=request.from_date,
            date_to=request.to_date,
        )
        existing_dates_count = len(existing_dates)
        missing_spans = bar_repository.compute_missing_date_spans(
            date_from=request.from_date,
            date_to=request.to_date,
            existing_trading_dates=existing_dates,
        )
        if mode == "append_only":
            # append_only only fetches right-side extension beyond last existing date.
            if existing_dates:
                last_existing = max(existing_dates)
                if request.to_date <= last_existing:
                    missing_spans = []
                else:
                    append_from = (datetime.strptime(last_existing, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
                    missing_spans = [(append_from, request.to_date)]

    request_payload["timeframe"] = timeframe
    request_payload["mode"] = mode
    request_payload["missing_spans"] = [{"from_date": a, "to_date": b} for a, b in missing_spans]
    request_payload["existing_dates_count"] = existing_dates_count

    job_id = str(uuid.uuid4())
    db = get_db()
    now_iso = now_ist_iso()

    if not missing_spans:
        await db.historical_ingest_jobs.insert_one(
            {
                "job_id": job_id,
                "status": "NO_DATA",
                "phase": "COMPLETED",
                "request": request_payload,
                "rows": 0,
                "rows_fetched": 0,
                "saved_rows": 0,
                "inserted": 0,
                "modified": 0,
                "skipped_existing_dates": existing_dates_count,
                "current_chunk": 0,
                "total_chunks": 0,
                "requested_from_date": request.from_date,
                "requested_to_date": request.to_date,
                "first_saved_trading_date": None,
                "last_saved_trading_date": None,
                "ingest_job_id": job_id,
                "cancel_requested_at": None,
                "cleanup_started_at": None,
                "cleanup_completed_at": None,
                "estimated_finish_at": None,
                "error_message": None,
                "performance": {
                    "fetch_seconds": 0.0,
                    "normalize_seconds": 0.0,
                    "write_seconds": 0.0,
                    "commit_seconds": 0.0,
                    "catalog_refresh_seconds": 0.0,
                    "rows_per_second": 0.0,
                    "chunks_per_second": 0.0,
                    "mode": mode,
                },
                "log_lines": [
                    f"[{now_iso}] Historical ingest request accepted.",
                    f"[{now_iso}] Skip-existing mode found no missing dates. Nothing to fetch.",
                ],
                "started_at": now_iso,
                "completed_at": now_iso,
                "updated_at": now_iso,
            }
        )
        return {"job_id": job_id, "status": "NO_DATA"}

    await db.historical_ingest_jobs.insert_one(
        {
            "job_id": job_id,
            "status": "PENDING",
            "phase": "PENDING",
            "request": request_payload,
            "rows": 0,
            "rows_fetched": 0,
            "saved_rows": 0,
            "inserted": 0,
            "modified": 0,
            "skipped_existing_dates": existing_dates_count,
            "current_chunk": 0,
            "total_chunks": 0,
            "requested_from_date": request.from_date,
            "requested_to_date": request.to_date,
            "first_saved_trading_date": None,
            "last_saved_trading_date": None,
            "ingest_job_id": job_id,
            "cancel_requested_at": None,
            "cleanup_started_at": None,
            "cleanup_completed_at": None,
            "estimated_finish_at": None,
            "error_message": None,
            "performance": {
                "fetch_seconds": 0.0,
                "normalize_seconds": 0.0,
                "write_seconds": 0.0,
                "commit_seconds": 0.0,
                "catalog_refresh_seconds": 0.0,
                "rows_per_second": 0.0,
                "chunks_per_second": 0.0,
                "mode": mode,
            },
            "log_lines": [
                f"[{now_iso}] Historical ingest request accepted.",
                f"[{now_iso}] mode={mode}, existing_dates={existing_dates_count}, missing_spans={len(missing_spans)}",
            ],
            "started_at": None,
            "completed_at": None,
            "updated_at": now_iso,
        }
    )
    background_tasks.add_task(_run_ingest_job, job_id, request_payload)
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


@router.post("/historical/ingest/{job_id}/cancel")
async def cancel_historical_ingest_job(job_id: str):
    db = get_db()
    doc = await db.historical_ingest_jobs.find_one({"job_id": job_id})
    if doc is None:
        raise HTTPException(status_code=404, detail="Historical ingest job not found")

    status = str(doc.get("status") or "").upper()
    if status in _TERMINAL_JOB_STATUSES:
        doc.pop("_id", None)
        return {"job_id": job_id, "status": status, "message": "Job already completed."}
    if status == "CANCEL_REQUESTED":
        doc.pop("_id", None)
        return {"job_id": job_id, "status": "CANCEL_REQUESTED", "message": "Cancellation already requested."}

    now_iso = now_ist_iso()
    result = await db.historical_ingest_jobs.update_one(
        {"job_id": job_id, "status": {"$in": ["PENDING", "RUNNING"]}},
        {
            "$set": {
                "status": "CANCEL_REQUESTED",
                "phase": "CANCEL_REQUESTED",
                "cancel_requested_at": now_iso,
                "updated_at": now_iso,
            },
            "$push": {"log_lines": {"$each": [f"[{now_iso}] Cancellation requested by user."], "$slice": -_JOB_LOG_CAP}},
        },
    )
    if result.matched_count == 0:
        latest = await db.historical_ingest_jobs.find_one({"job_id": job_id}, {"_id": 0, "status": 1})
        latest_status = str((latest or {}).get("status") or "UNKNOWN").upper()
        return {"job_id": job_id, "status": latest_status, "message": "Job state changed before cancellation could be applied."}
    return {"job_id": job_id, "status": "CANCEL_REQUESTED"}


async def _run_ingest_job(job_id: str, payload: dict[str, Any]) -> None:
    db = get_db()
    started_iso = now_ist_iso()
    started_wall = time.perf_counter()
    performance: dict[str, float] = {
        "fetch_seconds": 0.0,
        "normalize_seconds": 0.0,
        "write_seconds": 0.0,
        "commit_seconds": 0.0,
        "catalog_refresh_seconds": 0.0,
        "rows_per_second": 0.0,
        "chunks_per_second": 0.0,
    }
    await db.historical_ingest_jobs.update_one(
        {"job_id": job_id},
        {
            "$set": {
                "status": "RUNNING",
                "phase": "FETCHING",
                "started_at": started_iso,
                "updated_at": started_iso,
            },
            "$push": {"log_lines": {"$each": [f"[{started_iso}] Historical ingest started."], "$slice": -_JOB_LOG_CAP}},
        },
    )
    try:
        from backend.database.sync_connection import get_sync_db

        sync_db = get_sync_db()
        job_request = dict(payload or {})
        missing_spans = [
            (str(span.get("from_date")), str(span.get("to_date")))
            for span in (job_request.get("missing_spans") or [])
            if span and span.get("from_date") and span.get("to_date")
        ]
        if not missing_spans:
            missing_spans = [(str(job_request["from_date"]), str(job_request["to_date"]))]
        skipped_existing_dates = int(job_request.get("existing_dates_count", 0) or 0)

        def _sync_append_job_log(message: str) -> None:
            now_iso = now_ist_iso()
            sync_db.historical_ingest_jobs.update_one(
                {"job_id": job_id},
                {"$push": {"log_lines": {"$each": [f"[{now_iso}] {message}"], "$slice": -_JOB_LOG_CAP}}},
            )

        _sync_append_job_log(
            f"mode={job_request.get('mode', 'skip_existing')}, missing_spans={len(missing_spans)}, skipped_existing_dates={skipped_existing_dates}",
        )

        cancel_cache = {"last_check": 0.0, "value": False}

        def _is_cancel_requested() -> bool:
            now_tick = time.monotonic()
            if (now_tick - cancel_cache["last_check"]) < max(0.1, float(settings.HISTORICAL_CANCEL_CHECK_SECONDS)):
                return bool(cancel_cache["value"])
            cancel_cache["last_check"] = now_tick
            doc = sync_db.historical_ingest_jobs.find_one({"job_id": job_id}, {"_id": 0, "status": 1})
            status = str((doc or {}).get("status") or "").upper()
            cancel_cache["value"] = status == "CANCEL_REQUESTED"
            return bool(cancel_cache["value"])

        def _estimate_finish_iso(*, started_at: str | None, current_chunk: int, total_chunks: int) -> str | None:
            if not started_at or current_chunk <= 0 or total_chunks <= current_chunk:
                return None
            try:
                started_dt = datetime.fromisoformat(started_at)
            except ValueError:
                return None
            elapsed = (now_ist() - started_dt).total_seconds()
            if elapsed <= 0:
                return None
            avg_per_chunk = elapsed / float(current_chunk)
            remaining_chunks = max(0, total_chunks - current_chunk)
            eta_seconds = int(avg_per_chunk * remaining_chunks)
            return (now_ist() + timedelta(seconds=eta_seconds)).isoformat()

        progress_state = {"last_push_ts": 0.0, "last_signature": "", "started_at": started_iso}

        def _progress_callback(progress: dict[str, Any]) -> None:
            current_chunk = int(progress.get("current_chunk", 0))
            total_chunks = int(progress.get("total_chunks", 0))
            estimated_finish_at = _estimate_finish_iso(
                started_at=str(progress_state.get("started_at") or started_iso),
                current_chunk=current_chunk,
                total_chunks=total_chunks,
            )
            now_tick = time.monotonic()
            signature = "|".join([
                str(progress.get("phase", "RUNNING")),
                str(current_chunk),
                str(total_chunks),
                str(int(progress.get("rows", 0))),
                str(int(progress.get("saved_rows", 0))),
                str(int(progress.get("inserted", 0))),
                str(int(progress.get("modified", 0))),
            ])
            if (
                signature == progress_state["last_signature"]
                and (now_tick - progress_state["last_push_ts"]) < float(settings.HISTORICAL_PROGRESS_UPDATE_SECONDS)
            ):
                return
            progress_state["last_signature"] = signature
            progress_state["last_push_ts"] = now_tick
            sync_db.historical_ingest_jobs.update_one(
                {"job_id": job_id},
                {"$set": {
                    "status": "RUNNING",
                    "phase": str(progress.get("phase", "RUNNING")),
                    "current_chunk": current_chunk,
                    "total_chunks": total_chunks,
                    "rows": int(progress.get("rows", 0)),
                    "rows_fetched": int(progress.get("rows_fetched", progress.get("rows", 0))),
                    "saved_rows": int(progress.get("saved_rows", 0)),
                    "inserted": int(progress.get("inserted", 0)),
                    "modified": int(progress.get("modified", 0)),
                    "performance.fetch_seconds": float(progress.get("fetch_seconds", 0.0)),
                    "performance.normalize_seconds": float(progress.get("normalize_seconds", 0.0)),
                    "performance.write_seconds": float(progress.get("write_seconds", 0.0)),
                    "performance.rows_per_second": float(progress.get("rows_per_second", 0.0)),
                    "performance.chunks_per_second": float(progress.get("chunks_per_second", 0.0)),
                    "estimated_finish_at": estimated_finish_at,
                    "updated_at": now_ist_iso(),
                }},
            )

        aggregate: dict[str, Any] = {
            "rows": 0,
            "rows_fetched": 0,
            "saved_rows": 0,
            "inserted": 0,
            "modified": 0,
            "current_chunk": 0,
            "total_chunks": 0,
            "first_saved_trading_date": None,
            "last_saved_trading_date": None,
        }
        fetch_seconds_total = 0.0
        normalize_seconds_total = 0.0
        write_seconds_total = 0.0
        chunk_accumulator = 0

        for span_from, span_to in missing_spans:
            _sync_append_job_log(f"Fetching span {span_from} -> {span_to}")
            span_result = await asyncio.to_thread(
                ingestion_manager.ingest,
                instrument_token=int(job_request["instrument_token"]),
                tradingsymbol=str(job_request["tradingsymbol"]),
                from_date=span_from,
                to_date=span_to,
                interval=str(job_request["interval"]),
                progress_callback=_progress_callback,
                should_cancel=_is_cancel_requested,
                event_callback=_sync_append_job_log,
                job_id=job_id,
            )

            aggregate["rows"] += int(span_result.get("rows", 0))
            aggregate["rows_fetched"] += int(span_result.get("rows_fetched", span_result.get("rows", 0)))
            aggregate["saved_rows"] += int(span_result.get("saved_rows", 0))
            aggregate["inserted"] += int(span_result.get("inserted", 0))
            aggregate["modified"] += int(span_result.get("modified", 0))
            aggregate["current_chunk"] += int(span_result.get("current_chunk", 0))
            aggregate["total_chunks"] += int(span_result.get("total_chunks", 0))
            fetch_seconds_total += float(span_result.get("fetch_seconds", 0.0))
            normalize_seconds_total += float(span_result.get("normalize_seconds", 0.0))
            write_seconds_total += float(span_result.get("write_seconds", 0.0))
            chunk_accumulator += int(span_result.get("total_chunks", 0))

            span_first = span_result.get("first_saved_trading_date")
            span_last = span_result.get("last_saved_trading_date")
            if span_first and (aggregate["first_saved_trading_date"] is None or span_first < aggregate["first_saved_trading_date"]):
                aggregate["first_saved_trading_date"] = span_first
            if span_last and (aggregate["last_saved_trading_date"] is None or span_last > aggregate["last_saved_trading_date"]):
                aggregate["last_saved_trading_date"] = span_last

        status = "NO_DATA" if int(aggregate["rows_fetched"]) <= 0 else "COMPLETED"
        completed_iso = now_ist_iso()
        if status == "COMPLETED":
            committing_iso = now_ist_iso()
            await db.historical_ingest_jobs.update_one(
                {"job_id": job_id},
                {"$set": {"phase": "COMMITTING", "updated_at": committing_iso}},
            )
            commit_start = time.perf_counter()
            await db.bars.update_many(
                {"ingest_job_id": job_id},
                {"$set": {"ingest_status": "committed"}},
            )
            performance["commit_seconds"] = max(0.0, time.perf_counter() - commit_start)
            catalog_phase_iso = now_ist_iso()
            await db.historical_ingest_jobs.update_one(
                {"job_id": job_id},
                {"$set": {"phase": "CATALOG_REFRESH", "updated_at": catalog_phase_iso}},
            )
            catalog_start = time.perf_counter()
            await bar_repository.refresh_catalog_for_instrument(int(job_request["instrument_token"]))
            performance["catalog_refresh_seconds"] = max(0.0, time.perf_counter() - catalog_start)

        elapsed_total = max(0.001, time.perf_counter() - started_wall)
        performance["fetch_seconds"] = fetch_seconds_total
        performance["normalize_seconds"] = normalize_seconds_total
        performance["write_seconds"] = write_seconds_total
        performance["rows_per_second"] = float(aggregate["saved_rows"]) / elapsed_total
        performance["chunks_per_second"] = float(chunk_accumulator) / elapsed_total if chunk_accumulator > 0 else 0.0

        await db.historical_ingest_jobs.update_one(
            {"job_id": job_id},
            {"$set": {
                "status": status,
                "phase": status,
                "rows": int(aggregate.get("rows", 0)),
                "rows_fetched": int(aggregate.get("rows_fetched", aggregate.get("rows", 0))),
                "saved_rows": int(aggregate.get("saved_rows", 0)),
                "inserted": int(aggregate.get("inserted", 0)),
                "modified": int(aggregate.get("modified", 0)),
                "requested_from_date": job_request.get("from_date"),
                "requested_to_date": job_request.get("to_date"),
                "first_saved_trading_date": aggregate.get("first_saved_trading_date"),
                "last_saved_trading_date": aggregate.get("last_saved_trading_date"),
                "current_chunk": int(aggregate.get("current_chunk", 0)),
                "total_chunks": int(aggregate.get("total_chunks", 0)),
                "skipped_existing_dates": skipped_existing_dates,
                "performance": performance,
                "estimated_finish_at": None,
                "error_message": None,
                "completed_at": completed_iso,
                "ingest_job_id": job_id,
                "updated_at": completed_iso,
            },
            "$push": {
                "log_lines": {
                    "$each": [f"[{completed_iso}] Historical ingest finished with status={status}."],
                    "$slice": -_JOB_LOG_CAP,
                }
            }},
        )
    except ingestion_manager.IngestCancelled as exc:
        cancelled_iso = now_ist_iso()
        cleanup_started_iso = now_ist_iso()
        await db.historical_ingest_jobs.update_one(
            {"job_id": job_id},
            {
                "$set": {
                    "phase": "CLEANUP",
                    "cleanup_started_at": cleanup_started_iso,
                    "updated_at": cleanup_started_iso,
                },
                "$push": {
                    "log_lines": {
                        "$each": [f"[{cleanup_started_iso}] Cancellation cleanup started."],
                        "$slice": -_JOB_LOG_CAP,
                    }
                },
            },
        )
        cleanup = await db.bars.delete_many({"ingest_job_id": job_id})
        cleanup_completed_iso = now_ist_iso()
        stats = dict(exc.stats or {})
        elapsed_total = max(0.001, time.perf_counter() - started_wall)
        performance["fetch_seconds"] = float(stats.get("fetch_seconds", performance.get("fetch_seconds", 0.0)))
        performance["normalize_seconds"] = float(stats.get("normalize_seconds", performance.get("normalize_seconds", 0.0)))
        performance["write_seconds"] = float(stats.get("write_seconds", performance.get("write_seconds", 0.0)))
        performance["rows_per_second"] = float(stats.get("saved_rows", 0)) / elapsed_total
        performance["chunks_per_second"] = float(stats.get("total_chunks", 0)) / elapsed_total if int(stats.get("total_chunks", 0)) > 0 else 0.0
        await db.historical_ingest_jobs.update_one(
            {"job_id": job_id},
            {
                "$set": {
                    "status": "CANCELLED",
                    "phase": "CANCELLED",
                    "rows": int(stats.get("rows", 0)),
                    "rows_fetched": int(stats.get("rows_fetched", stats.get("rows", 0))),
                    "saved_rows": int(stats.get("saved_rows", 0)),
                    "inserted": int(stats.get("inserted", 0)),
                    "modified": int(stats.get("modified", 0)),
                    "current_chunk": int(stats.get("current_chunk", 0)),
                    "total_chunks": int(stats.get("total_chunks", 0)),
                    "first_saved_trading_date": stats.get("first_saved_trading_date"),
                    "last_saved_trading_date": stats.get("last_saved_trading_date"),
                    "cleanup_completed_at": cleanup_completed_iso,
                    "completed_at": cancelled_iso,
                    "performance": performance,
                    "estimated_finish_at": None,
                    "error_message": "Historical ingest cancelled by user.",
                    "updated_at": cancelled_iso,
                },
                "$push": {
                    "log_lines": {
                        "$each": [
                            f"[{cleanup_completed_iso}] Cleanup completed. Removed {int(cleanup.deleted_count)} bar rows for job lineage.",
                            f"[{cancelled_iso}] Job marked CANCELLED.",
                        ],
                        "$slice": -_JOB_LOG_CAP,
                    }
                },
            },
        )
    except Exception as exc:  # noqa: BLE001
        cleanup_started_iso = now_ist_iso()
        await db.historical_ingest_jobs.update_one(
            {"job_id": job_id},
            {
                "$set": {
                    "phase": "CLEANUP",
                    "cleanup_started_at": cleanup_started_iso,
                    "updated_at": cleanup_started_iso,
                },
                "$push": {
                    "log_lines": {
                        "$each": [f"[{cleanup_started_iso}] Failure cleanup started."],
                        "$slice": -_JOB_LOG_CAP,
                    }
                },
            },
        )
        cleanup = await db.bars.delete_many({"ingest_job_id": job_id})
        cleanup_completed_iso = now_ist_iso()
        failed_iso = now_ist_iso()
        await db.historical_ingest_jobs.update_one(
            {"job_id": job_id},
            {"$set": {
                "status": "FAILED",
                "phase": "FAILED",
                "error_message": _map_ingest_error(exc),
                "cleanup_completed_at": cleanup_completed_iso,
                "completed_at": failed_iso,
                "performance": performance,
                "estimated_finish_at": None,
                "updated_at": failed_iso,
            },
            "$push": {
                "log_lines": {
                    "$each": [
                        f"[{cleanup_completed_iso}] Failure cleanup completed. Removed {int(cleanup.deleted_count)} bar rows for job lineage.",
                        f"[{failed_iso}] Historical ingest failed: {_map_ingest_error(exc)}",
                    ],
                    "$slice": -_JOB_LOG_CAP,
                }
            }},
        )
