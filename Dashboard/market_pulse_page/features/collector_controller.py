from __future__ import annotations

from datetime import datetime
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
from typing import Any

from LiveMarket import COLLECTOR_STATUS_PATH, LIVE_MARKET_ROOT, PROJECT_ROOT, SNAPSHOTS_ROOT


PROCESS_STATE_PATH = LIVE_MARKET_ROOT / "process_state.json"
_COLLECTOR_SCRIPT = PROJECT_ROOT / "LiveMarket" / "run_collector.py"
_CALC_SCRIPT = PROJECT_ROOT / "LiveMarket" / "run_calculations.py"


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")
    temp_path.replace(path)


def _load_process_state() -> dict[str, Any]:
    state = _read_json(PROCESS_STATE_PATH)
    state.setdefault("collector", {})
    state.setdefault("calculator", {})
    return state


def _save_process_state(state: dict[str, Any]) -> None:
    _atomic_write_json(PROCESS_STATE_PATH, state)


def _is_pid_alive(pid: int | None) -> bool:
    if pid is None or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _coerce_pid(value: Any) -> int | None:
    try:
        pid = int(value)
    except (TypeError, ValueError):
        return None
    return pid if pid > 0 else None


def _start_script(script_path: Path, key: str) -> tuple[bool, str]:
    state = _load_process_state()
    process_state = state.get(key, {}) if isinstance(state.get(key), dict) else {}
    existing_pid = _coerce_pid(process_state.get("pid"))
    if _is_pid_alive(existing_pid):
        return False, f"{key.capitalize()} is already running (PID {existing_pid})."

    if not script_path.is_file():
        return False, f"Script not found: {script_path}"

    logs_dir = LIVE_MARKET_ROOT / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_path = logs_dir / f"{key}.log"
    stderr_path = logs_dir / f"{key}_error.log"

    with log_path.open("a", encoding="utf-8") as out_handle, stderr_path.open("a", encoding="utf-8") as err_handle:
        creationflags = 0
        if os.name == "nt":
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)

        process = subprocess.Popen(
            [sys.executable, str(script_path)],
            cwd=str(PROJECT_ROOT),
            stdout=out_handle,
            stderr=err_handle,
            creationflags=creationflags,
        )

    state[key] = {
        "pid": process.pid,
        "started_at": _now_iso(),
        "script": str(script_path),
    }
    _save_process_state(state)
    return True, f"{key.capitalize()} started (PID {process.pid})."


def _stop_pid(pid: int) -> None:
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            check=False,
            capture_output=True,
            text=True,
        )
        return

    try:
        os.kill(pid, signal.SIGTERM)
    except OSError:
        return


def _stop_process(key: str) -> tuple[bool, str]:
    state = _load_process_state()
    process_state = state.get(key, {}) if isinstance(state.get(key), dict) else {}
    pid = _coerce_pid(process_state.get("pid"))
    if not _is_pid_alive(pid):
        state[key] = {}
        _save_process_state(state)
        return False, f"{key.capitalize()} is not running."

    assert pid is not None
    _stop_pid(pid)
    state[key] = {}
    _save_process_state(state)
    return True, f"{key.capitalize()} stopped."


def start_collector() -> tuple[bool, str]:
    return _start_script(_COLLECTOR_SCRIPT, "collector")


def stop_collector() -> tuple[bool, str]:
    return _stop_process("collector")


def start_calculator() -> tuple[bool, str]:
    return _start_script(_CALC_SCRIPT, "calculator")


def stop_calculator() -> tuple[bool, str]:
    return _stop_process("calculator")


def start_all() -> tuple[bool, str]:
    collector_ok, collector_msg = start_collector()
    calculator_ok, calculator_msg = start_calculator()
    ok = collector_ok or calculator_ok
    return ok, f"{collector_msg} {calculator_msg}".strip()


def stop_all() -> tuple[bool, str]:
    collector_ok, collector_msg = stop_collector()
    calculator_ok, calculator_msg = stop_calculator()
    ok = collector_ok or calculator_ok
    return ok, f"{collector_msg} {calculator_msg}".strip()


def is_collector_running() -> bool:
    state = _load_process_state()
    pid = _coerce_pid((state.get("collector") or {}).get("pid"))
    return _is_pid_alive(pid)


def is_calculator_running() -> bool:
    state = _load_process_state()
    pid = _coerce_pid((state.get("calculator") or {}).get("pid"))
    return _is_pid_alive(pid)


def get_status() -> dict[str, Any]:
    state = _load_process_state()
    collector_state = state.get("collector") if isinstance(state.get("collector"), dict) else {}
    calculator_state = state.get("calculator") if isinstance(state.get("calculator"), dict) else {}

    collector_pid = _coerce_pid((collector_state or {}).get("pid"))
    calculator_pid = _coerce_pid((calculator_state or {}).get("pid"))
    collector_running = _is_pid_alive(collector_pid)
    calculator_running = _is_pid_alive(calculator_pid)

    collector_file_status = _read_json(COLLECTOR_STATUS_PATH)

    snapshot_files = {
        "vwap": SNAPSHOTS_ROOT / "vwap_snapshot.json",
        "ad": SNAPSHOTS_ROOT / "ad_snapshot.json",
        "pcr": SNAPSHOTS_ROOT / "pcr_snapshot.json",
        "atm_oi": SNAPSHOTS_ROOT / "atm_oi_snapshot.json",
        "vix": SNAPSHOTS_ROOT / "vix_snapshot.json",
    }
    snapshots_last_modified: dict[str, str | None] = {}
    for key, path in snapshot_files.items():
        if path.is_file():
            snapshots_last_modified[key] = datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec="seconds")
        else:
            snapshots_last_modified[key] = None

    return {
        "collector": {
            "running": collector_running,
            "pid": collector_pid,
            "started_at": (collector_state or {}).get("started_at"),
        },
        "calculator": {
            "running": calculator_running,
            "pid": calculator_pid,
            "started_at": (calculator_state or {}).get("started_at"),
        },
        "collector_file_status": collector_file_status,
        "snapshots_last_modified": snapshots_last_modified,
        "updated_at": _now_iso(),
    }


__all__ = [
    "get_status",
    "is_calculator_running",
    "is_collector_running",
    "start_all",
    "start_calculator",
    "start_collector",
    "stop_all",
    "stop_calculator",
    "stop_collector",
]
