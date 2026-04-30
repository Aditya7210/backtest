import streamlit as st

st.set_page_config(page_title="Algo Trading System", layout="wide", initial_sidebar_state="collapsed")

from navbar import render_navbar
from Backtesting_page.zerodha_authentication_page import render as render_zerodha_auth
from dashboard_section import render as render_dashboard
from Backtesting_page.Backtests_section import render as render_backtests
from market_pulse_page.market_pulse_section import render as render_market_pulse
from Live_market_data_visuals.ui_live_market import render as render_live_market_visuals

selected = render_navbar()

if selected == "Zerodha Authentication":
    render_zerodha_auth()
elif selected == "Dashboard":
    render_dashboard()
elif selected == "Backtests":
    render_backtests()
elif selected == "Market Pulse":
    render_market_pulse()
elif selected == "Live Market Data Visual":
    render_live_market_visuals()
