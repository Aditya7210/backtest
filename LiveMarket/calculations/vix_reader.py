from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from LiveMarket.time_utils import now_ist_iso


def read(vix_1min_csv: Path) -> dict[str, Any]:
    if not vix_1min_csv.is_file():
        return {
            "generated_at": now_ist_iso(),
            "vix": None,
            "vix_open": None,
        }
    df = pd.read_csv(vix_1min_csv)
    if df.empty:
        return {
            "generated_at": now_ist_iso(),
            "vix": None,
            "vix_open": None,
        }
    for column in ["open", "close"]:
        if column in df.columns:
            df[column] = pd.to_numeric(df[column], errors="coerce")
    df = df.dropna(subset=[column for column in ["open", "close"] if column in df.columns])
    if df.empty:
        return {
            "generated_at": now_ist_iso(),
            "vix": None,
            "vix_open": None,
        }
    latest = df.iloc[-1]
    first = df.iloc[0]
    return {
        "generated_at": now_ist_iso(),
        "vix": float(latest.get("close")) if latest.get("close") is not None else None,
        "vix_open": float(first.get("open")) if first.get("open") is not None else None,
    }


__all__ = ["read"]
