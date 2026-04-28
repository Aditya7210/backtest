from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

from LiveMarket import LIVE_MARKET_ROOT


_TIMEFRAMES = ["1min", "3min", "5min", "10min", "15min", "30min", "60min"]


def _discover_available_dates(daily_root: Path) -> list[str]:
    if not daily_root.is_dir():
        return []
    available: list[str] = []
    for day_dir in daily_root.iterdir():
        if not day_dir.is_dir():
            continue
        if (day_dir / "equities_1min.csv").is_file() or (day_dir / "options_1min.csv").is_file():
            available.append(day_dir.name)
    return sorted(available, reverse=True)


def _load_instrument_index(date_str: str, data_type: str) -> list[dict[str, Any]]:
    daily_csv = LIVE_MARKET_ROOT / "daily" / date_str / f"{data_type}_1min.csv"
    if not daily_csv.is_file():
        return []

    df = pd.read_csv(daily_csv)
    required = {"instrument_token", "tradingsymbol"}
    if not required.issubset(set(df.columns)):
        return []

    token_series = pd.to_numeric(df["instrument_token"], errors="coerce")
    df = df.loc[token_series.notna()].copy()
    df["instrument_token"] = token_series.loc[df.index].astype("int64")
    df["tradingsymbol"] = df["tradingsymbol"].astype(str).str.strip().str.upper()

    count_df = (
        df.groupby(["instrument_token", "tradingsymbol"], dropna=False)
        .size()
        .reset_index(name="bar_count")
        .sort_values(["tradingsymbol", "instrument_token"])
    )

    results: list[dict[str, Any]] = []
    for row in count_df.itertuples(index=False):
        results.append(
            {
                "token": int(row.instrument_token),
                "tradingsymbol": str(row.tradingsymbol),
                "bar_count": int(row.bar_count),
            }
        )
    return results


def _timeframe_exists(date_str: str, data_type: str, timeframe: str) -> bool:
    return (LIVE_MARKET_ROOT / "daily" / date_str / f"{data_type}_{timeframe}.csv").is_file()


def render() -> None:
    st.markdown("### Live Market Data")
    daily_root = LIVE_MARKET_ROOT / "daily"
    available_dates = _discover_available_dates(daily_root)
    if not available_dates:
        st.info("No live market data collected yet. Start the collector from the Market Pulse page.")
        return

    col1, col2, col3 = st.columns(3, gap="small")
    selected_date = col1.selectbox("Available Dates", options=available_dates, key="live_selected_date")
    data_type = col2.selectbox("Data Type", options=["equities", "options"], key="live_selected_data_type")
    timeframe = col3.selectbox("Timeframe", options=_TIMEFRAMES, index=2, key="live_selected_timeframe")

    cache_key = f"{selected_date}:{data_type}:instrument_index"
    cache_payload = st.session_state.get("_live_instrument_index_cache", {})
    if not isinstance(cache_payload, dict):
        cache_payload = {}

    if cache_key not in cache_payload:
        try:
            cache_payload[cache_key] = _load_instrument_index(selected_date, data_type)
        except Exception as exc:
            st.error(f"Failed to read instrument index: {exc}")
            return
        st.session_state["_live_instrument_index_cache"] = cache_payload

    instrument_index = list(cache_payload.get(cache_key, []))
    if not instrument_index:
        st.warning("No instruments found for selected date/data type.")
        return

    query = st.text_input("Instrument Search", placeholder="Type symbol name...", key="live_instrument_search")
    normalized_query = str(query or "").strip().upper()
    filtered = [
        item
        for item in instrument_index
        if normalized_query in str(item.get("tradingsymbol", "")).upper()
    ]

    if not filtered:
        st.info("No instruments match the search query.")
        return

    option_labels = [
        f"{item['tradingsymbol']} (token: {item['token']})  [{item['bar_count']} bars]"
        for item in filtered
    ]
    selected_label = st.radio("Select Instrument", options=option_labels, key="live_instrument_radio")

    selected_instrument: dict[str, Any] | None = None
    for label, item in zip(option_labels, filtered):
        if label == selected_label:
            selected_instrument = item
            break

    if selected_instrument is None:
        st.warning("Select an instrument to continue.")
        return

    timeframe_available = _timeframe_exists(selected_date, data_type, timeframe)
    if not timeframe_available:
        st.warning(f"{timeframe} data not available for {selected_date}. Try 1min.")

    st.caption(
        "Selected: "
        f"{selected_instrument['tradingsymbol']} · {selected_date} · {timeframe} · {selected_instrument['bar_count']} bars"
    )

    if st.button("Use This Data for Backtest", use_container_width=True, key="live_use_for_backtest"):
        st.session_state["live_selected_date"] = selected_date
        st.session_state["live_selected_token"] = int(selected_instrument["token"])
        st.session_state["live_selected_symbol"] = str(selected_instrument["tradingsymbol"])
        st.session_state["live_selected_timeframe"] = timeframe
        st.session_state["live_selected_data_type"] = data_type
        st.session_state["data_mode"] = "live_market"
        st.session_state["bt_data_mode_select"] = "Live Market"
        st.success("Live market selection updated.")


__all__ = ["render"]
