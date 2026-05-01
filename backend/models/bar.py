"""Pydantic v2 models for OHLCV bar data."""
from __future__ import annotations
from datetime import datetime
from pydantic import BaseModel


class OHLCVBar(BaseModel):
    timestamp: datetime
    trading_date: str
    timeframe: str
    instrument_type: str
    instrument_token: int
    tradingsymbol: str = ""
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0
    data_source: str = "live"
    strike: float | None = None
    expiry: str | None = None
    option_type: str | None = None
    oi: float | None = None


class OHLCVBarCreate(BaseModel):
    timestamp: datetime
    trading_date: str
    timeframe: str = "1min"
    instrument_type: str = "equity"
    instrument_token: int = 0
    tradingsymbol: str = ""
    open: float = 0.0
    high: float = 0.0
    low: float = 0.0
    close: float = 0.0
    volume: float = 0.0
    data_source: str = "live"
    strike: float | None = None
    expiry: str | None = None
    option_type: str | None = None
    oi: float | None = None


class BarResponse(BaseModel):
    time: int  # UNIX seconds for TradingView (E-09)
    open: float
    high: float
    low: float
    close: float
    volume: float
    sma5: float | None = None
    sma20: float | None = None
    sma50: float | None = None
    vwap: float | None = None
