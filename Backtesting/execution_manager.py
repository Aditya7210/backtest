from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import threading
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
        *,
        store_path: str | Path | None = None,
        poll_interval_seconds: float = 0.2,
    ) -> None:
        self._config = dict(config) if isinstance(config, dict) else {}
        self._terminal = terminal
        self._poll_interval_seconds = max(0.05, float(poll_interval_seconds))

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
        self._worker_thread: threading.Thread | None = None
        self._on_task_update: Any = None

        self._queue: list[dict[str, Any]] = []
        self._results_by_task_id: dict[str, dict[str, Any]] = {}
        self._task_counter = 0
        self._load_store()

    def set_terminal(self, terminal: Any | None) -> None:
        with self._lock:
            self._terminal = terminal

    def add_task(self, task: dict[str, Any]) -> str:
        if not isinstance(task, dict):
            raise ValueError("Task must be a dictionary")

        with self._lock:
            self._task_counter += 1
            task_id = f"TASK-{self._task_counter:04d}"
            queue_task = dict(task)
            queue_task.setdefault("task_id", task_id)

            queue_item = {
                "task_id": task_id,
                "task": queue_task,
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

    def has_active_tasks(self) -> bool:
        with self._lock:
            return any(
                item.get("status") in {"PENDING", "RUNNING"}
                for item in self._queue
            )

    def start_worker(self, on_task_update: Any = None) -> bool:
        with self._lock:
            if callable(on_task_update):
                self._on_task_update = on_task_update

            if self._worker_thread is not None and self._worker_thread.is_alive():
                return False

            self._stop_event.clear()
            self._worker_thread = threading.Thread(
                target=self._worker_loop,
                name="BacktestExecutionWorker",
                daemon=True,
            )
            self._worker_thread.start()

        self._log("Execution worker started", level="INFO")
        return True

    def stop_worker(self, timeout_seconds: float = 3.0) -> None:
        self._stop_event.set()
        worker = self._worker_thread
        was_running = worker is not None and worker.is_alive()
        if worker is not None and worker.is_alive():
            worker.join(timeout=max(0.1, float(timeout_seconds)))
        with self._lock:
            self._worker_thread = None
        if was_running:
            self._log("Execution worker stopped", level="WARNING")

    def is_worker_running(self) -> bool:
        worker = self._worker_thread
        return worker is not None and worker.is_alive()

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

    def _worker_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                queue_item = self._pick_next_pending_task()
                if queue_item is None:
                    time.sleep(self._poll_interval_seconds)
                    continue
                self._process_queue_item(queue_item)
            except Exception as exc:
                self._log(
                    f"Worker loop error: {exc}",
                    level="ERROR",
                )
                time.sleep(self._poll_interval_seconds)

    def _pick_next_pending_task(self) -> dict[str, Any] | None:
        with self._lock:
            queue_item = next(
                (item for item in self._queue if item.get("status") == "PENDING"),
                None,
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
        final_result = validate_result(
            final_result,
            symbol=symbol,
            execution_time=total_execution_time,
            retries=retries_used,
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
                f"{symbol} failed: {final_result.get('error')}",
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
        attempts = retry_limit + 1
        mode = str(task.get("mode", "")).strip().lower()
        last_result: dict[str, Any] = build_failed_result(symbol, "Execution did not run")

        for attempt_index in range(attempts):
            attempt_started_at = time.monotonic()
            retries_used = attempt_index

            try:
                execution_task = self._hydrate_strategy_class(task)
                raw_result = self._dispatch_task(
                    mode=mode,
                    task=execution_task,
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

            if timeout_seconds is not None and attempt_execution_time > timeout_seconds:
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

    def _hydrate_strategy_class(self, task: dict[str, Any]) -> dict[str, Any]:
        if isinstance(task.get("strategy_class"), type):
            return dict(task)

        strategy_file = str(task.get("strategy_file_path") or "").strip()
        strategy_class_name = str(task.get("strategy_class_name") or "").strip()
        if not strategy_file or not strategy_class_name:
            raise ValueError("Missing strategy metadata for task execution")

        from Dashboard.Backtesting_page.Features import backtest_data_service

        hydrated = dict(task)
        hydrated["strategy_class"] = backtest_data_service.load_strategy_class(
            strategy_file,
            strategy_class_name,
        )
        return hydrated

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
        return {
            "task_id": task_id,
            "task": task,
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
