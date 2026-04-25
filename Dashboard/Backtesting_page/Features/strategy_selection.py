from __future__ import annotations

import hashlib
import importlib.util
import inspect
import sys
from pathlib import Path
from threading import Lock
from typing import Any

import streamlit as st

try:
    import backtrader as bt
except ImportError:  # pragma: no cover - handled gracefully at runtime
    bt = None  # type: ignore[assignment]

try:
    from watchdog.events import FileSystemEvent, FileSystemEventHandler
    from watchdog.observers import Observer
except ImportError:  # pragma: no cover - handled gracefully at runtime
    FileSystemEvent = Any
    FileSystemEventHandler = object  # type: ignore[assignment]
    Observer = None  # type: ignore[assignment]


STRATEGY_CODES_ROOT = Path(__file__).resolve().parents[3] / "Strategies" / "Strategy_codes"
STRATEGY_VERSIONING_ROOT = STRATEGY_CODES_ROOT / "strategy_versioning"
_RUNTIME_KEY = "_strategy_selection_runtime"


class _StrategyFilesWatchHandler(FileSystemEventHandler):
    """Marks the strategy file cache dirty when files change on disk."""

    def __init__(self, session_state_proxy: Any, runtime_flags: dict[str, Any]) -> None:
        super().__init__()
        self._session_state_proxy = session_state_proxy
        self._runtime_flags = runtime_flags
        self._lock = Lock()

    def on_created(self, event: FileSystemEvent) -> None:
        self._mark_dirty_if_relevant(event)

    def on_deleted(self, event: FileSystemEvent) -> None:
        self._mark_dirty_if_relevant(event)

    def on_modified(self, event: FileSystemEvent) -> None:
        self._mark_dirty_if_relevant(event)

    def _mark_dirty_if_relevant(self, event: FileSystemEvent) -> None:
        if not _event_touches_strategy_root(event):
            return

        with self._lock:
            self._runtime_flags["strategy_files_dirty"] = True

            try:
                self._session_state_proxy["strategy_files_dirty"] = True
            except Exception:
                pass


def initialize_strategy_layer() -> None:
    """Initialize strategy session state and start the watchdog once."""

    runtime_flags = _ensure_session_defaults()
    observer = st.session_state.get("watchdog_observer_strategy")

    if observer is not None and getattr(observer, "is_alive", lambda: False)():
        return

    if Observer is None or not STRATEGY_CODES_ROOT.is_dir():
        return

    try:
        handler = _StrategyFilesWatchHandler(st.session_state, runtime_flags)
        observer = Observer()
        observer.daemon = True
        observer.schedule(handler, str(STRATEGY_CODES_ROOT), recursive=True)
        observer.start()
    except OSError:
        st.session_state["watchdog_observer_strategy"] = None
        return

    st.session_state["watchdog_observer_strategy"] = observer


def refresh_if_needed() -> list[dict[str, Any]]:
    """Refresh the cached strategy files only when dirty or empty."""

    runtime_flags = _ensure_session_defaults()

    if runtime_flags.get("strategy_files_dirty"):
        st.session_state["strategy_files_dirty"] = True

    if st.session_state.get("strategy_files_dirty", True) or not st.session_state["strategy_files_cache"]:
        st.session_state["strategy_files_cache"] = _scan_strategy_root()
        runtime_flags["strategy_files_dirty"] = False
        st.session_state["strategy_files_dirty"] = False

    return list(st.session_state["strategy_files_cache"])


def get_strategy_files() -> list[dict[str, Any]]:
    """Return the cached strategy file metadata list."""

    _ensure_session_defaults()
    return list(st.session_state["strategy_files_cache"])


def filter_strategy_files(files: list[dict[str, Any]], query: str) -> list[dict[str, Any]]:
    """Filter strategy files using a case-insensitive substring match."""

    normalized_query = (query or "").strip().lower()
    if not normalized_query:
        return list(files)

    return [
        file_meta
        for file_meta in files
        if normalized_query in file_meta["display_name"].lower()
        or normalized_query in file_meta["id"].lower()
    ]


def get_strategy_classes(file_id: str) -> list[str]:
    """Return valid backtrader.Strategy subclasses for a strategy file."""

    if bt is None:
        return []

    _ensure_session_defaults()

    file_path = _resolve_strategy_file(file_id)
    if file_path is None or not file_path.is_file():
        return []

    module_name = f"_strategy_selection_{hashlib.sha1(str(file_path).encode('utf-8')).hexdigest()}"

    try:
        spec = importlib.util.spec_from_file_location(module_name, file_path)
        if spec is None or spec.loader is None:
            return []

        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
    except Exception:
        return []
    finally:
        sys.modules.pop(module_name, None)

    strategy_classes = []
    for _, cls in inspect.getmembers(module, inspect.isclass):
        if cls.__module__ != module.__name__:
            continue

        try:
            if issubclass(cls, bt.Strategy) and cls is not bt.Strategy:
                strategy_classes.append(cls.__name__)
        except TypeError:
            continue

    return sorted(strategy_classes, key=str.lower)


def _ensure_session_defaults() -> dict[str, Any]:
    if "strategy_files_cache" not in st.session_state:
        st.session_state["strategy_files_cache"] = []

    if "strategy_files_dirty" not in st.session_state:
        st.session_state["strategy_files_dirty"] = True

    if "watchdog_observer_strategy" not in st.session_state:
        st.session_state["watchdog_observer_strategy"] = None

    runtime_flags = st.session_state.setdefault(_RUNTIME_KEY, {"strategy_files_dirty": True})
    runtime_flags.setdefault("strategy_files_dirty", True)
    return runtime_flags


def _scan_strategy_root() -> list[dict[str, Any]]:
    if not STRATEGY_CODES_ROOT.is_dir():
        return []

    strategy_files = []
    for file_path in STRATEGY_CODES_ROOT.rglob("*.py"):
        if not file_path.is_file():
            continue
        if "__pycache__" in file_path.parts:
            continue

        strategy_files.append(
            {
                "id": file_path.relative_to(STRATEGY_CODES_ROOT).as_posix(),
                "display_name": file_path.name,
                "full_path": str(file_path),
                "is_versioned": STRATEGY_VERSIONING_ROOT in file_path.parents,
            }
        )

    return sorted(
        strategy_files,
        key=lambda file_meta: (
            not file_meta["is_versioned"],
            file_meta["display_name"].lower(),
            file_meta["id"].lower(),
        ),
    )


def _resolve_strategy_file(file_id: str) -> Path | None:
    if not file_id:
        return None

    try:
        file_path = (STRATEGY_CODES_ROOT / file_id).resolve()
        file_path.relative_to(STRATEGY_CODES_ROOT.resolve())
    except (OSError, RuntimeError, ValueError):
        return None

    if file_path.suffix != ".py" or "__pycache__" in file_path.parts:
        return None

    return file_path


def _event_touches_strategy_root(event: FileSystemEvent) -> bool:
    event_paths = [getattr(event, "src_path", None), getattr(event, "dest_path", None)]

    for raw_path in event_paths:
        if not raw_path:
            continue

        try:
            path = Path(raw_path).resolve()
            path.relative_to(STRATEGY_CODES_ROOT.resolve())
        except (OSError, RuntimeError, ValueError):
            continue

        if path.suffix == ".py" or path.name == "__pycache__":
            return True

    return False
