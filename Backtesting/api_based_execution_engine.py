from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from Backtesting.backtest_core import (
    build_failed_result,
    execute_backtest_dataframe,
    extract_runtime_config,
    validate_result,
    validate_strategy_class,
)
from Backtesting.data_normalizer import normalize, should_normalize
from Dashboard.Backtesting_page.Features import backtest_data_service, zerodha_historical_data


def run_task(
    task: dict[str, Any],
    base_config: dict[str, Any] | None = None,
    *,
    terminal: Any | None = None,
    task_id: str | None = None,
) -> dict[str, Any]:
    symbol = str(task.get("symbol") or "UNKNOWN").strip().upper() or "UNKNOWN"
    try:
        _log(terminal, "Validating API task payload", task_id=task_id, symbol=symbol)
        strategy_class = validate_strategy_class(task.get("strategy_class"))

        raw_data = _resolve_api_data(
            task,
            terminal=terminal,
            task_id=task_id,
            symbol=symbol,
        )
        if raw_data.empty:
            raise ValueError("API returned empty dataset")

        execution_df = _prepare_api_dataframe(
            raw_data,
            terminal=terminal,
            task_id=task_id,
            symbol=symbol,
        )
        if execution_df.empty:
            raise ValueError("API normalization produced empty dataset")

        config = extract_runtime_config(base_config, task.get("config"))
        _log(terminal, "Running Backtrader", task_id=task_id, symbol=symbol)
        raw_result = execute_backtest_dataframe(
            data_df=execution_df,
            symbol=symbol,
            strategy_class=strategy_class,
            config=config,
            terminal=terminal,
            task_id=task_id,
        )
        result = validate_result(raw_result, symbol=symbol)
        _log(
            terminal,
            f"Execution complete. Final value: {result.get('final_value')}",
            level="SUCCESS",
            task_id=task_id,
            symbol=symbol,
        )
        return result
    except Exception as exc:
        _log(
            terminal,
            f"Execution failed: {exc}",
            level="ERROR",
            task_id=task_id,
            symbol=symbol,
        )
        return validate_result(build_failed_result(symbol, str(exc)), symbol=symbol)


def _resolve_api_data(
    task: dict[str, Any],
    *,
    terminal: Any | None,
    task_id: str | None,
    symbol: str,
) -> pd.DataFrame:
    raw_task_data = task.get("data")
    if isinstance(raw_task_data, pd.DataFrame):
        _log(
            terminal,
            "Using in-task API dataframe",
            task_id=task_id,
            symbol=symbol,
        )
        return raw_task_data.copy()

    instrument_token = _parse_instrument_token(task.get("instrument_token"))
    interval = backtest_data_service.normalize_interval(str(task.get("interval", "15minute")))
    start_date = _parse_datetime(task.get("start_date"), "start_date")
    end_date = _parse_datetime(task.get("end_date"), "end_date")
    if start_date > end_date:
        raise ValueError("start_date must be earlier than end_date")

    continuous = bool(task.get("continuous", False))
    oi = bool(task.get("oi", False))
    instrument_type = str(task.get("instrument_type") or "").strip().upper()
    if instrument_type != "FUT":
        continuous = False

    cache_path = _build_cache_path(
        symbol=symbol,
        interval=interval,
        start_date=start_date,
        end_date=end_date,
    )
    cached_df = _load_cached_dataframe(cache_path, start_date=start_date, end_date=end_date)
    if cached_df is not None:
        _log(
            terminal,
            f"Loaded cached API data: {cache_path.name}",
            task_id=task_id,
            symbol=symbol,
        )
        return cached_df

    _log(
        terminal,
        "Fetching Zerodha API data",
        task_id=task_id,
        symbol=symbol,
    )
    api_key, access_token = backtest_data_service.validate_zerodha_session()
    service = zerodha_historical_data.ZerodhaHistoricalData(
        api_key=api_key,
        access_token=access_token,
    )
    fetched_df = service.fetch_data(
        instrument_token=instrument_token,
        from_date=start_date,
        to_date=end_date,
        interval=interval,
        continuous=continuous,
        oi=oi,
    )
    if not isinstance(fetched_df, pd.DataFrame) or fetched_df.empty:
        raise RuntimeError("No data returned for given inputs")

    _save_cached_dataframe(cache_path, fetched_df)
    _log(
        terminal,
        f"Cached API data to: {cache_path.name}",
        task_id=task_id,
        symbol=symbol,
    )
    return fetched_df


def _build_cache_path(
    *,
    symbol: str,
    interval: str,
    start_date: datetime,
    end_date: datetime,
) -> Path:
    cache_dir = backtest_data_service.resolve_zerodha_cache_dir()
    cache_dir.mkdir(parents=True, exist_ok=True)
    safe_symbol = "".join(ch for ch in symbol if ch.isalnum() or ch in {"_", "-"}).upper()
    safe_symbol = safe_symbol or "UNKNOWN"
    safe_interval = "".join(ch for ch in interval if ch.isalnum() or ch in {"_", "-"})
    safe_interval = safe_interval or "15minute"
    filename = (
        f"{safe_symbol}_{safe_interval}_"
        f"{start_date.date().isoformat()}_{end_date.date().isoformat()}.csv"
    )
    return cache_dir / filename


def _load_cached_dataframe(
    cache_path: Path,
    *,
    start_date: datetime,
    end_date: datetime,
) -> pd.DataFrame | None:
    if not cache_path.is_file():
        return None

    try:
        cached_df = pd.read_csv(cache_path, parse_dates=["Date"], index_col="Date")
    except Exception:
        return None

    if not _is_cache_usable(cached_df, start_date=start_date, end_date=end_date):
        return None

    return cached_df


def _save_cached_dataframe(cache_path: Path, df: pd.DataFrame) -> None:
    try:
        payload = df.copy()
        if not isinstance(payload.index, pd.DatetimeIndex):
            payload.index = pd.to_datetime(payload.index, errors="coerce")
        payload = payload.sort_index()
        payload = payload[~payload.index.duplicated(keep="first")]
        payload.index.name = "Date"
        payload.to_csv(cache_path, index=True)
    except Exception:
        # Caching failures should not fail execution flow.
        pass


def _is_cache_usable(
    df: pd.DataFrame,
    *,
    start_date: datetime,
    end_date: datetime,
) -> bool:
    if not isinstance(df, pd.DataFrame) or df.empty:
        return False
    required = {"Open", "High", "Low", "Close"}
    if not required.issubset(set(df.columns)):
        return False
    if not isinstance(df.index, pd.DatetimeIndex):
        return False
    if df[["Open", "High", "Low", "Close"]].isna().any().any():
        return False

    min_idx = df.index.min()
    max_idx = df.index.max()
    if min_idx is None or max_idx is None:
        return False

    normalized_min = pd.Timestamp(min_idx).to_pydatetime().replace(tzinfo=None)
    normalized_max = pd.Timestamp(max_idx).to_pydatetime().replace(tzinfo=None)
    requested_start = start_date.date()
    requested_end = end_date.date()
    return (
        normalized_min.date() <= requested_start
        and normalized_max.date() >= requested_end
    )


def _prepare_api_dataframe(
    raw_data: pd.DataFrame,
    *,
    terminal: Any | None,
    task_id: str | None,
    symbol: str,
) -> pd.DataFrame:
    if should_normalize(raw_data):
        _log(terminal, "Normalizing API data", task_id=task_id, symbol=symbol)
        working_df = normalize(raw_data)
    else:
        _log(
            terminal,
            "Using pre-normalized API data",
            task_id=task_id,
            symbol=symbol,
        )
        working_df = raw_data.copy()
        if "Volume" not in working_df.columns:
            working_df["Volume"] = 0
        for column in ["Open", "High", "Low", "Close", "Volume"]:
            working_df[column] = pd.to_numeric(working_df[column], errors="coerce")

        if working_df[["Open", "High", "Low", "Close"]].isna().any().any():
            _log(
                terminal,
                "Detected invalid OHLC values. Falling back to normalization.",
                level="WARNING",
                task_id=task_id,
                symbol=symbol,
            )
            working_df = normalize(raw_data)
        else:
            working_df["Volume"] = working_df["Volume"].fillna(0)

    if "Volume" not in working_df.columns:
        working_df["Volume"] = 0
    working_df["Volume"] = pd.to_numeric(working_df["Volume"], errors="coerce").fillna(0)
    working_df = working_df.sort_index()
    working_df = working_df[~working_df.index.duplicated(keep="first")]
    return working_df[["Open", "High", "Low", "Close", "Volume"]]


def _parse_instrument_token(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("instrument_token is required for API tasks") from exc


def _parse_datetime(value: Any, field_name: str) -> datetime:
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    try:
        parsed = pd.to_datetime(value, errors="raise")
    except Exception as exc:
        raise ValueError(f"{field_name} must be a valid datetime") from exc

    if isinstance(parsed, pd.Timestamp):
        return parsed.to_pydatetime().replace(tzinfo=None)
    raise ValueError(f"{field_name} must be a valid datetime")


def _log(
    terminal: Any | None,
    message: str,
    *,
    level: str = "INFO",
    task_id: str | None = None,
    symbol: str | None = None,
) -> None:
    if terminal is None or not hasattr(terminal, "log"):
        return
    try:
        terminal.log(message, level=level, task_id=task_id, symbol=symbol)
    except Exception:
        pass


__all__ = ["run_task"]
