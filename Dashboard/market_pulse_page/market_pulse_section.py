from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
import sys
from typing import Any

import pandas as pd
import streamlit as st

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from LiveMarket import LIVE_MARKET_ROOT, SNAPSHOTS_ROOT
from LiveMarket.time_utils import coerce_to_ist, now_ist
from .features import collector_controller


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _snapshot_age_seconds(snapshot_payload: dict[str, Any]) -> float | None:
    raw_ts = str(snapshot_payload.get("generated_at") or "").strip()
    if not raw_ts:
        return None
    try:
        generated = datetime.fromisoformat(raw_ts)
    except ValueError:
        return None
    generated_ist = coerce_to_ist(generated)
    return max(0.0, (now_ist() - generated_ist).total_seconds())


def _format_badge(label: str, state: str) -> str:
    normalized = state.strip().lower()
    if normalized in {"live", "running"}:
        bg, fg = "#16A34A", "#FFFFFF"
    elif normalized in {"stale", "warning"}:
        bg, fg = "#F59E0B", "#111827"
    elif normalized in {"stopped", "down", "error"}:
        bg, fg = "#DC2626", "#FFFFFF"
    else:
        bg, fg = "#6B7280", "#FFFFFF"
    return (
        f"<span style='background:{bg};color:{fg};padding:4px 10px;"
        "border-radius:999px;font-size:12px;font-weight:600;'>"
        f"{label}: {state.upper()}"
        "</span>"
    )


def _read_snapshot_file(name: str) -> dict[str, Any]:
    return _read_json(SNAPSHOTS_ROOT / f"{name}_snapshot.json")


def _render_control_bar(status_payload: dict[str, Any]) -> None:
    st.markdown("### Control Bar")
    collector_running = bool((status_payload.get("collector") or {}).get("running", False))
    calculator_running = bool((status_payload.get("calculator") or {}).get("running", False))

    col1, col2, col3, col4, col5 = st.columns([1.1, 1.1, 1.1, 1.1, 2.6], gap="small")
    with col1:
        if st.button("Start Collector", use_container_width=True):
            ok, message = collector_controller.start_collector()
            (st.success if ok else st.warning)(message)
            st.rerun()
    with col2:
        if st.button("Stop Collector", use_container_width=True):
            ok, message = collector_controller.stop_collector()
            (st.success if ok else st.warning)(message)
            st.rerun()
    with col3:
        if st.button("Start Calc", use_container_width=True):
            ok, message = collector_controller.start_calculator()
            (st.success if ok else st.warning)(message)
            st.rerun()
    with col4:
        if st.button("Stop Calc", use_container_width=True):
            ok, message = collector_controller.stop_calculator()
            (st.success if ok else st.warning)(message)
            st.rerun()
    with col5:
        collector_state = "live" if collector_running else "stopped"
        calculator_state = "live" if calculator_running else "stopped"
        st.markdown(
            _format_badge("Collector", collector_state)
            + "&nbsp;"
            + _format_badge("Calculator", calculator_state),
            unsafe_allow_html=True,
        )


def _render_metrics(status_payload: dict[str, Any]) -> None:
    ad_snapshot = _read_snapshot_file("ad")
    pcr_snapshot = _read_snapshot_file("pcr")
    atm_snapshot = _read_snapshot_file("atm_oi")
    vix_snapshot = _read_snapshot_file("vix")
    collector_file_status = status_payload.get("collector_file_status", {})
    equity_universe = collector_file_status.get("equity_universe", {})
    ad_universes = ad_snapshot.get("universes", {})
    if not isinstance(ad_universes, dict) or not ad_universes:
        ad_universes = {"All Collected": ad_snapshot}
    preferred_order = [
        "All Collected",
        "NIFTY 50",
        "NIFTY BANK",
        "NIFTY 100",
        "NIFTY 200",
        "NIFTY 500",
        "F&O Stocks",
        "NIFTY500 + F&O",
    ]
    ad_filter_options = [
        option
        for option in preferred_order
        if option in ad_universes
    ] + [
        option
        for option in sorted(ad_universes.keys())
        if option not in preferred_order
    ]
    selected_ad_universe = st.selectbox(
        "A/D Filter",
        options=ad_filter_options,
        key="market_pulse_ad_filter",
    )
    selected_ad_snapshot = ad_universes.get(selected_ad_universe, ad_snapshot)
    if not isinstance(selected_ad_snapshot, dict):
        selected_ad_snapshot = ad_snapshot

    age = _snapshot_age_seconds(ad_snapshot)
    if age is not None and age > 120:
        st.warning(f"Snapshots are stale ({int(age)} seconds old).")

    row1 = st.columns(4, gap="small")
    row1[0].metric("Advances", selected_ad_snapshot.get("advances", 0))
    row1[1].metric("Declines", selected_ad_snapshot.get("declines", 0))
    row1[2].metric("A/D Ratio", selected_ad_snapshot.get("ad_ratio", 0))
    row1[3].metric("VIX", vix_snapshot.get("vix", "NA"))

    row2 = st.columns(4, gap="small")
    row2[0].metric("NIFTY PCR", pcr_snapshot.get("nifty_pcr", 0))
    row2[1].metric("BANKNIFTY PCR", pcr_snapshot.get("banknifty_pcr", 0))
    row2[2].metric("NIFTY ATM Strike", atm_snapshot.get("nifty_atm_strike", "NA"))
    row2[3].metric("BANKNIFTY ATM Strike", atm_snapshot.get("banknifty_atm_strike", "NA"))

    st.caption(
        "Last generated at: "
        f"{ad_snapshot.get('generated_at') or pcr_snapshot.get('generated_at') or 'NA'}"
    )
    st.caption(
        "A/D universe: "
        f"{selected_ad_universe} | "
        f"collector={equity_universe.get('name') or 'NA'} | "
        f"observed={selected_ad_snapshot.get('universe_observed', 0)} | "
        f"matched_prev_close={selected_ad_snapshot.get('matched_prev_close', 0)} | "
        f"missing_prev_close={selected_ad_snapshot.get('missing_prev_close', 0)}"
    )
    st.caption(
        "NIFTY PCR scope: "
        f"source={pcr_snapshot.get('source') or 'NA'} | "
        f"expiry={pcr_snapshot.get('nifty_expiry') or 'NA'} "
        f"contracts={pcr_snapshot.get('nifty_contracts', 0)} "
        f"strikes={pcr_snapshot.get('nifty_strike_min') or 'NA'}-"
        f"{pcr_snapshot.get('nifty_strike_max') or 'NA'}"
    )
    st.caption(
        "BANKNIFTY PCR scope: "
        f"source={pcr_snapshot.get('source') or 'NA'} | "
        f"expiry={pcr_snapshot.get('banknifty_expiry') or 'NA'} "
        f"contracts={pcr_snapshot.get('banknifty_contracts', 0)} "
        f"strikes={pcr_snapshot.get('banknifty_strike_min') or 'NA'}-"
        f"{pcr_snapshot.get('banknifty_strike_max') or 'NA'}"
    )
    _render_option_chain_visual(pcr_snapshot, atm_snapshot)


def _render_option_chain_visual(
    pcr_snapshot: dict[str, Any],
    atm_snapshot: dict[str, Any],
) -> None:
    option_chain = pcr_snapshot.get("option_chain", {})
    if not isinstance(option_chain, dict) or not option_chain:
        st.info("Option chain snapshot is not available yet.")
        return

    st.markdown("### Option Chain")
    chain_label = st.selectbox(
        "Option Chain Filter",
        options=["NIFTY 50", "BANKNIFTY"],
        key="market_pulse_option_chain_filter",
    )
    underlying = "BANKNIFTY" if chain_label == "BANKNIFTY" else "NIFTY"
    chain_rows = option_chain.get(underlying, [])
    if not isinstance(chain_rows, list) or not chain_rows:
        st.info(f"No option chain rows available for {chain_label}.")
        return

    chain_df = pd.DataFrame(chain_rows)
    required = {"strike", "ce_oi", "pe_oi", "ce_ltp", "pe_ltp", "strike_pcr"}
    if chain_df.empty or not required.issubset(set(chain_df.columns)):
        st.info(f"Option chain data for {chain_label} is incomplete.")
        return

    chain_df["strike"] = pd.to_numeric(chain_df["strike"], errors="coerce")
    chain_df = chain_df.dropna(subset=["strike"]).sort_values("strike")
    if chain_df.empty:
        st.info(f"No valid strikes available for {chain_label}.")
        return

    atm_key = "banknifty_atm_strike" if underlying == "BANKNIFTY" else "nifty_atm_strike"
    atm_raw = atm_snapshot.get(atm_key)
    try:
        atm_strike = float(atm_raw)
    except (TypeError, ValueError):
        atm_strike = float(chain_df["strike"].median())

    strike_window = st.slider(
        "Strikes Around ATM",
        min_value=5,
        max_value=40,
        value=12,
        step=1,
        key=f"market_pulse_option_chain_window_{underlying}",
    )
    visible_df = (
        chain_df.assign(_distance=(chain_df["strike"] - atm_strike).abs())
        .sort_values(["_distance", "strike"])
        .head((int(strike_window) * 2) + 1)
        .sort_values("strike")
        .drop(columns=["_distance"])
    )

    summary_col1, summary_col2, summary_col3, summary_col4 = st.columns(4, gap="small")
    summary_col1.metric("ATM Strike", int(atm_strike))
    summary_col2.metric("Contracts", len(chain_df) * 2)
    summary_col3.metric("Visible Strikes", len(visible_df))
    summary_col4.metric("Chain PCR", pcr_snapshot.get("banknifty_pcr" if underlying == "BANKNIFTY" else "nifty_pcr", 0))

    chart_df = visible_df[["strike", "ce_oi", "pe_oi"]].rename(
        columns={"ce_oi": "CE OI", "pe_oi": "PE OI"}
    )
    chart_df["strike"] = chart_df["strike"].astype("int64").astype(str)
    st.bar_chart(chart_df.set_index("strike"), use_container_width=True)

    display_df = visible_df[
        [
            "strike",
            "ce_ltp",
            "ce_oi",
            "ce_volume",
            "pe_ltp",
            "pe_oi",
            "pe_volume",
            "strike_pcr",
        ]
    ].rename(
        columns={
            "strike": "Strike",
            "ce_ltp": "CE LTP",
            "ce_oi": "CE OI",
            "ce_volume": "CE Vol",
            "pe_ltp": "PE LTP",
            "pe_oi": "PE OI",
            "pe_volume": "PE Vol",
            "strike_pcr": "Strike PCR",
        }
    )
    st.dataframe(display_df, use_container_width=True, hide_index=True)


def _render_status_panel(status_payload: dict[str, Any]) -> None:
    st.markdown("### Runtime Status")
    collector_file_status = status_payload.get("collector_file_status", {})
    collector_health = status_payload.get("collector_status_health", {})
    collector = status_payload.get("collector", {})
    calculator = status_payload.get("calculator", {})

    with st.expander("Collector Status", expanded=True):
        st.write(f"Collector running: {collector.get('running')}")
        st.write(f"Collector healthy: {collector.get('healthy')}")
        st.write(f"Collector PID: {collector.get('pid')}")
        st.write(f"Collector PID alive: {collector.get('pid_alive')}")
        st.write(f"Collector started_at: {collector.get('started_at')}")
        st.write(f"Bars written: {collector_file_status.get('bars_written')}")
        st.write(f"Last tick at: {collector_file_status.get('last_tick_at')}")
        st.write(f"Tokens subscribed: {collector_file_status.get('tokens_subscribed')}")
        st.write(f"Token counts: {collector_file_status.get('token_counts')}")
        st.write(f"Equity universe: {collector_file_status.get('equity_universe')}")
        st.write(f"Collector status file state: {collector_file_status.get('status')}")
        st.write(f"Collector status file exists: {collector_health.get('status_file_exists')}")
        st.write(f"Collector status freshness ok: {collector_health.get('status_recent')}")
        if collector_file_status.get("last_error"):
            st.error(f"Collector error: {collector_file_status.get('last_error')}")
        error_excerpt = str(status_payload.get("collector_error_excerpt") or "").strip()
        if error_excerpt and not collector.get("running"):
            st.error("Collector recent stderr:")
            st.code(error_excerpt, language="text")

    with st.expander("Calculation Status", expanded=False):
        st.write(f"Calculator running: {calculator.get('running')}")
        st.write(f"Calculator PID: {calculator.get('pid')}")
        st.write(f"Calculator started_at: {calculator.get('started_at')}")
        snapshot_times = status_payload.get("snapshots_last_modified", {})
        if snapshot_times:
            st.json(snapshot_times)


def _render_latest_data_preview() -> None:
    st.markdown("### Live Data Preview")
    daily_root = LIVE_MARKET_ROOT / "daily"
    if not daily_root.is_dir():
        st.info("No live_market/daily data directory exists yet.")
        return

    available_days = sorted([p for p in daily_root.glob("*") if p.is_dir()])
    if not available_days:
        st.info("No day directories available yet.")
        return

    selected_day = st.selectbox(
        "Trading Day",
        options=[p.name for p in reversed(available_days)],
        key="market_pulse_day",
    )

    day_dir = daily_root / selected_day
    timeframe = st.selectbox(
        "Timeframe",
        options=["1min", "3min", "5min", "10min", "15min", "30min", "60min"],
        index=0,
        key="market_pulse_timeframe",
    )

    equities_path = day_dir / f"equities_{timeframe}.csv"
    options_path = day_dir / f"options_{timeframe}.csv"
    vix_path = day_dir / f"vix_{timeframe}.csv"

    preview_col1, preview_col2, preview_col3 = st.columns(3, gap="small")

    with preview_col1:
        st.caption(f"Equities: {equities_path.name}")
        if equities_path.is_file():
            eq_df = pd.read_csv(equities_path)
            st.write(f"Rows: {len(eq_df)}")
            st.dataframe(eq_df.tail(5), use_container_width=True)
        else:
            st.info("File not found.")

    with preview_col2:
        st.caption(f"Options: {options_path.name}")
        if options_path.is_file():
            op_df = pd.read_csv(options_path)
            st.write(f"Rows: {len(op_df)}")
            st.dataframe(op_df.tail(5), use_container_width=True)
        else:
            st.info("File not found.")

    with preview_col3:
        st.caption(f"VIX: {vix_path.name}")
        if vix_path.is_file():
            vx_df = pd.read_csv(vix_path)
            st.write(f"Rows: {len(vx_df)}")
            st.dataframe(vx_df.tail(5), use_container_width=True)
        else:
            st.info("File not found.")


def _render_live_panels() -> None:
    status_payload = collector_controller.get_status()
    _render_control_bar(status_payload)
    _render_metrics(status_payload)
    _render_status_panel(status_payload)


@st.fragment(run_every=1)
def _render_live_panels_auto_refresh() -> None:
    _render_live_panels()


def _render_auto_refresh_toggle() -> bool:
    st.session_state.setdefault("market_pulse_auto_refresh", True)
    enabled = st.toggle("Auto Refresh (1s)", key="market_pulse_auto_refresh")
    return bool(enabled)


def render() -> None:
    st.markdown("## Market Pulse")
    st.caption("Real-time monitoring of collector, calculations, and derived snapshots.")

    if _render_auto_refresh_toggle():
        _render_live_panels_auto_refresh()
    else:
        _render_live_panels()

    _render_latest_data_preview()

    if st.button("Refresh Now", use_container_width=False, key="market_pulse_refresh_now"):
        st.rerun()


__all__ = ["render"]
