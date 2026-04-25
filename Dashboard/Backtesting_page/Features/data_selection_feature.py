from __future__ import annotations

from pathlib import Path
from threading import Lock
from typing import Any

import streamlit as st

try:
    from watchdog.events import FileSystemEvent, FileSystemEventHandler
    from watchdog.observers import Observer
except ImportError:  # pragma: no cover - handled gracefully at runtime
    FileSystemEvent = Any
    FileSystemEventHandler = object  # type: ignore[assignment]
    Observer = None  # type: ignore[assignment]


DATA_ROOT = Path(__file__).resolve().parents[3] / "Data" / "testing_data" / "Data_files"

_SOURCE_CONFIG = {
    "yfinance_data": {
        "label": "yfinance_data",
        "selectable": True,
        "disabled": False,
    },
    "Zerodha_data": {
        "label": "Zerodha_data",
        "selectable": True,
        "disabled": False,
    },
}

_RUNTIME_KEY = "_data_selection_runtime"


class _DataFilesWatchHandler(FileSystemEventHandler):
    """Marks the cached file list as dirty when the data directory changes."""

    def __init__(self, session_state_proxy: Any, runtime_flags: dict[str, Any]) -> None:
        super().__init__()
        self._session_state_proxy = session_state_proxy
        self._runtime_flags = runtime_flags
        self._lock = Lock()

    def on_created(self, event: FileSystemEvent) -> None:
        self._mark_dirty_if_relevant(event)

    def on_deleted(self, event: FileSystemEvent) -> None:
        self._mark_dirty_if_relevant(event)

    def on_moved(self, event: FileSystemEvent) -> None:
        self._mark_dirty_if_relevant(event)

    def _mark_dirty_if_relevant(self, event: FileSystemEvent) -> None:
        if not _event_touches_data_root(event):
            return

        with self._lock:
            self._runtime_flags["data_files_dirty"] = True

            try:
                self._session_state_proxy["data_files_dirty"] = True
            except Exception:
                # Background threads do not always have direct Streamlit access.
                # The runtime flag keeps the next UI rerun in sync.
                pass


def initialize_data_layer() -> None:
    """Initialize session state and start the watchdog observer once."""

    runtime_flags = _ensure_session_defaults()
    observer = st.session_state.get("watchdog_observer")

    if observer is not None and getattr(observer, "is_alive", lambda: False)():
        return

    if Observer is None or not DATA_ROOT.is_dir():
        return

    try:
        handler = _DataFilesWatchHandler(st.session_state, runtime_flags)
        observer = Observer()
        observer.daemon = True
        observer.schedule(handler, str(DATA_ROOT), recursive=True)
        observer.start()
    except OSError:
        st.session_state["watchdog_observer"] = None
        return

    st.session_state["watchdog_observer"] = observer


def get_data_sources() -> list[dict[str, Any]]:
    """Return the configured data sources with their current status."""

    _ensure_session_defaults()
    cache = st.session_state["data_files_cache"]

    return [
        {
            "name": source_name,
            "label": source_meta["label"],
            "disabled": source_meta["disabled"],
            "selectable": source_meta["selectable"],
            "directory_exists": source_meta["directory_exists"],
            "file_count": source_meta["file_count"],
            "root_exists": cache["root_exists"],
        }
        for source_name, source_meta in cache["sources"].items()
    ]


def get_data_files(source: str) -> list[dict[str, Any]]:
    """Return the cached file list for the requested data source."""

    _ensure_session_defaults()
    cache = st.session_state["data_files_cache"]
    source_meta = cache["sources"].get(source, {})
    return list(source_meta.get("files", []))


def filter_data_files(files: list[dict[str, Any]], query: str) -> list[dict[str, Any]]:
    """Filter data files by a case-insensitive substring match."""

    normalized_query = (query or "").strip().lower()
    if not normalized_query:
        return list(files)

    return [
        file_meta
        for file_meta in files
        if normalized_query in file_meta["display_name"].lower()
        or normalized_query in file_meta["name"].lower()
        or normalized_query in file_meta["relative_path"].lower()
    ]


def refresh_if_needed() -> dict[str, Any]:
    """Refresh the cached file list only when the dirty flag is set."""

    runtime_flags = _ensure_session_defaults()

    if runtime_flags.get("data_files_dirty"):
        st.session_state["data_files_dirty"] = True

    if st.session_state.get("data_files_dirty", True):
        st.session_state["data_files_cache"] = _scan_data_root()
        runtime_flags["data_files_dirty"] = False
        st.session_state["data_files_dirty"] = False

    st.session_state["selected_data_files"] = validate_selection(
        st.session_state.get("selected_data_files", [])
    )
    return st.session_state["data_files_cache"]


def validate_selection(selection: list[str] | tuple[str, ...] | None) -> list[str]:
    """Keep only existing, selectable files and remove duplicates."""

    _ensure_session_defaults()
    valid_ids = {
        file_meta["id"]
        for source_meta in st.session_state["data_files_cache"]["sources"].values()
        if source_meta["selectable"]
        for file_meta in source_meta["files"]
    }

    cleaned_selection: list[str] = []
    seen: set[str] = set()

    for selected_file in selection or []:
        if selected_file in valid_ids and selected_file not in seen:
            cleaned_selection.append(selected_file)
            seen.add(selected_file)

    st.session_state["selected_data_files"] = cleaned_selection
    return cleaned_selection


def _ensure_session_defaults() -> dict[str, Any]:
    if "data_files_cache" not in st.session_state:
        st.session_state["data_files_cache"] = _build_empty_cache()

    if "data_files_dirty" not in st.session_state:
        st.session_state["data_files_dirty"] = True

    if "selected_data_files" not in st.session_state:
        st.session_state["selected_data_files"] = []

    if "watchdog_observer" not in st.session_state:
        st.session_state["watchdog_observer"] = None

    runtime_flags = st.session_state.setdefault(_RUNTIME_KEY, {"data_files_dirty": True})
    runtime_flags.setdefault("data_files_dirty", True)
    return runtime_flags


def _build_empty_cache() -> dict[str, Any]:
    root_exists = DATA_ROOT.is_dir()
    sources = {}

    for source_name, config in _SOURCE_CONFIG.items():
        source_dir = DATA_ROOT / source_name
        sources[source_name] = {
            "label": config["label"],
            "selectable": config["selectable"],
            "disabled": config["disabled"],
            "directory_exists": source_dir.is_dir(),
            "files": [],
            "file_count": 0,
        }

    return {
        "root_exists": root_exists,
        "sources": sources,
    }


def _scan_data_root() -> dict[str, Any]:
    cache = _build_empty_cache()
    if not DATA_ROOT.is_dir():
        return cache

    for source_name, source_meta in cache["sources"].items():
        source_dir = DATA_ROOT / source_name
        source_meta["directory_exists"] = source_dir.is_dir()

        if not source_dir.is_dir():
            continue

        source_files = sorted(
            (file_path for file_path in source_dir.rglob("*.csv") if file_path.is_file()),
            key=lambda file_path: file_path.relative_to(source_dir).as_posix().lower(),
        )

        source_meta["files"] = [
            {
                "id": file_path.relative_to(DATA_ROOT).as_posix(),
                "name": file_path.name,
                "relative_path": file_path.relative_to(DATA_ROOT).as_posix(),
                "display_name": file_path.relative_to(source_dir).as_posix(),
            }
            for file_path in source_files
        ]
        source_meta["file_count"] = len(source_meta["files"])

    return cache


def _event_touches_data_root(event: FileSystemEvent) -> bool:
    event_paths = [getattr(event, "src_path", None), getattr(event, "dest_path", None)]

    for raw_path in event_paths:
        if not raw_path:
            continue

        try:
            path = Path(raw_path).resolve()
            path.relative_to(DATA_ROOT.resolve())
            return True
        except (OSError, RuntimeError, ValueError):
            continue

    return False
