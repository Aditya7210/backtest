from __future__ import annotations

from datetime import time
import logging

import pandas as pd
from pandas.api.types import (
    is_numeric_dtype,
    is_object_dtype,
    is_string_dtype,
)


_REQUIRED_COLUMNS = ["Open", "High", "Low", "Close", "Volume"]
_REQUIRED_PRICE_COLUMNS = ["Open", "High", "Low", "Close"]
_IST_TIMEZONE = "Asia/Kolkata"
_MARKET_OPEN_TIME = time(9, 15)
_MARKET_CLOSE_TIME = time(15, 30)
_LOGGER = logging.getLogger(__name__)


def _to_ist_timestamp(
    value: object,
    *,
    naive_source_timezone: str = _IST_TIMEZONE,
) -> pd.Timestamp | None:
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        return None

    ts = pd.Timestamp(parsed)
    if ts.tzinfo is None:
        ts = ts.tz_localize(naive_source_timezone)
    else:
        ts = ts.tz_convert(_IST_TIMEZONE)

    converted = ts.tz_convert(_IST_TIMEZONE)
    if converted.tzinfo is None:
        return None
    return converted


def should_normalize(df: pd.DataFrame) -> bool:
    if not isinstance(df, pd.DataFrame) or df.empty:
        return True

    if not set(_REQUIRED_PRICE_COLUMNS).issubset(set(df.columns)):
        return True

    if not isinstance(df.index, pd.DatetimeIndex):
        return True

    if df.index.tz is not None and _timezone_name(df.index.tz) != _IST_TIMEZONE:
        return True

    if df[_REQUIRED_PRICE_COLUMNS].isna().any().any():
        return True

    if df.index.duplicated().any():
        return True

    if _should_filter_market_hours(df.index):
        if not _are_all_times_within_market_hours(df.index):
            return True

    return False


def normalize(
    df: pd.DataFrame,
    *,
    enforce_market_hours: bool = True,
) -> pd.DataFrame:
    if not isinstance(df, pd.DataFrame):
        raise ValueError("Input must be a pandas DataFrame")
    if df.empty:
        raise ValueError("Input DataFrame is empty")

    working_df = df.copy()
    before_rows = int(len(working_df))
    _LOGGER.info("Normalization start: input rows=%d", before_rows)
    working_df = _rename_columns(working_df)
    working_df = _ensure_datetime_index(working_df)
    working_df = _ensure_required_price_columns(working_df)
    if "Volume" not in working_df.columns:
        working_df["Volume"] = 0

    for column in _REQUIRED_COLUMNS:
        working_df[column] = _to_numeric_safely(working_df[column])

    before_nan_drop = int(len(working_df))
    working_df = working_df.dropna(subset=_REQUIRED_PRICE_COLUMNS)
    after_nan_drop = int(len(working_df))
    _LOGGER.info(
        "Dropped %d rows due to NaN",
        max(0, before_nan_drop - after_nan_drop),
    )

    working_df["Volume"] = working_df["Volume"].fillna(0)
    working_df = working_df.sort_index()
    before_dedup = int(len(working_df))
    working_df = working_df[~working_df.index.duplicated(keep="first")]
    after_dedup = int(len(working_df))
    _LOGGER.info(
        "Dropped %d duplicate rows",
        max(0, before_dedup - after_dedup),
    )

    before_market_filter = int(len(working_df))
    working_df = _apply_market_hour_filter(
        working_df,
        enforce_market_hours=enforce_market_hours,
    )
    after_market_filter = int(len(working_df))
    _LOGGER.info(
        "Filtered %d rows outside market hours",
        max(0, before_market_filter - after_market_filter),
    )
    _assert_market_hours(
        working_df.index,
        enforce_market_hours=enforce_market_hours,
    )

    if working_df.empty:
        raise ValueError("No valid OHLCV rows after normalization")

    _LOGGER.info("Normalization complete: output rows=%d", int(len(working_df)))

    return working_df[_REQUIRED_COLUMNS]


def prepare_ohlcv_for_plot(
    df: pd.DataFrame,
    *,
    enforce_market_hours: bool = True,
) -> pd.DataFrame:
    """
    Normalize price data into plotting-ready OHLCV with stable datetime index.
    """
    normalized = normalize(df, enforce_market_hours=enforce_market_hours)
    normalized.index = pd.to_datetime(normalized.index, errors="coerce")
    normalized = normalized[~normalized.index.isna()]
    normalized = normalized.sort_index()
    normalized = normalized[~normalized.index.duplicated(keep="first")]
    if normalized.empty:
        raise ValueError("No valid rows available for plotting after datetime cleanup")
    return normalized


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

    working_df.index = _to_ist_index(working_df.index)

    working_df.index = pd.to_datetime(working_df.index, errors="coerce")
    working_df = working_df[~working_df.index.isna()]
    working_df = working_df.sort_index()
    working_df = working_df[~working_df.index.duplicated(keep="first")]
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
    if is_numeric_dtype(series):
        return pd.to_numeric(series, errors="coerce")

    if is_object_dtype(series) or is_string_dtype(series):
        def _clean_value(value: object) -> object:
            if value is None or pd.isna(value):
                return pd.NA
            if isinstance(value, str):
                cleaned = value.replace(",", "").strip()
                if cleaned.lower() in {"", "none", "nan", "null"}:
                    return pd.NA
                return cleaned
            return value

        cleaned = series.map(_clean_value)
        return pd.to_numeric(cleaned, errors="coerce")

    return pd.to_numeric(series, errors="coerce")


def _apply_market_hour_filter(
    df: pd.DataFrame,
    *,
    enforce_market_hours: bool,
) -> pd.DataFrame:
    if not isinstance(df.index, pd.DatetimeIndex) or df.empty:
        return df
    if not enforce_market_hours:
        _LOGGER.info("market hour filter skipped")
        return df
    if not _should_filter_market_hours(df.index):
        return df
    filtered = df.between_time(
        _MARKET_OPEN_TIME.strftime("%H:%M"),
        _MARKET_CLOSE_TIME.strftime("%H:%M"),
    )
    return filtered


def _assert_market_hours(
    index: pd.DatetimeIndex,
    *,
    enforce_market_hours: bool,
) -> None:
    if not isinstance(index, pd.DatetimeIndex) or index.empty:
        return
    if not enforce_market_hours:
        return
    if not _should_filter_market_hours(index):
        return
    if not _are_all_times_within_market_hours(index):
        raise ValueError("Detected timestamps outside market hours (09:15 to 15:30 IST)")


def _are_all_times_within_market_hours(index: pd.DatetimeIndex) -> bool:
    if not isinstance(index, pd.DatetimeIndex) or index.empty:
        return True
    time_series = pd.Series(index.time)
    return bool(
        ((time_series >= _MARKET_OPEN_TIME) & (time_series <= _MARKET_CLOSE_TIME)).all()
    )


def _should_filter_market_hours(index: pd.DatetimeIndex) -> bool:
    if not isinstance(index, pd.DatetimeIndex) or index.empty:
        return False

    unique_times = {
        (ts.hour, ts.minute, ts.second, ts.microsecond)
        for ts in index
    }
    if len(unique_times) == 1:
        only_time = next(iter(unique_times))
        if only_time in {(0, 0, 0, 0), (5, 30, 0, 0)}:
            return False
    return True


def _timezone_name(tz: object) -> str:
    if tz is None:
        return ""
    key = getattr(tz, "key", None)
    if isinstance(key, str) and key:
        return key
    zone = getattr(tz, "zone", None)
    if isinstance(zone, str) and zone:
        return zone
    return str(tz)


def _to_ist_index(index: pd.Index) -> pd.DatetimeIndex:
    parsed_values: list[pd.Timestamp] = []
    timezone_flags: list[bool] = []

    for raw_value in list(index):
        parsed = pd.to_datetime(raw_value, errors="coerce")
        if pd.isna(parsed):
            continue
        timezone_flags.append(pd.Timestamp(parsed).tzinfo is not None)
        converted = _to_ist_timestamp(raw_value, naive_source_timezone=_IST_TIMEZONE)
        if converted is not None:
            parsed_values.append(converted)

    if not parsed_values:
        return pd.DatetimeIndex([], tz=_IST_TIMEZONE)

    has_aware = any(timezone_flags)
    has_naive = any(not item for item in timezone_flags)
    if has_aware and has_naive:
        raise ValueError("Mixed timezone data detected in datetime index")

    converted = pd.DatetimeIndex(parsed_values)
    if has_aware:
        _LOGGER.info("Timezone detected: aware. Converted timestamps to IST.")
    else:
        _LOGGER.info("Timezone detected: naive. Assuming timestamps are already IST.")

    if converted.tz is None:
        raise ValueError("Datetime index timezone normalization failed")
    if _timezone_name(converted.tz) != _IST_TIMEZONE:
        raise ValueError("Datetime index timezone is inconsistent after normalization")
    return converted


__all__ = ["normalize", "prepare_ohlcv_for_plot", "should_normalize"]
