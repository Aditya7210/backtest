"""Indicator metadata and computation routes (pandas-ta backed)."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.database.repositories import bar_repository
from backend.indicators import pandas_ta_service

router = APIRouter(tags=["indicators"])


class IndicatorSpec(BaseModel):
    name: str
    params: dict[str, Any] = Field(default_factory=dict)


class IndicatorComputeRequest(BaseModel):
    instrument_token: int
    timeframe: str
    date_from: str | None = None
    date_to: str | None = None
    trading_date: str | None = None
    limit: int | None = Field(default=None, ge=50, le=10000)
    indicators: list[IndicatorSpec]


@router.get("/indicators")
async def get_indicators():
    try:
        metadata = pandas_ta_service.discover_indicator_metadata()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Failed to discover indicators: {exc}") from exc

    payload = []
    for item in metadata:
        payload.append({
            "name": item.name,
            "label": item.label,
            "category": item.category,
            "pane": item.pane,
            "params": item.params,
            "presets": item.presets,
        })
    return {"indicators": payload}


@router.post("/indicators/compute")
async def compute_indicators(request: IndicatorComputeRequest):
    bars = await bar_repository.get_bars(
        token=request.instrument_token,
        timeframe=request.timeframe,
        date_from=request.date_from,
        date_to=request.date_to,
        trading_date=request.trading_date,
    )
    if request.limit and len(bars) > request.limit:
        bars = bars[-request.limit :]
    if not bars:
        return {"series": [], "warnings": ["No bars found for selected data range."]}

    try:
        series, warnings = pandas_ta_service.compute_indicators(
            bars=bars,
            indicators=[item.model_dump() for item in request.indicators],
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Indicator compute failed: {exc}") from exc

    return {"series": series, "warnings": warnings}
