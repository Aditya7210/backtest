from __future__ import annotations

from typing import Any

from Backtesting.backtest_core import build_failed_result
from Backtesting.api_based_execution_engine import run_task as run_api_task
from Backtesting.execution_engine import run_task as run_csv_task


class ExecutionManager:
    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self._config = dict(config) if isinstance(config, dict) else {}
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
            }
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

    def run_next(
        self,
        on_task_update: Any = None,
    ) -> dict[str, Any] | None:
        queue_item = next((item for item in self._queue if item["status"] == "PENDING"), None)
        if queue_item is None:
            return None

        task_id = str(queue_item["task_id"])
        task = queue_item["task"]
        symbol = str(task.get("symbol") or task_id).strip() or task_id
        mode = str(task.get("mode", "")).strip().lower()

        queue_item["status"] = "RUNNING"
        self._emit_update(on_task_update, task_id, "RUNNING")

        try:
            if mode == "api":
                result = run_api_task(task, self._config)
            elif mode == "csv":
                result = run_csv_task(task, self._config)
            else:
                raise ValueError(f"Unsupported task mode: {mode}")
        except Exception as exc:
            result = build_failed_result(symbol, str(exc))

        if result is None:
            result = build_failed_result(symbol, "Engine returned no result")
        elif not isinstance(result, dict):
            result = build_failed_result(symbol, "Engine returned invalid result format")

        result = self._ensure_result_shape(result, symbol=symbol)
        final_status = "SUCCESS" if str(result["status"]).upper() == "SUCCESS" else "FAILED"
        result["status"] = final_status

        queue_item["status"] = final_status
        queue_item["result"] = dict(result)
        self._results_by_task_id[task_id] = dict(result)
        self._emit_update(on_task_update, task_id, final_status)

        return dict(result)

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

    def _emit_update(self, on_task_update: Any, task_id: str, status: str) -> None:
        if callable(on_task_update):
            try:
                on_task_update(task_id, status)
            except Exception:
                pass

    def _ensure_result_shape(self, result: dict[str, Any], *, symbol: str) -> dict[str, Any]:
        normalized = dict(result)
        normalized.setdefault("symbol", symbol)
        normalized.setdefault("status", "FAILED")
        normalized.setdefault("final_value", None)
        normalized.setdefault("log_file", "")
        normalized.setdefault("error", None)

        if str(normalized["status"]).upper() == "SUCCESS":
            normalized["status"] = "SUCCESS"
            normalized["error"] = None
            if normalized.get("final_value") is None:
                normalized = build_failed_result(
                    str(normalized["symbol"]),
                    "Execution succeeded without final_value",
                    log_file=str(normalized.get("log_file") or ""),
                )
        else:
            normalized["status"] = "FAILED"
            normalized["final_value"] = None
            if not normalized.get("error"):
                normalized["error"] = "Unknown execution error"
            normalized["log_file"] = str(normalized.get("log_file") or "")

        normalized["symbol"] = str(normalized.get("symbol") or symbol)
        normalized["log_file"] = str(normalized.get("log_file") or "")
        return normalized
