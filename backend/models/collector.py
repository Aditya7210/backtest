"""Pydantic v2 models for collector/calculator status."""
from __future__ import annotations
from pydantic import BaseModel


class CollectorState(BaseModel):
    status: str = "stopped"
    pid: int | None = None
    started_at: str | None = None
    trading_date: str | None = None
    tokens_subscribed: int = 0
    bars_written: int = 0
    last_tick_at: str | None = None
    last_error: str | None = None


class CalculatorState(BaseModel):
    status: str = "stopped"
    pid: int | None = None
    last_run_at: str | None = None
    last_error: str | None = None


class CollectorStatus(BaseModel):
    collector: CollectorState = CollectorState()
    calculator: CalculatorState = CalculatorState()
