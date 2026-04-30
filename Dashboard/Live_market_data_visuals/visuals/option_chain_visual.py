from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st


def _centered_window(frame: pd.DataFrame, atm_strike: float | int | None, around: int) -> pd.DataFrame:
    if frame.empty:
        return frame
    try:
        atm = float(atm_strike)
    except (TypeError, ValueError):
        atm = float(frame["strike"].median())
    return (
        frame.assign(_distance=(frame["strike"] - atm).abs())
        .sort_values(["_distance", "strike"])
        .head((int(around) * 2) + 1)
        .sort_values("strike")
        .drop(columns=["_distance"])
    )


def render(frame: pd.DataFrame, *, underlying: str | None, atm_strike: float | int | None) -> pd.DataFrame:
    st.markdown("### Option Chain")
    if frame.empty or not underlying:
        st.info("Option chain is available for NIFTY 50 and BANKNIFTY only.")
        return pd.DataFrame()

    around = st.slider(
        "Option Chain Strikes Around ATM",
        min_value=5,
        max_value=50,
        value=15,
        step=1,
        key=f"live_visual_chain_window_{underlying}",
    )
    visible = _centered_window(frame, atm_strike, around)
    if visible.empty:
        st.info("No option chain rows in the selected strike window.")
        return visible

    fig = go.Figure()
    fig.add_trace(go.Bar(x=visible["strike"], y=visible["ce_oi"], name="Call OI", marker_color="#EF5350"))
    fig.add_trace(go.Bar(x=visible["strike"], y=visible["pe_oi"], name="Put OI", marker_color="#26A69A"))
    if atm_strike is not None:
        fig.add_vline(x=float(atm_strike), line_width=1, line_dash="dash", line_color="#111827")
    fig.update_layout(
        barmode="group",
        height=280,
        margin=dict(l=10, r=10, t=10, b=10),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
    )
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

    table = visible[
        [
            "strike",
            "ce_ltp",
            "ce_oi",
            "ce_oi_change_pct",
            "pe_ltp",
            "pe_oi",
            "pe_oi_change_pct",
            "strike_pcr",
        ]
    ].rename(
        columns={
            "strike": "Strike",
            "ce_ltp": "CE LTP",
            "ce_oi": "CE OI",
            "ce_oi_change_pct": "CE OI Chg %",
            "pe_ltp": "PE LTP",
            "pe_oi": "PE OI",
            "pe_oi_change_pct": "PE OI Chg %",
            "strike_pcr": "Strike PCR",
        }
    )
    st.dataframe(table, use_container_width=True, hide_index=True)
    return visible


__all__ = ["render"]
