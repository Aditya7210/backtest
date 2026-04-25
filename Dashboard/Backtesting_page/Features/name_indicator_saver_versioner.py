from __future__ import annotations

import re
import tempfile
from pathlib import Path
from threading import Lock

import streamlit as st

from . import strategy_editor, strategy_selection

MAX_STRATEGY_NAME_LENGTH = 120
_SAVE_LOCK = Lock()
_BOUND_FILE_STATE_KEY = "_strategy_display_bound_file"

_INVALID_FILE_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1F]')
_ALLOWED_NAME_CHARS = re.compile(r"^[A-Za-z0-9 _-]+$")


def initialize_lifecycle_state() -> None:
    """Initialize lifecycle-related session state once per Streamlit session."""

    _ensure_lifecycle_defaults()
    sync_strategy_display_name()


def _ensure_lifecycle_defaults() -> None:
    """Initialize lifecycle session keys without mutating bound UI values."""

    st.session_state.setdefault("strategy_display_name", "")
    st.session_state.setdefault("versioning_enabled", False)
    st.session_state.setdefault("save_status_message", None)
    st.session_state.setdefault(_BOUND_FILE_STATE_KEY, None)


def sync_strategy_display_name() -> None:
    """
    Keep the editable strategy name bound to the currently selected strategy file.

    This updates the editable name only when the selected file changes.
    """

    selected_strategy_file = st.session_state.get("selected_strategy_file")
    bound_file = st.session_state.get(_BOUND_FILE_STATE_KEY)

    if selected_strategy_file == bound_file:
        return

    if not selected_strategy_file:
        st.session_state["strategy_display_name"] = ""
        st.session_state[_BOUND_FILE_STATE_KEY] = None
        return

    st.session_state["strategy_display_name"] = Path(str(selected_strategy_file)).stem
    st.session_state[_BOUND_FILE_STATE_KEY] = selected_strategy_file


def clean_strategy_name(name: str) -> str:
    """Normalize a strategy name into a safe Python filename stem."""

    raw_name = (name or "").strip()
    if raw_name.lower().endswith(".py"):
        raw_name = raw_name[:-3]

    # Replace spaces first, then remove unsupported characters.
    cleaned = raw_name.replace(" ", "_")
    cleaned = re.sub(r"[^A-Za-z0-9_-]", "", cleaned)
    cleaned = re.sub(r"_+", "_", cleaned)
    cleaned = cleaned.strip("._-")

    return cleaned


def validate_strategy_name(
    name: str,
    *,
    current_file_id: str | None = None,
) -> tuple[bool, str | None]:
    """Validate naming constraints before save/rename/version actions."""

    raw_name = (name or "").strip()
    if not raw_name:
        return False, "Strategy name cannot be empty"

    if raw_name.lower().endswith(".py"):
        raw_name = raw_name[:-3]

    if not raw_name.strip():
        return False, "Strategy name cannot be empty"

    if _INVALID_FILE_CHARS.search(raw_name):
        return False, "Strategy name contains invalid characters"

    if not _ALLOWED_NAME_CHARS.fullmatch(raw_name):
        return False, "Strategy name contains invalid characters"

    cleaned_name = clean_strategy_name(raw_name)
    if not cleaned_name:
        return False, "Strategy name cannot be empty"

    if len(raw_name) > MAX_STRATEGY_NAME_LENGTH:
        return False, "Strategy name is too long"

    if len(cleaned_name) > MAX_STRATEGY_NAME_LENGTH:
        return False, "Strategy name is too long"

    if _strategy_name_exists(cleaned_name, current_file_id=current_file_id):
        return False, "Strategy with this name already exists"

    return True, None


def get_indicator_color() -> str:
    """Return save indicator color based on editor dirty state."""

    return "red" if bool(st.session_state.get("is_dirty")) else "green"


def rename_strategy_file(
    old_path: Path,
    new_name: str,
) -> tuple[bool, Path | None, str | None]:
    """Rename an existing strategy file inside the strategy root safely."""

    file_path = _resolve_existing_path(old_path)
    if file_path is None:
        return False, None, "Selected strategy file is missing or invalid"

    cleaned_name = clean_strategy_name(new_name)
    if not cleaned_name:
        return False, None, "Strategy name cannot be empty"

    target_path = file_path.with_name(f"{cleaned_name}.py")
    target_path = _resolve_allowed_path(target_path)
    if target_path is None:
        return False, None, "Resolved strategy path is invalid"

    if target_path == file_path:
        return True, file_path, None

    if target_path.exists():
        return False, None, "Strategy with this name already exists"

    try:
        file_path.rename(target_path)
    except OSError as exc:
        return False, None, f"Unable to rename strategy: {exc}"

    return True, target_path, None


def create_version_file(base_name: str, content: str) -> tuple[bool, Path | None, str | None]:
    """Create a new versioned strategy file under strategy_versioning/."""

    cleaned_base_name = clean_strategy_name(base_name)
    if not cleaned_base_name:
        return False, None, "Strategy name cannot be empty"

    version_root = strategy_selection.STRATEGY_VERSIONING_ROOT
    try:
        version_root.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return False, None, f"Unable to create version folder: {exc}"

    version_pattern = re.compile(rf"^{re.escape(cleaned_base_name)}_v(\d+)\.py$", re.IGNORECASE)
    max_version = 0

    for version_file in version_root.glob(f"{cleaned_base_name}_v*.py"):
        if not version_file.is_file():
            continue
        match = version_pattern.fullmatch(version_file.name)
        if not match:
            continue
        max_version = max(max_version, int(match.group(1)))

    next_version = max_version + 1
    target_path = version_root / f"{cleaned_base_name}_v{next_version}.py"
    while target_path.exists():
        next_version += 1
        target_path = version_root / f"{cleaned_base_name}_v{next_version}.py"

    write_ok, write_error = _write_text_atomic(target_path, content)
    if not write_ok:
        return False, None, write_error

    return True, target_path, None


def save_strategy() -> tuple[bool, str]:
    """
    Save strategy content with optional rename/versioning.

    Returns:
        tuple[bool, str]:
            success flag and user-facing status message.
    """

    _ensure_lifecycle_defaults()

    with _SAVE_LOCK:
        selected_strategy_file = st.session_state.get("selected_strategy_file")
        if not selected_strategy_file:
            message = "Select a strategy file before saving"
            st.session_state["save_status_message"] = message
            return False, message

        source_path = _resolve_file_id(str(selected_strategy_file))
        if source_path is None or not source_path.is_file():
            st.session_state["selected_strategy_file"] = None
            strategy_editor._set_editor_state(
                current_strategy_file=None,
                editor_content="",
                saved_content="",
                is_dirty=False,
            )
            message = "Strategy file not found or unreadable. Editor cleared."
            st.session_state["save_status_message"] = message
            return False, message

        strategy_selection.refresh_if_needed()

        display_name = str(st.session_state.get("strategy_display_name", ""))
        valid_name, validation_error = validate_strategy_name(
            display_name,
            current_file_id=str(selected_strategy_file),
        )
        if not valid_name:
            message = validation_error or "Invalid strategy name"
            st.session_state["save_status_message"] = message
            return False, message

        cleaned_name = clean_strategy_name(display_name)
        editor_content = str(st.session_state.get("editor_content", ""))
        versioning_enabled = bool(st.session_state.get("versioning_enabled", False))

        working_path = source_path
        working_file_id = str(selected_strategy_file)

        if working_path.stem != cleaned_name:
            rename_ok, renamed_path, rename_error = rename_strategy_file(working_path, cleaned_name)
            if not rename_ok or renamed_path is None:
                message = rename_error or "Unable to rename strategy file"
                st.session_state["save_status_message"] = message
                return False, message
            working_path = renamed_path
            working_file_id = _path_to_file_id(working_path)

        if versioning_enabled:
            version_ok, version_path, version_error = create_version_file(cleaned_name, editor_content)
            if not version_ok or version_path is None:
                message = version_error or "Unable to create version file"
                st.session_state["save_status_message"] = message
                return False, message
            working_path = version_path
            working_file_id = _path_to_file_id(working_path)
            success_message = f"Strategy version saved: {working_path.name}"
        else:
            write_ok, write_error = _write_text_atomic(working_path, editor_content)
            if not write_ok:
                message = write_error or "Unable to save strategy"
                st.session_state["save_status_message"] = message
                return False, message
            success_message = f"Strategy saved: {working_path.name}"

        _mark_strategy_cache_dirty()
        strategy_selection.refresh_if_needed()

        st.session_state["selected_strategy_file"] = working_file_id
        # Do not write to the widget-bound key ("strategy_display_name") during the same
        # run after the widget is instantiated. Force next-run sync instead.
        st.session_state[_BOUND_FILE_STATE_KEY] = None
        st.session_state["save_status_message"] = success_message

        # Keep editor/session state authoritative after successful save.
        strategy_editor._set_editor_state(
            current_strategy_file=working_file_id,
            editor_content=editor_content,
            saved_content=editor_content,
            is_dirty=False,
        )

        return True, success_message


def _strategy_name_exists(cleaned_name: str, *, current_file_id: str | None) -> bool:
    target_filename = f"{cleaned_name}.py".lower()
    normalized_current = str(current_file_id or "").replace("\\", "/").lower()

    for file_meta in strategy_selection.get_strategy_files():
        file_id = str(file_meta.get("id", "")).replace("\\", "/").lower()
        display_name = str(file_meta.get("display_name", "")).lower()
        if display_name != target_filename:
            continue
        if normalized_current and file_id == normalized_current:
            continue
        return True

    return False


def _resolve_file_id(file_id: str) -> Path | None:
    if not file_id:
        return None

    try:
        file_path = (strategy_selection.STRATEGY_CODES_ROOT / file_id).resolve()
        file_path.relative_to(strategy_selection.STRATEGY_CODES_ROOT.resolve())
    except (OSError, RuntimeError, ValueError):
        return None

    if file_path.suffix != ".py" or "__pycache__" in file_path.parts:
        return None

    return file_path


def _resolve_existing_path(path: Path) -> Path | None:
    resolved = _resolve_allowed_path(path)
    if resolved is None or not resolved.is_file():
        return None
    return resolved


def _resolve_allowed_path(path: Path) -> Path | None:
    try:
        resolved = path.resolve()
        resolved.relative_to(strategy_selection.STRATEGY_CODES_ROOT.resolve())
    except (OSError, RuntimeError, ValueError):
        return None

    if resolved.suffix != ".py" or "__pycache__" in resolved.parts:
        return None

    return resolved


def _path_to_file_id(path: Path) -> str:
    return path.relative_to(strategy_selection.STRATEGY_CODES_ROOT).as_posix()


def _mark_strategy_cache_dirty() -> None:
    st.session_state["strategy_files_dirty"] = True
    runtime_flags = st.session_state.get("_strategy_selection_runtime")
    if isinstance(runtime_flags, dict):
        runtime_flags["strategy_files_dirty"] = True


def _write_text_atomic(target_path: Path, content: str) -> tuple[bool, str | None]:
    safe_path = _resolve_allowed_path(target_path)
    if safe_path is None:
        return False, "Resolved strategy path is invalid"

    parent_dir = safe_path.parent
    try:
        parent_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return False, f"Unable to prepare target directory: {exc}"

    temp_file_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=str(parent_dir),
            delete=False,
            suffix=".tmp",
        ) as temp_file:
            temp_file.write(content)
            temp_file_path = Path(temp_file.name)

        temp_file_path.replace(safe_path)
    except OSError as exc:
        if temp_file_path is not None and temp_file_path.exists():
            try:
                temp_file_path.unlink()
            except OSError:
                pass
        return False, f"Unable to write strategy file: {exc}"

    return True, None


__all__ = [
    "clean_strategy_name",
    "create_version_file",
    "get_indicator_color",
    "initialize_lifecycle_state",
    "rename_strategy_file",
    "save_strategy",
    "sync_strategy_display_name",
    "validate_strategy_name",
]
