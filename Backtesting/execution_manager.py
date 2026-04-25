from __future__ import annotations

from typing import Any

from Backtesting.api_based_execution_engine import run_task as run_api_task
from Backtesting.execution_engine import run_task as run_csv_task


class ExecutionManager:
    def __init__(self, config: dict[str, Any] | None = None) -> None:
        merged_config = {"initial_capital": 100000.0, "commission": 0.0003}
        if isinstance(config, dict):
            merged_config.update(config)
        self._config = merged_config
        self._tasks: list[dict[str, Any]] = []

    def add_task(self, task: dict[str, Any]) -> None:
        if not isinstance(task, dict):
            raise ValueError("Task must be a dictionary")
        if "mode" not in task:
            raise ValueError("Task missing required field: mode")
        self._tasks.append(dict(task))

    def clear_tasks(self) -> None:
        self._tasks.clear()

    def run(self) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []

        for index, task in enumerate(self._tasks):
            symbol = str(task.get("symbol") or f"TASK_{index + 1}").strip() or f"TASK_{index + 1}"
            mode = str(task.get("mode", "")).strip().lower()
            prepared_task = dict(task)

            task_config = prepared_task.get("config")
            if not isinstance(task_config, dict):
                task_config = {}
            merged_task_config = dict(self._config)
            merged_task_config.update(task_config)
            prepared_task["config"] = merged_task_config

            try:
                if mode == "api":
                    result = run_api_task(prepared_task)
                elif mode == "csv":
                    result = run_csv_task(prepared_task)
                else:
                    raise ValueError(f"Unsupported task mode: {mode}")
            except Exception as exc:
                result = {
                    "symbol": symbol,
                    "final_value": None,
                    "log_file": "",
                    "error": str(exc),
                }

            if not isinstance(result, dict):
                result = {
                    "symbol": symbol,
                    "final_value": None,
                    "log_file": "",
                    "error": "Engine returned invalid result format",
                }

            results.append(
                {
                    "symbol": str(result.get("symbol") or symbol),
                    "final_value": result.get("final_value"),
                    "log_file": str(result.get("log_file") or ""),
                    "error": result.get("error"),
                }
            )

        return results

