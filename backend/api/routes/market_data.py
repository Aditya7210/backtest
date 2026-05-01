"""Market data REST routes — live snapshots (E-09: UNIX timestamps)."""
from __future__ import annotations

from fastapi import APIRouter, Query

from backend.database.repositories import bar_repository, snapshot_repository

router = APIRouter(tags=["market-data"])


@router.get("/market/bars/{instrument_token}")
async def get_bars(
    instrument_token: int,
    timeframe: str = Query(default="1min"),
    trading_date: str | None = Query(default=None),
):
    """Fetch bars for a specific instrument token and timeframe."""
    bars = await bar_repository.get_bars(
        token=instrument_token,
        timeframe=timeframe,
        trading_date=trading_date,
    )
    # Convert to TradingView format (E-09: UNIX seconds, sorted)
    result = []
    for bar in bars:
        bar.pop("_id", None)
        ts = bar.get("timestamp")
        if ts:
            import calendar
            bar["time"] = int(calendar.timegm(ts.timetuple()))
        result.append(bar)
    return {"bars": result}


@router.get("/market/snapshot/{snapshot_type}")
async def get_snapshot(snapshot_type: str):
    """Fetch latest snapshot (vwap, ad, pcr, atm_oi, vix)."""
    doc = await snapshot_repository.get_latest_snapshot(snapshot_type)
    if doc is None:
        return {"snapshot_type": snapshot_type, "data": {}}
    doc.pop("_id", None)
    return doc


@router.get("/market/snapshots/all")
async def get_all_snapshots():
    """Fetch all latest snapshots in one call for dashboard."""
    snapshot_types = ["vwap", "ad", "pcr", "atm_oi", "vix"]
    result = {}
    for st in snapshot_types:
        doc = await snapshot_repository.get_latest_snapshot(st)
        if doc:
            doc.pop("_id", None)
            result[st] = doc
        else:
            result[st] = {}
    return result
