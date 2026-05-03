from __future__ import annotations

from datetime import datetime, time
from pathlib import Path
from typing import Any
import traceback
import warnings

import backtrader as bt
import pandas as pd

_IST_TIMEZONE = "Asia/Kolkata"
_MARKET_OPEN_TIME = time(9, 15)
_MARKET_CLOSE_TIME = time(15, 30)
_SHORT_ENABLE_FLAGS = (
    "allow_short",
    "allow_shorts",
    "allow_short_selling",
    "short_selling",
    "enable_short",
    "short_enabled",
)
_SHORT_SCALING_ENABLE_FLAGS = (
    "allow_short_scaling",
    "allow_short_scale_in",
    "short_scaling_enabled",
    "short_scale_in_enabled",
)
_POSITION_SIZE_TOLERANCE = 1e-9


def _to_ist_datetime(value: datetime) -> datetime:
    ts = pd.Timestamp(value)
    if ts.tzinfo is None:
        # Backtrader numeric datetimes are treated as UTC when tz info is missing.
        ts = ts.tz_localize("UTC")
    return ts.tz_convert(_IST_TIMEZONE).to_pydatetime()


def _format_ist_datetime(value: datetime) -> str:
    return _to_ist_datetime(value).strftime("%Y-%m-%d %H:%M:%S")


def validate_strategy_class(value: Any) -> type[Any]:
    if not isinstance(value, type):
        raise ValueError("Task strategy_class must be a valid class object")
    return value


def extract_runtime_config(
    base_config: dict[str, Any] | None = None,
    task_config: Any = None,
) -> dict[str, Any]:
    config = {
        "initial_capital": 100000.0,
        "commission": 0.0003,
        "slippage": 0.0,
        "lot_size": 1,
        "position_size": 1,
        "max_positions": 1,
        "execution_mode": "market",
        "enforce_market_hours": True,
    }
    if isinstance(base_config, dict):
        config.update(base_config)
    if isinstance(task_config, dict):
        config.update(task_config)

    config["initial_capital"] = float(config["initial_capital"])
    config["commission"] = float(config["commission"])
    config["slippage"] = float(config.get("slippage", 0.0))
    config["lot_size"] = int(config.get("lot_size", 1))
    config["position_size"] = int(config.get("position_size", 1))
    config["max_positions"] = int(config.get("max_positions", 1))
    config["execution_mode"] = str(config.get("execution_mode", "market") or "market").strip().lower()
    config["enforce_market_hours"] = bool(config.get("enforce_market_hours", True))

    if config["initial_capital"] <= 0:
        raise ValueError("initial_capital must be greater than 0")
    if config["commission"] < 0:
        raise ValueError("commission cannot be negative")
    if config["slippage"] < 0:
        raise ValueError("slippage cannot be negative")
    if config["lot_size"] <= 0:
        raise ValueError("lot_size must be greater than 0")
    if config["position_size"] <= 0:
        raise ValueError("position_size must be greater than 0")
    if config["max_positions"] <= 0:
        raise ValueError("max_positions must be greater than 0")
    if config["execution_mode"] not in {"market", "close"}:
        raise ValueError("execution_mode must be one of: market, close")

    return {
        "initial_capital": config["initial_capital"],
        "commission": config["commission"],
        "slippage": config["slippage"],
        "lot_size": config["lot_size"],
        "position_size": config["position_size"],
        "max_positions": config["max_positions"],
        "execution_mode": config["execution_mode"],
        "enforce_market_hours": config["enforce_market_hours"],
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
    metrics: dict[str, Any] | None = None,
    trades: list[dict[str, Any]] | None = None,
    execution_time: float = 0.0,
    retries: int = 0,
) -> dict[str, Any]:
    return {
        "symbol": symbol,
        "status": "SUCCESS",
        "final_value": float(final_value),
        "metrics": dict(metrics or {}),
        "trades": list(trades or []),
        "closed_trades": list(trades or []),
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
    raw_input_rows = int(len(data_df))
    _log_terminal(
        terminal,
        f"Input dataframe rows before preparation: {raw_input_rows}",
        task_id=task_id,
        symbol=symbol,
    )
    prepared_df = _prepare_dataframe_for_backtrader(
        data_df,
        enforce_market_hours=bool(config.get("enforce_market_hours", True)),
        terminal=terminal,
        task_id=task_id,
        symbol=symbol,
    )
    _validate_execution_dataframe(prepared_df)
    prepared_rows = int(len(prepared_df))
    _log_terminal(
        terminal,
        f"Rows passed to Backtrader data feed: {prepared_rows}",
        task_id=task_id,
        symbol=symbol,
    )

    initial_capital = float(config["initial_capital"])
    commission = float(config["commission"])
    slippage = float(config.get("slippage", 0.0))
    _log_terminal(
        terminal,
        "Starting Backtest",
        task_id=task_id,
        symbol=symbol,
    )
    _log_terminal(
        terminal,
        (
            f"Execution assumptions: mode={config.get('execution_mode')}, "
            f"position_size={config.get('position_size')}, lot_size={config.get('lot_size')}, "
            f"max_positions={config.get('max_positions')}, slippage={slippage}"
        ),
        task_id=task_id,
        symbol=symbol,
    )

    cerebro = bt.Cerebro(stdstats=False)
    data_feed = bt.feeds.PandasData(dataname=prepared_df)
    cerebro.adddata(data_feed)
    _log_terminal(
        terminal,
        (
            "Backtrader data feed attached with full prepared dataset "
            f"({prepared_rows} rows)"
        ),
        task_id=task_id,
        symbol=symbol,
    )
    guarded_strategy_class = _build_position_guarded_strategy(strategy_class)
    size_stake = max(1, int(config.get("position_size", 1)) * int(config.get("lot_size", 1)))
    cerebro.addsizer(bt.sizers.FixedSize, stake=size_stake)
    cerebro.addstrategy(guarded_strategy_class)
    cerebro.addanalyzer(_TradeEventAnalyzer, _name="trade_events")
    cerebro.addanalyzer(_ClosedTradesAnalyzer, _name="closed_trades")
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name="trade_stats")
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name="drawdown")
    # Uses annualized sharpe when possible; may be None for short/flat series.
    cerebro.addanalyzer(bt.analyzers.SharpeRatio_A, _name="sharpe", riskfreerate=0.0)
    _reset_cerebro_broker_state(
        cerebro,
        initial_capital=initial_capital,
        commission=commission,
        slippage=slippage,
        terminal=terminal,
        task_id=task_id,
        symbol=symbol,
    )
    results = _run_cerebro_with_isolation(
        cerebro,
        terminal=terminal,
        task_id=task_id,
        symbol=symbol,
    )

    strategy_instance = results[0] if results else None
    bars_processed = int(len(strategy_instance)) if strategy_instance is not None else 0
    _log_terminal(
        terminal,
        f"Bars processed by Backtrader: {bars_processed}",
        task_id=task_id,
        symbol=symbol,
    )
    if bars_processed != prepared_rows:
        mismatch_message = (
            "Row/bar sanity check failed. "
            f"Prepared rows={prepared_rows}, processed bars={bars_processed}"
        )
        _log_terminal(
            terminal,
            mismatch_message,
            level="ERROR",
            task_id=task_id,
            symbol=symbol,
        )
        raise RuntimeError(mismatch_message)
    else:
        _log_terminal(
            terminal,
            (
                "Row/bar sanity check passed: "
                f"{prepared_rows} input rows == {bars_processed} processed bars"
            ),
            level="SUCCESS",
            task_id=task_id,
            symbol=symbol,
        )

    trade_events: list[str] = []
    closed_trades: list[dict[str, Any]] = []
    trade_stats: dict[str, Any] = {}
    drawdown_stats: dict[str, Any] = {}
    sharpe_stats: dict[str, Any] = {}
    if strategy_instance is not None:
        blocked_sell_events = getattr(strategy_instance, "_position_guard_events", [])
        if isinstance(blocked_sell_events, list):
            for event in blocked_sell_events[:40]:
                _log_terminal(
                    terminal,
                    str(event),
                    level="WARNING",
                    task_id=task_id,
                    symbol=symbol,
                )
            if len(blocked_sell_events) > 40:
                _log_terminal(
                    terminal,
                    (
                        "... "
                        f"{len(blocked_sell_events) - 40} more blocked sell events"
                    ),
                    level="WARNING",
                    task_id=task_id,
                    symbol=symbol,
                )

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
            maybe_trade_stats = strategy_instance.analyzers.trade_stats.get_analysis()
            if isinstance(maybe_trade_stats, dict):
                trade_stats = maybe_trade_stats
            else:
                trade_stats = {}
        except Exception:
            trade_stats = {}

        try:
            maybe_drawdown = strategy_instance.analyzers.drawdown.get_analysis()
            if isinstance(maybe_drawdown, dict):
                drawdown_stats = maybe_drawdown
            else:
                drawdown_stats = {}
        except Exception:
            drawdown_stats = {}

        try:
            maybe_sharpe = strategy_instance.analyzers.sharpe.get_analysis()
            if isinstance(maybe_sharpe, dict):
                sharpe_stats = maybe_sharpe
            else:
                sharpe_stats = {}
        except Exception:
            sharpe_stats = {}
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
    initial_capital = float(config.get("initial_capital", 0.0) or 0.0)
    net_pnl = final_value - initial_capital if initial_capital else None
    return_pct = ((net_pnl / initial_capital) * 100.0) if initial_capital and net_pnl is not None else None
    won = int(trade_stats.get("won", {}).get("total", 0)) if isinstance(trade_stats, dict) else 0
    lost = int(trade_stats.get("lost", {}).get("total", 0)) if isinstance(trade_stats, dict) else 0
    gross_profit = float(trade_stats.get("won", {}).get("pnl", {}).get("total", 0.0)) if isinstance(trade_stats, dict) else 0.0
    gross_loss_raw = float(trade_stats.get("lost", {}).get("pnl", {}).get("total", 0.0)) if isinstance(trade_stats, dict) else 0.0
    gross_loss = abs(gross_loss_raw)
    trade_count = len(closed_trades)
    win_rate = (won / trade_count * 100.0) if trade_count > 0 else 0.0
    max_drawdown = None
    try:
        max_drawdown = float(drawdown_stats.get("max", {}).get("drawdown")) if isinstance(drawdown_stats, dict) else None
    except Exception:
        max_drawdown = None
    sharpe_ratio = None
    try:
        raw_sharpe = sharpe_stats.get("sharperatio") if isinstance(sharpe_stats, dict) else None
        sharpe_ratio = float(raw_sharpe) if raw_sharpe is not None else None
    except Exception:
        sharpe_ratio = None
    metrics = {
        "starting_value": initial_capital if initial_capital else None,
        "final_value": final_value,
        "net_pnl": net_pnl,
        "return_pct": return_pct,
        "total_trades": trade_count,
        "winning_trades": won,
        "losing_trades": lost,
        "win_rate": win_rate,
        "profit_factor": (gross_profit / gross_loss) if gross_loss > 0 else None,
        "max_drawdown": max_drawdown,
        "sharpe_ratio": sharpe_ratio,
        "trade_stats": trade_stats if isinstance(trade_stats, dict) else {},
        "drawdown_stats": drawdown_stats if isinstance(drawdown_stats, dict) else {},
        "sharpe_stats": sharpe_stats if isinstance(sharpe_stats, dict) else {},
    }
    return build_success_result(
        symbol=symbol,
        final_value=final_value,
        log_file=str(artifacts["log_file"]),
        metrics=metrics,
        trades=closed_trades,
    )


class _TradeEventAnalyzer(bt.Analyzer):
    def start(self) -> None:
        self.events: list[str] = []

    def notify_trade(self, trade: Any) -> None:
        try:
            if trade.justopened:
                side = "BUY" if trade.size > 0 else "SELL"
                event_time = _format_ist_datetime(bt.num2date(trade.dtopen))
                self.events.append(
                    f"{side} qty={abs(trade.size)} price={float(trade.price):.2f} at {event_time}"
                )
            if trade.isclosed:
                event_time = _format_ist_datetime(bt.num2date(trade.dtclose))
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
        self._open_qty: dict[int, float] = {}

    def notify_trade(self, trade: Any) -> None:
        try:
            if trade.justopened:
                direction = "BUY" if float(trade.size) > 0 else "SELL"
                self._open_dirs[int(trade.ref)] = direction
                self._open_qty[int(trade.ref)] = abs(float(trade.size))

            if not trade.isclosed:
                return

            trade_ref = int(trade.ref)
            direction = self._open_dirs.pop(trade_ref, "BUY")
            qty = abs(float(self._open_qty.pop(trade_ref, 0.0)))
            entry_px = float(trade.price)
            net_pnl = float(getattr(trade, "pnlcomm", 0.0) or 0.0)

            if qty > _POSITION_SIZE_TOLERANCE:
                pnl_per_unit = net_pnl / qty
                if direction == "SELL":
                    # Short trade: profit when exit < entry.
                    exit_px = entry_px - pnl_per_unit
                else:
                    # Long trade: profit when exit > entry.
                    exit_px = entry_px + pnl_per_unit
            else:
                exit_px = entry_px

            if abs(qty - round(qty)) <= _POSITION_SIZE_TOLERANCE:
                qty_value: int | float = int(round(qty))
            else:
                qty_value = round(qty, 6)

            self.rows.append(
                {
                    "Entry Date": _format_ist_datetime(bt.num2date(trade.dtopen)),
                    "Close Date": _format_ist_datetime(bt.num2date(trade.dtclose)),
                    "Symbol": "",
                    "Direction": direction,
                    "Qty": qty_value,
                    "Entry Price": round(entry_px, 2),
                    "Exit Price": round(exit_px, 2),
                    "Gross P&L": round(float(trade.pnl), 2),
                    "Net P&L": round(net_pnl, 2),
                }
            )
        except Exception:
            return

    def get_analysis(self) -> list[dict[str, Any]]:
        return self.rows


def _build_position_guarded_strategy(strategy_class: type[Any]) -> type[Any]:
    class _PositionGuardedStrategy(strategy_class):  # type: ignore[misc, valid-type]
        def _resolve_bool_setting(self, keys: tuple[str, ...]) -> bool:
            for key in keys:
                if hasattr(self, key):
                    value = getattr(self, key)
                    if isinstance(value, bool):
                        return value

            params = getattr(self, "p", None)
            if params is not None:
                for key in keys:
                    if hasattr(params, key):
                        value = getattr(params, key)
                        if isinstance(value, bool):
                            return value
            return False

        def _resolve_short_enabled(self) -> bool:
            return self._resolve_bool_setting(_SHORT_ENABLE_FLAGS)

        def _resolve_short_scaling_enabled(self) -> bool:
            return self._resolve_bool_setting(_SHORT_SCALING_ENABLE_FLAGS)

        def _resolve_sell_data(self, args: tuple[Any, ...], kwargs: dict[str, Any]) -> Any | None:
            if "data" in kwargs and kwargs.get("data") is not None:
                return kwargs.get("data")
            if args:
                candidate = args[0]
                if not isinstance(candidate, (bool, int, float, str)):
                    return candidate
            return None

        def _position_size_for_data(self, data_obj: Any | None) -> float:
            try:
                if data_obj is not None and hasattr(self, "getposition"):
                    position = self.getposition(data=data_obj)
                else:
                    position = self.position
            except Exception:
                position = self.position
            try:
                return float(getattr(position, "size", 0.0) or 0.0)
            except Exception:
                return 0.0

        def _describe_data_label(self, data_obj: Any | None) -> str:
            if data_obj is None:
                return "default"

            raw_name: Any | None = None
            try:
                raw_name = getattr(data_obj, "_name", None)
            except Exception:
                raw_name = None

            if isinstance(raw_name, str) and raw_name.strip():
                return raw_name.strip()

            try:
                raw_data_name = getattr(data_obj, "_dataname", None)
            except Exception:
                raw_data_name = None

            if isinstance(raw_data_name, str) and raw_data_name.strip():
                return raw_data_name.strip()

            if raw_data_name is not None:
                return type(raw_data_name).__name__

            return type(data_obj).__name__

        def _record_blocked_sell(
            self,
            *,
            position_size: float,
            short_enabled: bool,
            short_scaling_enabled: bool,
            reason: str,
            data_obj: Any | None,
        ) -> None:
            events = getattr(self, "_position_guard_events", None)
            if not isinstance(events, list):
                events = []
                setattr(self, "_position_guard_events", events)

            timestamp = "N/A"
            try:
                timestamp = _format_ist_datetime(self.datetime.datetime(0))
            except Exception:
                pass

            data_label = self._describe_data_label(data_obj)

            events.append(
                "[OrderGuard] Blocked sell order "
                f"at {timestamp} (data={data_label}, position_size={position_size}, "
                f"short_enabled={short_enabled}, "
                f"short_scaling_enabled={short_scaling_enabled}, "
                f"reason={reason})."
            )

        def _record_sell_interpretation(
            self,
            *,
            message: str,
            position_size: float,
            short_enabled: bool,
            short_scaling_enabled: bool,
            data_obj: Any | None,
        ) -> None:
            events = getattr(self, "_position_guard_events", None)
            if not isinstance(events, list):
                events = []
                setattr(self, "_position_guard_events", events)

            timestamp = "N/A"
            try:
                timestamp = _format_ist_datetime(self.datetime.datetime(0))
            except Exception:
                pass

            data_label = self._describe_data_label(data_obj)

            events.append(
                f"{message} at {timestamp} "
                f"(data={data_label}, position_size={position_size}, "
                f"short_enabled={short_enabled}, "
                f"short_scaling_enabled={short_scaling_enabled})."
            )

        def sell(self, *args: Any, **kwargs: Any) -> Any:
            data_obj = self._resolve_sell_data(args, kwargs)
            position_size = self._position_size_for_data(data_obj)
            short_enabled = self._resolve_short_enabled()
            short_scaling_enabled = self._resolve_short_scaling_enabled()

            if position_size > _POSITION_SIZE_TOLERANCE:
                self._record_sell_interpretation(
                    message="[OrderGuard] SELL interpreted as LONG EXIT",
                    position_size=position_size,
                    short_enabled=short_enabled,
                    short_scaling_enabled=short_scaling_enabled,
                    data_obj=data_obj,
                )
                return super().sell(*args, **kwargs)

            if abs(position_size) <= _POSITION_SIZE_TOLERANCE and short_enabled:
                self._record_sell_interpretation(
                    message="[OrderGuard] SELL interpreted as SHORT ENTRY",
                    position_size=position_size,
                    short_enabled=short_enabled,
                    short_scaling_enabled=short_scaling_enabled,
                    data_obj=data_obj,
                )
                return super().sell(*args, **kwargs)

            if position_size < -_POSITION_SIZE_TOLERANCE and short_scaling_enabled:
                self._record_sell_interpretation(
                    message="[OrderGuard] SELL interpreted as SHORT ENTRY",
                    position_size=position_size,
                    short_enabled=short_enabled,
                    short_scaling_enabled=short_scaling_enabled,
                    data_obj=data_obj,
                )
                return super().sell(*args, **kwargs)

            if abs(position_size) <= _POSITION_SIZE_TOLERANCE:
                reason = "flat-position-short-disabled"
            elif position_size < 0:
                reason = "short-position-scaling-disabled"
            else:
                reason = "sell-not-allowed"

            self._record_blocked_sell(
                position_size=position_size,
                short_enabled=short_enabled,
                short_scaling_enabled=short_scaling_enabled,
                reason=reason,
                data_obj=data_obj,
            )
            return None

    _PositionGuardedStrategy.__name__ = f"{strategy_class.__name__}PositionGuarded"
    _PositionGuardedStrategy.__qualname__ = _PositionGuardedStrategy.__name__
    return _PositionGuardedStrategy


def _reset_cerebro_broker_state(
    cerebro: bt.Cerebro,
    *,
    initial_capital: float,
    commission: float,
    slippage: float,
    terminal: Any | None,
    task_id: str | None,
    symbol: str,
) -> None:
    try:
        # Fresh broker instance avoids carry-over state between runs.
        cerebro.broker = bt.brokers.BackBroker()
    except Exception:
        pass

    cerebro.broker.setcash(float(initial_capital))
    cerebro.broker.setcommission(commission=float(commission))
    if slippage > 0:
        cerebro.broker.set_slippage_perc(
            perc=float(slippage),
            slip_open=True,
            slip_limit=True,
            slip_match=True,
            slip_out=False,
        )
    _log_terminal(
        terminal,
        "Broker state reset for isolated run",
        task_id=task_id,
        symbol=symbol,
    )


def _run_cerebro_with_isolation(
    cerebro: bt.Cerebro,
    *,
    terminal: Any | None,
    task_id: str | None,
    symbol: str,
) -> list[Any]:
    try:
        with warnings.catch_warnings(record=True) as captured_warnings:
            warnings.simplefilter("always")
            results = cerebro.run()
    except Exception as exc:
        trace = traceback.format_exc()
        print(trace)
        _log_terminal(
            terminal,
            f"Backtrader sandbox trapped exception: {type(exc).__name__}: {exc}",
            level="ERROR",
            task_id=task_id,
            symbol=symbol,
        )
        _log_terminal(
            terminal,
            trace,
            level="ERROR",
            task_id=task_id,
            symbol=symbol,
        )
        raise RuntimeError(f"Strategy execution failed: {type(exc).__name__}: {exc}") from exc

    if captured_warnings:
        max_warning_logs = 25
        for warning_item in captured_warnings[:max_warning_logs]:
            warning_msg = str(getattr(warning_item, "message", "") or "").strip()
            warning_category = getattr(getattr(warning_item, "category", None), "__name__", "Warning")
            warning_file = str(getattr(warning_item, "filename", "") or "")
            warning_line = int(getattr(warning_item, "lineno", 0) or 0)
            location = f"{Path(warning_file).name}:{warning_line}" if warning_file else f"line:{warning_line}"
            _log_terminal(
                terminal,
                f"[Backtrader Warning] {warning_category} at {location}: {warning_msg}",
                level="WARNING",
                task_id=task_id,
                symbol=symbol,
            )

        if len(captured_warnings) > max_warning_logs:
            _log_terminal(
                terminal,
                (
                    "[Backtrader Warning] "
                    f"{len(captured_warnings) - max_warning_logs} additional warnings suppressed"
                ),
                level="WARNING",
                task_id=task_id,
                symbol=symbol,
            )

    if not isinstance(results, list):
        raise RuntimeError("Strategy execution failed: Backtrader returned invalid result payload")
    return results


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


def _prepare_dataframe_for_backtrader(
    data_df: pd.DataFrame,
    *,
    enforce_market_hours: bool,
    terminal: Any | None,
    task_id: str | None,
    symbol: str,
) -> pd.DataFrame:
    prepared_df = data_df.copy()
    if prepared_df.empty:
        return prepared_df

    prepared_df.index = _to_ist_index(prepared_df.index)
    prepared_df = prepared_df[~prepared_df.index.isna()]
    if prepared_df.empty:
        raise ValueError("No valid datetime index values after parsing")
    prepared_df = prepared_df.sort_index()
    prepared_df = prepared_df[~prepared_df.index.duplicated(keep="first")]

    if enforce_market_hours and _should_filter_market_hours(prepared_df.index):
        prepared_df = prepared_df.between_time(
            _MARKET_OPEN_TIME.strftime("%H:%M"),
            _MARKET_CLOSE_TIME.strftime("%H:%M"),
        )
        _assert_market_hours(prepared_df.index)
    elif not enforce_market_hours:
        _log_terminal(
            terminal,
            "market hour filter skipped",
            task_id=task_id,
            symbol=symbol,
        )

    if prepared_df.empty:
        raise ValueError("No rows remain after market hour filtering")

    if prepared_df.index.tz is not None:
        # Feed Backtrader as naive UTC so bt.num2date outputs can be safely mapped back to IST.
        prepared_df.index = prepared_df.index.tz_convert("UTC").tz_localize(None)

    return prepared_df


def _to_ist_index(index: pd.Index) -> pd.DatetimeIndex:
    parsed_values: list[pd.Timestamp] = []
    timezone_flags: list[bool] = []
    for raw_value in list(index):
        parsed = pd.to_datetime(raw_value, errors="coerce")
        if pd.isna(parsed):
            continue
        ts = pd.Timestamp(parsed)
        parsed_values.append(ts)
        timezone_flags.append(ts.tzinfo is not None)

    if not parsed_values:
        return pd.DatetimeIndex([], tz=_IST_TIMEZONE)

    has_aware = any(timezone_flags)
    has_naive = any(not flag for flag in timezone_flags)
    if has_aware and has_naive:
        raise ValueError("Mixed timezone data detected in execution index")

    if has_aware:
        converted_values = [ts.tz_convert(_IST_TIMEZONE) for ts in parsed_values]
    else:
        # Naive timestamps are assumed to already be IST.
        converted_values = [ts.tz_localize(_IST_TIMEZONE) for ts in parsed_values]

    converted = pd.DatetimeIndex(converted_values)
    if converted.tz is None:
        raise ValueError("Failed to normalize execution index timezone")
    return converted


def _should_filter_market_hours(index: pd.DatetimeIndex) -> bool:
    if not isinstance(index, pd.DatetimeIndex) or index.empty:
        return False

    unique_times = {
        (ts.hour, ts.minute, ts.second, ts.microsecond)
        for ts in index
    }
    if len(unique_times) == 1:
        only_time = next(iter(unique_times))
        if only_time in {(0, 0, 0, 0), (5, 30, 0, 0)}:
            return False
    return True


def _assert_market_hours(index: pd.DatetimeIndex) -> None:
    if not isinstance(index, pd.DatetimeIndex) or index.empty:
        return
    index_times = pd.Series(index.time)
    valid = (
        (index_times >= _MARKET_OPEN_TIME)
        & (index_times <= _MARKET_CLOSE_TIME)
    )
    if not bool(valid.all()):
        raise ValueError("Detected timestamps outside market hours (09:15 to 15:30 IST)")


__all__ = [
    "build_failed_result",
    "build_success_result",
    "execute_backtest_dataframe",
    "extract_runtime_config",
    "validate_result",
    "validate_strategy_class",
]
