"""Collector subprocess management — spawn/stop ws_collector (E-12, E-03: sync pymongo)."""
from __future__ import annotations

import os
import signal
import subprocess
import sys
from typing import Any

from backend.database.sync_connection import get_sync_db
from backend.utils.time_utils import now_ist_iso

_collector_process: subprocess.Popen | None = None


def _is_collector_running() -> bool:
    """Check if collector subprocess is alive."""
    global _collector_process
    if _collector_process is None:
        return False
    return _collector_process.poll() is None


def start_collector() -> dict[str, Any]:
    """Spawn the collector as a subprocess."""
    global _collector_process
    if _is_collector_running():
        raise RuntimeError(f"Collector already running (PID {_collector_process.pid})")

    # Inherit stdout/stderr so collector errors are visible in backend logs
    # and avoid PIPE buffer backpressure on long-running workloads.
    _collector_process = subprocess.Popen(
        [sys.executable, "-m", "backend.collector.run_collector"],
    )

    # Update status in MongoDB
    db = get_sync_db()
    db.collector_status.update_one(
        {"_id": "singleton"},
        {"$set": {
            "collector.status": "running",
            "collector.pid": _collector_process.pid,
            "collector.started_at": now_ist_iso(),
            "collector.heartbeat_at": now_ist_iso(),
            "collector.last_error": None,
        }},
        upsert=True,
    )

    return {"pid": _collector_process.pid}


def stop_collector() -> dict[str, Any]:
    """Stop the collector subprocess."""
    global _collector_process
    if not _is_collector_running():
        return {"message": "Collector is not running"}

    pid = _collector_process.pid
    try:
        if os.name == "nt":
            _collector_process.terminate()
        else:
            os.kill(pid, signal.SIGTERM)
        _collector_process.wait(timeout=10)
    except Exception:
        _collector_process.kill()
    finally:
        _collector_process = None

    # Update status
    db = get_sync_db()
    db.collector_status.update_one(
        {"_id": "singleton"},
        {"$set": {
            "collector.status": "stopped",
            "collector.pid": None,
            "collector.heartbeat_at": now_ist_iso(),
        }},
        upsert=True,
    )

    return {"pid": pid, "message": "Collector stopped"}
