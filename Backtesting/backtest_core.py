from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import backtrader as bt
import pandas as pd


def validate_strategy_class(value: Any) -> type[Any]:
    if not isinstance(value, type):
        raise ValueError("Task strategy_class must be a valid class object")
    return value


def extract_runtime_config(
    base_config: dict[str, Any] | None = None,
    task_config: Any = None,
) -> dict[str, float]:
    config = {"initial_capital": 100000.0, "commission": 0.0003}
    if isinstance(base_config, dict):
        config.update(base_config)
    if isinstance(task_config, dict):
        config.update(task_config)

    config["initial_capital"] = float(config["initial_capital"])
    config["commission"] = float(config["commission"])

    if config["initial_capital"] <= 0:
        raise ValueError("initial_capital must be greater than 0")
    if config["commission"] < 0:
        raise ValueError("commission cannot be negative")

    return {
        "initial_capital": config["initial_capital"],
        "commission": config["commission"],
    }


def build_failed_result(symbol: str, error: str, *, log_file: str = "") -> dict[str, Any]:
    resolved_log_file = str(log_file or "")
    if not resolved_log_file:
        try:
            resolved_log_file = str(_write_error_log(symbol=symbol, error=error))
        except Exception:
            resolved_log_file = ""

    return {
        "symbol": symbol,
        "status": "FAILED",
        "final_value": None,
        "log_file": resolved_log_file,
        "error": str(error or "Unknown execution error"),
    }


def build_success_result(
    symbol: str,
    final_value: float,
    *,
    log_file: str,
) -> dict[str, Any]:
    return {
        "symbol": symbol,
        "status": "SUCCESS",
        "final_value": float(final_value),
        "log_file": str(log_file or ""),
        "error": None,
    }


def execute_backtest_dataframe(
    *,
    data_df: pd.DataFrame,
    symbol: str,
    strategy_class: type[Any],
    config: dict[str, float],
) -> dict[str, Any]:
    if not isinstance(data_df, pd.DataFrame) or data_df.empty:
        raise ValueError("Backtest data is empty")
    if not isinstance(strategy_class, type):
        raise ValueError("Invalid strategy class")
    _validate_execution_dataframe(data_df)

    initial_capital = float(config["initial_capital"])
    commission = float(config["commission"])

    cerebro = bt.Cerebro(stdstats=False)
    data_feed = bt.feeds.PandasData(dataname=data_df)
    cerebro.adddata(data_feed)
    cerebro.addstrategy(strategy_class)
    cerebro.broker.setcash(initial_capital)
    cerebro.broker.setcommission(commission=commission)
    try:
        cerebro.run()
    except Exception as exc:
        raise RuntimeError(f"Strategy execution failed: {exc}") from exc
    final_value = float(cerebro.broker.getvalue())

    log_file = _write_log(symbol=symbol, final_value=final_value, config=config)
    return build_success_result(symbol=symbol, final_value=final_value, log_file=str(log_file))


def _write_log(*, symbol: str, final_value: float, config: dict[str, float]) -> Path:
    log_dir = (
        Path(__file__).resolve().parents[1]
        / "Data"
        / "Logs"
        / "Backtesting_result_log"
    )
    log_dir.mkdir(parents=True, exist_ok=True)

    safe_symbol = "".join(ch for ch in symbol if ch.isalnum() or ch in {"_", "-"})
    safe_symbol = safe_symbol or "UNKNOWN"
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    log_path = log_dir / f"{safe_symbol}_execution_{timestamp}.log"
    log_path.write_text(
        "\n".join(
            [
                f"symbol={symbol}",
                f"final_value={final_value}",
                f"initial_capital={config['initial_capital']}",
                f"commission={config['commission']}",
            ]
        ),
        encoding="utf-8",
    )
    return log_path


def _write_error_log(*, symbol: str, error: str) -> Path:
    log_dir = (
        Path(__file__).resolve().parents[1]
        / "Data"
        / "Logs"
        / "Backtesting_result_log"
    )
    log_dir.mkdir(parents=True, exist_ok=True)

    safe_symbol = "".join(ch for ch in symbol if ch.isalnum() or ch in {"_", "-"})
    safe_symbol = safe_symbol or "UNKNOWN"
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    log_path = log_dir / f"{safe_symbol}_execution_error_{timestamp}.log"
    log_path.write_text(
        "\n".join(
            [
                f"symbol={symbol}",
                f"status=FAILED",
                f"error={error}",
            ]
        ),
        encoding="utf-8",
    )
    return log_path


def _validate_execution_dataframe(data_df: pd.DataFrame) -> None:
    required = ["Open", "High", "Low", "Close"]
    missing = [column for column in required if column not in data_df.columns]
    if missing:
        raise ValueError(f"Missing required OHLC columns: {missing}")

    if len(data_df) <= 50:
        raise ValueError("Insufficient rows for strategy execution (minimum > 50)")

    fully_nan_ohlc = data_df[required].isna().all(axis=1)
    if bool(fully_nan_ohlc.any()):
        raise ValueError("Data contains rows with fully NaN OHLC values")


__all__ = [
    "build_failed_result",
    "build_success_result",
    "execute_backtest_dataframe",
    "extract_runtime_config",
    "validate_strategy_class",
]
