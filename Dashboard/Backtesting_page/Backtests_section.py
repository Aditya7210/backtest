from datetime import date, datetime, time, timedelta
import os
from pathlib import Path

import streamlit as st
from streamlit_ace import st_ace

from .Features import (
    data_selection_feature,
    instrument_mapper as instrument_mapper_feature,
    name_indicator_saver_versioner,
    strategy_editor,
    strategy_selection,
    zerodha_auth as zerodha_auth_feature,
    zerodha_csv_downloader,
    zerodha_historical_data,
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


def _resolve_env_path() -> Path:
    return Path(__file__).resolve().parents[2] / ".env"


def _get_zerodha_credentials() -> tuple[str, str]:
    api_key = os.getenv("ZERODHA_API_KEY", "").strip()
    access_token = str(st.session_state.get("ZERODHA_ACCESS_TOKEN") or "").strip()

    if not access_token:
        env_path = _resolve_env_path()
        if env_path.is_file():
            try:
                env_data = zerodha_auth_feature.load_env_variables(str(env_path))
            except Exception:
                env_data = {}
            if not api_key:
                api_key = str(env_data.get("api_key") or "").strip()
            access_token = str(env_data.get("access_token") or "").strip()

    if not access_token:
        access_token = os.getenv("ZERODHA_ACCESS_TOKEN", "").strip()

    return api_key, access_token


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
    st.session_state.setdefault("zerodha_data_frame", None)
    st.session_state.setdefault("zerodha_fetch_status", None)
    st.session_state.setdefault("zerodha_fetch_error", None)
    st.session_state.setdefault("zerodha_loading", False)
    st.session_state.setdefault("instrument_mapper", None)
    st.session_state.setdefault("instrument_mapper_identity", None)
    st.session_state.setdefault("zerodha_service", None)
    st.session_state.setdefault("zerodha_service_identity", None)
    st.session_state.setdefault("selected_instrument", None)


def _on_symbol_suggestion_change(
    label_to_symbol: dict[str, str],
    label_to_item: dict[str, dict[str, object]],
) -> None:
    selected_label = st.session_state.get("symbol_suggestions")
    if selected_label not in label_to_symbol:
        return

    resolved_symbol = label_to_symbol[selected_label]
    st.session_state["zerodha_symbol"] = resolved_symbol
    st.session_state["selected_instrument"] = label_to_item.get(selected_label)


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


def _get_cached_zerodha_service(
    api_key: str,
    access_token: str,
) -> zerodha_historical_data.ZerodhaHistoricalData:
    identity = (api_key, access_token)
    service = st.session_state.get("zerodha_service")
    service_identity = st.session_state.get("zerodha_service_identity")

    if service is not None and service_identity == identity:
        return service

    service = zerodha_historical_data.ZerodhaHistoricalData(
        api_key=api_key,
        access_token=access_token,
    )
    st.session_state["zerodha_service"] = service
    st.session_state["zerodha_service_identity"] = identity
    return service


def _fetch_zerodha_data_from_ui() -> None:
    api_key, access_token = _get_zerodha_credentials()

    if not api_key or not access_token:
        st.session_state["zerodha_fetch_error"] = (
            "Missing Zerodha credentials. Set ZERODHA_API_KEY and ZERODHA_ACCESS_TOKEN in environment."
        )
        st.session_state["zerodha_fetch_status"] = None
        st.session_state["zerodha_data_frame"] = None
        return

    selected_instrument = st.session_state.get("selected_instrument")
    if not isinstance(selected_instrument, dict) or not selected_instrument:
        st.session_state["zerodha_fetch_error"] = (
            "Please select a valid instrument from suggestions"
        )
        st.session_state["zerodha_fetch_status"] = None
        st.session_state["zerodha_data_frame"] = None
        return

    symbol = str(selected_instrument.get("tradingsymbol", "")).strip().upper()
    if not symbol:
        st.session_state["zerodha_fetch_error"] = (
            "Please select a valid instrument from suggestions"
        )
        st.session_state["zerodha_fetch_status"] = None
        st.session_state["zerodha_data_frame"] = None
        return

    instrument_token_raw = selected_instrument.get("instrument_token")
    if instrument_token_raw in (None, ""):
        st.session_state["zerodha_fetch_error"] = "Instrument token not found"
        st.session_state["zerodha_fetch_status"] = None
        st.session_state["zerodha_data_frame"] = None
        return

    try:
        instrument_token = int(instrument_token_raw)
    except (TypeError, ValueError):
        st.session_state["zerodha_fetch_error"] = "Instrument token not found"
        st.session_state["zerodha_fetch_status"] = None
        st.session_state["zerodha_data_frame"] = None
        return

    instrument_type = str(selected_instrument.get("instrument_type", "")).strip().upper()

    from_day = st.session_state.get("zerodha_from_date")
    to_day = st.session_state.get("zerodha_to_date")
    interval = str(st.session_state.get("zerodha_interval", "15minute")).lower().strip()
    requested_continuous = bool(st.session_state.get("zerodha_continuous", False))
    continuous = requested_continuous and instrument_type == "FUT"
    oi = bool(st.session_state.get("zerodha_oi", False))

    from_dt = datetime.combine(from_day, time.min)
    to_dt = datetime.combine(to_day, time.max)

    try:
        service = _get_cached_zerodha_service(api_key, access_token)
        with st.spinner("Fetching Zerodha historical candles..."):
            data = service.fetch_data(
                instrument_token=instrument_token,
                from_date=from_dt,
                to_date=to_dt,
                interval=interval,
                continuous=continuous,
                oi=oi,
            )
    except Exception as exc:
        st.session_state["zerodha_service"] = None
        st.session_state["zerodha_service_identity"] = None
        st.session_state["zerodha_fetch_error"] = str(exc)
        st.session_state["zerodha_fetch_status"] = None
        st.session_state["zerodha_data_frame"] = None
        return

    data = data.copy()
    data["Symbol"] = symbol
    data["Interval"] = interval

    st.session_state["zerodha_data_frame"] = data
    st.session_state["zerodha_fetch_error"] = None
    st.session_state["zerodha_fetch_status"] = (
        f"Fetched {len(data)} rows for {symbol} ({interval})."
    )


def _render_zerodha_data_selection() -> None:
    st.session_state["selected_data_files"] = []

    query = st.text_input(
        "Symbol",
        value=st.session_state.get("zerodha_symbol", ""),
        key="zerodha_symbol_input",
        placeholder="e.g. RELIANCE",
    ).strip()
    st.session_state["zerodha_symbol"] = query
    st.caption("Instrument token is resolved automatically from the symbol.")

    if len(query) >= 2:
        api_key, access_token = _get_zerodha_credentials()

        results: list[dict[str, object]] = []
        if not api_key or not access_token:
            st.warning("Zerodha credentials not found. Symbol search disabled.")
        else:
            try:
                mapper = _get_cached_instrument_mapper(api_key, access_token)
                results = mapper.search_symbol(query)[:15]
            except Exception:
                results = []

        if results:
            st.markdown("### 🔍 Matching Instruments")
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

            selected_option = st.selectbox(
                "Select Matching Symbol",
                options=options,
                key="symbol_suggestions",
                index=0,
                on_change=_on_symbol_suggestion_change,
                args=(label_to_symbol, label_to_item),
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

        st.write("Selected Instrument Debug:", st.session_state.get("selected_instrument"))

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

    action_col1, action_col2 = st.columns([2, 1], gap="small")
    with action_col1:
        fetch_clicked = st.button(
            "Fetch Zerodha Data",
            type="primary",
            use_container_width=True,
            key="bt_fetch_zerodha_data",
            disabled=bool(st.session_state.get("zerodha_loading", False)),
        )
    with action_col2:
        clear_clicked = st.button(
            "Clear",
            use_container_width=True,
            key="bt_clear_zerodha_data",
        )
        download_clicked = st.button(
            "Download CSV",
            use_container_width=True,
            key="bt_download_zerodha_data",
            disabled=bool(st.session_state.get("zerodha_loading", False)),
        )

    if fetch_clicked and not st.session_state.get("zerodha_loading", False):
        from_day = st.session_state.get("zerodha_from_date")
        to_day = st.session_state.get("zerodha_to_date")

        if from_day is None or to_day is None:
            st.error("Please select valid dates")
            st.session_state["zerodha_fetch_error"] = "Please select valid dates"
            st.session_state["zerodha_fetch_status"] = None
            st.session_state["zerodha_loading"] = False
        elif from_day > to_day:
            st.error("From Date must be earlier than To Date")
            st.session_state["zerodha_fetch_error"] = "From Date must be earlier than To Date"
            st.session_state["zerodha_fetch_status"] = None
            st.session_state["zerodha_loading"] = False
        else:
            st.session_state["zerodha_fetch_error"] = None
            st.session_state["zerodha_fetch_status"] = None
            st.session_state["zerodha_loading"] = True
            try:
                _fetch_zerodha_data_from_ui()
            except Exception as exc:
                st.session_state["zerodha_fetch_error"] = str(exc)
                st.session_state["zerodha_fetch_status"] = None
                st.session_state["zerodha_data_frame"] = None
            finally:
                st.session_state["zerodha_loading"] = False

    if clear_clicked:
        st.session_state["zerodha_data_frame"] = None
        st.session_state["zerodha_fetch_status"] = None
        st.session_state["zerodha_fetch_error"] = None
        st.session_state["zerodha_loading"] = False

    if download_clicked:
        df = st.session_state.get("zerodha_data_frame")
        from_day = st.session_state.get("zerodha_from_date")
        to_day = st.session_state.get("zerodha_to_date")
        selected_instrument = st.session_state.get("selected_instrument")
        interval = str(st.session_state.get("zerodha_interval", "15minute")).lower().strip()

        if df is None:
            st.error("No data available to download. Fetch Zerodha data first.")
        elif from_day is None or to_day is None:
            st.error("Please select valid dates before downloading CSV.")
        elif (
            not isinstance(selected_instrument, dict)
            or not selected_instrument.get("tradingsymbol")
        ):
            st.error("Please select a valid instrument from suggestions before downloading.")
        else:
            symbol = str(selected_instrument["tradingsymbol"]).strip().upper()
            try:
                save_result = zerodha_csv_downloader.download_and_save_data(
                    df=df,
                    symbol=symbol,
                    start_date=datetime.combine(from_day, time.min),
                    end_date=datetime.combine(to_day, time.max),
                    interval=interval,
                )
            except Exception as exc:
                st.error(f"Failed to save CSV: {exc}")
            else:
                if save_result.get("status") == "exists":
                    st.info("File already exists")
                else:
                    st.success("CSV saved successfully")
                    st.caption(f"Saved to: {save_result.get('file_path')}")

    fetch_error = st.session_state.get("zerodha_fetch_error")
    fetch_status = st.session_state.get("zerodha_fetch_status")
    fetched_df = st.session_state.get("zerodha_data_frame")

    if fetch_error:
        st.error(str(fetch_error))
    elif fetch_status:
        st.success(str(fetch_status))

    if fetched_df is not None:
        if fetched_df.empty:
            st.info("No candles found (market closed or no data available for selected range).")
        else:
            st.caption(
                f"Rows: {len(fetched_df)} | "
                f"Range: {fetched_df.index.min()} to {fetched_df.index.max()}"
            )
            st.caption("Preview (last 100 rows)")
            preview_df = fetched_df.tail(100).copy()
            date_column = "Date" if "Date" not in preview_df.columns else "Date (Index)"
            time_column = "Time" if "Time" not in preview_df.columns else "Time (Index)"
            if hasattr(preview_df.index, "strftime"):
                preview_df.insert(0, date_column, preview_df.index.strftime("%Y-%m-%d"))
                preview_df.insert(1, time_column, preview_df.index.strftime("%H:%M:%S"))
            else:
                preview_df.insert(0, date_column, preview_df.index.astype(str))
                preview_df.insert(1, time_column, "")
            st.dataframe(
                preview_df,
                use_container_width=True,
                hide_index=True,
            )
    else:
        st.caption("Configure Zerodha data inputs for backtesting")


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

            st.button(
                "Execute Strategy",
                use_container_width=True,
                type="primary",
                disabled=True,
                key="bt_execute",
            )

            st.button(
                "+ Create New Strategy",
                use_container_width=True,
                disabled=True,
                key="bt_create",
            )

    st.markdown(
        """
<div style="margin-top:16px;">
  <div style="background:#F3F4F6; border:1px solid #E5E7EB;
              border-radius:8px 8px 0 0; padding:8px 16px;
              display:flex; align-items:center; gap:8px;">
    <span style="width:8px;height:8px;border-radius:50%;background:#E5E7EB;
                 display:inline-block;"></span>
    <span style="width:8px;height:8px;border-radius:50%;background:#E5E7EB;
                 display:inline-block;"></span>
    <span style="width:8px;height:8px;border-radius:50%;background:#E5E7EB;
                 display:inline-block;"></span>
    <span style="font-size:12px; color:#7D8C99; margin-left:8px;
                 font-family:'Inter',sans-serif;">
      Terminal &mdash; Strategy Execution Output
    </span>
  </div>
  <div style="background:#1E1E2E; border:1px solid #E5E7EB; border-top:none;
              border-radius:0 0 8px 8px; padding:16px; height:200px;
              overflow-y:auto; font-family:'Consolas','Courier New',monospace;
              font-size:12px; line-height:1.6;">
    <span style="color:#AAB3BC;">[system] Engine idle &mdash; no strategy loaded.</span><br>
    <span style="color:#AAB3BC;">[system] Awaiting execution signal...</span><br>
    <span style="color:#AAB3BC;">[system] Data feed: not connected.</span><br>
    <span style="color:#AAB3BC;">[system] Strategy engine: standby.</span><br>
    <span style="color:#FFC107;">&gt; _</span>
  </div>
</div>
""",
        unsafe_allow_html=True,
    )
