from __future__ import annotations

from datetime import datetime, timezone
import time
from typing import Any

from Backtesting.api_based_execution_engine import run_task as run_api_task
from Backtesting.backtest_core import build_failed_result, validate_result
from Backtesting.execution_engine import run_task as run_csv_task


class ExecutionManager:
    def __init__(
        self,
        config: dict[str, Any] | None = None,
        terminal: Any | None = None,
    ) -> None:
        self._config = dict(config) if isinstance(config, dict) else {}
        self._terminal = terminal
        self._queue: list[dict[str, Any]] = []
        self._results_by_task_id: dict[str, dict[str, Any]] = {}
        self._task_counter = 0

    def add_task(self, task: dict[str, Any]) -> str:
        if not isinstance(task, dict):
            raise ValueError("Task must be a dictionary")

        self._task_counter += 1
        task_id = f"TASK-{self._task_counter:04d}"
        self._queue.append(
            {
                "task_id": task_id,
                "task": dict(task),
                "status": "PENDING",
                "result": None,
                "start_time": None,
                "end_time": None,
                "execution_time": 0.0,
                "retries": 0,
            }
        )
        symbol = str(task.get("symbol") or "UNKNOWN").strip().upper() or "UNKNOWN"
        self._log(
            f"Queued task {task_id} for {symbol}",
            level="INFO",
            task_id=task_id,
            symbol=symbol,
        )
        return task_id

    def clear_tasks(self) -> None:
        self._queue.clear()
        self._results_by_task_id.clear()
        self._task_counter = 0

    def get_queue_snapshot(self) -> list[dict[str, Any]]:
        return [dict(item) for item in self._queue]

    def get_results(self) -> dict[str, dict[str, Any]]:
        return {task_id: dict(result) for task_id, result in self._results_by_task_id.items()}

    def run_next(self, on_task_update: Any = None) -> dict[str, Any] | None:
        queue_item = next((item for item in self._queue if item["status"] == "PENDING"), None)
        if queue_item is None:
            return None

        task_id = str(queue_item["task_id"])
        task = queue_item["task"]
        symbol = str(task.get("symbol") or task_id).strip().upper() or task_id
        retry_limit = self._get_retry_limit()
        timeout_seconds = self._get_timeout_seconds()

        queue_item["status"] = "RUNNING"
        queue_item["start_time"] = self._utc_iso_now()
        self._log(
            f"Starting {symbol}",
            level="INFO",
            task_id=task_id,
            symbol=symbol,
        )
        self._emit_update(on_task_update, task_id, "RUNNING")

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

        final_result = validate_result(
            final_result,
            symbol=symbol,
            execution_time=total_execution_time,
            retries=retries_used,
        )
        final_status = str(final_result["status"]).upper()

        queue_item["status"] = final_status
        queue_item["result"] = dict(final_result)
        queue_item["end_time"] = self._utc_iso_now()
        queue_item["execution_time"] = float(final_result.get("execution_time", 0.0))
        queue_item["retries"] = int(final_result.get("retries", 0))
        self._results_by_task_id[task_id] = dict(final_result)
        self._emit_update(on_task_update, task_id, final_status)

        if final_status == "SUCCESS":
            self._log(
                (
                    f"{symbol} completed. Value: "
                    f"{final_result.get('final_value')}"
                ),
                level="SUCCESS",
                task_id=task_id,
                symbol=symbol,
            )
        else:
            self._log(
                f"{symbol} failed: {final_result.get('error')}",
                level="ERROR",
                task_id=task_id,
                symbol=symbol,
            )

        return dict(final_result)

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

        ordered_results: list[dict[str, Any]] = []
        for item in self._queue:
            stored_result = item.get("result")
            if isinstance(stored_result, dict):
                ordered_results.append(dict(stored_result))
        return ordered_results

    def _execute_with_retries(
        self,
        *,
        task: dict[str, Any],
        task_id: str,
        symbol: str,
        retry_limit: int,
        timeout_seconds: float | None,
    ) -> dict[str, Any]:
        attempts = retry_limit + 1
        mode = str(task.get("mode", "")).strip().lower()
        last_result: dict[str, Any] = build_failed_result(symbol, "Execution did not run")

        for attempt_index in range(attempts):
            attempt_started_at = time.monotonic()
            retries_used = attempt_index

            try:
                raw_result = self._dispatch_task(
                    mode=mode,
                    task=task,
                    task_id=task_id,
                    symbol=symbol,
                )
            except Exception as exc:
                raw_result = build_failed_result(symbol, str(exc))
                self._log(
                    f"Task execution crashed: {exc}",
                    level="ERROR",
                    task_id=task_id,
                    symbol=symbol,
                )

            if raw_result is None:
                raw_result = build_failed_result(symbol, "Engine returned no result")
            elif not isinstance(raw_result, dict):
                raw_result = build_failed_result(symbol, "Engine returned invalid result format")

            attempt_execution_time = max(0.0, time.monotonic() - attempt_started_at)
            validated_attempt_result = validate_result(
                raw_result,
                symbol=symbol,
                execution_time=attempt_execution_time,
                retries=retries_used,
            )

            if (
                timeout_seconds is not None
                and attempt_execution_time > timeout_seconds
            ):
                self._log(
                    (
                        f"Timeout exceeded on attempt {attempt_index + 1}: "
                        f"{attempt_execution_time:.2f}s > {timeout_seconds:.2f}s"
                    ),
                    level="WARNING",
                    task_id=task_id,
                    symbol=symbol,
                )
                validated_attempt_result = validate_result(
                    build_failed_result(
                        symbol,
                        (
                            "Task exceeded timeout "
                            f"({attempt_execution_time:.2f}s > {timeout_seconds:.2f}s)"
                        ),
                        log_file=str(validated_attempt_result.get("log_file") or ""),
                    ),
                    symbol=symbol,
                    execution_time=attempt_execution_time,
                    retries=retries_used,
                )

            last_result = validated_attempt_result
            if str(validated_attempt_result.get("status", "")).upper() == "SUCCESS":
                return validated_attempt_result

            if attempt_index < retry_limit:
                self._log(
                    f"Retrying {symbol} ({attempt_index + 1}/{retry_limit})",
                    level="WARNING",
                    task_id=task_id,
                    symbol=symbol,
                )

        return validate_result(last_result, symbol=symbol, retries=retry_limit)

    def _dispatch_task(
        self,
        *,
        mode: str,
        task: dict[str, Any],
        task_id: str,
        symbol: str,
    ) -> dict[str, Any]:
        if mode == "api":
            return run_api_task(
                task,
                self._config,
                terminal=self._terminal,
                task_id=task_id,
            )
        if mode == "csv":
            return run_csv_task(
                task,
                self._config,
                terminal=self._terminal,
                task_id=task_id,
            )
        raise ValueError(f"Unsupported task mode: {mode or '<missing>'}")

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

    def _emit_update(self, on_task_update: Any, task_id: str, status: str) -> None:
        if callable(on_task_update):
            try:
                on_task_update(task_id, status)
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
        if self._terminal is None or not hasattr(self._terminal, "log"):
            return
        try:
            self._terminal.log(
                message,
                level=level,
                task_id=task_id,
                symbol=symbol,
            )
        except Exception:
            pass

    @staticmethod
    def _utc_iso_now() -> str:
        return datetime.now(timezone.utc).isoformat()
