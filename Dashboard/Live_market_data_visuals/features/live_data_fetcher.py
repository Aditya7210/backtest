from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

from LiveMarket import COLLECTOR_STATUS_PATH, DAILY_ROOT, SNAPSHOTS_ROOT


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def get_latest_day_dir() -> Path | None:
    status = _read_json(COLLECTOR_STATUS_PATH)
    trading_date = str(status.get("trading_date") or "").strip()
    if trading_date:
        candidate = DAILY_ROOT / trading_date
        if candidate.is_dir():
            return candidate

    if not DAILY_ROOT.is_dir():
        return None
    days = sorted([path for path in DAILY_ROOT.glob("*") if path.is_dir()])
    return days[-1] if days else None


@st.cache_data(ttl=2, show_spinner=False)
def read_live_csv(path_text: str) -> pd.DataFrame:
    path = Path(path_text)
    if not path.is_file():
        return pd.DataFrame()
    try:
        frame = pd.read_csv(path)
    except Exception:
        return pd.DataFrame()
    if "timestamp" in frame.columns:
        frame["timestamp"] = pd.to_datetime(frame["timestamp"], errors="coerce")
        frame = frame.dropna(subset=["timestamp"])
    return frame


@st.cache_data(ttl=2, show_spinner=False)
def read_snapshot(name: str) -> dict[str, Any]:
    return _read_json(SNAPSHOTS_ROOT / f"{name}_snapshot.json")


def load_market_context(timeframe: str = "1min") -> dict[str, Any]:
    day_dir = get_latest_day_dir()
    if day_dir is None:
        return {
            "day_dir": None,
            "equities": pd.DataFrame(),
            "options": pd.DataFrame(),
            "vix": pd.DataFrame(),
            "prev_close": {},
            "snapshots": {},
        }

    prev_close_payload = _read_json(day_dir / "prev_close.json")
    prev_close_data = prev_close_payload.get("data", {})
    if not isinstance(prev_close_data, dict):
        prev_close_data = {}

    return {
        "day_dir": day_dir,
        "equities": read_live_csv(str(day_dir / f"equities_{timeframe}.csv")),
        "options": read_live_csv(str(day_dir / f"options_{timeframe}.csv")),
        "vix": read_live_csv(str(day_dir / f"vix_{timeframe}.csv")),
        "prev_close": prev_close_data,
        "snapshots": {
            "ad": read_snapshot("ad"),
            "pcr": read_snapshot("pcr"),
            "atm_oi": read_snapshot("atm_oi"),
            "vix": read_snapshot("vix"),
            "vwap": read_snapshot("vwap"),
        },
    }


__all__ = ["get_latest_day_dir", "load_market_context", "read_live_csv", "read_snapshot"]
