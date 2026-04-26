from __future__ import annotations

from collections import OrderedDict
from datetime import datetime
from datetime import timedelta, timezone
from html import escape
from threading import RLock
from typing import Literal, TypedDict
from zoneinfo import ZoneInfo


LogLevel = Literal["INFO", "SUCCESS", "ERROR", "WARNING"]
_VALID_LEVELS: tuple[LogLevel, ...] = ("INFO", "SUCCESS", "ERROR", "WARNING")
_IST_FALLBACK = timezone(timedelta(hours=5, minutes=30))

try:
    _IST_TZ = ZoneInfo("Asia/Kolkata")
except Exception:
    _IST_TZ = _IST_FALLBACK

LEVEL_COLORS: dict[LogLevel, str] = {
    "INFO": "#AAB3BC",
    "SUCCESS": "#16A34A",
    "ERROR": "#DC2626",
    "WARNING": "#F59E0B",
}


class TerminalLogEntry(TypedDict):
    timestamp: str
    level: LogLevel
    message: str
    task_id: str | None
    symbol: str | None


class ExecutionTerminal:
    def __init__(self, max_lines: int = 1000) -> None:
        self.logs: list[TerminalLogEntry] = []
        self.max_lines = max(100, int(max_lines))
        self._lock = RLock()

    def log(
        self,
        message: str,
        level: str = "INFO",
        task_id: str | None = None,
        symbol: str | None = None,
    ) -> TerminalLogEntry:
        timestamp = datetime.now(_IST_TZ).strftime("%H:%M:%S")
        normalized_level = self._normalize_level(level)
        normalized_message = str(message or "").strip() or "(empty message)"
        normalized_task_id = str(task_id).strip() if task_id else None
        normalized_symbol = str(symbol).strip().upper() if symbol else None

        log_entry: TerminalLogEntry = {
            "timestamp": timestamp,
            "level": normalized_level,
            "message": normalized_message,
            "task_id": normalized_task_id,
            "symbol": normalized_symbol,
        }
        with self._lock:
            self.logs.append(log_entry)
            self._trim_locked()
        return log_entry

    def get_logs(self) -> list[TerminalLogEntry]:
        with self._lock:
            return [dict(item) for item in self.logs]

    def get_logs_by_task(self, task_id: str) -> list[TerminalLogEntry]:
        normalized = str(task_id or "").strip()
        if not normalized:
            return []
        with self._lock:
            return [dict(item) for item in self.logs if item.get("task_id") == normalized]

    def filter_logs(
        self,
        *,
        filter_symbol: str | None = None,
        filter_level: str | None = None,
        error_only: bool = False,
    ) -> list[TerminalLogEntry]:
        symbol_filter = self._normalize_filter(filter_symbol)
        level_filter = self._normalize_level_filter(filter_level)
        bypass_symbol_filter = not symbol_filter or symbol_filter == "ALL"
        bypass_level_filter = not level_filter

        filtered: list[TerminalLogEntry] = []
        with self._lock:
            for item in self.logs:
                symbol = str(item.get("symbol") or "").upper()
                level = str(item.get("level") or "INFO").upper()

                if not bypass_symbol_filter and symbol != symbol_filter:
                    continue
                if not bypass_level_filter and level != level_filter:
                    continue
                if error_only and level != "ERROR":
                    continue
                filtered.append(dict(item))
        return filtered

    def get_symbols(self) -> list[str]:
        with self._lock:
            symbols = {
                str(item.get("symbol") or "").strip().upper()
                for item in self.logs
                if str(item.get("symbol") or "").strip()
            }
        return sorted(symbols)

    def clear(self) -> None:
        with self._lock:
            self.logs = []

    def to_text(
        self,
        *,
        filter_symbol: str | None = None,
        filter_level: str | None = None,
        error_only: bool = False,
    ) -> str:
        filtered = self.filter_logs(
            filter_symbol=filter_symbol,
            filter_level=filter_level,
            error_only=error_only,
        )
        if not filtered:
            return "No logs yet"
        return "\n".join(_format_log_line(item) for item in filtered)

    def _trim_locked(self) -> None:
        if len(self.logs) <= self.max_lines:
            return
        self.logs = self.logs[-self.max_lines :]

    @staticmethod
    def _normalize_level(level: str | None) -> LogLevel:
        normalized = str(level or "INFO").strip().upper()
        if normalized in _VALID_LEVELS:
            return normalized  # type: ignore[return-value]
        return "INFO"

    @staticmethod
    def _normalize_filter(value: str | None) -> str:
        return str(value or "").strip().upper()

    @staticmethod
    def _normalize_level_filter(level: str | None) -> str:
        normalized = str(level or "").strip().upper()
        if not normalized or normalized == "ALL":
            return ""
        if normalized in _VALID_LEVELS:
            return normalized
        return ""


def render_terminal(
    terminal: ExecutionTerminal,
    *,
    filter_symbol: str | None = None,
    filter_level: str | None = None,
    error_only: bool = False,
    placeholder=None,
) -> list[TerminalLogEntry]:
    import streamlit as st

    target = placeholder or st.empty()
    requested_level = str(filter_level or "").strip().upper()
    filtered = terminal.filter_logs(
        filter_symbol=filter_symbol,
        filter_level=filter_level,
        error_only=error_only,
    )

    if requested_level in {"", "ALL"} and not error_only:
        all_count = len(filtered)
        for level in _VALID_LEVELS:
            specific_count = len(
                terminal.filter_logs(
                    filter_symbol=filter_symbol,
                    filter_level=level,
                    error_only=False,
                )
            )
            if specific_count > all_count:
                target.warning(
                    "Terminal filter sanity warning: ALL filter returned fewer logs than "
                    f"{level} filter."
                )
                break

    if not filtered:
        target.info("No logs yet")
        return []

    rendered_lines = "\n".join(_render_log_html(item) for item in filtered)
    target.markdown(
        f"""
<div style="background:#1E1E2E; border:1px solid #E5E7EB; border-radius:8px;
            padding:14px; max-height:280px; overflow-y:auto;
            font-family:'Consolas','Courier New',monospace; font-size:12px; line-height:1.6;">
{rendered_lines}
</div>
""",
        unsafe_allow_html=True,
    )
    return filtered


def render_terminal_panel(
    terminal: ExecutionTerminal,
    *,
    key_prefix: str = "execution_terminal",
) -> None:
    import streamlit as st

    st.markdown("#### Execution Terminal")

    symbols = terminal.get_symbols()
    level_options = ["All", "INFO", "SUCCESS", "WARNING", "ERROR"]

    col1, col2, col3 = st.columns([2, 2, 1], gap="small")
    with col1:
        selected_symbol = st.selectbox(
            "Filter Symbol",
            options=["All", *symbols],
            key=f"{key_prefix}_symbol_filter",
        )
    with col2:
        selected_level = st.selectbox(
            "Filter Level",
            options=level_options,
            key=f"{key_prefix}_level_filter",
        )
    with col3:
        error_only = st.toggle(
            "Errors",
            key=f"{key_prefix}_error_only",
            help="Show ERROR logs only.",
        )

    action_col1, action_col2, action_col3 = st.columns([1, 1, 2], gap="small")
    with action_col1:
        clear_clicked = st.button("Clear", key=f"{key_prefix}_clear")
    with action_col2:
        show_copy = st.button("Copy View", key=f"{key_prefix}_copy")
    with action_col3:
        download_text = terminal.to_text(
            filter_symbol=selected_symbol,
            filter_level=selected_level,
            error_only=error_only,
        )
        st.download_button(
            "Download Logs",
            data=download_text,
            file_name=f"{key_prefix}_logs.txt",
            mime="text/plain",
            key=f"{key_prefix}_download",
        )

    if clear_clicked:
        terminal.clear()
        st.rerun()

    if show_copy:
        st.code(download_text, language="text")

    placeholder = st.empty()
    render_terminal(
        terminal,
        filter_symbol=selected_symbol,
        filter_level=selected_level,
        error_only=error_only,
        placeholder=placeholder,
    )

    _render_task_logs(terminal, key_prefix=key_prefix)


def _render_task_logs(terminal: ExecutionTerminal, *, key_prefix: str) -> None:
    import streamlit as st

    task_map: OrderedDict[str, dict[str, str]] = OrderedDict()
    for item in terminal.get_logs():
        task_id = str(item.get("task_id") or "").strip()
        if not task_id:
            continue
        if task_id not in task_map:
            task_map[task_id] = {
                "task_id": task_id,
                "symbol": str(item.get("symbol") or "").strip().upper() or "UNKNOWN",
            }

    if not task_map:
        st.caption("No task-level logs yet.")
        return

    st.caption("Task Logs")
    for task in task_map.values():
        task_id = task["task_id"]
        symbol = task["symbol"]
        with st.expander(f"Logs for {symbol} ({task_id})", expanded=False):
            logs = terminal.get_logs_by_task(task_id)
            if not logs:
                st.caption("No logs for this task.")
                continue
            text = "\n".join(_format_log_line(item) for item in logs)
            st.code(text, language="text")


def _render_log_html(item: TerminalLogEntry) -> str:
    level = str(item.get("level") or "INFO").upper()
    level_color = LEVEL_COLORS.get(level, LEVEL_COLORS["INFO"])
    label_color = "#D1D5DB"
    message_color = "#E5E7EB"
    timestamp = escape(str(item.get("timestamp") or "00:00:00"))
    level_label = escape(level)
    symbol = str(item.get("symbol") or "").strip().upper()
    message = escape(str(item.get("message") or "").strip())
    symbol_prefix = f"{escape(symbol)} -> " if symbol else ""

    return (
        f"<div style='white-space:pre-wrap;'>"
        f"<span style='color:{label_color};'>[{timestamp}] </span>"
        f"<span style='color:{level_color};'>[{level_label}] </span>"
        f"<span style='color:{message_color};'>{symbol_prefix}{message}</span>"
        f"</div>"
    )


def _format_log_line(item: TerminalLogEntry) -> str:
    timestamp = str(item.get("timestamp") or "00:00:00")
    level = str(item.get("level") or "INFO").upper()
    symbol = str(item.get("symbol") or "").strip().upper()
    message = str(item.get("message") or "").strip()
    symbol_prefix = f"{symbol} -> " if symbol else ""
    return f"[{timestamp}] [{level}] {symbol_prefix}{message}"


__all__ = [
    "ExecutionTerminal",
    "LEVEL_COLORS",
    "TerminalLogEntry",
    "render_terminal",
    "render_terminal_panel",
]
