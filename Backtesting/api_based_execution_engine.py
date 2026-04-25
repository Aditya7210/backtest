from __future__ import annotations

from typing import Any

import pandas as pd

from Backtesting.data_normalizer import normalize
from Backtesting.execution_engine import (
    execute_backtest_dataframe,
    extract_runtime_config,
    validate_strategy_class,
)


def run_task(task: dict[str, Any]) -> dict[str, Any]:
    symbol = str(task.get("symbol") or "UNKNOWN").strip().upper() or "UNKNOWN"
    try:
        strategy_class = validate_strategy_class(task.get("strategy_class"))
        raw_data = task.get("data")
        if not isinstance(raw_data, pd.DataFrame):
            raise ValueError("Task data must be a pandas DataFrame for API mode")
        normalized_df = normalize(raw_data)
        config = extract_runtime_config(task.get("config"))
        return execute_backtest_dataframe(
            data_df=normalized_df,
            symbol=symbol,
            strategy_class=strategy_class,
            config=config,
        )
    except Exception as exc:
        return {
            "symbol": symbol,
            "final_value": None,
            "log_file": "",
            "error": str(exc),
        }


__all__ = ["run_task"]
