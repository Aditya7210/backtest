from __future__ import annotations

from datetime import date
from pathlib import Path

import streamlit as st

from .Features.zerodha_auth import (
    generate_access_token,
    get_login_url,
    load_env_variables,
    save_access_token_to_env,
)


def _resolve_env_path() -> Path:
    # Project root: .../Algo_Trading_System
    return Path(__file__).resolve().parents[2] / ".env"


def _extract_request_token() -> str | None:
    raw_value = st.query_params.get("request_token")
    if raw_value is None:
        return None
    if isinstance(raw_value, list):
        return str(raw_value[0]).strip() if raw_value else None
    return str(raw_value).strip()


def _persist_and_store_token(env_path: Path, token: str) -> None:
    save_access_token_to_env(str(env_path), token)
    st.session_state["ZERODHA_ACCESS_TOKEN"] = token
    st.session_state["ZERODHA_TOKEN_DATE"] = date.today().isoformat()
    st.session_state["zerodha_auth_status"] = "Connected to Zerodha"


def render() -> None:
    env_path = _resolve_env_path()

    st.session_state.setdefault("ZERODHA_ACCESS_TOKEN", None)
    st.session_state.setdefault("zerodha_auth_status", None)

    st.markdown("### Zerodha Authentication")
    st.caption("You will be redirected back after login. Token handling is automatic.")

    try:
        env_data = load_env_variables(str(env_path))
        api_key = str(env_data["api_key"])
        api_secret = str(env_data["api_secret"])
        env_access_token = env_data.get("access_token")
    except Exception as exc:
        st.error(f"Unable to load Zerodha credentials: {exc}")
        st.session_state["zerodha_auth_status"] = "Not connected"
        return

    if not st.session_state.get("ZERODHA_ACCESS_TOKEN") and env_access_token:
        st.session_state["ZERODHA_ACCESS_TOKEN"] = env_access_token

    if st.button("Login to Zerodha", type="primary"):
        try:
            login_url = get_login_url(api_key)
        except Exception as exc:
            st.error(f"Unable to generate login URL: {exc}")
        else:
            st.markdown(f"[Click here to login]({login_url})")
            st.info("After login, Zerodha will redirect back with a request_token.")

    request_token = _extract_request_token()
    if request_token:
        st.info("Request token received")
        try:
            access_token = generate_access_token(api_key, api_secret, request_token)
            _persist_and_store_token(env_path, access_token)
            st.success("Zerodha connected successfully")
            st.query_params.clear()
        except Exception as exc:
            st.error(f"Failed to generate access token: {exc}")
            st.session_state["zerodha_auth_status"] = "Not connected"
    else:
        manual_request_token = st.text_input(
            "Paste request_token (if not auto-detected)",
            key="zerodha_manual_request_token",
        )
        if st.button("Generate Access Token"):
            cleaned_token = (manual_request_token or "").strip()
            if not cleaned_token:
                st.error("Please provide a valid request_token")
            else:
                try:
                    access_token = generate_access_token(api_key, api_secret, cleaned_token)
                    _persist_and_store_token(env_path, access_token)
                    st.success("Zerodha connected successfully")
                except Exception as exc:
                    st.error(f"Failed to generate access token: {exc}")
                    st.session_state["zerodha_auth_status"] = "Not connected"

    token_in_session = st.session_state.get("ZERODHA_ACCESS_TOKEN")
    if token_in_session:
        st.success("Connected to Zerodha")
        st.session_state["zerodha_auth_status"] = "Connected to Zerodha"
    else:
        st.warning("Not connected")
        st.session_state["zerodha_auth_status"] = "Not connected"
