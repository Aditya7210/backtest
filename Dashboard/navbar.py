import streamlit as st
from streamlit_option_menu import option_menu

# Strict Color Palette — single source of truth, imported by all section files
TV_UP = '#089981'
TV_DOWN = '#f23645'
PRIMARY_BLUE = '#2962FF'
BORDER_COLOR = '#e1e3e6'
BG_COLOR = '#ffffff'

def render_navbar() -> str:
    st.markdown(f"""
    <style>
        /* Global Typography */
        html, body, [class*="css"] {{
            font-family: 'Inter', sans-serif;
        }}

        /* KPI Section CSS */
        .kpi-card {{
            background: {BG_COLOR};
            border: 1px solid {BORDER_COLOR};
            border-radius: 8px;
            padding: 20px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.02);
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            transition: transform 0.2s, box-shadow 0.2s;
        }}
        .kpi-card:hover {{
            transform: translateY(-2px);
            box-shadow: 0 4px 12px rgba(0,0,0,0.05);
        }}
        .kpi-title {{
            color: #787b86;
            font-size: 0.9rem;
            font-weight: 500;
            margin-bottom: 5px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }}
        .kpi-value {{
            color: #131722;
            font-size: 1.8rem;
            font-weight: 700;
        }}
        .kpi-value.profit {{ color: {TV_UP}; }}
        .kpi-value.loss {{ color: {TV_DOWN}; }}

        /* Container Styling */
        .card-container {{
            background: {BG_COLOR};
            border: 1px solid {BORDER_COLOR};
            border-radius: 8px;
            padding: 15px;
            margin-bottom: 15px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.02);
        }}

        .block-container {{
            padding-top: 3rem !important;
        }}
    </style>
    """, unsafe_allow_html=True)

    selected = option_menu(
        menu_title=None,
        options=["Zerodha Authentication", "Dashboard", "Backtests", "Market Pulse"],
        icons=["shield-lock", "activity", "bar-chart-steps", "broadcast"],
        menu_icon="cast",
        default_index=0,
        orientation="horizontal",
        styles={
            "container": {"padding": "10px!important", "background-color": BG_COLOR, "border-bottom": f"1px solid {BORDER_COLOR}", "margin-bottom": "20px"},
            "icon": {"color": PRIMARY_BLUE, "font-size": "18px"},
            "nav-link": {"font-size": "15px", "text-align": "center", "margin": "0px 5px", "font-weight": "500", "padding": "10px 15px"},
            "nav-link-selected": {"background-color": PRIMARY_BLUE},
        }
    )
    return selected
