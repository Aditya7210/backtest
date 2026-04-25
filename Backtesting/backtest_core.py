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
        "execution_time": 0.0,
        "retries": 0,
    }


def build_success_result(
    symbol: str,
    final_value: float,
    *,
    log_file: str,
    execution_time: float = 0.0,
    retries: int = 0,
) -> dict[str, Any]:
    return {
        "symbol": symbol,
        "status": "SUCCESS",
        "final_value": float(final_value),
        "log_file": str(log_file or ""),
        "error": None,
        "execution_time": max(0.0, float(execution_time)),
        "retries": max(0, int(retries)),
    }


def validate_result(
    payload: Any,
    *,
    symbol: str,
    execution_time: float | None = None,
    retries: int | None = None,
) -> dict[str, Any]:
    if not isinstance(payload, dict):
        result = build_failed_result(symbol, "Engine returned invalid result format")
    else:
        result = dict(payload)

    resolved_symbol = str(result.get("symbol") or symbol).strip().upper() or str(symbol)
    status = str(result.get("status", "FAILED")).strip().upper()
    log_file = str(result.get("log_file") or "")
    error = result.get("error")
    final_value = result.get("final_value")

    if status not in {"SUCCESS", "FAILED"}:
        result = build_failed_result(
            resolved_symbol,
            "Invalid result status from engine",
            log_file=log_file,
        )
        status = "FAILED"

    if status == "SUCCESS":
        if final_value is None:
            result = build_failed_result(
                resolved_symbol,
                "Execution succeeded without final_value",
                log_file=log_file,
            )
            status = "FAILED"
        else:
            try:
                normalized_final_value: float | None = float(final_value)
            except (TypeError, ValueError):
                result = build_failed_result(
                    resolved_symbol,
                    "Execution returned non-numeric final_value",
                    log_file=log_file,
                )
                status = "FAILED"
            else:
                result = build_success_result(
                    symbol=resolved_symbol,
                    final_value=normalized_final_value,
                    log_file=log_file,
                )
    else:
        resolved_error = str(error or "").strip()
        if not resolved_error:
            resolved_error = "Unknown execution error"
        result = build_failed_result(
            resolved_symbol,
            resolved_error,
            log_file=log_file,
        )

    if execution_time is not None:
        try:
            result["execution_time"] = max(0.0, float(execution_time))
        except (TypeError, ValueError):
            result["execution_time"] = 0.0
    else:
        result["execution_time"] = max(0.0, float(result.get("execution_time", 0.0)))

    if retries is not None:
        try:
            result["retries"] = max(0, int(retries))
        except (TypeError, ValueError):
            result["retries"] = 0
    else:
        try:
            result["retries"] = max(0, int(result.get("retries", 0)))
        except (TypeError, ValueError):
            result["retries"] = 0

    return result


def execute_backtest_dataframe(
    *,
    data_df: pd.DataFrame,
    symbol: str,
    strategy_class: type[Any],
    config: dict[str, float],
    terminal: Any | None = None,
    task_id: str | None = None,
) -> dict[str, Any]:
    if not isinstance(data_df, pd.DataFrame) or data_df.empty:
        raise ValueError("Backtest data is empty")
    if not isinstance(strategy_class, type):
        raise ValueError("Invalid strategy class")
    _validate_execution_dataframe(data_df)

    initial_capital = float(config["initial_capital"])
    commission = float(config["commission"])
    _log_terminal(
        terminal,
        "Starting Backtest",
        task_id=task_id,
        symbol=symbol,
    )

    cerebro = bt.Cerebro(stdstats=False)
    data_feed = bt.feeds.PandasData(dataname=data_df)
    cerebro.adddata(data_feed)
    cerebro.addstrategy(strategy_class)
    cerebro.addanalyzer(_TradeEventAnalyzer, _name="trade_events")
    cerebro.addanalyzer(_ClosedTradesAnalyzer, _name="closed_trades")
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name="trade_stats")
    cerebro.broker.setcash(initial_capital)
    cerebro.broker.setcommission(commission=commission)
    try:
        results = cerebro.run()
    except Exception as exc:
        raise RuntimeError(f"Strategy execution failed: {exc}") from exc

    strategy_instance = results[0] if results else None
    trade_events: list[str] = []
    closed_trades: list[dict[str, Any]] = []
    if strategy_instance is not None:
        try:
            raw_events = strategy_instance.analyzers.trade_events.get_analysis()
        except Exception:
            raw_events = []
        if isinstance(raw_events, list):
            trade_events = [str(item) for item in raw_events]

        try:
            raw_closed_trades = strategy_instance.analyzers.closed_trades.get_analysis()
        except Exception:
            raw_closed_trades = []
        if isinstance(raw_closed_trades, list):
            for row in raw_closed_trades:
                if isinstance(row, dict):
                    closed_trades.append(dict(row))

        if isinstance(trade_events, list):
            for event in trade_events[:40]:
                _log_terminal(
                    terminal,
                    str(event),
                    task_id=task_id,
                    symbol=symbol,
                )
            if len(trade_events) > 40:
                _log_terminal(
                    terminal,
                    f"... {len(trade_events) - 40} more trade events",
                    level="WARNING",
                    task_id=task_id,
                    symbol=symbol,
                )

        try:
            trade_stats = strategy_instance.analyzers.trade_stats.get_analysis()
        except Exception:
            trade_stats = {}
        total_trades = int(trade_stats.get("total", {}).get("total", 0)) if isinstance(trade_stats, dict) else 0
        if total_trades > 0:
            _log_terminal(
                terminal,
                f"Total trades executed: {total_trades}",
                task_id=task_id,
                symbol=symbol,
            )

    final_value = float(cerebro.broker.getvalue())
    _log_terminal(
        terminal,
        f"Final Portfolio Value: {final_value}",
        level="SUCCESS",
        task_id=task_id,
        symbol=symbol,
    )

    artifacts = _write_dashboard_artifacts(
        symbol=symbol,
        final_value=final_value,
        config=config,
        trade_events=trade_events,
        closed_trades=closed_trades,
    )
    return build_success_result(
        symbol=symbol,
        final_value=final_value,
        log_file=str(artifacts["log_file"]),
    )


class _TradeEventAnalyzer(bt.Analyzer):
    def start(self) -> None:
        self.events: list[str] = []

    def notify_trade(self, trade: Any) -> None:
        try:
            if trade.justopened:
                side = "BUY" if trade.size > 0 else "SELL"
                event_time = bt.num2date(trade.dtopen).strftime("%Y-%m-%d %H:%M:%S")
                self.events.append(
                    f"{side} qty={abs(trade.size)} price={float(trade.price):.2f} at {event_time}"
                )
            if trade.isclosed:
                event_time = bt.num2date(trade.dtclose).strftime("%Y-%m-%d %H:%M:%S")
                self.events.append(
                    f"CLOSE pnl={float(trade.pnlcomm):.2f} at {event_time}"
                )
        except Exception:
            return

    def get_analysis(self) -> list[str]:
        return self.events


class _ClosedTradesAnalyzer(bt.Analyzer):
    def start(self) -> None:
        self.rows: list[dict[str, Any]] = []
        self._open_dirs: dict[int, str] = {}
        self._open_qty: dict[int, int] = {}

    def notify_trade(self, trade: Any) -> None:
        try:
            if trade.justopened:
                direction = "BUY" if float(trade.size) > 0 else "SELL"
                self._open_dirs[int(trade.ref)] = direction
                self._open_qty[int(trade.ref)] = max(1, int(abs(float(trade.size))))

            if not trade.isclosed:
                return

            trade_ref = int(trade.ref)
            direction = self._open_dirs.pop(trade_ref, "BUY")
            qty = self._open_qty.pop(trade_ref, 1)
            entry_px = float(trade.price)
            exit_px = (float(trade.pnl) / qty + entry_px) if qty > 0 else entry_px

            self.rows.append(
                {
                    "Entry Date": bt.num2date(trade.dtopen).strftime("%Y-%m-%d %H:%M:%S"),
                    "Close Date": bt.num2date(trade.dtclose).strftime("%Y-%m-%d %H:%M:%S"),
                    "Symbol": "",
                    "Direction": direction,
                    "Qty": qty,
                    "Entry Price": round(entry_px, 2),
                    "Exit Price": round(exit_px, 2),
                    "Gross P&L": round(float(trade.pnl), 2),
                    "Net P&L": round(float(trade.pnlcomm), 2),
                }
            )
        except Exception:
            return

    def get_analysis(self) -> list[dict[str, Any]]:
        return self.rows


def _log_terminal(
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


def _write_dashboard_artifacts(
    *,
    symbol: str,
    final_value: float,
    config: dict[str, float],
    trade_events: list[str],
    closed_trades: list[dict[str, Any]],
) -> dict[str, Path]:
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
    result_path = log_dir / f"{safe_symbol}_result_{timestamp}.csv"
    log_path = log_dir / f"{safe_symbol}_log_{timestamp}.log"

    trade_columns = [
        "Entry Date",
        "Close Date",
        "Symbol",
        "Direction",
        "Qty",
        "Entry Price",
        "Exit Price",
        "Gross P&L",
        "Net P&L",
    ]
    normalized_rows = []
    for row in closed_trades:
        normalized = {column: row.get(column) for column in trade_columns}
        normalized["Symbol"] = symbol
        normalized_rows.append(normalized)
    pd.DataFrame(normalized_rows, columns=trade_columns).to_csv(result_path, index=False)

    event_lines = trade_events if trade_events else ["No trade events captured."]
    log_path.write_text(
        "\n".join(
            [
                f"symbol={symbol}",
                f"final_value={final_value}",
                f"initial_capital={config['initial_capital']}",
                f"commission={config['commission']}",
                f"total_closed_trades={len(normalized_rows)}",
                "",
                "trade_events:",
                *event_lines,
            ]
        ),
        encoding="utf-8",
    )
    return {"result_file": result_path, "log_file": log_path}


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
    "validate_result",
    "validate_strategy_class",
]
