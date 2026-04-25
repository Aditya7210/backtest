from datetime import date, timedelta
from pathlib import Path
import sys
import time as time_module

import streamlit as st
from streamlit_ace import st_ace

# Ensure top-level project modules (e.g. Backtesting/) are importable in Streamlit runtime.
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from .Features import (
    backtest_data_service,
    data_selection_feature,
    instrument_mapper as instrument_mapper_feature,
    name_indicator_saver_versioner,
    strategy_editor,
    strategy_selection,
    terminal as terminal_feature,
)

_STRATEGY_FILE_PLACEHOLDER = "__strategy_file_placeholder__"
_STRATEGY_CLASS_PLACEHOLDER = "__strategy_class_placeholder__"
_VERSIONED_HEADER_OPTION = "__versioned_header__"
_BASE_HEADER_OPTION = "__base_header__"
_STRATEGY_HEADER_OPTIONS = {_VERSIONED_HEADER_OPTION, _BASE_HEADER_OPTION}

_PLACEHOLDER_CODE = """\
# -- Strategy: No Strategy Selected --------------------------------
# Load a strategy from the control panel to begin editing.
#
# Example structure:
#
# def initialize(context):
#     context.symbol    = "NIFTY"
#     context.quantity  = 50
#     context.sl_pct    = 0.015   # 1.5% stop-loss
#     context.tp_pct    = 0.03    # 3.0% take-profit
#
# def on_bar(context, data):
#     close  = data.close[-1]
#     sma_20 = data.sma(20)[-1]
#     sma_50 = data.sma(50)[-1]
#
#     if close > sma_20 > sma_50:
#         context.order_target(context.symbol, context.quantity)
#     elif close < sma_20:
#         context.order_target(context.symbol, 0)
#
# def on_fill(context, order):
#     context.log(f"Fill: {order.symbol} qty={order.quantity} @ {order.price}")
"""

_CSS = """
<style>
details summary {
    font-size: 13px;
    font-weight: 500;
    color: #7D8C99;
    padding: 10px 12px 10px 13px;
    border-left: 3px solid transparent;
    transition: border-color 0.2s ease, color 0.2s ease, font-weight 0.2s ease;
    cursor: pointer;
    list-style: none;
}
details summary::-webkit-details-marker { display: none; }

details[open] > summary {
    border-left: 3px solid #FFC107;
    color: #3E3E55;
    font-weight: 600;
}

.stTextArea textarea {
    font-family: 'Consolas', 'Courier New', monospace !important;
    font-size: 13px !important;
    line-height: 1.6 !important;
    background-color: #F9FAFB !important;
    color: #3E3E55 !important;
    border: 1px solid #E5E7EB !important;
    border-top: none !important;
    border-radius: 0 0 8px 8px !important;
    padding: 16px !important;
    resize: vertical !important;
}
.stTextArea label { display: none !important; }

.stButton button, details summary {
    transition: all 0.15s ease;
}

div[data-testid="stButton"] button[kind="primary"] {
    background-color: #3E3E55 !important;
    border: none !important;
    color: #FFFFFF !important;
    font-weight: 600 !important;
    font-size: 13px !important;
    letter-spacing: 0.3px !important;
    min-height: 44px !important;
}
div[data-testid="stButton"] button[kind="primary"]:hover {
    background-color: #2e2e42 !important;
}
div[data-testid="stButton"] button[kind="primary"]:disabled {
    background-color: #AAB3BC !important;
    cursor: not-allowed !important;
}

div[data-testid="stButton"] button[kind="secondary"] {
    min-height: 44px !important;
    font-size: 13px !important;
    color: #3E3E55 !important;
    border-color: #E5E7EB !important;
}
div[data-testid="stButton"] button[kind="secondary"]:disabled {
    color: #AAB3BC !important;
    cursor: not-allowed !important;
}

[data-testid="stVerticalBlockBorderWrapper"] {
    background: #F3F4F6 !important;
    border-radius: 12px !important;
    border: none !important;
}

[data-testid="stVerticalBlockBorderWrapper"] > div {
    padding: 12px 8px 12px 12px !important;
    scroll-behavior: smooth;
}

[data-testid="stVerticalBlockBorderWrapper"] > div::-webkit-scrollbar {
    width: 4px;
}
[data-testid="stVerticalBlockBorderWrapper"] > div::-webkit-scrollbar-track {
    background: transparent;
}
[data-testid="stVerticalBlockBorderWrapper"] > div::-webkit-scrollbar-thumb {
    background: #D1D5DB;
    border-radius: 2px;
}
[data-testid="stVerticalBlockBorderWrapper"] > div::-webkit-scrollbar-thumb:hover {
    background: #AAB3BC;
}
</style>
"""

_ZERODHA_INTERVALS = [
    "minute",
    "3minute",
    "5minute",
    "10minute",
    "15minute",
    "30minute",
    "60minute",
    "day",
]


def _initialize_zerodha_state() -> None:
    today = date.today()
    st.session_state.setdefault("zerodha_symbol", "")
    st.session_state.setdefault(
        "zerodha_symbol_input",
        str(st.session_state.get("zerodha_symbol", "")),
    )
    st.session_state.setdefault("zerodha_interval", "15minute")
    st.session_state.setdefault("zerodha_from_date", today - timedelta(days=30))
    st.session_state.setdefault("zerodha_to_date", today)
    st.session_state.setdefault("zerodha_oi", False)
    st.session_state.setdefault("zerodha_continuous", False)
    st.session_state.setdefault("instrument_mapper", None)
    st.session_state.setdefault("instrument_mapper_identity", None)
    st.session_state.setdefault("selected_instrument", None)
    st.session_state.setdefault("zerodha_queue", [])
    st.session_state.setdefault("bt_execution_tasks", [])
    st.session_state.setdefault("bt_execution_results", [])
    st.session_state.setdefault("bt_execute_status", None)
    st.session_state.setdefault("execution_status", "IDLE")
    st.session_state.setdefault("results", [])
    st.session_state.setdefault("progress", 0.0)
    st.session_state.setdefault("execution_running", False)
    st.session_state.setdefault("execution_total_tasks", 0)
    st.session_state.setdefault("execution_manager", None)
    st.session_state.setdefault("execution_task_states", {})
    st.session_state.setdefault("_execution_last_refresh_ts", 0.0)
    st.session_state.setdefault("bt_initial_capital", 100000.0)
    st.session_state.setdefault("bt_commission", 0.0003)
    st.session_state.setdefault("bt_max_retries", 1)
    st.session_state.setdefault("bt_task_timeout_seconds", 300)
    st.session_state.setdefault("instrument_mapper_bootstrap_done", False)
    st.session_state.setdefault("instrument_mapper_bootstrap_ok", True)
    st.session_state.setdefault("instrument_mapper_bootstrap_message", "")
    if "execution_terminal" not in st.session_state:
        st.session_state["execution_terminal"] = terminal_feature.ExecutionTerminal(max_lines=2000)


def _get_execution_terminal() -> terminal_feature.ExecutionTerminal:
    terminal_obj = st.session_state.get("execution_terminal")
    if terminal_obj is None or not hasattr(terminal_obj, "log"):
        terminal_obj = terminal_feature.ExecutionTerminal(max_lines=2000)
        st.session_state["execution_terminal"] = terminal_obj
    return terminal_obj


def _ensure_instrument_mapper_bootstrap() -> None:
    if st.session_state.get("instrument_mapper_bootstrap_done", False):
        return

    ok, message = backtest_data_service.ensure_instrument_mapper_ready()
    st.session_state["instrument_mapper_bootstrap_done"] = True
    st.session_state["instrument_mapper_bootstrap_ok"] = bool(ok)
    st.session_state["instrument_mapper_bootstrap_message"] = str(message or "")


def _start_execution_job(tasks: list[dict[str, object]], config: dict[str, float]) -> None:
    from Backtesting.execution_manager import ExecutionManager

    existing_manager = st.session_state.get("execution_manager")
    if existing_manager is not None and hasattr(existing_manager, "stop_worker"):
        try:
            existing_manager.stop_worker(timeout_seconds=0.5)
        except Exception:
            pass

    terminal_obj = _get_execution_terminal()
    terminal_obj.clear()
    terminal_obj.log("Execution started", level="INFO")
    terminal_obj.log(f"Queued {len(tasks)} tasks", level="INFO")

    manager = ExecutionManager(config, terminal=terminal_obj)
    manager.clear_tasks()
    for task in tasks:
        manager.add_task(task)

    manager.start_worker()
    queue_snapshot = manager.get_queue_snapshot()
    task_states = {
        str(item.get("task_id")): str(item.get("status"))
        for item in queue_snapshot
        if item.get("task_id")
    }

    st.session_state["execution_manager"] = manager
    st.session_state["execution_task_states"] = task_states
    st.session_state["execution_running"] = True
    st.session_state["execution_status"] = "RUNNING"
    st.session_state["execution_total_tasks"] = len(queue_snapshot)
    st.session_state["progress"] = 0.0
    st.session_state["results"] = manager.get_ordered_results()


def _process_execution_queue_tick() -> None:
    manager = st.session_state.get("execution_manager")
    if manager is None:
        from Backtesting.execution_manager import ExecutionManager

        manager = ExecutionManager(
            {
                "initial_capital": float(
                    st.session_state.get("bt_initial_capital", 100000.0)
                ),
                "commission": float(
                    st.session_state.get("bt_commission", 0.0003)
                ),
                "max_retries": int(
                    st.session_state.get("bt_max_retries", 1)
                ),
                "task_timeout_seconds": float(
                    st.session_state.get("bt_task_timeout_seconds", 300)
                ),
            },
            terminal=_get_execution_terminal(),
        )
        st.session_state["execution_manager"] = manager
    if hasattr(manager, "set_terminal"):
        manager.set_terminal(_get_execution_terminal())

    queue_snapshot = manager.get_queue_snapshot()
    task_states = {
        str(item.get("task_id")): str(item.get("status"))
        for item in queue_snapshot
        if item.get("task_id")
    }
    st.session_state["execution_task_states"] = task_states
    total = len(queue_snapshot)
    st.session_state["execution_total_tasks"] = total

    completed = sum(
        1 for status in task_states.values() if status in {"SUCCESS", "FAILED"}
    )

    st.session_state["progress"] = (completed / total) if total > 0 else 0.0
    st.session_state["results"] = manager.get_ordered_results()

    has_active_tasks = any(
        status in {"PENDING", "RUNNING"}
        for status in task_states.values()
    )
    if has_active_tasks and not manager.is_worker_running():
        manager.start_worker()

    previous_status = str(st.session_state.get("execution_status", "IDLE"))
    if has_active_tasks:
        st.session_state["execution_running"] = True
        st.session_state["execution_status"] = "RUNNING"
    else:
        if manager.is_worker_running() and hasattr(manager, "stop_worker"):
            manager.stop_worker(timeout_seconds=0.2)
        st.session_state["execution_running"] = False
        if total == 0:
            st.session_state["execution_status"] = "IDLE"
            st.session_state["progress"] = 0.0
        else:
            next_status = (
                "COMPLETED"
                if all(status == "SUCCESS" for status in task_states.values())
                else "COMPLETED_WITH_ERRORS"
            )
            st.session_state["execution_status"] = next_status
            st.session_state["progress"] = 1.0

            if previous_status == "RUNNING" and next_status == "COMPLETED":
                _get_execution_terminal().log("Execution completed", level="SUCCESS")
            elif previous_status == "RUNNING" and next_status == "COMPLETED_WITH_ERRORS":
                _get_execution_terminal().log(
                    "Execution completed with errors",
                    level="WARNING",
                )


def _render_execution_terminal_panel() -> None:
    terminal_obj = _get_execution_terminal()
    terminal_feature.render_terminal_panel(
        terminal_obj,
        key_prefix="bt_execution_terminal",
    )


def _schedule_execution_refresh() -> None:
    if not bool(st.session_state.get("execution_running", False)):
        return

    current_time = float(time_module.time())
    last_refresh = float(st.session_state.get("_execution_last_refresh_ts", 0.0))
    if (current_time - last_refresh) < 0.9:
        return

    st.session_state["_execution_last_refresh_ts"] = current_time
    time_module.sleep(0.35)
    st.rerun()


def _get_cached_instrument_mapper(
    api_key: str,
    access_token: str,
) -> instrument_mapper_feature.InstrumentMapper:
    identity = (api_key, access_token)
    mapper = st.session_state.get("instrument_mapper")
    mapper_identity = st.session_state.get("instrument_mapper_identity")

    if mapper is not None and mapper_identity == identity:
        return mapper

    mapper = instrument_mapper_feature.InstrumentMapper(
        api_key=api_key,
        access_token=access_token,
        auto_update=False,
    )
    st.session_state["instrument_mapper"] = mapper
    st.session_state["instrument_mapper_identity"] = identity
    return mapper


def _render_zerodha_data_selection() -> None:
    st.session_state["selected_data_files"] = []

    bootstrap_ok = bool(st.session_state.get("instrument_mapper_bootstrap_ok", True))
    bootstrap_message = str(st.session_state.get("instrument_mapper_bootstrap_message", "")).strip()
    if bootstrap_message:
        if bootstrap_ok:
            st.caption(bootstrap_message)
        else:
            st.warning(bootstrap_message)

    query = st.text_input(
        "Symbol",
        value=st.session_state.get("zerodha_symbol", ""),
        key="zerodha_symbol_input",
        placeholder="e.g. RELIANCE",
    ).strip()
    st.session_state["zerodha_symbol"] = query
    st.caption("Instrument token is resolved automatically from the symbol.")

    if len(query) >= 2:
        results: list[dict[str, object]] = []
        try:
            api_key, access_token = backtest_data_service.validate_zerodha_session()
        except Exception as exc:
            st.warning(str(exc))
        else:
            try:
                mapper = _get_cached_instrument_mapper(api_key, access_token)
                results = mapper.search_symbol(query)[:15]
            except Exception:
                results = []

        if results:
            st.markdown("### Matching Instruments")
            st.caption("Showing top matches")
            options = [
                f"{item['tradingsymbol']} ({item['exchange']}, {item['instrument_type']})"
                for item in results
            ]
            label_to_symbol = {
                option: str(item["tradingsymbol"])
                for option, item in zip(options, results)
            }
            label_to_item = {
                option: dict(item)
                for option, item in zip(options, results)
            }

            selected_option = st.radio(
                "Select Matching Symbol",
                options=options,
                key="symbol_suggestions",
                index=0,
            )
            selected_label = st.session_state.get("symbol_suggestions") or selected_option

            if selected_label in label_to_item:
                st.session_state["selected_instrument"] = label_to_item[selected_label]
                st.session_state["zerodha_symbol"] = label_to_symbol[selected_label]
        else:
            st.selectbox(
                "Select Matching Symbol",
                options=["No matches"],
                key="symbol_suggestions_no_match",
                disabled=True,
            )
            st.session_state["selected_instrument"] = None
            st.caption("No matching instruments found")
    else:
        st.session_state["selected_instrument"] = None

    st.selectbox(
        "Interval",
        _ZERODHA_INTERVALS,
        key="zerodha_interval",
    )

    date_col1, date_col2 = st.columns(2, gap="small")
    with date_col1:
        st.date_input("From Date", key="zerodha_from_date")
    with date_col2:
        st.date_input("To Date", key="zerodha_to_date")

    st.toggle("Include Open Interest (OI)", key="zerodha_oi")
    st.toggle("Continuous Futures", key="zerodha_continuous")

    add_to_queue_clicked = st.button(
        "Add to Backtest Queue",
        use_container_width=True,
        key="bt_add_zerodha_queue",
    )

    if add_to_queue_clicked:
        selected = st.session_state.get("selected_instrument")
        interval = backtest_data_service.normalize_interval(
            str(st.session_state.get("zerodha_interval", "15minute"))
        )
        from_day = st.session_state.get("zerodha_from_date")
        to_day = st.session_state.get("zerodha_to_date")
        requested_continuous = bool(st.session_state.get("zerodha_continuous", False))
        oi = bool(st.session_state.get("zerodha_oi", False))

        try:
            queue_item = backtest_data_service.create_queue_item(
                selected_instrument=selected if isinstance(selected, dict) else None,
                interval=interval,
                from_day=from_day,
                to_day=to_day,
                requested_continuous=requested_continuous,
                oi=oi,
            )
        except ValueError as exc:
            st.error(str(exc))
        else:
            st.session_state["zerodha_queue"].append(queue_item)
            symbol = str(selected.get("tradingsymbol", "")).strip().upper()
            st.success(f"Added {symbol} ({interval}) to queue.")

    st.caption("Backtest Queue")
    queue = st.session_state.get("zerodha_queue", [])
    if not queue:
        st.caption("Queue is empty.")
    else:
        remove_idx: int | None = None
        for i, item in enumerate(queue):
            instrument = item.get("instrument", {})
            symbol = str(instrument.get("tradingsymbol", "UNKNOWN"))
            interval = str(item.get("interval", ""))
            from_day = item.get("from")
            to_day = item.get("to")
            row_col1, row_col2 = st.columns([4, 1], gap="small")
            with row_col1:
                st.write(f"{i + 1}. {symbol} ({interval}) [{from_day} -> {to_day}]")
            with row_col2:
                if st.button("Remove", key=f"bt_remove_queue_{i}"):
                    remove_idx = i
        if remove_idx is not None:
            st.session_state["zerodha_queue"].pop(remove_idx)
            st.rerun()

    st.caption("Queue-based mode: data will be fetched only when Execute Strategy is clicked.")


def _default_data_source(sources: list[dict[str, object]]) -> str | None:
    for source in sources:
        if source["selectable"] and source["directory_exists"]:
            return str(source["name"])

    for source in sources:
        if source["selectable"]:
            return str(source["name"])

    if not sources:
        return None

    return str(sources[0]["name"])


def _format_data_source_label(source: dict[str, object]) -> str:
    label = str(source["label"])

    if not source["root_exists"]:
        return f"{label} (data root missing)"

    if not source["directory_exists"]:
        return f"{label} (folder missing)"

    if source["disabled"]:
        return f"{label} (disabled)"

    file_count = int(source["file_count"])
    suffix = "file" if file_count == 1 else "files"
    return f"{label} ({file_count} {suffix})"


def _render_data_selection() -> None:
    data_mode = st.session_state.get("data_mode", "csv")

    if data_mode == "zerodha":
        _render_zerodha_data_selection()
        return

    sources = data_selection_feature.get_data_sources()
    if not sources:
        st.info("No configured data sources are available.")
        return

    source_lookup = {str(source["name"]): source for source in sources}
    default_source = _default_data_source(sources)

    if default_source is None:
        st.info("No configured data sources are available.")
        return

    if st.session_state.get("bt_data_source") not in source_lookup:
        st.session_state["bt_data_source"] = default_source

    selected_source_name = st.selectbox(
        "Data Source",
        options=list(source_lookup.keys()),
        key="bt_data_source",
        format_func=lambda source_name: _format_data_source_label(source_lookup[source_name]),
    )
    selected_source = source_lookup[selected_source_name]
    source_files = data_selection_feature.get_data_files(selected_source_name)
    source_file_ids = {file_meta["id"] for file_meta in source_files}

    validated_selection = data_selection_feature.validate_selection(
        st.session_state.get("selected_data_files", [])
    )

    if selected_source["selectable"]:
        validated_selection = [
            file_id for file_id in validated_selection if file_id in source_file_ids
        ]
        st.session_state["selected_data_files"] = validated_selection

    search_disabled = not source_files
    search_query = st.text_input(
        "Search CSV Files",
        key="bt_data_file_search",
        placeholder="Search by filename or relative path",
        disabled=search_disabled,
    )

    filtered_files = data_selection_feature.filter_data_files(source_files, search_query)
    file_lookup = {file_meta["id"]: file_meta for file_meta in source_files}
    visible_file_ids = validated_selection + [
        file_meta["id"]
        for file_meta in filtered_files
        if file_meta["id"] not in validated_selection
    ]
    visible_file_ids_set = set(visible_file_ids)

    widget_selection = st.session_state.get("bt_data_files_widget", validated_selection)
    normalized_widget_selection = [
        file_id
        for file_id in widget_selection
        if file_id in visible_file_ids_set
    ]

    if normalized_widget_selection != widget_selection:
        st.session_state["bt_data_files_widget"] = normalized_widget_selection

    if not selected_source["root_exists"]:
        st.warning(
            "The backtesting data directory is unavailable, so no CSV files can be selected."
        )
    elif not selected_source["directory_exists"]:
        st.info(f"{selected_source_name} is configured but its folder does not exist yet.")
    elif not source_files:
        st.info("No CSV files were found in this source.")

    selected_files = st.multiselect(
        "CSV Files",
        options=visible_file_ids,
        key="bt_data_files_widget",
        format_func=lambda file_id: file_lookup.get(file_id, {}).get("display_name", file_id),
        disabled=not source_files,
        help="Choose one or more CSV files from the selected data source.",
    )

    st.session_state["selected_data_files"] = data_selection_feature.validate_selection(
        selected_files
    )

    if selected_source["selectable"]:
        st.session_state["selected_data_files"] = [
            file_id
            for file_id in st.session_state["selected_data_files"]
            if file_id in source_file_ids
        ]

    st.caption(
        f"{len(filtered_files)} matching files | "
        f"{len(st.session_state['selected_data_files'])} selected"
    )


def _strategy_lookup(files: list[dict[str, object]]) -> dict[str, dict[str, object]]:
    return {
        str(file_meta["id"]): file_meta
        for file_meta in files
    }


def _ensure_strategy_selection_state() -> None:
    st.session_state.setdefault("selected_strategy_file", None)
    st.session_state.setdefault("selected_strategy_class", None)
    st.session_state.setdefault("bt_strategy_file_widget", _STRATEGY_FILE_PLACEHOLDER)
    st.session_state.setdefault("bt_strategy_class_widget", _STRATEGY_CLASS_PLACEHOLDER)


def _normalize_strategy_selection_state(
    strategy_lookup: dict[str, dict[str, object]],
) -> None:
    selected_file = st.session_state.get("selected_strategy_file")
    if selected_file in strategy_lookup:
        return

    st.session_state["selected_strategy_file"] = None
    st.session_state["selected_strategy_class"] = None
    st.session_state["bt_strategy_file_widget"] = _STRATEGY_FILE_PLACEHOLDER
    st.session_state["bt_strategy_class_widget"] = _STRATEGY_CLASS_PLACEHOLDER


def _format_strategy_file_option(
    option: str,
    strategy_lookup: dict[str, dict[str, object]],
) -> str:
    if option == _STRATEGY_FILE_PLACEHOLDER:
        return "Select a strategy file"
    if option == _VERSIONED_HEADER_OPTION:
        return "── Versioned Strategies ──"
    if option == _BASE_HEADER_OPTION:
        return "── Base Strategies ──"
    return str(strategy_lookup[option]["display_name"])


def _format_strategy_class_option(option: str) -> str:
    if option == _STRATEGY_CLASS_PLACEHOLDER:
        return "Select a strategy class"
    return option


def _normalize_editor_text(content: str) -> str:
    return (content or "").replace("\r\n", "\n").replace("\r", "\n")


def _on_strategy_file_change(visible_file_ids: tuple[str, ...]) -> None:
    selected_option = st.session_state.get("bt_strategy_file_widget", _STRATEGY_FILE_PLACEHOLDER)
    previous_file = st.session_state.get("selected_strategy_file")
    visible_file_id_set = set(visible_file_ids)

    if selected_option in _STRATEGY_HEADER_OPTIONS:
        if previous_file in visible_file_id_set:
            st.session_state["bt_strategy_file_widget"] = previous_file
        else:
            st.session_state["bt_strategy_file_widget"] = _STRATEGY_FILE_PLACEHOLDER
        return

    if selected_option == _STRATEGY_FILE_PLACEHOLDER or selected_option not in visible_file_id_set:
        st.session_state["selected_strategy_file"] = None
        st.session_state["selected_strategy_class"] = None
        st.session_state["bt_strategy_file_widget"] = _STRATEGY_FILE_PLACEHOLDER
        st.session_state["bt_strategy_class_widget"] = _STRATEGY_CLASS_PLACEHOLDER
        return

    st.session_state["selected_strategy_file"] = selected_option
    if selected_option != previous_file:
        st.session_state["selected_strategy_class"] = None
        st.session_state["bt_strategy_class_widget"] = _STRATEGY_CLASS_PLACEHOLDER


def _on_strategy_class_change(valid_classes: tuple[str, ...]) -> None:
    selected_option = st.session_state.get(
        "bt_strategy_class_widget",
        _STRATEGY_CLASS_PLACEHOLDER,
    )

    if selected_option == _STRATEGY_CLASS_PLACEHOLDER or selected_option not in set(valid_classes):
        st.session_state["selected_strategy_class"] = None
        st.session_state["bt_strategy_class_widget"] = _STRATEGY_CLASS_PLACEHOLDER
        return

    st.session_state["selected_strategy_class"] = selected_option


def _render_strategy_selection() -> None:
    _ensure_strategy_selection_state()
    strategy_files = strategy_selection.get_strategy_files()
    all_strategy_lookup = _strategy_lookup(strategy_files)
    _normalize_strategy_selection_state(all_strategy_lookup)

    if not all_strategy_lookup:
        st.info("No strategies available")
        return

    search_query = st.text_input(
        "Search Strategy Files",
        key="bt_strategy_search",
        placeholder="Search strategy files",
    )

    filtered_files = strategy_selection.filter_strategy_files(strategy_files, search_query)
    filtered_lookup = _strategy_lookup(filtered_files)

    if not filtered_lookup:
        st.info("No strategies found")
        return

    strategy_file_options = [_STRATEGY_FILE_PLACEHOLDER]
    visible_file_ids = []
    versioned_files = sorted(
        [file_meta for file_meta in filtered_files if file_meta["is_versioned"]],
        key=lambda file_meta: str(file_meta["display_name"]).lower(),
    )
    base_files = sorted(
        [file_meta for file_meta in filtered_files if not file_meta["is_versioned"]],
        key=lambda file_meta: str(file_meta["display_name"]).lower(),
    )

    if versioned_files:
        strategy_file_options.append(_VERSIONED_HEADER_OPTION)
        strategy_file_options.extend(str(file_meta["id"]) for file_meta in versioned_files)
        visible_file_ids.extend(str(file_meta["id"]) for file_meta in versioned_files)

    if base_files:
        strategy_file_options.append(_BASE_HEADER_OPTION)
        strategy_file_options.extend(str(file_meta["id"]) for file_meta in base_files)
        visible_file_ids.extend(str(file_meta["id"]) for file_meta in base_files)

    selected_file = st.session_state.get("selected_strategy_file")
    target_widget_file = (
        selected_file if selected_file in filtered_lookup else _STRATEGY_FILE_PLACEHOLDER
    )
    current_widget_file = st.session_state.get("bt_strategy_file_widget")

    if (
        current_widget_file not in strategy_file_options
        or current_widget_file in _STRATEGY_HEADER_OPTIONS
        or (
            current_widget_file == _STRATEGY_FILE_PLACEHOLDER
            and target_widget_file != _STRATEGY_FILE_PLACEHOLDER
        )
    ):
        st.session_state["bt_strategy_file_widget"] = target_widget_file

    st.selectbox(
        "Strategy File",
        options=strategy_file_options,
        key="bt_strategy_file_widget",
        format_func=lambda option: _format_strategy_file_option(option, filtered_lookup),
        on_change=_on_strategy_file_change,
        args=(tuple(visible_file_ids),),
    )

    selected_file = st.session_state.get("selected_strategy_file")
    selected_file_meta = all_strategy_lookup.get(selected_file)

    if selected_file_meta is None:
        return

    if search_query and selected_file not in filtered_lookup:
        st.caption("Current file selection is hidden by the search filter.")

    strategy_classes = strategy_selection.get_strategy_classes(str(selected_file_meta["id"]))
    if not strategy_classes:
        st.session_state["selected_strategy_class"] = None
        st.session_state["bt_strategy_class_widget"] = _STRATEGY_CLASS_PLACEHOLDER
        st.info("No valid strategy classes found")
        st.caption(f"Selected: {selected_file_meta['display_name']} -> -")
        return

    strategy_class_options = [_STRATEGY_CLASS_PLACEHOLDER, *strategy_classes]
    selected_class = st.session_state.get("selected_strategy_class")
    target_widget_class = (
        selected_class if selected_class in strategy_classes else _STRATEGY_CLASS_PLACEHOLDER
    )
    current_widget_class = st.session_state.get("bt_strategy_class_widget")

    if current_widget_class not in strategy_class_options:
        st.session_state["bt_strategy_class_widget"] = target_widget_class

    st.selectbox(
        "Strategy Class",
        options=strategy_class_options,
        key="bt_strategy_class_widget",
        format_func=_format_strategy_class_option,
        on_change=_on_strategy_class_change,
        args=(tuple(strategy_classes),),
    )

    selected_class = st.session_state.get("selected_strategy_class") or "-"
    st.caption(f"Selected: {selected_file_meta['display_name']} -> {selected_class}")


def render() -> None:
    strategy_editor._initialize_editor_state()
    st.session_state.setdefault("_last_loaded_file", None)
    st.session_state.setdefault("data_mode", "csv")
    _initialize_zerodha_state()
    _ensure_instrument_mapper_bootstrap()
    _process_execution_queue_tick()
    st.session_state.setdefault(
        "bt_data_mode_toggle",
        st.session_state["data_mode"] == "zerodha",
    )

    initial_mode = "zerodha" if st.session_state.get("bt_data_mode_toggle") else "csv"
    if initial_mode != st.session_state["data_mode"]:
        st.session_state["data_mode"] = initial_mode

    if st.session_state["data_mode"] == "zerodha":
        st.session_state["selected_data_files"] = []

    if st.session_state["data_mode"] == "csv":
        data_selection_feature.initialize_data_layer()
        data_selection_feature.refresh_if_needed()
    strategy_selection.initialize_strategy_layer()
    strategy_selection.refresh_if_needed()
    editor_status_message = strategy_editor._sync_editor_state_with_selection()
    name_indicator_saver_versioner.initialize_lifecycle_state()
    name_indicator_saver_versioner.sync_strategy_display_name()

    pending_save_message = st.session_state.get("save_status_message")
    if pending_save_message:
        if str(pending_save_message).startswith(("Strategy saved:", "Strategy version saved:")):
            st.toast(str(pending_save_message), icon="✅")
        else:
            st.toast(str(pending_save_message), icon="⚠️")
        st.session_state["save_status_message"] = None

    current_strategy_file = st.session_state.get("current_strategy_file")
    if st.session_state.get("_last_loaded_file") != current_strategy_file:
        st.session_state["bt_code_editor"] = st.session_state.get("editor_content", "")
        st.session_state["_last_loaded_file"] = current_strategy_file

    indicator_state = name_indicator_saver_versioner.get_indicator_color()
    indicator_color = "#16A34A" if indicator_state == "green" else "#DC2626"
    indicator_tooltip = "All changes saved" if indicator_state == "green" else "Unsaved changes"
    if not current_strategy_file:
        indicator_color = "#AAB3BC"
        indicator_tooltip = "No strategy selected"

    st.markdown(_CSS, unsafe_allow_html=True)

    col_editor, col_controls = st.columns([13, 7], gap="medium")

    with col_editor:
        if editor_status_message:
            st.warning(editor_status_message)

        has_strategy_selected = bool(st.session_state.get("selected_strategy_file"))
        header_left_col, header_right_col = st.columns([8, 3], gap="small")

        with header_left_col:
            st.text_input(
                "",
                key="strategy_display_name",
                placeholder="Strategy Name",
                disabled=not has_strategy_selected,
                label_visibility="collapsed",
            )

        with header_right_col:
            indicator_col, save_col, toggle_col = st.columns([1, 3, 3], gap="small")
            with indicator_col:
                st.markdown(
                    f"""
<div style="display:flex; align-items:center; justify-content:center; height:38px;">
  <span title="{indicator_tooltip}" style="width:10px; height:10px; border-radius:50%; background:{indicator_color}; display:inline-block;"></span>
</div>
""",
                    unsafe_allow_html=True,
                )
            with save_col:
                save_clicked = st.button(
                    "💾 Save",
                    use_container_width=False,
                    type="primary",
                    disabled=not has_strategy_selected,
                    key="bt_save_strategy_inline",
                )
                if save_clicked:
                    name_indicator_saver_versioner.save_strategy()

            with toggle_col:
                toggle_value = st.toggle(
                    "CSV / Zerodha",
                    value=(st.session_state["data_mode"] == "zerodha"),
                    key="bt_data_mode_toggle",
                )

                new_mode = "zerodha" if toggle_value else "csv"
                if new_mode != st.session_state["data_mode"]:
                    st.session_state["data_mode"] = new_mode
                    if new_mode == "zerodha":
                        st.session_state["selected_data_files"] = []
                        st.session_state["bt_data_files_widget"] = []

                if st.session_state["data_mode"] == "csv":
                    st.caption("Using local CSV data")
                else:
                    st.caption("Using Zerodha API data")

        ace_widget_key = (
            f"bt_code_editor_ace::{current_strategy_file}"
            if current_strategy_file
            else "bt_code_editor_ace::none"
        )

        ace_value = st_ace(
            value=st.session_state.get("bt_code_editor", ""),
            language="python",
            theme="github",
            height=480,
            show_gutter=True,
            wrap=True,
            auto_update=True,
            tab_size=4,
            font_size=13,
            key=ace_widget_key,
            placeholder=_PLACEHOLDER_CODE if not current_strategy_file else "",
        )

        if ace_value is not None:
            normalized_ace_value = _normalize_editor_text(ace_value)
            normalized_editor_value = _normalize_editor_text(
                st.session_state.get("bt_code_editor", "")
            )
        else:
            normalized_ace_value = None
            normalized_editor_value = _normalize_editor_text(
                st.session_state.get("bt_code_editor", "")
            )

        if normalized_ace_value is not None and normalized_ace_value != normalized_editor_value:
            st.session_state["bt_code_editor"] = normalized_ace_value
            strategy_editor._on_editor_change()

    with col_controls:
        with st.container(height=542, border=False):
            with st.expander("Data Selection", expanded=True):
                _render_data_selection()

            with st.expander("Strategy Selection"):
                _render_strategy_selection()

            with st.expander("Versioning"):
                st.toggle(
                    "Enable Version Control",
                    key="versioning_enabled",
                )
                st.caption("When enabled, Save creates a new versioned strategy file.")

            with st.expander("Execution Config"):
                cfg_col1, cfg_col2 = st.columns(2, gap="small")
                with cfg_col1:
                    st.number_input(
                        "Initial Capital",
                        min_value=1.0,
                        step=1000.0,
                        format="%.2f",
                        key="bt_initial_capital",
                        help="Starting portfolio value used by the backtest engine.",
                    )
                    st.number_input(
                        "Max Retries",
                        min_value=0,
                        max_value=10,
                        step=1,
                        key="bt_max_retries",
                        help="Retries per task after a failed execution attempt.",
                    )
                with cfg_col2:
                    st.number_input(
                        "Commission",
                        min_value=0.0,
                        step=0.0001,
                        format="%.4f",
                        key="bt_commission",
                        help="Broker commission applied by Backtrader.",
                    )
                    st.number_input(
                        "Task Timeout (seconds)",
                        min_value=10,
                        max_value=7200,
                        step=10,
                        key="bt_task_timeout_seconds",
                        help="Maximum allowed runtime per task.",
                    )

            data_mode = st.session_state.get("data_mode", "csv")
            queue_count = len(st.session_state.get("zerodha_queue", []))
            csv_count = len(st.session_state.get("selected_data_files", []))
            can_execute = queue_count > 0 if data_mode == "zerodha" else csv_count > 0
            execution_running = bool(st.session_state.get("execution_running", False))

            execute_clicked = st.button(
                "Execute Strategy",
                use_container_width=True,
                type="primary",
                disabled=(not can_execute) or execution_running,
                key="bt_execute",
            )
            if execute_clicked:
                if bool(st.session_state.get("execution_running", False)):
                    st.info("Execution is already running. Please wait for current run to finish.")
                else:
                    try:
                        selected_file = st.session_state.get("selected_strategy_file")
                        selected_class_name = st.session_state.get("selected_strategy_class")
                        if not selected_file or not selected_class_name:
                            raise ValueError("Please select a valid strategy")

                        strategy_class = backtest_data_service.load_strategy_class(
                            str(selected_file),
                            str(selected_class_name),
                        )

                        if data_mode == "zerodha":
                            tasks = backtest_data_service.build_zerodha_queue_tasks(
                                queue=st.session_state.get("zerodha_queue", []),
                                selected_strategy=strategy_class,
                            )
                        else:
                            tasks = backtest_data_service.build_csv_tasks(
                                st.session_state.get("selected_data_files", []),
                                strategy_class,
                            )

                        for task in tasks:
                            task["strategy_file_path"] = str(selected_file)
                            task["strategy_class_name"] = str(selected_class_name)

                        config = {
                            "initial_capital": float(
                                st.session_state.get("bt_initial_capital", 100000.0)
                            ),
                            "commission": float(
                                st.session_state.get("bt_commission", 0.0003)
                            ),
                            "max_retries": int(
                                st.session_state.get("bt_max_retries", 1)
                            ),
                            "task_timeout_seconds": float(
                                st.session_state.get("bt_task_timeout_seconds", 300)
                            ),
                        }
                        _start_execution_job(tasks, config)
                    except Exception as exc:
                        st.error(f"Failed to execute backtests: {exc}")
                        st.session_state["bt_execution_tasks"] = []
                    else:
                        st.session_state["bt_execution_tasks"] = tasks
                        st.session_state["bt_execution_results"] = []
                        st.session_state["bt_execute_status"] = "Execution started"
                        st.success(st.session_state["bt_execute_status"])

            st.caption(f"Execution Status: {st.session_state.get('execution_status', 'IDLE')}")
            st.progress(float(st.session_state.get("progress", 0.0)))

            session_results = list(st.session_state.get("results", []))
            if session_results:
                st.session_state["bt_execution_results"] = session_results
                for res in session_results:
                    st.write(f"Symbol: {res.get('symbol')}")
                    st.write(f"Status: {res.get('status')}")
                    st.write(f"Final Value: {res.get('final_value')}")
                    st.write(f"Log File: {res.get('log_file')}")
                    if res.get("error"):
                        st.error(f"Error: {res.get('error')}")

            st.button(
                "+ Create New Strategy",
                use_container_width=True,
                disabled=True,
                key="bt_create",
            )

    _render_execution_terminal_panel()
    _schedule_execution_refresh()
