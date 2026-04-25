from __future__ import annotations

from pathlib import Path

import streamlit as st

from . import strategy_selection

STRATEGY_ROOT = strategy_selection.STRATEGY_CODES_ROOT
_EDITOR_CLEARED_MESSAGE = "Strategy file not found or unreadable. Editor cleared."


def _normalize_editor_text(content: str) -> str:
    """Normalize editor text so dirty checks are stable across line-ending styles."""

    return (content or "").replace("\r\n", "\n").replace("\r", "\n")


def _initialize_editor_state() -> None:
    st.session_state.setdefault("current_strategy_file", None)
    st.session_state.setdefault("editor_content", "")
    st.session_state.setdefault("saved_content", "")
    st.session_state.setdefault("is_dirty", False)
    st.session_state.setdefault("bt_code_editor", "")


def _set_editor_state(
    *,
    current_strategy_file: str | None,
    editor_content: str,
    saved_content: str,
    is_dirty: bool,
) -> None:
    normalized_editor_content = _normalize_editor_text(editor_content)
    normalized_saved_content = _normalize_editor_text(saved_content)

    st.session_state["current_strategy_file"] = current_strategy_file
    st.session_state["editor_content"] = normalized_editor_content
    st.session_state["saved_content"] = normalized_saved_content
    st.session_state["is_dirty"] = is_dirty
    st.session_state["bt_code_editor"] = normalized_editor_content


def _reset_editor_state() -> None:
    _set_editor_state(
        current_strategy_file=None,
        editor_content="",
        saved_content="",
        is_dirty=False,
    )


def _resolve_strategy_file(file_id: str | None) -> Path | None:
    if not file_id:
        return None

    try:
        file_path = (STRATEGY_ROOT / file_id).resolve()
        file_path.relative_to(STRATEGY_ROOT.resolve())
    except (OSError, RuntimeError, ValueError):
        return None

    if file_path.suffix != ".py" or "__pycache__" in file_path.parts:
        return None

    return file_path


def _sync_editor_state_with_selection() -> str | None:
    selected_strategy_file = st.session_state.get("selected_strategy_file")
    current_strategy_file = st.session_state.get("current_strategy_file")

    if selected_strategy_file == current_strategy_file:
        if selected_strategy_file:
            file_path = _resolve_strategy_file(selected_strategy_file)
            if file_path is None or not file_path.is_file():
                _reset_editor_state()
                st.session_state["selected_strategy_file"] = None
                return _EDITOR_CLEARED_MESSAGE
        return None

    if not selected_strategy_file:
        _reset_editor_state()
        return None

    file_path = _resolve_strategy_file(selected_strategy_file)
    if file_path is None or not file_path.is_file():
        _reset_editor_state()
        st.session_state["selected_strategy_file"] = None
        return _EDITOR_CLEARED_MESSAGE

    try:
        file_content = file_path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        _reset_editor_state()
        st.session_state["selected_strategy_file"] = None
        return _EDITOR_CLEARED_MESSAGE

    _set_editor_state(
        current_strategy_file=selected_strategy_file,
        editor_content=file_content,
        saved_content=file_content,
        is_dirty=False,
    )
    return None


def _on_editor_change() -> None:
    if st.session_state.get("selected_strategy_file") is None:
        if st.session_state.get("current_strategy_file") is not None:
            _reset_editor_state()
        return

    editor_content = _normalize_editor_text(st.session_state.get("bt_code_editor", ""))
    saved_content = _normalize_editor_text(st.session_state.get("saved_content", ""))
    st.session_state["editor_content"] = editor_content
    st.session_state["is_dirty"] = (
        editor_content != saved_content
    )
