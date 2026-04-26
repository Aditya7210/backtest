from __future__ import annotations

from bisect import bisect_left, insort
from datetime import datetime, timezone
import json
from pathlib import Path
import threading
from typing import Any


class PerformanceTracker:
    """
    Thread-safe execution metrics tracker with atomic persistence.
    """

    def __init__(
        self,
        metrics_path: str | Path | None = None,
    ) -> None:
        default_metrics_path = (
            Path(__file__).resolve().parents[1]
            / "Data"
            / "Logs"
            / "execution_metrics.json"
        )
        self._metrics_path = (
            Path(metrics_path).resolve()
            if metrics_path is not None
            else default_metrics_path.resolve()
        )
        self._metrics_path.parent.mkdir(parents=True, exist_ok=True)

        self._lock = threading.RLock()
        self._task_metrics: dict[str, dict[str, Any]] = {}
        self._total_execution_time = 0.0
        self._execution_times_sorted: list[float] = []
        self._success_count = 0
        self._failure_count = 0
        self._retry_count = 0
        self._timeout_count = 0
        self._load_existing_metrics()

    def record_task(
        self,
        *,
        task_id: str,
        symbol: str,
        status: str,
        execution_time: float,
        wait_time: float,
        retries: int,
        timeout: bool,
        error_type: str | None = None,
        error_message: str | None = None,
        stage: str | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
    ) -> None:
        resolved_task_id = str(task_id or "").strip()
        if not resolved_task_id:
            return

        resolved_status = str(status or "FAILED").strip().upper()
        if resolved_status not in {"SUCCESS", "FAILED"}:
            resolved_status = "FAILED"

        resolved_symbol = str(symbol or "UNKNOWN").strip().upper() or "UNKNOWN"
        resolved_execution_time = max(0.0, float(execution_time or 0.0))
        resolved_wait_time = max(0.0, float(wait_time or 0.0))
        resolved_retries = max(0, int(retries or 0))
        resolved_timeout = bool(timeout)
        resolved_error_type = str(error_type or "").strip().upper() or None
        resolved_error_message = str(error_message or "").strip() or None
        resolved_stage = str(stage or "").strip().lower() or None

        entry = {
            "task_id": resolved_task_id,
            "symbol": resolved_symbol,
            "status": resolved_status,
            "execution_time": resolved_execution_time,
            "wait_time": resolved_wait_time,
            "retries": resolved_retries,
            "timeout": resolved_timeout,
            "error_type": resolved_error_type,
            "error_message": resolved_error_message,
            "stage": resolved_stage,
            "start_time": start_time,
            "end_time": end_time,
            "updated_at": self._utc_iso_now(),
        }

        with self._lock:
            existing = self._task_metrics.get(resolved_task_id)
            if isinstance(existing, dict):
                self._remove_task_contribution(existing)

            self._task_metrics[resolved_task_id] = entry
            self._apply_task_contribution(entry)
            self._persist_locked()

    def get_metrics_snapshot(self) -> dict[str, Any]:
        with self._lock:
            return self._build_payload_locked()

    def clear(self) -> None:
        with self._lock:
            self._task_metrics.clear()
            self._total_execution_time = 0.0
            self._execution_times_sorted.clear()
            self._success_count = 0
            self._failure_count = 0
            self._retry_count = 0
            self._timeout_count = 0
            self._persist_locked()

    def _apply_task_contribution(self, entry: dict[str, Any]) -> None:
        status = str(entry.get("status") or "FAILED").upper()
        execution_time = max(0.0, float(entry.get("execution_time") or 0.0))
        retries = max(0, int(entry.get("retries") or 0))
        timeout = bool(entry.get("timeout"))

        if status == "SUCCESS":
            self._success_count += 1
        else:
            self._failure_count += 1

        self._total_execution_time += execution_time
        insort(self._execution_times_sorted, execution_time)
        self._retry_count += retries
        if timeout:
            self._timeout_count += 1

    def _remove_task_contribution(self, entry: dict[str, Any]) -> None:
        status = str(entry.get("status") or "FAILED").upper()
        execution_time = max(0.0, float(entry.get("execution_time") or 0.0))
        retries = max(0, int(entry.get("retries") or 0))
        timeout = bool(entry.get("timeout"))

        if status == "SUCCESS":
            self._success_count = max(0, self._success_count - 1)
        else:
            self._failure_count = max(0, self._failure_count - 1)

        self._total_execution_time = max(0.0, self._total_execution_time - execution_time)
        idx = bisect_left(self._execution_times_sorted, execution_time)
        if idx < len(self._execution_times_sorted):
            candidate = float(self._execution_times_sorted[idx])
            if abs(candidate - execution_time) <= 1e-9:
                self._execution_times_sorted.pop(idx)

        self._retry_count = max(0, self._retry_count - retries)
        if timeout:
            self._timeout_count = max(0, self._timeout_count - 1)

    def _load_existing_metrics(self) -> None:
        if not self._metrics_path.is_file():
            return

        try:
            payload = json.loads(self._metrics_path.read_text(encoding="utf-8"))
        except Exception:
            self._handle_corrupt_metrics_file()
            return

        if not isinstance(payload, dict):
            self._handle_corrupt_metrics_file()
            return

        tasks = payload.get("tasks")
        if not isinstance(tasks, dict):
            return

        with self._lock:
            self._task_metrics.clear()
            self._total_execution_time = 0.0
            self._execution_times_sorted.clear()
            self._success_count = 0
            self._failure_count = 0
            self._retry_count = 0
            self._timeout_count = 0

            for task_id, value in tasks.items():
                if not isinstance(task_id, str) or not isinstance(value, dict):
                    continue
                try:
                    execution_time = max(0.0, float(value.get("execution_time") or 0.0))
                    wait_time = max(0.0, float(value.get("wait_time") or 0.0))
                    retries = max(0, int(value.get("retries") or 0))
                except (TypeError, ValueError):
                    execution_time = 0.0
                    wait_time = 0.0
                    retries = 0
                entry = {
                    "task_id": task_id,
                    "symbol": str(value.get("symbol") or "UNKNOWN").strip().upper() or "UNKNOWN",
                    "status": str(value.get("status") or "FAILED").strip().upper(),
                    "execution_time": execution_time,
                    "wait_time": wait_time,
                    "retries": retries,
                    "timeout": bool(value.get("timeout", False)),
                    "error_type": str(value.get("error_type") or "").strip().upper() or None,
                    "error_message": str(value.get("error_message") or "").strip() or None,
                    "stage": str(value.get("stage") or "").strip().lower() or None,
                    "start_time": value.get("start_time"),
                    "end_time": value.get("end_time"),
                    "updated_at": value.get("updated_at") or self._utc_iso_now(),
                }
                if entry["status"] not in {"SUCCESS", "FAILED"}:
                    entry["status"] = "FAILED"
                self._task_metrics[task_id] = entry
                self._apply_task_contribution(entry)

    def _build_payload_locked(self) -> dict[str, Any]:
        total_tasks = len(self._task_metrics)
        avg_execution_time = (
            self._total_execution_time / total_tasks if total_tasks > 0 else 0.0
        )
        median_execution_time = self._median_execution_time_locked()
        success_rate = (self._success_count / total_tasks) if total_tasks > 0 else 0.0
        failure_rate = (self._failure_count / total_tasks) if total_tasks > 0 else 0.0

        return {
            "updated_at": self._utc_iso_now(),
            "total_tasks": total_tasks,
            "success_rate": success_rate,
            "failure_rate": failure_rate,
            "avg_execution_time": avg_execution_time,
            "median_execution_time": median_execution_time,
            "retry_count": self._retry_count,
            "timeout_count": self._timeout_count,
            "tasks": {
                task_id: dict(value)
                for task_id, value in self._task_metrics.items()
            },
        }

    def _median_execution_time_locked(self) -> float:
        if not self._execution_times_sorted:
            return 0.0
        n = len(self._execution_times_sorted)
        mid = n // 2
        if n % 2 == 1:
            return float(self._execution_times_sorted[mid])
        return float((self._execution_times_sorted[mid - 1] + self._execution_times_sorted[mid]) / 2.0)

    def _persist_locked(self) -> None:
        payload = self._build_payload_locked()
        temp_path = self._metrics_path.with_suffix(self._metrics_path.suffix + ".tmp")
        try:
            serialized = json.dumps(payload, indent=2, ensure_ascii=True)
            temp_path.write_text(serialized, encoding="utf-8")
            temp_path.replace(self._metrics_path)
        except Exception:
            try:
                if temp_path.is_file():
                    temp_path.unlink()
            except Exception:
                pass

    def _handle_corrupt_metrics_file(self) -> None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = self._metrics_path.with_suffix(f".corrupt.{timestamp}.json")
        try:
            self._metrics_path.replace(backup_path)
        except Exception:
            pass

    @staticmethod
    def _utc_iso_now() -> str:
        return datetime.now(timezone.utc).isoformat()


__all__ = ["PerformanceTracker"]
