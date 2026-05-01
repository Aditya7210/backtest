"""Pydantic v2 models for instrument master data."""
from __future__ import annotations
from datetime import datetime
from pydantic import BaseModel


class Instrument(BaseModel):
    instrument_token: int
    tradingsymbol: str
    exchange: str = ""
    segment: str = ""
    instrument_type: str = ""
    strike: float | None = None
    expiry: str | None = None
    lot_size: int = 1
    tick_size: float = 0.05
    name: str = ""


class InstrumentSearch(BaseModel):
    q: str = ""
    exchange: str = ""
    instrument_type: str = ""
    limit: int = 50
