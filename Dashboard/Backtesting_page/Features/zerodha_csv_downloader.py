from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd


_SAVE_DIR = (
    Path(__file__).resolve().parents[3]
    / "Data"
    / "testing_data"
    / "Data_files"
    / "Zerodha_data"
)


def download_and_save_data(
    df: pd.DataFrame,
    symbol: str,
    start_date: datetime,
    end_date: datetime,
    interval: str,
    overwrite: bool = False,
) -> dict[str, Any]:
    """
    Save Zerodha historical data to CSV using:
    SYMBOL_INTERVAL_STARTDATE_ENDDATE.csv
    """

    if not isinstance(df, pd.DataFrame):
        raise ValueError("df must be a pandas DataFrame")
    if df.empty:
        raise ValueError("Cannot save empty DataFrame")

    normalized_symbol = _normalize_symbol(symbol)
    normalized_start = _normalize_datetime(start_date, "start_date")
    normalized_end = _normalize_datetime(end_date, "end_date")
    normalized_interval = _normalize_interval(interval)

    if normalized_start > normalized_end:
        raise ValueError("start_date must be earlier than or equal to end_date")

    normalized_df = _normalize_dataframe(df)

    filename = (
        f"{normalized_symbol}_{normalized_interval}_{normalized_start.strftime('%Y-%m-%d')}"
        f"_{normalized_end.strftime('%Y-%m-%d')}.csv"
    )
    file_path = _SAVE_DIR / filename

    if file_path.exists() and not overwrite:
        return {
            "status": "exists",
            "message": "File already exists",
            "file_path": str(file_path),
        }

    _SAVE_DIR.mkdir(parents=True, exist_ok=True)
    normalized_df.to_csv(file_path, index=True)

    return {
        "status": "saved",
        "message": "Saved successfully",
        "file_path": str(file_path),
    }


def _normalize_symbol(symbol: str) -> str:
    normalized = (symbol or "").strip().upper()
    if not normalized:
        raise ValueError("symbol cannot be empty")

    safe = "".join(ch for ch in normalized if ch.isalnum() or ch in {"_", "-"})
    if not safe:
        raise ValueError("symbol contains no valid filename characters")
    return safe


def _normalize_datetime(value: datetime, field_name: str) -> datetime:
    if not isinstance(value, datetime):
        raise ValueError(f"{field_name} must be a datetime instance")
    return value


def _normalize_interval(interval: str) -> str:
    normalized = (interval or "").strip().lower()
    if not normalized:
        raise ValueError("interval cannot be empty")

    safe = "".join(ch for ch in normalized if ch.isalnum() or ch in {"_", "-"})
    if not safe:
        raise ValueError("interval contains no valid filename characters")
    return safe


def _normalize_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    working_df = df.copy()

    if not isinstance(working_df.index, pd.DatetimeIndex):
        converted_index = pd.to_datetime(working_df.index, errors="coerce")
        if converted_index.isna().any():
            raise ValueError("DataFrame index must be datetime-like")
        working_df.index = converted_index

    working_df = working_df.sort_index()
    working_df = working_df[~working_df.index.duplicated(keep="first")]
    working_df.index.name = "Date"
    return working_df


__all__ = ["download_and_save_data"]
