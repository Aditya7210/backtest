from __future__ import annotations

import streamlit as st

from .features import data_transformer, instrument_selector, live_data_fetcher
from .features.indicator_engine import indicator_summary
from .visuals import (
    advance_decline_chart,
    atm_straddle_chart,
    candlestick_chart,
    oi_heatmap_table,
    option_chain_visual,
    pcr_chart,
)


def _atm_for_underlying(atm_snapshot: dict, underlying: str | None) -> int | None:
    if underlying == "BANKNIFTY":
        value = atm_snapshot.get("banknifty_atm_strike")
    elif underlying == "NIFTY":
        value = atm_snapshot.get("nifty_atm_strike")
    else:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _render_indicator_panel(ohlc) -> None:
    summary = indicator_summary(ohlc)
    st.markdown("### Technicals")
    col1, col2, col3 = st.columns(3, gap="small")
    col1.metric("Short Term", summary["short_term"])
    col2.metric("Long Term", summary["long_term"])
    col3.metric("RSI (14)", f"{summary['rsi']} - {summary['rsi_label']}")


def _render_visual_body() -> None:
    bootstrap_context = live_data_fetcher.load_market_context("1min")
    instrument, timeframe = instrument_selector.render(bootstrap_context["equities"])
    context = bootstrap_context if timeframe == "1min" else live_data_fetcher.load_market_context(timeframe)

    equities = context["equities"]
    options = context["options"]
    vix = context["vix"]
    prev_close = context["prev_close"]
    snapshots = context["snapshots"]
    pcr_snapshot = snapshots.get("pcr", {})
    atm_snapshot = snapshots.get("atm_oi", {})

    underlying = instrument_selector.option_underlying_for_instrument(instrument)
    atm_strike = _atm_for_underlying(atm_snapshot, underlying)

    ohlc = data_transformer.instrument_ohlc(equities, instrument)
    chain = data_transformer.option_chain_frame(pcr_snapshot, underlying)
    baseline = data_transformer.option_baseline_frame(options, underlying)
    chain = data_transformer.enrich_option_chain_with_oi_change(chain, baseline)

    top_left, top_right = st.columns([1.65, 1], gap="small")
    with top_left:
        candlestick_chart.render(ohlc, instrument)
    with top_right:
        visible_chain = option_chain_visual.render(chain, underlying=underlying, atm_strike=atm_strike)

    _render_indicator_panel(ohlc)

    ad_filter = "NIFTY BANK" if instrument == "NIFTY BANK" else ("NIFTY 50" if instrument == "NIFTY 50" else "All Collected")
    ad_series = data_transformer.advance_decline_series(equities, prev_close, ad_filter)
    advance_decline_chart.render(ad_series, f"{ad_filter} Breadth")

    straddle = data_transformer.atm_straddle_series(options, underlying, atm_strike)
    iv = data_transformer.vix_series(vix)
    atm_straddle_chart.render(iv, straddle)

    lower_left, lower_right = st.columns([1, 1], gap="small")
    with lower_left:
        pcr_chart.render(pcr_snapshot, underlying)
    with lower_right:
        oi_heatmap_table.render(visible_chain if not visible_chain.empty else chain)


@st.fragment(run_every=2)
def _render_visual_body_auto_refresh() -> None:
    _render_visual_body()


def render() -> None:
    st.markdown("## Live Market Data Visual")
    st.caption("Live CSV and snapshot based market visuals powered by the existing collector and calculator.")
    st.session_state.setdefault("live_visual_auto_refresh", True)
    auto_refresh = st.toggle("Auto Refresh (2s)", key="live_visual_auto_refresh")
    if auto_refresh:
        _render_visual_body_auto_refresh()
    else:
        _render_visual_body()


__all__ = ["render"]
