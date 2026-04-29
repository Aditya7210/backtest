from __future__ import annotations

from datetime import datetime
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from typing import Any

from LiveMarket import COLLECTOR_STATUS_PATH, LIVE_MARKET_ROOT, PROJECT_ROOT, SNAPSHOTS_ROOT


PROCESS_STATE_PATH = LIVE_MARKET_ROOT / "process_state.json"
_COLLECTOR_SCRIPT = PROJECT_ROOT / "LiveMarket" / "run_collector.py"
_CALC_SCRIPT = PROJECT_ROOT / "LiveMarket" / "run_calculations.py"
_COLLECTOR_MODULE = "LiveMarket.run_collector"
_CALCULATOR_MODULE = "LiveMarket.run_calculations"
_LOGS_DIR = LIVE_MARKET_ROOT / "logs"
_COLLECTOR_ERROR_LOG = _LOGS_DIR / "collector_error.log"
_COLLECTOR_STATUS_MAX_STALE_SECONDS = 45


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

    # Linux: treat zombie processes as not alive for controller health.
    if os.name != "nt":
        stat_path = Path("/proc") / str(pid) / "stat"
        if stat_path.is_file():
            try:
                fields = stat_path.read_text(encoding="utf-8", errors="replace").split()
                # /proc/<pid>/stat third field is process state.
                if len(fields) >= 3 and fields[2] == "Z":
                    return False
            except Exception:
                pass

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


def _tail_text_file(path: Path, max_lines: int = 30) -> str:
    if not path.is_file():
        return ""
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception:
        return ""
    if not lines:
        return ""
    return "\n".join(lines[-max_lines:])


def _parse_iso_datetime(value: Any) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        return None


def _is_recent_iso_timestamp(value: Any, *, max_age_seconds: int) -> bool:
    parsed = _parse_iso_datetime(value)
    if parsed is None:
        return False

    if parsed.tzinfo is not None:
        now = datetime.now(parsed.tzinfo)
    else:
        now = datetime.now()
    age = (now - parsed).total_seconds()
    return 0 <= age <= float(max_age_seconds)


def _start_script(script_path: Path, key: str, module_name: str) -> tuple[bool, str]:
    state = _load_process_state()
    process_state = state.get(key, {}) if isinstance(state.get(key), dict) else {}
    existing_pid = _coerce_pid(process_state.get("pid"))
    if _is_pid_alive(existing_pid):
        return False, f"{key.capitalize()} is already running (PID {existing_pid})."

    if not script_path.is_file():
        return False, f"Script not found: {script_path}"

    _LOGS_DIR.mkdir(parents=True, exist_ok=True)
    log_path = _LOGS_DIR / f"{key}.log"
    stderr_path = _LOGS_DIR / f"{key}_error.log"

    with log_path.open("a", encoding="utf-8") as out_handle, stderr_path.open("a", encoding="utf-8") as err_handle:
        creationflags = 0
        if os.name == "nt":
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)

        process = subprocess.Popen(
            [sys.executable, "-m", module_name],
            cwd=str(PROJECT_ROOT),
            stdout=out_handle,
            stderr=err_handle,
            creationflags=creationflags,
        )

    # If process dies immediately, clear stale state and surface logs.
    time.sleep(0.35)
    return_code = process.poll()
    if return_code is not None:
        state[key] = {}
        _save_process_state(state)
        error_excerpt = _tail_text_file(stderr_path, max_lines=25)
        suffix = f"\n{error_excerpt}" if error_excerpt else ""
        return (
            False,
            f"{key.capitalize()} failed to start (exit code {return_code}).{suffix}",
        )

    state[key] = {
        "pid": process.pid,
        "started_at": _now_iso(),
        "script": str(script_path),
        "module": module_name,
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
    return _start_script(_COLLECTOR_SCRIPT, "collector", _COLLECTOR_MODULE)


def stop_collector() -> tuple[bool, str]:
    return _stop_process("collector")


def start_calculator() -> tuple[bool, str]:
    return _start_script(_CALC_SCRIPT, "calculator", _CALCULATOR_MODULE)


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
    collector_pid_alive = _is_pid_alive(collector_pid)
    calculator_running = _is_pid_alive(calculator_pid)

    state_changed = False
    if collector_pid is not None and not collector_pid_alive and collector_state:
        state["collector"] = {}
        collector_state = {}
        collector_pid = None
        state_changed = True
    if calculator_pid is not None and not calculator_running and calculator_state:
        state["calculator"] = {}
        calculator_state = {}
        calculator_pid = None
        state_changed = True
    if state_changed:
        _save_process_state(state)

    collector_file_status = _read_json(COLLECTOR_STATUS_PATH)
    collector_file_exists = COLLECTOR_STATUS_PATH.is_file()
    collector_file_state = str(collector_file_status.get("status") or "").strip().lower()
    status_updated_at = (
        collector_file_status.get("updated_at")
        or collector_file_status.get("started_at")
        or collector_file_status.get("date")
    )
    collector_status_fresh = _is_recent_iso_timestamp(
        status_updated_at,
        max_age_seconds=_COLLECTOR_STATUS_MAX_STALE_SECONDS,
    )
    collector_started_at = (collector_state or {}).get("started_at")
    collector_started_recent = _is_recent_iso_timestamp(
        collector_started_at,
        max_age_seconds=_COLLECTOR_STATUS_MAX_STALE_SECONDS,
    )
    if collector_pid_alive and not collector_file_exists and not collector_started_recent:
        # Stale PID metadata without heartbeat/status file: clear persisted state.
        state["collector"] = {}
        _save_process_state(state)
        collector_state = {}
        collector_pid = None
        collector_pid_alive = False

    collector_running = (
        collector_pid_alive
        and collector_file_exists
        and collector_file_state == "running"
        and collector_status_fresh
    )
    collector_error_excerpt = ""
    if not collector_file_exists or not collector_running:
        collector_error_excerpt = _tail_text_file(_COLLECTOR_ERROR_LOG, max_lines=30)

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
            "pid_alive": collector_pid_alive,
            "pid": collector_pid,
            "started_at": (collector_state or {}).get("started_at"),
            "healthy": collector_running,
        },
        "calculator": {
            "running": calculator_running,
            "pid": calculator_pid,
            "started_at": (calculator_state or {}).get("started_at"),
        },
        "collector_file_status": collector_file_status,
        "collector_status_health": {
            "status_file_exists": collector_file_exists,
            "status_file_state": collector_file_state or None,
            "status_recent": collector_status_fresh,
        },
        "collector_error_excerpt": collector_error_excerpt,
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
