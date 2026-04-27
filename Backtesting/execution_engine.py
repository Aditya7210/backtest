from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pandas as pd
from pandas.errors import EmptyDataError, ParserError

from Backtesting.api_based_execution_engine import run_task as _run_api_task
from Backtesting.backtest_core import (
    build_failed_result,
    execute_backtest_dataframe,
    extract_runtime_config,
    validate_result,
    validate_strategy_class,
)
from Backtesting.data_normalizer import normalize

MAX_CSV_SIZE_MB = 200.0


def run_csv_task(
    task: dict[str, Any],
    base_config: dict[str, Any] | None = None,
    *,
    terminal: Any | None = None,
    task_id: str | None = None,
) -> dict[str, Any]:
    symbol = str(task.get("symbol") or "UNKNOWN").strip().upper() or "UNKNOWN"
    _log(terminal, "Validating CSV task payload", task_id=task_id, symbol=symbol)
    try:
        strategy_class = validate_strategy_class(task.get("strategy_class"))
        csv_path = _resolve_csv_path(task.get("data"))
    except Exception as exc:
        return _build_failure_result(
            symbol,
            exc,
            error_type=_classify_validation_error(exc),
            stage="validation",
            terminal=terminal,
            task_id=task_id,
        )

    _log(
        terminal,
        f"Loading CSV: {csv_path}",
        task_id=task_id,
        symbol=symbol,
    )
    try:
        file_size_mb = os.path.getsize(csv_path) / (1024 * 1024)
        if file_size_mb > MAX_CSV_SIZE_MB:
            raise ValueError(
                f"CSV too large: {file_size_mb:.2f} MB (max {MAX_CSV_SIZE_MB:.2f} MB)"
            )
        raw_df = pd.read_csv(csv_path)
    except EmptyDataError as exc:
        return _build_failure_result(
            symbol,
            ValueError(f"CSV is empty: {csv_path}"),
            error_type="DATA_ERROR",
            stage="data_fetch",
            terminal=terminal,
            task_id=task_id,
        )
    except ParserError as exc:
        return _build_failure_result(
            symbol,
            ValueError(f"CSV parsing failed: {csv_path}"),
            error_type="DATA_ERROR",
            stage="data_fetch",
            terminal=terminal,
            task_id=task_id,
        )
    except TimeoutError as exc:
        return _build_failure_result(
            symbol,
            exc,
            error_type="TIMEOUT_ERROR",
            stage="data_fetch",
            terminal=terminal,
            task_id=task_id,
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

    _log(terminal, "Validating CSV data", task_id=task_id, symbol=symbol)
    try:
        if raw_df.empty:
            raise ValueError(f"CSV has no rows: {csv_path}")
        _validate_raw_csv_dataframe(raw_df, csv_path)
        enforce_market_hours = bool(task.get("enforce_market_hours", True))

        _log(terminal, "Normalizing CSV data", task_id=task_id, symbol=symbol)
        execution_df = normalize(
            raw_df,
            enforce_market_hours=enforce_market_hours,
        )
        if execution_df.empty:
            raise ValueError("CSV normalization produced empty dataset")
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


def run_task(
    task: dict[str, Any],
    base_config: dict[str, Any] | None = None,
    *,
    terminal: Any | None = None,
    task_id: str | None = None,
) -> dict[str, Any]:
    """
    Backward-compatible CSV entrypoint.
    """
    return run_csv_task(
        task=task,
        base_config=base_config,
        terminal=terminal,
        task_id=task_id,
    )


class ExecutionEngine:
    """
    Execution routing layer.

    Keeps orchestration concerns out of the manager by exposing one execute() call
    while preserving direct API/CSV execution methods for compatibility.
    """

    def __init__(
        self,
        base_config: dict[str, Any] | None = None,
        *,
        terminal: Any | None = None,
    ) -> None:
        self._base_config = dict(base_config) if isinstance(base_config, dict) else {}
        self._terminal = terminal

    def set_terminal(self, terminal: Any | None) -> None:
        self._terminal = terminal

    def set_base_config(self, base_config: dict[str, Any] | None) -> None:
        self._base_config = dict(base_config) if isinstance(base_config, dict) else {}

    def run_api_task(
        self,
        task: dict[str, Any],
        *,
        task_id: str | None = None,
    ) -> dict[str, Any]:
        return _run_api_task(
            task=task,
            base_config=self._base_config,
            terminal=self._terminal,
            task_id=task_id,
        )

    def run_csv_task(
        self,
        task: dict[str, Any],
        *,
        task_id: str | None = None,
    ) -> dict[str, Any]:
        return run_csv_task(
            task=task,
            base_config=self._base_config,
            terminal=self._terminal,
            task_id=task_id,
        )

    def execute(
        self,
        task: dict[str, Any],
        *,
        task_id: str | None = None,
        mode: str | None = None,
    ) -> dict[str, Any]:
        symbol = str(task.get("symbol") or "UNKNOWN").strip().upper() or "UNKNOWN"
        resolved_mode = str(mode or task.get("mode", "")).strip().lower()

        if resolved_mode == "api":
            return self.run_api_task(task, task_id=task_id)
        if resolved_mode == "csv":
            return self.run_csv_task(task, task_id=task_id)

        return _build_failure_result(
            symbol,
            ValueError(f"Unsupported task mode: {resolved_mode or '<missing>'}"),
            error_type="VALIDATION_ERROR",
            stage="validation",
            terminal=self._terminal,
            task_id=task_id,
        )


def _resolve_csv_path(data_ref: Any) -> Path:
    if data_ref is None:
        raise ValueError("Task data is missing for CSV mode")

    raw_path = Path(str(data_ref))
    data_root = (
        Path(__file__).resolve().parents[1]
        / "Data"
        / "testing_data"
        / "Data_files"
    ).resolve()

    if raw_path.is_absolute():
        resolved = raw_path.resolve()
        if not resolved.is_file():
            raise ValueError(f"CSV file not found: {resolved}")
        return resolved

    resolved = (data_root / raw_path).resolve()
    try:
        resolved.relative_to(data_root)
    except ValueError as exc:
        raise ValueError(
            "Invalid CSV path. Relative paths must stay inside Data/testing_data/Data_files"
        ) from exc

    if not resolved.is_file():
        raise ValueError(f"CSV file not found: {resolved}")
    return resolved


def _validate_raw_csv_dataframe(raw_df: pd.DataFrame, csv_path: Path) -> None:
    column_lookup = {str(column).strip().lower() for column in raw_df.columns}
    required = {"open", "high", "low", "close"}
    if not required.issubset(column_lookup):
        raise ValueError(
            f"CSV missing OHLC columns before normalization: {csv_path}"
        )

    date_like_columns = ["date", "datetime", "timestamp", "time"]
    detected_date_column = next(
        (column for column in raw_df.columns if str(column).strip().lower() in date_like_columns),
        None,
    )

    if detected_date_column is not None:
        parsed_dates = pd.to_datetime(raw_df[detected_date_column], errors="coerce")
        if parsed_dates.notna().sum() == 0:
            raise ValueError(f"CSV date parsing failed: {csv_path}")
        return

    if isinstance(raw_df.index, pd.RangeIndex) or pd.api.types.is_numeric_dtype(raw_df.index):
        raise ValueError(f"CSV missing a parseable datetime column: {csv_path}")

    parsed_index = pd.to_datetime(raw_df.index, errors="coerce")
    if parsed_index.notna().sum() == 0:
        raise ValueError(f"CSV datetime index parsing failed: {csv_path}")


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
    except Exception as exc:
        print(f"[LoggingError] {exc}")


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
    if isinstance(error, TimeoutError) or "timeout" in message or "timed out" in message:
        return "TIMEOUT_ERROR"
    if any(
        marker in message
        for marker in (
            "file not found",
            "csv",
            "parse",
            "empty",
            "no rows",
            "permission",
            "path",
            "too large",
            "size",
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
            "path",
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
            "datetime",
            "date parsing",
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


__all__ = [
    "ExecutionEngine",
    "run_csv_task",
    "run_task",
]
