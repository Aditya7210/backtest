"""Calculator subprocess management — spawn/stop calculation_runner (E-12, E-03)."""
from __future__ import annotations

import os
import signal
import subprocess
import sys
from typing import Any

from backend.database.sync_connection import get_sync_db

_calculator_process: subprocess.Popen | None = None


def _is_calculator_running() -> bool:
    global _calculator_process
    if _calculator_process is None:
        return False
    return _calculator_process.poll() is None


def start_calculator() -> dict[str, Any]:
    global _calculator_process
    if _is_calculator_running():
        raise RuntimeError(f"Calculator already running (PID {_calculator_process.pid})")

    _calculator_process = subprocess.Popen(
        [sys.executable, "-m", "backend.calculations.run_calculator"],
    )

    db = get_sync_db()
    db.collector_status.update_one(
        {"_id": "singleton"},
        {"$set": {
            "calculator.status": "running",
            "calculator.pid": _calculator_process.pid,
        }},
        upsert=True,
    )

    return {"pid": _calculator_process.pid}


def stop_calculator() -> dict[str, Any]:
    global _calculator_process
    if not _is_calculator_running():
        return {"message": "Calculator is not running"}

    pid = _calculator_process.pid
    try:
        if os.name == "nt":
            _calculator_process.terminate()
        else:
            os.kill(pid, signal.SIGTERM)
        _calculator_process.wait(timeout=10)
    except Exception:
        _calculator_process.kill()
    finally:
        _calculator_process = None

    db = get_sync_db()
    db.collector_status.update_one(
        {"_id": "singleton"},
        {"$set": {"calculator.status": "stopped", "calculator.pid": None}},
        upsert=True,
    )

    return {"pid": pid, "message": "Calculator stopped"}
