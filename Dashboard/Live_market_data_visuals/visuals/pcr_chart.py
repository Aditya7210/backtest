from __future__ import annotations

from typing import Any

import streamlit as st


def render(pcr_snapshot: dict[str, Any], underlying: str | None) -> None:
    label = "BANKNIFTY" if underlying == "BANKNIFTY" else "NIFTY"
    key_prefix = "banknifty" if underlying == "BANKNIFTY" else "nifty"
    pcr = pcr_snapshot.get(f"{key_prefix}_pcr", 0)
    call_oi = pcr_snapshot.get(f"{key_prefix}_call_oi", 0)
    put_oi = pcr_snapshot.get(f"{key_prefix}_put_oi", 0)
    contracts = pcr_snapshot.get(f"{key_prefix}_contracts", 0)
    st.markdown("### PCR")
    col1, col2, col3 = st.columns(3, gap="small")
    col1.metric(f"{label} PCR", pcr)
    col2.metric("Call OI", f"{int(call_oi):,}" if call_oi else "0")
    col3.metric("Put OI", f"{int(put_oi):,}" if put_oi else "0")
    st.caption(
        f"Contracts={contracts} | "
        f"Expiry={pcr_snapshot.get(f'{key_prefix}_expiry') or 'NA'} | "
        f"Source={pcr_snapshot.get('source') or 'NA'}"
    )


__all__ = ["render"]
