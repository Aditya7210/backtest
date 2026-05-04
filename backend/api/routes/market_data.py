"""Market data REST routes — live snapshots (E-09: UNIX timestamps)."""
from __future__ import annotations

from fastapi import APIRouter, Query

from backend.database.repositories import bar_repository, snapshot_repository
from backend.database.repositories.live_market_view_repository import get_live_market_view
from backend.database.repositories.live_tick_repository import get_latest_tick
from backend.database.repositories.live_timeframe_repository import (
    SUPPORTED_LIVE_TIMEFRAMES,
    get_live_bars,
)

router = APIRouter(tags=["market-data"])


@router.get("/market/bars/{instrument_token}")
async def get_bars(
    instrument_token: int,
    timeframe: str = Query(default="1min"),
    trading_date: str | None = Query(default=None),
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
):
    """Fetch bars for a specific instrument token and timeframe."""
    normalized_tf = (timeframe or "1min").strip().lower()
    if normalized_tf in SUPPORTED_LIVE_TIMEFRAMES:
        bars, meta = await get_live_bars(
            token=instrument_token,
            timeframe=normalized_tf,
            trading_date=trading_date,
            date_from=date_from,
            date_to=date_to,
        )
    else:
        bars = await bar_repository.get_bars(
            token=instrument_token,
            timeframe=timeframe,
            trading_date=trading_date,
            date_from=date_from,
            date_to=date_to,
        )
        meta = {"derived": False, "source_timeframe": timeframe, "target_timeframe": timeframe}
    # Convert to TradingView format (E-09: UNIX seconds, sorted)
    result = []
    for bar in bars:
        bar.pop("_id", None)
        ts = bar.get("timestamp")
        if ts:
            bar["time"] = int(ts.timestamp())
        result.append(bar)
    return {"bars": result, "meta": meta}


@router.get("/market/tick/{instrument_token}")
async def get_latest_market_tick(instrument_token: int):
    """Fetch latest tick snapshot for a single token."""
    tick = await get_latest_tick(instrument_token)
    if tick is None:
        return {"instrument_token": instrument_token, "tick": None}
    ts = tick.get("timestamp")
    if ts:
        tick["time"] = int(ts.timestamp())
    return {"instrument_token": instrument_token, "tick": tick}


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
    snapshot_types = ["vwap", "prev_close", "ad", "pcr", "atm_oi", "vix"]
    result = {}
    for st in snapshot_types:
        doc = await snapshot_repository.get_latest_snapshot(st)
        if doc:
            doc.pop("_id", None)
            result[st] = doc
        else:
            result[st] = {}
    return result


@router.get("/live/instruments")
async def get_live_instruments(
    q: str = Query(default=""),
    instrument_type: str = Query(default="all"),
    universe: str = Query(default="all"),
    underlying: str = Query(default="all"),
    expiry: str = Query(default="all"),
    timeframe: str = Query(default="1min"),
    trading_date: str | None = Query(default=None),
    data_source: str = Query(default="all"),
    active_only: bool = Query(default=False),
    stale_threshold_seconds: int = Query(default=180, ge=30, le=3600),
    limit: int = Query(default=500, ge=1, le=5000),
):
    """Fetch searchable/filterable live instrument inventory."""
    payload = await bar_repository.get_live_instruments_inventory(
        search=q,
        instrument_type=instrument_type,
        universe=universe,
        underlying=underlying,
        expiry=expiry,
        timeframe=timeframe,
        trading_date=trading_date,
        data_source=data_source,
        active_only=active_only,
        stale_threshold_seconds=stale_threshold_seconds,
        limit=limit,
    )
    universe_health = await bar_repository.get_live_universe_health(
        trading_date=trading_date,
        timeframe=timeframe,
        stale_threshold_seconds=stale_threshold_seconds,
    )
    payload["universe_health"] = universe_health
    return payload


@router.get("/live/universe-health")
async def get_live_universe_health(
    trading_date: str | None = Query(default=None),
    timeframe: str = Query(default="1min"),
    stale_threshold_seconds: int = Query(default=180, ge=30, le=3600),
):
    """Fetch summary health for NIFTY/BANKNIFTY live universes."""
    return await bar_repository.get_live_universe_health(
        trading_date=trading_date,
        timeframe=timeframe,
        stale_threshold_seconds=stale_threshold_seconds,
    )


@router.get("/live/market-view")
async def get_market_view():
    """Fetch spot + futures layered market view for NIFTY/BANKNIFTY."""
    return await get_live_market_view()
