from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import backtrader as bt
import pandas as pd

from Backtesting.data_normalizer import normalize


def run_task(task: dict[str, Any]) -> dict[str, Any]:
    symbol = str(task.get("symbol") or "UNKNOWN").strip().upper() or "UNKNOWN"
    try:
        strategy_class = validate_strategy_class(task.get("strategy_class"))
        csv_path = _resolve_csv_path(task.get("data"))
        raw_df = pd.read_csv(csv_path)
        normalized_df = normalize(raw_df)
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

    initial_capital = float(config["initial_capital"])
    commission = float(config["commission"])

    cerebro = bt.Cerebro(stdstats=False)
    data_feed = bt.feeds.PandasData(dataname=data_df)
    cerebro.adddata(data_feed)
    cerebro.addstrategy(strategy_class)
    cerebro.broker.setcash(initial_capital)
    cerebro.broker.setcommission(commission=commission)
    cerebro.run()
    final_value = float(cerebro.broker.getvalue())

    log_file = _write_log(symbol=symbol, final_value=final_value, config=config)
    return {
        "symbol": symbol,
        "final_value": final_value,
        "log_file": str(log_file),
        "error": None,
    }


def validate_strategy_class(value: Any) -> type[Any]:
    if not isinstance(value, type):
        raise ValueError("Task strategy_class must be a valid class object")
    return value


def extract_runtime_config(value: Any) -> dict[str, float]:
    defaults = {"initial_capital": 100000.0, "commission": 0.0003}
    if isinstance(value, dict):
        if "initial_capital" in value:
            defaults["initial_capital"] = float(value["initial_capital"])
        if "commission" in value:
            defaults["commission"] = float(value["commission"])

    if defaults["initial_capital"] <= 0:
        raise ValueError("initial_capital must be greater than 0")
    if defaults["commission"] < 0:
        raise ValueError("commission cannot be negative")

    return defaults


def _resolve_csv_path(data_ref: Any) -> Path:
    if data_ref is None:
        raise ValueError("Task data is missing for CSV mode")

    raw_path = Path(str(data_ref))
    if raw_path.is_absolute():
        candidate_paths = [raw_path]
    else:
        project_root = Path(__file__).resolve().parents[1]
        candidate_paths = [
            project_root / "Data" / "testing_data" / "Data_files" / raw_path,
            project_root / raw_path,
            raw_path,
        ]

    for candidate in candidate_paths:
        resolved = candidate.resolve()
        if resolved.is_file():
            return resolved

    raise ValueError(f"CSV file not found: {data_ref}")


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


__all__ = [
    "execute_backtest_dataframe",
    "extract_runtime_config",
    "run_task",
    "validate_strategy_class",
]
