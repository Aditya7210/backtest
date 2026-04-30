from __future__ import annotations

import pandas as pd
import streamlit as st


_PREFERRED = ["NIFTY 50", "NIFTY BANK"]


def _available_symbols(equities: pd.DataFrame) -> list[str]:
    if equities.empty or "tradingsymbol" not in equities.columns:
        return list(_PREFERRED)
    symbols = sorted({
        str(symbol).strip().upper()
        for symbol in equities["tradingsymbol"].dropna().tolist()
        if str(symbol).strip()
    })
    preferred = [symbol for symbol in _PREFERRED if symbol in symbols]
    rest = [symbol for symbol in symbols if symbol not in preferred]
    return preferred + rest


def render(equities: pd.DataFrame) -> tuple[str, str]:
    col1, col2 = st.columns([2.8, 1], gap="small")
    symbols = _available_symbols(equities)
    with col1:
        instrument = st.selectbox(
            "Instrument",
            options=symbols,
            index=0,
            key="live_visual_instrument",
        )
    with col2:
        timeframe = st.selectbox(
            "Timeframe",
            options=["1min", "3min", "5min", "10min", "15min", "30min", "60min"],
            index=0,
            key="live_visual_timeframe",
        )
    return instrument, timeframe


def option_underlying_for_instrument(instrument: str) -> str | None:
    symbol = str(instrument or "").strip().upper()
    if symbol in {"NIFTY BANK", "BANKNIFTY"}:
        return "BANKNIFTY"
    if symbol in {"NIFTY 50", "NIFTY"}:
        return "NIFTY"
    return None


__all__ = ["option_underlying_for_instrument", "render"]
