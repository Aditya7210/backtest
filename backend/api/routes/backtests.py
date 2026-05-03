"""Backtest REST routes - submit, list, get results."""
from __future__ import annotations

import asyncio
import importlib.util
import uuid
from typing import Any

import pandas as pd
from fastapi import APIRouter, BackgroundTasks, HTTPException

from backend.database.repositories import backtest_repository, bar_repository, strategy_repository
from backend.models.backtest import BacktestRequest

router = APIRouter(tags=["backtests"])


def _to_float(value: Any) -> float | None:
    try:
        num = float(value)
    except Exception:
        return None
    return num


def _normalize_trade_rows(raw_rows: Any) -> list[dict[str, Any]]:
    if not isinstance(raw_rows, list):
        return []
    normalized: list[dict[str, Any]] = []
    for row in raw_rows:
        if not isinstance(row, dict):
            continue
        direction_raw = str(
            row.get("direction")
            or row.get("Direction")
            or row.get("side")
            or "LONG",
        ).upper()
        direction = "SHORT" if "SHORT" in direction_raw or direction_raw == "SELL" else "LONG"
        entry_action = str(row.get("entry_action") or ("BUY" if direction == "LONG" else "SELL_SHORT")).upper()
        exit_action = str(row.get("exit_action") or ("SELL_EXIT" if direction == "LONG" else "BUY_COVER")).upper()
        normalized.append({
            "trade_id": str(row.get("trade_id") or ""),
            "instrument_token": row.get("instrument_token"),
            "symbol": str(row.get("symbol") or row.get("Symbol") or ""),
            "entry_date": str(row.get("entry_date") or row.get("Entry Date") or row.get("entryDate") or ""),
            "exit_date": str(row.get("exit_date") or row.get("Close Date") or row.get("Exit Date") or ""),
            "direction": direction,
            "entry_action": entry_action,
            "exit_action": exit_action,
            "entry_price": _to_float(row.get("entry_price") or row.get("Entry Price") or row.get("entryPrice")) or 0.0,
            "exit_price": _to_float(row.get("exit_price") or row.get("Exit Price") or row.get("exitPrice")) or 0.0,
            "pnl": _to_float(row.get("pnl") or row.get("Net P&L") or row.get("net_pnl") or row.get("Gross P&L")) or 0.0,
            "size": _to_float(row.get("size") or row.get("Qty") or row.get("qty") or row.get("quantity")) or 0.0,
            "gross_pnl": _to_float(row.get("gross_pnl") or row.get("Gross P&L")) or 0.0,
            "net_pnl": _to_float(row.get("net_pnl") or row.get("Net P&L") or row.get("pnl")) or 0.0,
            "commission": _to_float(row.get("commission")) or 0.0,
            "bars_held": int(_to_float(row.get("bars_held")) or 0),
            "status": str(row.get("status") or "CLOSED"),
            "position_before_entry": _to_float(row.get("position_before_entry")),
            "position_after_entry": _to_float(row.get("position_after_entry")),
            "position_before_exit": _to_float(row.get("position_before_exit")),
            "position_after_exit": _to_float(row.get("position_after_exit")),
        })
    return normalized


def _normalize_order_events(raw_rows: Any) -> list[dict[str, Any]]:
    if not isinstance(raw_rows, list):
        return []
    normalized: list[dict[str, Any]] = []
    for row in raw_rows:
        if not isinstance(row, dict):
            continue
        normalized.append(
            {
                "event_id": str(row.get("event_id") or ""),
                "time": str(row.get("time") or ""),
                "action": str(row.get("action") or ""),
                "status": str(row.get("status") or ""),
                "requested_size": _to_float(row.get("requested_size")),
                "executed_size": _to_float(row.get("executed_size")),
                "price": _to_float(row.get("price")),
                "reason": str(row.get("reason") or "") or None,
                "position_before": _to_float(row.get("position_before")),
                "position_after": _to_float(row.get("position_after")),
                "cash_before": _to_float(row.get("cash_before")),
                "cash_after": _to_float(row.get("cash_after")),
            }
        )
    return normalized


def _build_metrics(
    *,
    runtime_metrics: Any,
    config: dict[str, Any],
    final_value: float | None,
    trades: list[dict[str, Any]],
) -> dict[str, Any]:
    metrics = dict(runtime_metrics) if isinstance(runtime_metrics, dict) else {}
    initial_capital = _to_float(config.get("initial_capital")) or 0.0
    if final_value is not None:
        metrics.setdefault("final_value", float(final_value))
    metrics.setdefault("starting_value", float(initial_capital) if initial_capital else None)

    if initial_capital and final_value is not None:
        net_pnl = float(final_value) - float(initial_capital)
        return_pct = (net_pnl / float(initial_capital)) * 100.0
        metrics.setdefault("net_pnl", net_pnl)
        metrics.setdefault("return_pct", return_pct)

    if trades:
        total = len(trades)
        wins = sum(1 for trade in trades if _to_float(trade.get("net_pnl", trade.get("pnl"))) and float(trade.get("net_pnl", trade.get("pnl", 0))) > 0)
        losses = sum(1 for trade in trades if _to_float(trade.get("net_pnl", trade.get("pnl"))) and float(trade.get("net_pnl", trade.get("pnl", 0))) < 0)
        gross_profit = sum(float(trade.get("net_pnl", trade.get("pnl", 0))) for trade in trades if float(trade.get("net_pnl", trade.get("pnl", 0))) > 0)
        gross_loss = abs(sum(float(trade.get("net_pnl", trade.get("pnl", 0))) for trade in trades if float(trade.get("net_pnl", trade.get("pnl", 0))) < 0))
        metrics.setdefault("total_trades", total)
        metrics.setdefault("winning_trades", wins)
        metrics.setdefault("losing_trades", losses)
        metrics.setdefault("win_rate", (wins / total * 100.0) if total else 0.0)
        if gross_loss > 0:
            metrics.setdefault("profit_factor", gross_profit / gross_loss)
    return metrics


def _normalize_result_document(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return {}
    out = dict(raw)
    trades_source = (
        out.get("trades")
        or out.get("trade_log")
        or out.get("orders")
        or out.get("transactions")
        or []
    )
    out["trades"] = _normalize_trade_rows(trades_source)
    events_source = out.get("order_events") or out.get("trade_events") or []
    out["order_events"] = _normalize_order_events(events_source)
    out["metrics"] = dict(out.get("metrics") or {})
    out["integrity"] = dict(out.get("integrity") or {})
    out["result_schema_version"] = int(out.get("result_schema_version") or 1)
    if out["result_schema_version"] < 2:
        warnings = out["integrity"].get("warnings")
        warning_list = warnings if isinstance(warnings, list) else []
        if "legacy_trade_direction_ambiguous" not in warning_list:
            warning_list.append("legacy_trade_direction_ambiguous")
        out["integrity"]["warnings"] = warning_list
    return out


@router.post("/backtests/run")
async def run_backtest(
    request: BacktestRequest,
    background_tasks: BackgroundTasks,
):
    """Submit a backtest. Data is always loaded from MongoDB."""
    # Pre-validate data availability before task creation.
    bars = await bar_repository.get_bars(
        token=request.instrument_token,
        timeframe=request.timeframe,
        date_from=request.date_from,
        date_to=request.date_to,
    )
    if not bars:
        raise HTTPException(
            status_code=422,
            detail="No data found for the selected instrument/timeframe/date range.",
        )

    task_id = str(uuid.uuid4())
    symbol = await bar_repository.get_symbol_for_token(request.instrument_token) or ""

    data_selection = {
        "instrument_token": request.instrument_token,
        "tradingsymbol": symbol,
        "timeframe": request.timeframe,
        "date_from": request.date_from,
        "date_to": request.date_to,
    }

    config = {
        "task_id": task_id,
        "strategy_name": request.strategy_name,
        "strategy_id": request.strategy_id,
        "strategy_class_name": request.strategy_class_name,
        "symbol": symbol,
        "data_selection": data_selection,
        "initial_capital": request.initial_capital,
        "commission": request.commission,
        "slippage": request.slippage,
        "lot_size": request.lot_size,
        "position_size": request.position_size,
        "max_positions": request.max_positions,
        "execution_mode": request.execution_mode,
        "max_retries": max(0, int(request.max_retries)),
        "task_timeout_seconds": max(10, int(request.task_timeout_seconds)),
        "enforce_market_hours": request.enforce_market_hours,
    }

    await backtest_repository.create(task_id, config)
    background_tasks.add_task(_run_backtest_background, task_id, config)
    return {"task_id": task_id, "status": "PENDING"}


@router.get("/backtests")
async def list_backtests():
    """List all backtest results."""
    results = await backtest_repository.get_all()
    return {"results": [_normalize_result_document(row) for row in results]}


@router.get("/backtests/{task_id}")
async def get_backtest(task_id: str):
    """Get a specific backtest result."""
    result = await backtest_repository.get_by_id(task_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Backtest not found")
    return _normalize_result_document(result)


def _resolve_strategy_class(mod: Any, requested_name: str | None) -> type[Any] | None:
    import backtrader as bt

    candidates: dict[str, type[Any]] = {}
    for attr_name in dir(mod):
        attr = getattr(mod, attr_name)
        if isinstance(attr, type) and issubclass(attr, bt.Strategy) and attr is not bt.Strategy:
            candidates[attr_name] = attr

    if not candidates:
        return None
    if requested_name:
        return candidates.get(requested_name)
    # Backward compatibility: use first discovered class if not explicitly selected.
    return next(iter(candidates.values()))


async def _run_backtest_background(task_id: str, config: dict[str, Any]) -> None:
    """Execute backtest in background. Loads data from MongoDB and runs Backtrader."""
    try:
        await backtest_repository.set_status(task_id, "RUNNING")
        await backtest_repository.append_log(task_id, "Backtest started.")

        ds = config["data_selection"]
        bars = await bar_repository.get_bars(
            token=ds["instrument_token"],
            timeframe=ds["timeframe"],
            date_from=ds["date_from"],
            date_to=ds["date_to"],
        )
        if not bars:
            await backtest_repository.append_log(task_id, "No bars found for selection.", "ERROR")
            await backtest_repository.update_result(task_id, {
                "status": "FAILED",
                "error_message": "No data found for the specified instrument/timeframe/date range.",
            })
            return

        await backtest_repository.append_log(task_id, f"Loaded {len(bars)} bars from MongoDB.")

        df = pd.DataFrame(bars)
        df = df.rename(columns={
            "timestamp": "Date",
            "open": "Open",
            "high": "High",
            "low": "Low",
            "close": "Close",
            "volume": "Volume",
        })
        df["Date"] = pd.to_datetime(df["Date"])
        df = df.set_index("Date").sort_index()
        if df.index.tz is None:
            df.index = df.index.tz_localize("UTC").tz_convert("Asia/Kolkata")
        else:
            df.index = df.index.tz_convert("Asia/Kolkata")

        strategy_name = config["strategy_name"]
        strategy_path = strategy_repository.resolve_strategy_path(
            strategy_id=config.get("strategy_id"),
            name=strategy_name,
        )
        if strategy_path is None or not strategy_path.is_file():
            await backtest_repository.append_log(task_id, f"Strategy file not found: {strategy_name}.py", "ERROR")
            await backtest_repository.update_result(task_id, {
                "status": "FAILED",
                "error_message": f"Strategy file not found: {strategy_name}.py",
            })
            return

        spec = importlib.util.spec_from_file_location(strategy_name, strategy_path)
        if spec is None or spec.loader is None:
            raise ImportError(f"Cannot load strategy module: {strategy_name}")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        strategy_class = _resolve_strategy_class(mod, config.get("strategy_class_name"))
        if strategy_class is None:
            await backtest_repository.append_log(
                task_id,
                f"No bt.Strategy subclass found in {strategy_name}.py",
                "ERROR",
            )
            await backtest_repository.update_result(task_id, {
                "status": "FAILED",
                "error_message": f"No bt.Strategy subclass found in {strategy_name}.py",
            })
            return

        await backtest_repository.append_log(task_id, f"Selected strategy class: {strategy_class.__name__}")

        from Backtesting.backtest_core import (
            execute_backtest_dataframe,
            extract_runtime_config,
            validate_strategy_class,
        )

        validated_class = validate_strategy_class(strategy_class)
        runtime_config = extract_runtime_config({
            "initial_capital": config.get("initial_capital", 100000),
            "commission": config.get("commission", 0.0003),
            "slippage": config.get("slippage", 0.0),
            "lot_size": config.get("lot_size", 1),
            "position_size": config.get("position_size", 1),
            "max_positions": config.get("max_positions", 1),
            "execution_mode": config.get("execution_mode", "market"),
            "enforce_market_hours": config.get("enforce_market_hours", True),
        })

        max_retries = int(config.get("max_retries", 0))
        timeout_seconds = int(config.get("task_timeout_seconds", 300))
        symbol = config.get("symbol", "")

        async def _execute_once() -> dict[str, Any]:
            return await asyncio.to_thread(
                execute_backtest_dataframe,
                data_df=df[["Open", "High", "Low", "Close", "Volume"]],
                symbol=symbol,
                strategy_class=validated_class,
                config=runtime_config,
            )

        last_error: Exception | None = None
        for attempt in range(max_retries + 1):
            try:
                await backtest_repository.append_log(
                    task_id,
                    f"Execution attempt {attempt + 1} of {max_retries + 1}.",
                )
                result = await asyncio.wait_for(_execute_once(), timeout=timeout_seconds)
                await backtest_repository.append_log(task_id, "Backtest completed successfully.", "SUCCESS")
                final_value = _to_float(result.get("final_value"))
                normalized_trades = _normalize_trade_rows(
                    result.get("trades")
                    or result.get("closed_trades")
                    or result.get("trade_log")
                    or [],
                )
                normalized_events = _normalize_order_events(
                    result.get("order_events")
                    or result.get("trade_events")
                    or [],
                )
                integrity = result.get("integrity") if isinstance(result.get("integrity"), dict) else {}
                metrics = _build_metrics(
                    runtime_metrics=result.get("metrics"),
                    config=config,
                    final_value=final_value,
                    trades=normalized_trades,
                )
                await backtest_repository.update_result(task_id, {
                    "status": "COMPLETED",
                    "final_value": final_value,
                    "metrics": metrics,
                    "trades": normalized_trades,
                    "order_events": normalized_events,
                    "integrity": integrity,
                    "result_schema_version": int(result.get("result_schema_version", 2) or 2),
                })
                return
            except asyncio.TimeoutError as exc:
                last_error = exc
                await backtest_repository.append_log(
                    task_id,
                    f"Execution timed out after {timeout_seconds}s.",
                    "ERROR",
                )
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                await backtest_repository.append_log(
                    task_id,
                    f"{type(exc).__name__}: {exc}",
                    "ERROR",
                )

        if last_error is None:
            error_message = "Backtest execution failed."
        elif isinstance(last_error, asyncio.TimeoutError):
            error_message = f"Execution timed out after {timeout_seconds} seconds."
        else:
            error_message = f"{type(last_error).__name__}: {last_error}"

        await backtest_repository.append_log(task_id, error_message, "ERROR")
        await backtest_repository.update_result(task_id, {
            "status": "FAILED",
            "error_message": error_message,
        })
    except Exception as exc:  # noqa: BLE001
        await backtest_repository.append_log(task_id, f"Fatal execution error: {type(exc).__name__}: {exc}", "ERROR")
        await backtest_repository.update_result(task_id, {
            "status": "FAILED",
            "error_message": f"{type(exc).__name__}: {exc}",
        })
