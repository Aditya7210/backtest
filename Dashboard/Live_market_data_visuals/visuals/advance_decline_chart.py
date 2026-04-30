from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st


def render(frame: pd.DataFrame, title: str) -> None:
    st.markdown("### Advance / Decline")
    if frame.empty:
        st.info("Advance/Decline history is not available yet.")
        return
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=frame["timestamp"], y=frame["Advance"], mode="lines", name="Advance", line=dict(color="#26A69A", width=2)))
    fig.add_trace(go.Scatter(x=frame["timestamp"], y=frame["Decline"], mode="lines", name="Decline", line=dict(color="#EF5350", width=2)))
    fig.update_layout(
        title=title,
        height=280,
        margin=dict(l=10, r=10, t=32, b=10),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        hovermode="x unified",
    )
    fig.update_yaxes(showgrid=True, gridcolor="#EEF2F7")
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})


__all__ = ["render"]
