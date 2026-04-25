print("Docker + Python working")

# Import dependencies
import backtrader as bt
import matplotlib
import pandas as pd
import numpy as np
from loguru import logger
import importlib
import jugaad_data

packages = [
    "numpy",
    "pandas",
    "matplotlib",
    "loguru",
    "backtrader",
    "jugaad_data",
    "kiteconnect",
    "requests",
    "plotly",
    "talib",
    "streamlit",
    "yfinance",
    "ruff",
    "black",
    "streamlit_elements",
    "streamlit_option_menu",
    "streamlit_extras",
    "streamlit_shadcn_ui",
    "streamlit_toggle",
    "streamlit_ace",
    "watchdog",
]

for pkg in packages:
    try:
        importlib.import_module(pkg)
        print(f"{pkg} is installed")
    except ImportError:
        print(f"{pkg} is missing")
