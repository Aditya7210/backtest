from __future__ import annotations

import pandas as pd
import streamlit as st


def _color_pct(value: object) -> str:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return ""
    if numeric > 0:
        return "color: #067A46; background-color: #DCFCE7"
    if numeric < 0:
        return "color: #B91C1C; background-color: #FEE2E2"
    return "color: #374151; background-color: #F3F4F6"


def render(frame: pd.DataFrame) -> None:
    st.markdown("### OI Change From Market Open")
    if frame.empty:
        st.info("OI change cannot be calculated until option bars establish an opening baseline.")
        return
    columns = [
        "strike",
        "ce_oi",
        "ce_oi_change_pct",
        "pe_oi",
        "pe_oi_change_pct",
        "strike_pcr",
    ]
    available = [column for column in columns if column in frame.columns]
    table = frame[available].rename(
        columns={
            "strike": "Strike",
            "ce_oi": "CE OI",
            "ce_oi_change_pct": "CE OI Chg %",
            "pe_oi": "PE OI",
            "pe_oi_change_pct": "PE OI Chg %",
            "strike_pcr": "Strike PCR",
        }
    )
    styled = table.style.applymap(_color_pct, subset=["CE OI Chg %", "PE OI Chg %"])
    st.dataframe(styled, use_container_width=True, hide_index=True)


__all__ = ["render"]
