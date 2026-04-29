"""
Adani Power — Historical Daily Price Data (Last 5 Years)
=========================================================
Source  : Yahoo Finance via yfinance
Ticker  : ADANIPOWER.NS  (NSE listing)
Period  : Last 5 years, daily OHLCV
Output  : Data/testing_data/Data_files/yfinance_data/ADANIPOWER_daily_5yr.csv
Log     : Data/Logs/Script_logs/adani_power_data.log
"""

import os
import sys

import pandas as pd
import yfinance as yf
from loguru import logger

# ── Config ────────────────────────────────────────────────────────────────
TICKER = "ADANIPOWER.NS"  # NSE ticker on Yahoo Finance
START_DATE = "2022-01-01"  # From Jan 1st, 2022 till date
INTERVAL = "1d"  # Daily bars

# Relative paths to ensure it works identically in Windows and Docker
PROJECT_DATA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

OUTPUT_DIR = os.path.join(PROJECT_DATA_DIR, "testing_data", "Data_files", "yfinance_data")
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "ADANIPOWER_daily_since_2022.csv")

LOG_DIR = os.path.join(PROJECT_DATA_DIR, "Logs", "Script_logs")
LOG_FILE = os.path.join(LOG_DIR, "adani_power_data.log")
# ─────────────────────────────────────────────────────────────────────────

os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(LOG_DIR, exist_ok=True)

# Configure loguru
logger.remove()
logger.add(
    sys.stderr,
    level="INFO",
    format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{message}</cyan>",
)
logger.add(
    LOG_FILE,
    level="DEBUG",
    rotation="5 MB",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {message}",
)

logger.info(f"Downloading {TICKER} — daily data from {START_DATE} till date ...")
logger.info(f"Output : {os.path.abspath(OUTPUT_FILE)}")
logger.info("-" * 60)

# ── Download ──────────────────────────────────────────────────────────────
ticker_obj = yf.Ticker(TICKER)
df = ticker_obj.history(start=START_DATE, interval=INTERVAL, auto_adjust=True)

if df.empty:
    logger.error("No data returned. Check ticker symbol or internet connection.")
    sys.exit(1)

# ── Clean up ──────────────────────────────────────────────────────────────
df.index = df.index.tz_localize(None)  # Remove timezone info
df.index.name = "Date"
df = df[["Open", "High", "Low", "Close", "Volume"]]  # Keep standard OHLCV columns
df = df.dropna()
df = df.sort_index()

# ── Save ──────────────────────────────────────────────────────────────────
df.to_csv(OUTPUT_FILE)

logger.info(f"Ticker  : {TICKER}")
logger.info(f"Rows    : {len(df):,}")
logger.info(f"From    : {df.index[0].date()}")
logger.info(f"To      : {df.index[-1].date()}")
logger.info(f"Columns : {list(df.columns)}")
logger.info("-" * 60)
logger.info(f"Saved   : {os.path.abspath(OUTPUT_FILE)}")
logger.info("\nSample (last 5 rows):")
logger.info("\n" + df.tail(5).to_string())