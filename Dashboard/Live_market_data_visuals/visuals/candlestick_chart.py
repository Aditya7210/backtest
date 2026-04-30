from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st


def render(frame: pd.DataFrame, instrument: str) -> None:
    st.markdown("### Live Market Candlestick")
    if frame.empty:
        st.info("No OHLC data available for the selected instrument.")
        return

    fig = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.03,
        row_heights=[0.74, 0.26],
    )
    fig.add_trace(
        go.Candlestick(
            x=frame["timestamp"],
            open=frame["open"],
            high=frame["high"],
            low=frame["low"],
            close=frame["close"],
            name=instrument,
            increasing_line_color="#089981",
            decreasing_line_color="#f23645",
        ),
        row=1,
        col=1,
    )
    for column, color, label in [
        ("sma_5", "#2962FF", "SMA 5"),
        ("sma_20", "#F59E0B", "SMA 20"),
        ("sma_50", "#7C3AED", "SMA 50"),
        ("vwap", "#0F766E", "VWAP"),
    ]:
        if column in frame.columns:
            fig.add_trace(
                go.Scatter(x=frame["timestamp"], y=frame[column], mode="lines", name=label, line=dict(width=1.2, color=color)),
                row=1,
                col=1,
            )
    if "volume" in frame.columns:
        colors = ["#089981" if close >= open_ else "#f23645" for open_, close in zip(frame["open"], frame["close"])]
        fig.add_trace(
            go.Bar(x=frame["timestamp"], y=frame["volume"], name="Volume", marker_color=colors, opacity=0.45),
            row=2,
            col=1,
        )
    fig.update_layout(
        height=520,
        margin=dict(l=10, r=10, t=10, b=10),
        xaxis_rangeslider_visible=False,
        legend=dict(orientation="h", yanchor="bottom", y=1.01, xanchor="left", x=0),
        hovermode="x unified",
    )
    fig.update_yaxes(showgrid=True, gridcolor="#EEF2F7")
    st.plotly_chart(fig, use_container_width=True, config={"scrollZoom": True, "displayModeBar": True})


__all__ = ["render"]
