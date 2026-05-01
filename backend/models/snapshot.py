"""Pydantic v2 models for snapshot data."""
from __future__ import annotations
from typing import Any
from pydantic import BaseModel


class SnapshotBase(BaseModel):
    snapshot_type: str
    generated_at: str
    trading_date: str
    data: dict[str, Any]


class SnapshotCreate(BaseModel):
    snapshot_type: str
    trading_date: str
    data: dict[str, Any]
