from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st


def render(vix_frame: pd.DataFrame, straddle_frame: pd.DataFrame) -> None:
    st.markdown("### IV / ATM Straddle")
    if vix_frame.empty and straddle_frame.empty:
        st.info("IV/Straddle history is not available yet.")
        return
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    if not vix_frame.empty:
        fig.add_trace(go.Scatter(x=vix_frame["timestamp"], y=vix_frame["IV"], mode="lines", name="IV", line=dict(color="#3B82F6", width=2)), secondary_y=False)
    if not straddle_frame.empty:
        fig.add_trace(go.Scatter(x=straddle_frame["timestamp"], y=straddle_frame["Straddle"], mode="lines", name="Straddle", line=dict(color="#EF4444", width=2)), secondary_y=True)
    fig.update_layout(
        height=280,
        margin=dict(l=10, r=10, t=20, b=10),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        hovermode="x unified",
    )
    fig.update_yaxes(title_text="IV", secondary_y=False)
    fig.update_yaxes(title_text="Straddle", secondary_y=True)
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})


__all__ = ["render"]
