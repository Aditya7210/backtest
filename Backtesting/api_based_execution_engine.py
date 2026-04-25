from __future__ import annotations

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
        raw_data = task.get("data")
        if not isinstance(raw_data, pd.DataFrame):
            raise ValueError("Task data must be a pandas DataFrame for API mode")
        if raw_data.empty:
            raise ValueError("Task data is empty for API mode")

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
