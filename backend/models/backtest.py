"""Pydantic v2 models for backtest requests and results (E-06: no data_file field)."""
from __future__ import annotations
from typing import Any
from pydantic import BaseModel


class DataSelection(BaseModel):
    instrument_token: int
    tradingsymbol: str = ""
    timeframe: str = "5min"
    date_from: str
    date_to: str


class BacktestRequest(BaseModel):
    strategy_name: str
    strategy_id: str | None = None
    strategy_class_name: str | None = None
    instrument_token: int
    timeframe: str = "5min"
    date_from: str
    date_to: str
    initial_capital: float = 100000
    commission: float = 0.0003
    slippage: float = 0.0
    lot_size: int = 1
    position_size: int = 1
    max_positions: int = 1
    execution_mode: str = "market"
    max_retries: int = 0
    task_timeout_seconds: int = 300
    enforce_market_hours: bool = True


class BacktestResult(BaseModel):
    task_id: str
    strategy_name: str
    symbol: str = ""
    data_selection: DataSelection | None = None
    config: dict[str, Any] = {}
    status: str = "PENDING"
    started_at: str | None = None
    completed_at: str | None = None
    final_value: float | None = None
    metrics: dict[str, Any] = {}
    trades: list[dict[str, Any]] = []
    order_events: list[dict[str, Any]] = []
    integrity: dict[str, Any] = {}
    result_schema_version: int = 2
    data_gaps: list[str] | None = None  # E-18: Optional
    error_message: str | None = None


class Trade(BaseModel):
    entry_date: str
    exit_date: str
    direction: str
    entry_price: float
    exit_price: float
    pnl: float
    size: int = 0
