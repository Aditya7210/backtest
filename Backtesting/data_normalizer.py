from __future__ import annotations

import pandas as pd
from pandas.api.types import is_object_dtype, is_string_dtype


_REQUIRED_COLUMNS = ["Open", "High", "Low", "Close", "Volume"]
_REQUIRED_PRICE_COLUMNS = ["Open", "High", "Low", "Close"]


def normalize(df: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(df, pd.DataFrame):
        raise ValueError("Input must be a pandas DataFrame")
    if df.empty:
        raise ValueError("Input DataFrame is empty")

    working_df = df.copy()
    working_df = _rename_columns(working_df)
    working_df = _ensure_datetime_index(working_df)
    working_df = _ensure_required_price_columns(working_df)
    if "Volume" not in working_df.columns:
        working_df["Volume"] = 0

    for column in _REQUIRED_COLUMNS:
        working_df[column] = _to_numeric_safely(working_df[column])

    working_df = working_df.dropna(subset=_REQUIRED_PRICE_COLUMNS)
    working_df["Volume"] = working_df["Volume"].fillna(0)
    working_df = working_df.sort_index()
    working_df = working_df[~working_df.index.duplicated(keep="first")]

    if working_df.empty:
        raise ValueError("No valid OHLCV rows after normalization")

    return working_df[_REQUIRED_COLUMNS]


def _rename_columns(df: pd.DataFrame) -> pd.DataFrame:
    rename_lookup = {
        "date": "Date",
        "datetime": "Date",
        "timestamp": "Date",
        "time": "Date",
        "open": "Open",
        "high": "High",
        "low": "Low",
        "close": "Close",
        "volume": "Volume",
    }

    renamed = {
        column: rename_lookup.get(str(column).strip().lower(), column)
        for column in df.columns
    }
    normalized = df.rename(columns=renamed)
    normalized = normalized.loc[:, ~normalized.columns.duplicated(keep="first")]
    return normalized


def _ensure_datetime_index(df: pd.DataFrame) -> pd.DataFrame:
    working_df = df.copy()

    if "Date" in working_df.columns:
        working_df["Date"] = pd.to_datetime(working_df["Date"], errors="coerce")
        working_df = working_df.dropna(subset=["Date"]).set_index("Date")
    else:
        converted_index = pd.to_datetime(working_df.index, errors="coerce")
        if isinstance(converted_index, pd.DatetimeIndex):
            working_df.index = converted_index
            working_df = working_df[~working_df.index.isna()]
        else:
            raise ValueError("Failed to parse datetime index")

    if not isinstance(working_df.index, pd.DatetimeIndex):
        raise ValueError("Normalized index must be DatetimeIndex")
    if working_df.index.tz is not None:
        working_df.index = working_df.index.tz_localize(None)
    if working_df.index.empty:
        raise ValueError("No valid datetime values found")

    working_df.index.name = "Date"
    return working_df


def _ensure_required_price_columns(df: pd.DataFrame) -> pd.DataFrame:
    missing = [column for column in _REQUIRED_PRICE_COLUMNS if column not in df.columns]
    if missing:
        raise ValueError(f"Missing required OHLC columns: {missing}")
    return df


def _to_numeric_safely(series: pd.Series) -> pd.Series:
    if is_object_dtype(series) or is_string_dtype(series):
        cleaned = (
            series
            .astype("string")
            .str.replace(",", "", regex=False)
            .str.strip()
            .replace({"": pd.NA, "None": pd.NA, "nan": pd.NA, "NaN": pd.NA})
        )
        return pd.to_numeric(cleaned, errors="coerce")
    return pd.to_numeric(series, errors="coerce")


__all__ = ["normalize"]
