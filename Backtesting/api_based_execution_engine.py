from __future__ import annotations

from typing import Any

import pandas as pd

from Backtesting.backtest_core import (
    build_failed_result,
    execute_backtest_dataframe,
    extract_runtime_config,
    validate_strategy_class,
)
from Backtesting.data_normalizer import normalize


def run_task(
    task: dict[str, Any],
    base_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    symbol = str(task.get("symbol") or "UNKNOWN").strip().upper() or "UNKNOWN"
    try:
        strategy_class = validate_strategy_class(task.get("strategy_class"))
        raw_data = task.get("data")
        if not isinstance(raw_data, pd.DataFrame):
            raise ValueError("Task data must be a pandas DataFrame for API mode")
        if raw_data.empty:
            raise ValueError("Task data is empty for API mode")

        normalized_df = _prepare_api_dataframe(raw_data)
        if normalized_df.empty:
            raise ValueError("API normalization produced empty dataset")

        config = extract_runtime_config(base_config, task.get("config"))
        return execute_backtest_dataframe(
            data_df=normalized_df,
            symbol=symbol,
            strategy_class=strategy_class,
            config=config,
        )
    except Exception as exc:
        return build_failed_result(symbol, str(exc))


def _prepare_api_dataframe(raw_data: pd.DataFrame) -> pd.DataFrame:
    if _is_already_normalized_api_data(raw_data):
        working_df = raw_data.copy()
        if "Volume" not in working_df.columns:
            working_df["Volume"] = 0
        for column in ["Open", "High", "Low", "Close", "Volume"]:
            working_df[column] = pd.to_numeric(working_df[column], errors="coerce")
        if working_df[["Open", "High", "Low", "Close"]].isna().any().any():
            return normalize(raw_data)
        working_df = working_df.sort_index()
        working_df = working_df[~working_df.index.duplicated(keep="first")]
        return working_df[["Open", "High", "Low", "Close", "Volume"]]

    return normalize(raw_data)


def _is_already_normalized_api_data(raw_data: pd.DataFrame) -> bool:
    required = ["Open", "High", "Low", "Close"]
    if not all(column in raw_data.columns for column in required):
        return False
    if not isinstance(raw_data.index, pd.DatetimeIndex):
        return False
    if raw_data[required].isna().any().any():
        return False
    return True


__all__ = ["run_task"]
