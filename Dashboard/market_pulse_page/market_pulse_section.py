from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
import sys
import time
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

    age = _snapshot_age_seconds(ad_snapshot)
    if age is not None and age > 120:
        st.warning(f"Snapshots are stale ({int(age)} seconds old).")

    row1 = st.columns(4, gap="small")
    row1[0].metric("Advances", ad_snapshot.get("advances", 0))
    row1[1].metric("Declines", ad_snapshot.get("declines", 0))
    row1[2].metric("A/D Ratio", ad_snapshot.get("ad_ratio", 0))
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


def _auto_refresh() -> None:
    st.session_state.setdefault("market_pulse_auto_refresh", True)
    enabled = st.toggle("Auto Refresh (10s)", key="market_pulse_auto_refresh")
    if not enabled:
        return
    now = time.time()
    st.session_state.setdefault("market_pulse_last_refresh", 0.0)
    if now - float(st.session_state["market_pulse_last_refresh"]) < 10.0:
        return
    st.session_state["market_pulse_last_refresh"] = now
    time.sleep(0.2)
    st.rerun()


def render() -> None:
    st.markdown("## Market Pulse")
    st.caption("Real-time monitoring of collector, calculations, and derived snapshots.")

    status_payload = collector_controller.get_status()
    _render_control_bar(status_payload)
    _render_metrics(status_payload)
    _render_status_panel(status_payload)
    _render_latest_data_preview()

    if st.button("Refresh Now", use_container_width=False, key="market_pulse_refresh_now"):
        st.rerun()

    _auto_refresh()


__all__ = ["render"]
