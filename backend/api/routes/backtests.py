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
    return {"results": results}


@router.get("/backtests/{task_id}")
async def get_backtest(task_id: str):
    """Get a specific backtest result."""
    result = await backtest_repository.get_by_id(task_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Backtest not found")
    return result


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
                await backtest_repository.update_result(task_id, {
                    "status": "COMPLETED",
                    "final_value": result.get("final_value"),
                    "metrics": result.get("metrics", {}),
                    "trades": result.get("trades", []),
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
