from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
from pandas.errors import EmptyDataError, ParserError

from Backtesting.backtest_core import (
    build_failed_result,
    execute_backtest_dataframe,
    extract_runtime_config,
    validate_result,
    validate_strategy_class,
)
from Backtesting.data_normalizer import normalize


def run_task(
    task: dict[str, Any],
    base_config: dict[str, Any] | None = None,
    *,
    terminal: Any | None = None,
    task_id: str | None = None,
) -> dict[str, Any]:
    symbol = str(task.get("symbol") or "UNKNOWN").strip().upper() or "UNKNOWN"
    try:
        _log(terminal, "Validating CSV task payload", task_id=task_id, symbol=symbol)
        strategy_class = validate_strategy_class(task.get("strategy_class"))
        csv_path = _resolve_csv_path(task.get("data"))
        _log(
            terminal,
            f"Loading CSV: {csv_path}",
            task_id=task_id,
            symbol=symbol,
        )
        try:
            raw_df = pd.read_csv(csv_path)
        except EmptyDataError as exc:
            raise ValueError(f"CSV is empty: {csv_path}") from exc
        except ParserError as exc:
            raise ValueError(f"CSV parsing failed: {csv_path}") from exc

        if raw_df.empty:
            raise ValueError(f"CSV has no rows: {csv_path}")
        _log(terminal, "Validating CSV data", task_id=task_id, symbol=symbol)
        _validate_raw_csv_dataframe(raw_df, csv_path)

        _log(terminal, "Normalizing CSV data", task_id=task_id, symbol=symbol)
        execution_df = normalize(raw_df)
        if execution_df.empty:
            raise ValueError("CSV normalization produced empty dataset")

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
    except Exception:
        pass


__all__ = [
    "run_task",
]
