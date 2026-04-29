from __future__ import annotations

import copy
from datetime import datetime, timezone
import json
import multiprocessing
from pathlib import Path
import queue as std_queue
import threading
import time
import traceback
from typing import Any

from Backtesting.backtest_core import build_failed_result, validate_result
from Backtesting.execution_engine import ExecutionEngine
from Backtesting.performance_tracker import PerformanceTracker


class _SubprocessTerminal:
    def __init__(self, max_lines: int = 1500) -> None:
        self.logs: list[dict[str, str | None]] = []
        self.max_lines = max(100, int(max_lines))

    def log(
        self,
        message: str,
        level: str = "INFO",
        task_id: str | None = None,
        symbol: str | None = None,
    ) -> None:
        self.logs.append(
            {
                "message": str(message or "").strip() or "(empty message)",
                "level": str(level or "INFO").strip().upper() or "INFO",
                "task_id": str(task_id).strip() if task_id else None,
                "symbol": str(symbol).strip().upper() if symbol else None,
            }
        )
        if len(self.logs) > self.max_lines:
            self.logs = self.logs[-self.max_lines :]


def _execute_task_in_subprocess(
    result_queue: Any,
    *,
    base_config: dict[str, Any],
    mode: str,
    task: dict[str, Any],
    task_id: str,
) -> None:
    subprocess_terminal = _SubprocessTerminal()
    try:
        execution_task = dict(task) if isinstance(task, dict) else {}
        if not isinstance(execution_task.get("strategy_class"), type):
            strategy_file = str(execution_task.get("strategy_file_path") or "").strip()
            strategy_class_name = str(execution_task.get("strategy_class_name") or "").strip()
            if strategy_file and strategy_class_name:
                from Dashboard.Backtesting_page.Features import backtest_data_service

                safe_strategy_path = backtest_data_service.resolve_strategy_file_path(
                    strategy_file
                )
                execution_task["strategy_class"] = backtest_data_service.load_strategy_class(
                    str(safe_strategy_path),
                    strategy_class_name,
                )

        engine = ExecutionEngine(
            base_config=dict(base_config) if isinstance(base_config, dict) else {},
            terminal=subprocess_terminal,
        )
        result = engine.execute(
            task=execution_task,
            task_id=str(task_id or ""),
            mode=str(mode or "").strip().lower(),
        )
        result_queue.put(
            {
                "ok": True,
                "result": result,
                "logs": subprocess_terminal.logs,
            }
        )
    except Exception as exc:
        subprocess_terminal.log(
            f"Task subprocess crashed: {type(exc).__name__}: {exc}",
            level="ERROR",
            task_id=str(task_id or ""),
        )
        result_queue.put(
            {
                "ok": False,
                "error": f"{type(exc).__name__}: {exc}",
                "traceback": traceback.format_exc(),
                "logs": subprocess_terminal.logs,
            }
        )


class ExecutionManager:
    def __init__(
        self,
        config: dict[str, Any] | None = None,
        terminal: Any | None = None,
        *,
        store_path: str | Path | None = None,
        metrics_path: str | Path | None = None,
        poll_interval_seconds: float = 0.2,
        worker_count: int = 3,
    ) -> None:
        self._config = dict(config) if isinstance(config, dict) else {}
        self._terminal = terminal
        self._poll_interval_seconds = max(0.05, float(poll_interval_seconds))
        requested_worker_count = self._config.get("worker_count", worker_count)
        try:
            self._worker_count = max(1, int(requested_worker_count))
        except (TypeError, ValueError):
            self._worker_count = 3

        default_store_path = (
            Path(__file__).resolve().parents[1]
            / "Data"
            / "Logs"
            / "task_store.json"
        )
        self._store_path = (
            Path(store_path).resolve()
            if store_path is not None
            else default_store_path.resolve()
        )
        self._store_path.parent.mkdir(parents=True, exist_ok=True)

        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self.workers: list[threading.Thread] = []
        self._on_task_update: Any = None
        self._execution_engine = ExecutionEngine(
            base_config=self._config,
            terminal=self._terminal,
        )
        resolved_metrics_path = metrics_path
        if resolved_metrics_path is None:
            resolved_metrics_path = self._config.get("metrics_path")
        self._performance_tracker = PerformanceTracker(
            metrics_path=resolved_metrics_path,
        )

        self._queue: list[dict[str, Any]] = []
        self._results_by_task_id: dict[str, dict[str, Any]] = {}
        self._task_counter = 0
        self._load_store()

    def set_terminal(self, terminal: Any | None) -> None:
        with self._lock:
            self._terminal = terminal
            self._execution_engine.set_terminal(terminal)

    def add_task(self, task: dict[str, Any]) -> str:
        if not isinstance(task, dict):
            raise ValueError("Task must be a dictionary")

        with self._lock:
            self._task_counter += 1
            task_id = f"TASK-{self._task_counter:04d}"
            queue_task = copy.deepcopy(task)
            queue_task.setdefault("task_id", task_id)
            created_at = self._utc_iso_now()

            queue_item = {
                "task_id": task_id,
                "task": queue_task,
                "created_at": created_at,
                "status": "PENDING",
                "result": None,
                "start_time": None,
                "end_time": None,
                "execution_time": 0.0,
                "retries": 0,
            }
            self._queue.append(queue_item)
            self._save_store_locked()

        symbol = str(task.get("symbol") or "UNKNOWN").strip().upper() or "UNKNOWN"
        self._log(
            f"Queued task {task_id} for {symbol}",
            level="INFO",
            task_id=task_id,
            symbol=symbol,
        )
        return task_id

    def clear_tasks(self) -> None:
        with self._lock:
            self._queue.clear()
            self._results_by_task_id.clear()
            self._task_counter = 0
            self._save_store_locked()

    def get_queue_snapshot(self) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(item) for item in self._queue]

    def get_results(self) -> dict[str, dict[str, Any]]:
        with self._lock:
            return {
                task_id: dict(result)
                for task_id, result in self._results_by_task_id.items()
            }

    def get_ordered_results(self) -> list[dict[str, Any]]:
        with self._lock:
            ordered_results: list[dict[str, Any]] = []
            for item in self._queue:
                stored_result = item.get("result")
                if isinstance(stored_result, dict):
                    ordered_results.append(dict(stored_result))
            return ordered_results

    def get_performance_metrics(self) -> dict[str, Any]:
        return self._performance_tracker.get_metrics_snapshot()

    def has_active_tasks(self) -> bool:
        with self._lock:
            return any(
                item.get("status") in {"PENDING", "RUNNING"}
                for item in self._queue
            )

    def start_workers(
        self,
        on_task_update: Any = None,
        worker_count: int | None = None,
    ) -> int:
        with self._lock:
            if callable(on_task_update):
                self._on_task_update = on_task_update

            active_workers = [worker for worker in self.workers if worker.is_alive()]
            if active_workers:
                self.workers = active_workers
                return len(active_workers)

            if worker_count is not None:
                try:
                    self._worker_count = max(1, int(worker_count))
                except (TypeError, ValueError):
                    self._worker_count = 3

            self._stop_event.clear()
            self.workers = []
            for worker_index in range(self._worker_count):
                worker_thread = threading.Thread(
                    target=self._worker_loop,
                    args=(worker_index + 1,),
                    name=f"BacktestExecutionWorker-{worker_index + 1}",
                    daemon=True,
                )
                worker_thread.start()
                self.workers.append(worker_thread)

        self._log(
            f"Execution workers started (count={len(self.workers)})",
            level="INFO",
        )
        return len(self.workers)

    def stop_workers(self, timeout_seconds: float = 3.0) -> None:
        self._stop_event.set()
        workers = list(self.workers)
        was_running = any(worker.is_alive() for worker in workers)
        join_timeout = max(0.1, float(timeout_seconds))
        for worker in workers:
            if worker.is_alive():
                worker.join(timeout=join_timeout)
        with self._lock:
            self.workers = []
        if was_running:
            self._log("Execution workers stopped", level="WARNING")

    def get_active_workers(self) -> int:
        with self._lock:
            self.workers = [worker for worker in self.workers if worker.is_alive()]
            return len(self.workers)

    def start_worker(self, on_task_update: Any = None) -> bool:
        return self.start_workers(on_task_update=on_task_update) > 0

    def stop_worker(self, timeout_seconds: float = 3.0) -> None:
        self.stop_workers(timeout_seconds=timeout_seconds)

    def is_worker_running(self) -> bool:
        return self.get_active_workers() > 0

    def run_next(self, on_task_update: Any = None) -> dict[str, Any] | None:
        if callable(on_task_update):
            with self._lock:
                self._on_task_update = on_task_update

        queue_item = self._pick_next_pending_task()
        if queue_item is None:
            return None
        return self._process_queue_item(queue_item)

    def run(
        self,
        on_task_update: Any = None,
        max_tasks: int | None = None,
    ) -> list[dict[str, Any]]:
        processed_count = 0
        while True:
            if max_tasks is not None and processed_count >= max_tasks:
                break
            result = self.run_next(on_task_update=on_task_update)
            if result is None:
                break
            processed_count += 1
        return self.get_ordered_results()

    def _worker_loop(self, worker_id: int) -> None:
        while not self._stop_event.is_set():
            try:
                queue_item = self._pick_next_pending_task()
                if queue_item is None:
                    time.sleep(self._poll_interval_seconds)
                    continue
                self._process_queue_item(queue_item)
            except Exception as exc:
                self._log(
                    f"Worker {worker_id} loop error: {exc}",
                    level="ERROR",
                )
                time.sleep(self._poll_interval_seconds)

    def _pick_next_pending_task(self) -> dict[str, Any] | None:
        with self._lock:
            pending_items = [
                item for item in self._queue if item.get("status") == "PENDING"
            ]
            queue_item = (
                sorted(
                    pending_items,
                    key=lambda item: (
                        str(item.get("created_at") or ""),
                        str(item.get("task_id") or ""),
                    ),
                )[0]
                if pending_items
                else None
            )
            if queue_item is None:
                return None

            task_id = str(queue_item["task_id"])
            task = queue_item.get("task", {})
            symbol = str(task.get("symbol") or task_id).strip().upper() or task_id

            queue_item["status"] = "RUNNING"
            queue_item["start_time"] = self._utc_iso_now()
            queue_item["end_time"] = None
            queue_item["execution_time"] = 0.0
            queue_item["retries"] = 0
            self._save_store_locked()

        self._log(
            f"Starting {symbol}",
            level="INFO",
            task_id=task_id,
            symbol=symbol,
        )
        self._emit_update(task_id, "RUNNING")
        return queue_item

    def _process_queue_item(self, queue_item: dict[str, Any]) -> dict[str, Any]:
        task_id = str(queue_item.get("task_id") or "")
        task = queue_item.get("task") if isinstance(queue_item.get("task"), dict) else {}
        symbol = str(task.get("symbol") or task_id).strip().upper() or task_id
        retry_limit = self._get_retry_limit()
        timeout_seconds = self._get_timeout_seconds()

        task_started_at = time.monotonic()
        final_result = self._execute_with_retries(
            task=task,
            task_id=task_id,
            symbol=symbol,
            retry_limit=retry_limit,
            timeout_seconds=timeout_seconds,
        )
        total_execution_time = max(0.0, time.monotonic() - task_started_at)
        retries_used = int(final_result.get("retries", 0))
        validated_final_result = validate_result(
            final_result,
            symbol=symbol,
            execution_time=total_execution_time,
            retries=retries_used,
        )
        final_result = self._apply_failure_intelligence(
            validated_final_result,
            symbol=symbol,
            source_result=final_result,
            default_stage="execution",
            default_error_type="SYSTEM_ERROR",
        )
        final_status = str(final_result["status"]).upper()

        with self._lock:
            queue_item["status"] = final_status
            queue_item["result"] = dict(final_result)
            queue_item["end_time"] = self._utc_iso_now()
            queue_item["execution_time"] = float(final_result.get("execution_time", 0.0))
            queue_item["retries"] = int(final_result.get("retries", 0))
            self._results_by_task_id[task_id] = dict(final_result)
            self._save_store_locked()

            created_at = str(queue_item.get("created_at") or "")
            start_time = str(queue_item.get("start_time") or "")
            end_time = str(queue_item.get("end_time") or "")
            execution_time = float(queue_item.get("execution_time") or 0.0)
            retries = int(queue_item.get("retries") or 0)

        self._record_performance_metrics(
            task_id=task_id,
            symbol=symbol,
            status=final_status,
            created_at=created_at,
            start_time=start_time,
            end_time=end_time,
            execution_time=execution_time,
            retries=retries,
            final_result=final_result,
        )
        self._emit_update(task_id, final_status)
        if final_status == "SUCCESS":
            self._log(
                f"{symbol} completed. Value: {final_result.get('final_value')}",
                level="SUCCESS",
                task_id=task_id,
                symbol=symbol,
            )
        else:
            self._log(
                (
                    f"{symbol} failed [{final_result.get('error_type')} @ "
                    f"{final_result.get('stage')}]: {final_result.get('error_message')}"
                ),
                level="ERROR",
                task_id=task_id,
                symbol=symbol,
            )
        return dict(final_result)

    def _execute_with_retries(
        self,
        *,
        task: dict[str, Any],
        task_id: str,
        symbol: str,
        retry_limit: int,
        timeout_seconds: float | None,
    ) -> dict[str, Any]:
        immutable_task = copy.deepcopy(task)
        attempts = retry_limit + 1
        mode = str(immutable_task.get("mode", "")).strip().lower()
        last_result: dict[str, Any] = build_failed_result(symbol, "Execution did not run")

        for attempt_index in range(attempts):
            attempt_started_at = time.monotonic()
            retries_used = attempt_index

            try:
                execution_task = copy.deepcopy(immutable_task)
                execution_task = self._hydrate_strategy_class(execution_task)
            except Exception as exc:
                stage_hint = "validation"
                error_type = self._classify_error_type(exc, stage_hint=stage_hint)
                raw_result = self._build_classified_failure(
                    symbol=symbol,
                    error=exc,
                    error_type=error_type,
                    stage=stage_hint,
                )
                self._log(
                    f"Task validation failed: {self._resolve_error_message(exc)}",
                    level="ERROR",
                    task_id=task_id,
                    symbol=symbol,
                )
            else:
                try:
                    raw_result = self._dispatch_task_with_hard_timeout(
                        mode=mode,
                        task=execution_task,
                        task_id=task_id,
                        symbol=symbol,
                        timeout_seconds=timeout_seconds,
                    )
                except TimeoutError as exc:
                    raw_result = self._build_classified_failure(
                        symbol=symbol,
                        error=exc,
                        error_type="TIMEOUT_ERROR",
                        stage="execution",
                    )
                    self._log(
                        f"Task execution timed out: {self._resolve_error_message(exc)}",
                        level="ERROR",
                        task_id=task_id,
                        symbol=symbol,
                    )
                except Exception as exc:
                    stage_hint = "execution"
                    if "unsupported task mode" in self._resolve_error_message(exc).lower():
                        stage_hint = "validation"
                    error_type = self._classify_error_type(exc, stage_hint=stage_hint)
                    raw_result = self._build_classified_failure(
                        symbol=symbol,
                        error=exc,
                        error_type=error_type,
                        stage=stage_hint,
                    )
                    self._log(
                        f"Task execution crashed: {self._resolve_error_message(exc)}",
                        level="ERROR",
                        task_id=task_id,
                        symbol=symbol,
                    )

            if raw_result is None:
                raw_result = self._build_classified_failure(
                    symbol=symbol,
                    error="Engine returned no result",
                    error_type="SYSTEM_ERROR",
                    stage="execution",
                )
            elif not isinstance(raw_result, dict):
                raw_result = self._build_classified_failure(
                    symbol=symbol,
                    error="Engine returned invalid result format",
                    error_type="SYSTEM_ERROR",
                    stage="execution",
                )

            attempt_execution_time = max(0.0, time.monotonic() - attempt_started_at)
            validated_attempt_result = self._apply_failure_intelligence(
                validate_result(
                    raw_result,
                    symbol=symbol,
                    execution_time=attempt_execution_time,
                    retries=retries_used,
                ),
                symbol=symbol,
                source_result=raw_result,
                default_stage="execution",
                default_error_type="SYSTEM_ERROR",
            )

            last_result = validated_attempt_result
            if str(validated_attempt_result.get("status", "")).upper() == "SUCCESS":
                return validated_attempt_result

            if attempt_index < retry_limit:
                if self._is_retryable_failure(validated_attempt_result):
                    self._log(
                        f"Retrying {symbol} ({attempt_index + 1}/{retry_limit})",
                        level="WARNING",
                        task_id=task_id,
                        symbol=symbol,
                    )
                else:
                    non_retryable_type = self._sanitize_error_type(
                        (
                            validated_attempt_result.get("error_type")
                            if isinstance(validated_attempt_result, dict)
                            else None
                        )
                    )
                    self._log(
                        (
                            f"Not retrying {symbol}: non-retryable error type "
                            f"{non_retryable_type}"
                        ),
                        level="WARNING",
                        task_id=task_id,
                        symbol=symbol,
                    )
                    break

        resolved_retries = 0
        if isinstance(last_result, dict):
            try:
                resolved_retries = max(0, int(last_result.get("retries", 0)))
            except (TypeError, ValueError):
                resolved_retries = 0
        return self._apply_failure_intelligence(
            validate_result(
                last_result,
                symbol=symbol,
                retries=resolved_retries,
            ),
            symbol=symbol,
            source_result=last_result,
            default_stage="execution",
            default_error_type="SYSTEM_ERROR",
        )

    def _dispatch_task(
        self,
        *,
        mode: str,
        task: dict[str, Any],
        task_id: str,
        symbol: str,
    ) -> dict[str, Any]:
        self._execution_engine.set_base_config(self._config)
        return self._execution_engine.execute(
            task=task,
            task_id=task_id,
            mode=mode,
        )

    def _dispatch_task_with_hard_timeout(
        self,
        *,
        mode: str,
        task: dict[str, Any],
        task_id: str,
        symbol: str,
        timeout_seconds: float | None,
    ) -> dict[str, Any]:
        if timeout_seconds is None:
            return self._dispatch_task(
                mode=mode,
                task=task,
                task_id=task_id,
                symbol=symbol,
            )

        timeout = max(0.1, float(timeout_seconds))
        subprocess_task = self._prepare_task_for_subprocess(task)
        process_context = multiprocessing.get_context("spawn")
        result_queue = process_context.Queue(maxsize=1)
        process = process_context.Process(
            target=_execute_task_in_subprocess,
            kwargs={
                "result_queue": result_queue,
                "base_config": dict(self._config),
                "mode": mode,
                "task": subprocess_task,
                "task_id": task_id,
            },
            daemon=True,
        )

        try:
            process.start()
        except Exception:
            self._close_result_queue(result_queue)
            raise
        process.join(timeout=timeout)
        if process.is_alive():
            process.terminate()
            process.join(timeout=1.0)
            if process.is_alive() and hasattr(process, "kill"):
                process.kill()
                process.join(timeout=1.0)

            self._close_result_queue(result_queue)
            raise TimeoutError(f"Task exceeded hard timeout ({timeout:.2f}s)")

        try:
            payload = result_queue.get(timeout=0.5)
        except std_queue.Empty:
            payload = None
        finally:
            self._close_result_queue(result_queue)

        if not isinstance(payload, dict):
            raise RuntimeError(
                f"Task subprocess finished without result (exit_code={process.exitcode})"
            )

        self._replay_subprocess_logs(payload)

        if bool(payload.get("ok")):
            result = payload.get("result")
            if isinstance(result, dict):
                return result
            raise RuntimeError("Task subprocess returned invalid result payload")

        error_message = str(payload.get("error") or "Task subprocess failed")
        traceback_text = str(payload.get("traceback") or "").strip()
        if traceback_text:
            self._log(
                "Task subprocess traceback follows:",
                level="ERROR",
                task_id=task_id,
                symbol=symbol,
            )
            for line in traceback_text.splitlines()[-25:]:
                self._log(
                    line,
                    level="ERROR",
                    task_id=task_id,
                    symbol=symbol,
                )
        raise RuntimeError(error_message)

    def _replay_subprocess_logs(self, payload: dict[str, Any]) -> None:
        raw_logs = payload.get("logs")
        if not isinstance(raw_logs, list):
            return

        for item in raw_logs:
            if not isinstance(item, dict):
                continue
            message = str(item.get("message") or "").strip()
            if not message:
                continue
            self._log(
                message,
                level=str(item.get("level") or "INFO"),
                task_id=str(item.get("task_id") or "").strip() or None,
                symbol=str(item.get("symbol") or "").strip().upper() or None,
            )

    @staticmethod
    def _close_result_queue(result_queue: Any) -> None:
        try:
            result_queue.close()
        except Exception:
            pass
        try:
            result_queue.join_thread()
        except Exception:
            pass

    @staticmethod
    def _prepare_task_for_subprocess(task: dict[str, Any]) -> dict[str, Any]:
        prepared = copy.deepcopy(task) if isinstance(task, dict) else {}
        # Avoid pickling dynamic class objects; child process re-hydrates safely.
        prepared.pop("strategy_class", None)
        return prepared

    def _hydrate_strategy_class(self, task: dict[str, Any]) -> dict[str, Any]:
        if isinstance(task.get("strategy_class"), type):
            return dict(task)

        strategy_file = str(task.get("strategy_file_path") or "").strip()
        strategy_class_name = str(task.get("strategy_class_name") or "").strip()
        if not strategy_file or not strategy_class_name:
            raise ValueError("Missing strategy metadata for task execution")

        from Dashboard.Backtesting_page.Features import backtest_data_service

        hydrated = dict(task)
        safe_strategy_path = backtest_data_service.resolve_strategy_file_path(strategy_file)
        hydrated["strategy_class"] = backtest_data_service.load_strategy_class(
            str(safe_strategy_path),
            strategy_class_name,
        )
        return hydrated

    def _build_classified_failure(
        self,
        *,
        symbol: str,
        error: Exception | str,
        error_type: str,
        stage: str,
        log_file: str = "",
    ) -> dict[str, Any]:
        error_message = self._resolve_error_message(error)
        payload = build_failed_result(symbol, error_message, log_file=log_file)
        payload["error"] = error_message
        payload["error_message"] = error_message
        payload["error_type"] = self._sanitize_error_type(error_type)
        payload["stage"] = self._sanitize_stage(stage)
        return payload

    def _apply_failure_intelligence(
        self,
        result: dict[str, Any],
        *,
        symbol: str,
        source_result: Any,
        default_stage: str,
        default_error_type: str,
    ) -> dict[str, Any]:
        normalized = validate_result(
            result,
            symbol=symbol,
            execution_time=float(result.get("execution_time", 0.0)),
            retries=int(result.get("retries", 0)),
        )
        if str(normalized.get("status", "")).upper() == "SUCCESS":
            normalized["error_type"] = None
            normalized["error_message"] = None
            normalized["stage"] = None
            return normalized

        source = source_result if isinstance(source_result, dict) else {}
        resolved_error_message = str(
            source.get("error_message")
            or source.get("error")
            or normalized.get("error")
            or "Unknown execution error"
        ).strip() or "Unknown execution error"
        resolved_stage = self._sanitize_stage(
            source.get("stage") or default_stage
        )
        resolved_error_type = self._sanitize_error_type(
            source.get("error_type")
            or self._classify_error_type_from_message(
                resolved_error_message,
                stage_hint=resolved_stage,
            )
            or default_error_type
        )

        normalized["error"] = resolved_error_message
        normalized["error_message"] = resolved_error_message
        normalized["error_type"] = resolved_error_type
        normalized["stage"] = resolved_stage
        return normalized

    def _classify_error_type(self, error: Exception, *, stage_hint: str) -> str:
        message = self._resolve_error_message(error)
        return self._classify_error_type_from_message(message, stage_hint=stage_hint)

    def _classify_error_type_from_message(self, message: str, *, stage_hint: str) -> str:
        lowered = str(message or "").strip().lower()
        if "timeout" in lowered or "timed out" in lowered:
            return "TIMEOUT_ERROR"
        if stage_hint == "validation":
            return "VALIDATION_ERROR"
        if any(
            marker in lowered
            for marker in ("strategy execution failed", "strategy", "indicator")
        ):
            return "STRATEGY_ERROR"
        if any(
            marker in lowered
            for marker in (
                "zerodha",
                "kite",
                "tokenexception",
                "networkexception",
                "ratelimitexception",
                "api",
            )
        ):
            return "API_ERROR"
        if any(
            marker in lowered
            for marker in (
                "ohlc",
                "data",
                "dataset",
                "column",
                "nan",
                "csv",
                "empty",
            )
        ):
            return "DATA_ERROR"
        return "SYSTEM_ERROR"

    @staticmethod
    def _sanitize_error_type(value: Any) -> str:
        allowed = {
            "DATA_ERROR",
            "API_ERROR",
            "STRATEGY_ERROR",
            "TIMEOUT_ERROR",
            "VALIDATION_ERROR",
            "SYSTEM_ERROR",
        }
        candidate = str(value or "").strip().upper()
        if candidate in allowed:
            return candidate
        return "SYSTEM_ERROR"

    @staticmethod
    def _sanitize_stage(value: Any) -> str:
        allowed = {"DATA_FETCH", "EXECUTION", "VALIDATION"}
        candidate = str(value or "").strip().upper()
        if candidate in allowed:
            return candidate.lower()
        return "execution"

    def _is_retryable_failure(self, result: Any) -> bool:
        if not isinstance(result, dict):
            return False
        if str(result.get("status", "")).strip().upper() == "SUCCESS":
            return False
        error_type = self._sanitize_error_type(result.get("error_type"))
        return error_type in {"TIMEOUT_ERROR", "API_ERROR"}

    @staticmethod
    def _resolve_error_message(error: Exception | str) -> str:
        if isinstance(error, Exception):
            resolved = str(error).strip()
            if resolved:
                return resolved
            return type(error).__name__
        resolved = str(error).strip()
        return resolved or "Unknown execution error"

    def _record_performance_metrics(
        self,
        *,
        task_id: str,
        symbol: str,
        status: str,
        created_at: str,
        start_time: str,
        end_time: str,
        execution_time: float,
        retries: int,
        final_result: dict[str, Any],
    ) -> None:
        wait_time = self._calculate_wait_time_seconds(
            created_at=created_at,
            start_time=start_time,
        )
        error_type = str(final_result.get("error_type") or "").strip().upper() or None
        timeout = error_type == "TIMEOUT_ERROR"
        error_message = str(final_result.get("error_message") or final_result.get("error") or "").strip() or None
        stage = str(final_result.get("stage") or "").strip().lower() or None

        try:
            self._performance_tracker.record_task(
                task_id=task_id,
                symbol=symbol,
                status=status,
                execution_time=execution_time,
                wait_time=wait_time,
                retries=retries,
                timeout=timeout,
                error_type=error_type,
                error_message=error_message,
                stage=stage,
                start_time=start_time,
                end_time=end_time,
            )
        except Exception as exc:
            self._log(
                f"Failed to record performance metrics: {exc}",
                level="WARNING",
                task_id=task_id,
                symbol=symbol,
            )

    def _calculate_wait_time_seconds(
        self,
        *,
        created_at: str,
        start_time: str,
    ) -> float:
        created_dt = self._parse_iso_datetime(created_at)
        start_dt = self._parse_iso_datetime(start_time)
        if created_dt is None or start_dt is None:
            return 0.0
        return max(0.0, (start_dt - created_dt).total_seconds())

    @staticmethod
    def _parse_iso_datetime(value: str) -> datetime | None:
        raw = str(value or "").strip()
        if not raw:
            return None
        try:
            parsed = datetime.fromisoformat(raw)
        except ValueError:
            return None
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed

    def _emit_update(self, task_id: str, status: str) -> None:
        callback = self._on_task_update
        if callable(callback):
            try:
                callback(task_id, status)
            except Exception:
                pass

    def _log(
        self,
        message: str,
        *,
        level: str = "INFO",
        task_id: str | None = None,
        symbol: str | None = None,
    ) -> None:
        terminal = self._terminal
        if terminal is None or not hasattr(terminal, "log"):
            return
        try:
            terminal.log(message, level=level, task_id=task_id, symbol=symbol)
        except Exception:
            pass

    def _get_retry_limit(self) -> int:
        value = self._config.get("max_retries", 1)
        try:
            return max(0, int(value))
        except (TypeError, ValueError):
            return 1

    def _get_timeout_seconds(self) -> float | None:
        for key in ("task_timeout_seconds", "timeout_seconds"):
            value = self._config.get(key)
            if value in (None, ""):
                continue
            try:
                timeout = float(value)
            except (TypeError, ValueError):
                continue
            if timeout > 0:
                return timeout
        return None

    def _save_store_locked(self) -> None:
        payload = self._build_store_payload_locked()
        temp_path = self._store_path.with_suffix(self._store_path.suffix + ".tmp")
        try:
            serialized = json.dumps(payload, indent=2, ensure_ascii=True)
            temp_path.write_text(serialized, encoding="utf-8")
            temp_path.replace(self._store_path)
        except Exception as exc:
            try:
                if temp_path.is_file():
                    temp_path.unlink()
            except Exception:
                pass
            self._log(f"Failed to persist task store: {exc}", level="ERROR")

    def _build_store_payload_locked(self) -> dict[str, Any]:
        completed_tasks = [
            self._serialize_queue_item(item)
            for item in self._queue
            if item.get("status") == "SUCCESS"
        ]
        failed_tasks = [
            self._serialize_queue_item(item)
            for item in self._queue
            if item.get("status") == "FAILED"
        ]
        return {
            "updated_at": self._utc_iso_now(),
            "task_counter": self._task_counter,
            "queue": [self._serialize_queue_item(item) for item in self._queue],
            "completed_tasks": completed_tasks,
            "failed_tasks": failed_tasks,
            "results_by_task_id": {
                key: self._serialize_value(value)
                for key, value in self._results_by_task_id.items()
            },
        }

    def _load_store(self) -> None:
        if not self._store_path.is_file():
            return

        try:
            raw_payload = json.loads(self._store_path.read_text(encoding="utf-8"))
        except Exception:
            self._handle_corrupt_store()
            return

        if not isinstance(raw_payload, dict):
            self._handle_corrupt_store()
            return

        raw_queue = raw_payload.get("queue")
        raw_results = raw_payload.get("results_by_task_id")
        raw_counter = raw_payload.get("task_counter")

        queue: list[dict[str, Any]] = []
        if isinstance(raw_queue, list):
            for item in raw_queue:
                if not isinstance(item, dict):
                    continue
                parsed_item = self._deserialize_queue_item(item)
                if parsed_item is None:
                    continue
                if parsed_item.get("status") == "RUNNING":
                    parsed_item["status"] = "PENDING"
                    parsed_item["start_time"] = None
                queue.append(parsed_item)

        results_by_task_id: dict[str, dict[str, Any]] = {}
        if isinstance(raw_results, dict):
            for task_id, result in raw_results.items():
                if not isinstance(task_id, str):
                    continue
                deserialized = self._deserialize_value(result)
                if isinstance(deserialized, dict):
                    results_by_task_id[task_id] = deserialized

        if not results_by_task_id:
            for item in queue:
                task_id = str(item.get("task_id") or "")
                result = item.get("result")
                if task_id and isinstance(result, dict):
                    results_by_task_id[task_id] = dict(result)

        with self._lock:
            self._queue = queue
            self._results_by_task_id = results_by_task_id
            if isinstance(raw_counter, int) and raw_counter >= 0:
                self._task_counter = raw_counter
            else:
                self._task_counter = len(queue)

    def _handle_corrupt_store(self) -> None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = self._store_path.with_suffix(f".corrupt.{timestamp}.json")
        try:
            self._store_path.replace(backup_path)
        except Exception:
            pass
        with self._lock:
            self._queue = []
            self._results_by_task_id = {}
            self._task_counter = 0

    def _serialize_queue_item(self, item: dict[str, Any]) -> dict[str, Any]:
        return {
            "task_id": str(item.get("task_id") or ""),
            "task": self._serialize_value(item.get("task", {})),
            "created_at": item.get("created_at"),
            "status": str(item.get("status") or "PENDING"),
            "result": self._serialize_value(item.get("result")),
            "start_time": item.get("start_time"),
            "end_time": item.get("end_time"),
            "execution_time": float(item.get("execution_time", 0.0)),
            "retries": int(item.get("retries", 0)),
        }

    def _deserialize_queue_item(self, item: dict[str, Any]) -> dict[str, Any] | None:
        task_id = str(item.get("task_id") or "").strip()
        if not task_id:
            return None
        deserialized_task = self._deserialize_value(item.get("task", {}))
        task = deserialized_task if isinstance(deserialized_task, dict) else {}
        deserialized_result = self._deserialize_value(item.get("result"))
        result = deserialized_result if isinstance(deserialized_result, dict) else None
        created_at = str(item.get("created_at") or "").strip()
        if not created_at:
            created_at = str(
                item.get("start_time") or item.get("end_time") or self._utc_iso_now()
            )
        return {
            "task_id": task_id,
            "task": task,
            "created_at": created_at,
            "status": str(item.get("status") or "PENDING").upper(),
            "result": result,
            "start_time": item.get("start_time"),
            "end_time": item.get("end_time"),
            "execution_time": float(item.get("execution_time", 0.0)),
            "retries": int(item.get("retries", 0)),
        }

    def _serialize_value(self, value: Any) -> Any:
        if isinstance(value, (str, int, float, bool)) or value is None:
            return value
        if isinstance(value, datetime):
            return {"__kind__": "datetime", "value": value.isoformat()}
        if isinstance(value, Path):
            return {"__kind__": "path", "value": str(value)}
        if isinstance(value, type):
            return {"__kind__": "class", "value": value.__name__}
        if value.__class__.__name__ == "DataFrame":
            return {"__kind__": "dataframe", "value": "<omitted>"}
        if isinstance(value, list):
            return [self._serialize_value(item) for item in value]
        if isinstance(value, tuple):
            return [self._serialize_value(item) for item in value]
        if isinstance(value, dict):
            return {
                str(key): self._serialize_value(val)
                for key, val in value.items()
                if str(key) != "strategy_class"
            }
        return str(value)

    def _deserialize_value(self, value: Any) -> Any:
        if isinstance(value, list):
            return [self._deserialize_value(item) for item in value]
        if isinstance(value, dict):
            marker = value.get("__kind__")
            if marker == "datetime":
                raw = value.get("value")
                if isinstance(raw, str):
                    try:
                        return datetime.fromisoformat(raw)
                    except ValueError:
                        return raw
            if marker == "path":
                raw = value.get("value")
                return str(raw) if raw is not None else ""
            if marker == "class":
                return None
            if marker == "dataframe":
                return None
            return {
                str(key): self._deserialize_value(val)
                for key, val in value.items()
            }
        return value

    @staticmethod
    def _utc_iso_now() -> str:
        return datetime.now(timezone.utc).isoformat()
