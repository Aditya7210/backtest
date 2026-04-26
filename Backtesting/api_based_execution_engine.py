from __future__ import annotations

from datetime import datetime, timedelta
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
    _log(terminal, "Validating API task payload", task_id=task_id, symbol=symbol)
    try:
        strategy_class = validate_strategy_class(task.get("strategy_class"))
    except Exception as exc:
        return _build_failure_result(
            symbol,
            exc,
            error_type=_classify_validation_error(exc),
            stage="validation",
            terminal=terminal,
            task_id=task_id,
        )

    try:
        raw_data = _resolve_api_data(
            task,
            terminal=terminal,
            task_id=task_id,
            symbol=symbol,
        )
    except Exception as exc:
        return _build_failure_result(
            symbol,
            exc,
            error_type=_classify_fetch_error(exc),
            stage="data_fetch",
            terminal=terminal,
            task_id=task_id,
        )

    _log(terminal, "Validating API data", task_id=task_id, symbol=symbol)
    try:
        if not isinstance(raw_data, pd.DataFrame):
            raise ValueError("API fetch returned invalid dataset type")
        if raw_data.empty:
            raise ValueError("API returned empty dataset")
        raw_rows = int(len(raw_data))
        print(raw_rows)
        _log(
            terminal,
            f"Raw API dataframe rows resolved: {raw_rows}",
            task_id=task_id,
            symbol=symbol,
        )

        execution_df = _prepare_api_dataframe(
            raw_data,
            terminal=terminal,
            task_id=task_id,
            symbol=symbol,
            enforce_market_hours=bool(task.get("enforce_market_hours", True)),
        )
        if execution_df.empty:
            raise ValueError("API normalization produced empty dataset")
    except Exception as exc:
        return _build_failure_result(
            symbol,
            exc,
            error_type=_classify_validation_error(exc),
            stage="validation",
            terminal=terminal,
            task_id=task_id,
        )

    try:
        config = extract_runtime_config(base_config, task.get("config"))
        rows_before_execution = int(len(execution_df))
        print(rows_before_execution)
        _log(
            terminal,
            f"API dataframe rows before execution: {rows_before_execution}",
            task_id=task_id,
            symbol=symbol,
        )
        _log(terminal, "Running Backtrader", task_id=task_id, symbol=symbol)
        raw_result = execute_backtest_dataframe(
            data_df=execution_df,
            symbol=symbol,
            strategy_class=strategy_class,
            config=config,
            terminal=terminal,
            task_id=task_id,
        )
        result = _enrich_result(
            validate_result(raw_result, symbol=symbol),
            symbol=symbol,
        )
        if str(result.get("status", "")).upper() != "SUCCESS":
            _log(
                terminal,
                f"Execution failed: {result.get('error_message')}",
                level="ERROR",
                task_id=task_id,
                symbol=symbol,
            )
            return result

        _log(
            terminal,
            f"Execution complete. Final value: {result.get('final_value')}",
            level="SUCCESS",
            task_id=task_id,
            symbol=symbol,
        )
        return result
    except TimeoutError as exc:
        return _build_failure_result(
            symbol,
            exc,
            error_type="TIMEOUT_ERROR",
            stage="execution",
            terminal=terminal,
            task_id=task_id,
        )
    except Exception as exc:
        _log(
            terminal,
            f"Execution failed: {exc}",
            level="ERROR",
            task_id=task_id,
            symbol=symbol,
        )
        return _build_failure_result(
            symbol,
            exc,
            error_type=_classify_execution_error(exc),
            stage="execution",
            terminal=terminal,
            task_id=task_id,
        )


def run_api_task(
    task: dict[str, Any],
    base_config: dict[str, Any] | None = None,
    *,
    terminal: Any | None = None,
    task_id: str | None = None,
) -> dict[str, Any]:
    """
    Backward- and forward-compatible API entrypoint.
    """
    return run_task(
        task=task,
        base_config=base_config,
        terminal=terminal,
        task_id=task_id,
    )


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
    enforce_market_hours = bool(task.get("enforce_market_hours", True))
    instrument_type = str(task.get("instrument_type") or "").strip().upper()
    if instrument_type != "FUT":
        continuous = False

    cache_path = _build_cache_path(
        symbol=symbol,
        interval=interval,
        start_date=start_date,
        end_date=end_date,
    )
    cache_state = _inspect_cache(
        cache_path=cache_path,
        start_date=start_date,
        end_date=end_date,
        interval=interval,
    )
    cached_df = cache_state.get("data") if isinstance(cache_state.get("data"), pd.DataFrame) else None
    cache_status = str(cache_state.get("status") or "missing")

    if cache_status == "valid" and cached_df is not None:
        _log(
            terminal,
            f"Loaded cached API data: {cache_path.name}",
            task_id=task_id,
            symbol=symbol,
        )
        return cached_df

    try:
        api_key, access_token = backtest_data_service.validate_zerodha_session()
    except Exception as exc:
        fallback_df = _build_cache_fallback(cached_df, start_date=start_date, end_date=end_date)
        if fallback_df is not None:
            _log(
                terminal,
                f"Zerodha session unavailable. Using cached fallback: {exc}",
                level="WARNING",
                task_id=task_id,
                symbol=symbol,
            )
            return fallback_df
        raise
    service = zerodha_historical_data.ZerodhaHistoricalData(
        api_key=api_key,
        access_token=access_token,
    )

    if cache_status == "partial" and cached_df is not None and not cached_df.empty:
        _log(
            terminal,
            "Cache partially matches request. Fetching missing ranges.",
            level="WARNING",
            task_id=task_id,
            symbol=symbol,
        )
        missing_segments = _compute_missing_segments(
            cached_df,
            start_date=start_date,
            end_date=end_date,
        )
        fetched_frames: list[pd.DataFrame] = []
        segment_fetch_error: Exception | None = None
        for segment_start, segment_end in missing_segments:
            if segment_start > segment_end:
                continue
            try:
                segment_df = service.fetch_data(
                    instrument_token=instrument_token,
                    from_date=segment_start,
                    to_date=segment_end,
                    interval=interval,
                    continuous=continuous,
                    oi=oi,
                    enforce_market_hours=enforce_market_hours,
                )
                if isinstance(segment_df, pd.DataFrame) and not segment_df.empty:
                    fetched_frames.append(segment_df)
            except Exception as exc:
                segment_fetch_error = exc
                _log(
                    terminal,
                    f"Failed to fetch missing cache segment: {exc}",
                    level="WARNING",
                    task_id=task_id,
                    symbol=symbol,
                )
                break

        if fetched_frames:
            merged_df = _merge_cache_with_new_frames(cached_df, fetched_frames)
            if _is_cache_usable(
                merged_df,
                start_date=start_date,
                end_date=end_date,
                interval=interval,
            ):
                _save_cached_dataframe(cache_path, merged_df)
                _log(
                    terminal,
                    f"Merged and refreshed cache: {cache_path.name}",
                    task_id=task_id,
                    symbol=symbol,
                )
                return merged_df
            cached_df = merged_df

        if segment_fetch_error is not None:
            fallback_df = _build_cache_fallback(cached_df, start_date=start_date, end_date=end_date)
            if fallback_df is not None:
                _log(
                    terminal,
                    "Using cached data fallback after API segment failure.",
                    level="WARNING",
                    task_id=task_id,
                    symbol=symbol,
                )
                return fallback_df

    if cache_status == "invalid" and cache_path.is_file():
        _log(
            terminal,
            f"Invalid cache detected. Refetching: {cache_path.name}",
            level="WARNING",
            task_id=task_id,
            symbol=symbol,
        )
        try:
            cache_path.unlink()
        except Exception:
            pass

    _log(
        terminal,
        "Fetching Zerodha API data",
        task_id=task_id,
        symbol=symbol,
    )
    try:
        fetched_df = service.fetch_data(
            instrument_token=instrument_token,
            from_date=start_date,
            to_date=end_date,
            interval=interval,
            continuous=continuous,
            oi=oi,
            enforce_market_hours=enforce_market_hours,
        )
    except Exception as exc:
        fallback_df = _build_cache_fallback(cached_df, start_date=start_date, end_date=end_date)
        if fallback_df is not None:
            _log(
                terminal,
                f"API failed. Falling back to cached data: {exc}",
                level="WARNING",
                task_id=task_id,
                symbol=symbol,
            )
            return fallback_df
        raise

    if not isinstance(fetched_df, pd.DataFrame) or fetched_df.empty:
        fallback_df = _build_cache_fallback(cached_df, start_date=start_date, end_date=end_date)
        if fallback_df is not None:
            _log(
                terminal,
                "API returned empty data. Using cached fallback.",
                level="WARNING",
                task_id=task_id,
                symbol=symbol,
            )
            return fallback_df
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


def _inspect_cache(
    *,
    cache_path: Path,
    start_date: datetime,
    end_date: datetime,
    interval: str,
) -> dict[str, Any]:
    if not cache_path.is_file():
        return {"status": "missing", "data": None}

    try:
        cached_df = pd.read_csv(cache_path, parse_dates=["Date"], index_col="Date")
    except Exception:
        return {"status": "invalid", "data": None}

    normalized_cache = _sanitize_cache_dataframe(cached_df)
    if normalized_cache is None or normalized_cache.empty:
        return {"status": "invalid", "data": None}

    if _is_cache_usable(
        normalized_cache,
        start_date=start_date,
        end_date=end_date,
        interval=interval,
    ):
        return {"status": "valid", "data": normalized_cache}

    if _is_cache_partially_usable(
        normalized_cache,
        start_date=start_date,
        end_date=end_date,
        interval=interval,
    ):
        return {"status": "partial", "data": normalized_cache}

    return {"status": "invalid", "data": normalized_cache}


def _save_cached_dataframe(cache_path: Path, df: pd.DataFrame) -> None:
    try:
        payload = _sanitize_cache_dataframe(df)
        if payload is None or payload.empty:
            return
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
    interval: str,
) -> bool:
    sanitized_df = _sanitize_cache_dataframe(df)
    if sanitized_df is None or sanitized_df.empty:
        return False
    if _has_internal_missing_timestamps(sanitized_df, interval=interval):
        return False

    min_idx = sanitized_df.index.min()
    max_idx = sanitized_df.index.max()
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


def _is_cache_partially_usable(
    df: pd.DataFrame,
    *,
    start_date: datetime,
    end_date: datetime,
    interval: str,
) -> bool:
    sanitized_df = _sanitize_cache_dataframe(df)
    if sanitized_df is None or sanitized_df.empty:
        return False
    if _has_internal_missing_timestamps(sanitized_df, interval=interval):
        return False

    min_idx = sanitized_df.index.min()
    max_idx = sanitized_df.index.max()
    if min_idx is None or max_idx is None:
        return False

    cache_start = pd.Timestamp(min_idx).to_pydatetime().replace(tzinfo=None).date()
    cache_end = pd.Timestamp(max_idx).to_pydatetime().replace(tzinfo=None).date()
    requested_start = start_date.date()
    requested_end = end_date.date()
    overlaps_request = not (cache_end < requested_start or cache_start > requested_end)
    if not overlaps_request:
        return False

    return cache_start > requested_start or cache_end < requested_end


def _sanitize_cache_dataframe(df: pd.DataFrame) -> pd.DataFrame | None:
    if not isinstance(df, pd.DataFrame) or df.empty:
        return None

    payload = df.copy()
    if not isinstance(payload.index, pd.DatetimeIndex):
        converted = pd.to_datetime(payload.index, errors="coerce")
        if not isinstance(converted, pd.DatetimeIndex):
            return None
        payload.index = converted

    payload = payload[~payload.index.isna()]
    payload = payload.sort_index()
    payload = payload[~payload.index.duplicated(keep="first")]
    required_columns = ["Open", "High", "Low", "Close"]
    if not set(required_columns).issubset(set(payload.columns)):
        return None
    if "Volume" not in payload.columns:
        payload["Volume"] = 0

    for column in ["Open", "High", "Low", "Close", "Volume"]:
        payload[column] = pd.to_numeric(payload[column], errors="coerce")

    payload = payload.dropna(subset=["Open", "High", "Low", "Close"])
    payload["Volume"] = payload["Volume"].fillna(0)
    payload.index.name = "Date"
    if payload.empty:
        return None
    return payload[["Open", "High", "Low", "Close", "Volume"]]


def _has_internal_missing_timestamps(df: pd.DataFrame, *, interval: str) -> bool:
    if not isinstance(df, pd.DataFrame) or df.empty:
        return False
    normalized_interval = str(interval or "").strip().lower()
    if normalized_interval == "day":
        return False

    try:
        expected_step = zerodha_historical_data.ZerodhaHistoricalData.interval_to_timedelta(
            normalized_interval
        )
    except Exception:
        return False

    if not isinstance(df.index, pd.DatetimeIndex):
        return True
    sorted_index = df.index.sort_values()
    unique_dates = pd.Index(sorted_index.date).unique()
    for trade_day in unique_dates:
        day_index = sorted_index[sorted_index.date == trade_day]
        if len(day_index) <= 1:
            continue
        day_diffs = day_index.to_series().diff().dropna()
        if bool((day_diffs > expected_step).any()):
            return True
    return False


def _compute_missing_segments(
    cached_df: pd.DataFrame,
    *,
    start_date: datetime,
    end_date: datetime,
) -> list[tuple[datetime, datetime]]:
    if not isinstance(cached_df, pd.DataFrame) or cached_df.empty:
        return [(start_date, end_date)]

    min_idx = cached_df.index.min()
    max_idx = cached_df.index.max()
    if min_idx is None or max_idx is None:
        return [(start_date, end_date)]

    cache_min = pd.Timestamp(min_idx).to_pydatetime().replace(tzinfo=None)
    cache_max = pd.Timestamp(max_idx).to_pydatetime().replace(tzinfo=None)
    segments: list[tuple[datetime, datetime]] = []

    if cache_min.date() > start_date.date():
        left_end = min(cache_min - timedelta(seconds=1), end_date)
        if start_date <= left_end:
            segments.append((start_date, left_end))

    if cache_max.date() < end_date.date():
        right_start = max(cache_max + timedelta(seconds=1), start_date)
        if right_start <= end_date:
            segments.append((right_start, end_date))

    return segments


def _merge_cache_with_new_frames(
    cached_df: pd.DataFrame,
    fetched_frames: list[pd.DataFrame],
) -> pd.DataFrame:
    valid_frames = [frame for frame in fetched_frames if isinstance(frame, pd.DataFrame) and not frame.empty]
    if not valid_frames:
        return cached_df.copy()
    merged = pd.concat([cached_df, *valid_frames], axis=0, ignore_index=False, sort=False)
    normalized_merged = _sanitize_cache_dataframe(merged)
    return normalized_merged if normalized_merged is not None else cached_df.copy()


def _build_cache_fallback(
    cached_df: pd.DataFrame | None,
    *,
    start_date: datetime,
    end_date: datetime,
) -> pd.DataFrame | None:
    if not isinstance(cached_df, pd.DataFrame) or cached_df.empty:
        return None
    normalized_cache = _sanitize_cache_dataframe(cached_df)
    if normalized_cache is None or normalized_cache.empty:
        return None

    requested_start = start_date.date()
    requested_end = end_date.date()
    date_mask = (
        pd.Index(normalized_cache.index.date) >= requested_start
    ) & (
        pd.Index(normalized_cache.index.date) <= requested_end
    )
    fallback_df = normalized_cache.loc[date_mask]
    if fallback_df.empty:
        return None
    return fallback_df


def _prepare_api_dataframe(
    raw_data: pd.DataFrame,
    *,
    terminal: Any | None,
    task_id: str | None,
    symbol: str,
    enforce_market_hours: bool,
) -> pd.DataFrame:
    if should_normalize(raw_data):
        _log(terminal, "Normalizing API data", task_id=task_id, symbol=symbol)
        working_df = normalize(
            raw_data,
            enforce_market_hours=enforce_market_hours,
        )
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
            working_df = normalize(
                raw_data,
                enforce_market_hours=enforce_market_hours,
            )
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


def _build_failure_result(
    symbol: str,
    error: Exception | str,
    *,
    error_type: str,
    stage: str,
    log_file: str = "",
    terminal: Any | None = None,
    task_id: str | None = None,
) -> dict[str, Any]:
    message = _resolve_error_message(error)
    base = build_failed_result(symbol, message, log_file=log_file)
    enriched = _enrich_result(
        validate_result(base, symbol=symbol),
        symbol=symbol,
        error_type=error_type,
        error_message=message,
        stage=stage,
    )
    _log(
        terminal,
        (
            f"Execution failed [{enriched.get('error_type')} @ "
            f"{enriched.get('stage')}]: {enriched.get('error_message')}"
        ),
        level="ERROR",
        task_id=task_id,
        symbol=symbol,
    )
    return enriched


def _enrich_result(
    payload: dict[str, Any],
    *,
    symbol: str,
    error_type: str | None = None,
    error_message: str | None = None,
    stage: str | None = None,
) -> dict[str, Any]:
    result = validate_result(payload, symbol=symbol)
    if str(result.get("status", "")).upper() == "SUCCESS":
        result["error_type"] = None
        result["error_message"] = None
        result["stage"] = None
        return result

    resolved_message = (
        str(error_message or result.get("error") or "Unknown execution error").strip()
        or "Unknown execution error"
    )
    result["error"] = resolved_message
    result["error_message"] = resolved_message
    result["error_type"] = _sanitize_error_type(error_type)
    result["stage"] = _sanitize_stage(stage)
    return result


def _classify_fetch_error(error: Exception) -> str:
    message = _resolve_error_message(error).lower()
    class_name = type(error).__name__.lower()
    if isinstance(error, TimeoutError) or "timeout" in message or "timed out" in message:
        return "TIMEOUT_ERROR"
    if any(
        marker in class_name
        for marker in (
            "tokenexception",
            "networkexception",
            "ratelimitexception",
            "inputexception",
            "kiteexception",
        )
    ):
        return "API_ERROR"
    if any(
        marker in message
        for marker in (
            "zerodha",
            "kite",
            "api",
            "session expired",
            "access_token",
            "api_key",
            "token",
            "network",
            "rate limit",
        )
    ):
        return "API_ERROR"
    if any(
        marker in message
        for marker in (
            "empty",
            "no data",
            "missing",
            "instrument",
            "date",
        )
    ):
        return "DATA_ERROR"
    return "SYSTEM_ERROR"


def _classify_validation_error(error: Exception) -> str:
    message = _resolve_error_message(error).lower()
    if isinstance(error, TimeoutError) or "timeout" in message or "timed out" in message:
        return "TIMEOUT_ERROR"
    if any(
        marker in message
        for marker in (
            "missing",
            "invalid",
            "must be",
            "strategy_class",
            "datetime",
        )
    ):
        return "VALIDATION_ERROR"
    if any(
        marker in message
        for marker in (
            "ohlc",
            "column",
            "nan",
            "normalize",
            "dataframe",
            "dataset",
            "empty",
        )
    ):
        return "DATA_ERROR"
    return "VALIDATION_ERROR"


def _classify_execution_error(error: Exception) -> str:
    message = _resolve_error_message(error).lower()
    if isinstance(error, TimeoutError) or "timeout" in message or "timed out" in message:
        return "TIMEOUT_ERROR"
    if "strategy execution failed" in message or "strategy" in message:
        return "STRATEGY_ERROR"
    if any(
        marker in message
        for marker in (
            "ohlc",
            "data is empty",
            "insufficient rows",
            "nan",
        )
    ):
        return "DATA_ERROR"
    if any(
        marker in message
        for marker in (
            "initial_capital",
            "commission",
            "invalid strategy class",
        )
    ):
        return "VALIDATION_ERROR"
    return "SYSTEM_ERROR"


def _resolve_error_message(error: Exception | str) -> str:
    if isinstance(error, Exception):
        message = str(error).strip()
        if message:
            return message
        return type(error).__name__
    resolved = str(error).strip()
    return resolved or "Unknown execution error"


def _sanitize_error_type(value: str | None) -> str:
    allowed = {
        "DATA_ERROR",
        "API_ERROR",
        "STRATEGY_ERROR",
        "TIMEOUT_ERROR",
        "VALIDATION_ERROR",
        "SYSTEM_ERROR",
    }
    candidate = str(value or "").strip().upper()
    if candidate in allowed:
        return candidate
    return "SYSTEM_ERROR"


def _sanitize_stage(value: str | None) -> str:
    allowed = {"DATA_FETCH", "EXECUTION", "VALIDATION"}
    candidate = str(value or "").strip().upper()
    if candidate in allowed:
        return candidate.lower()
    return "execution"


__all__ = ["run_api_task", "run_task"]
