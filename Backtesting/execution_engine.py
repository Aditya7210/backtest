"""
Backtest Execution Script — Adani Power Trend + Pullback Strategy
=================================================================
Executes the TrendPullbackStrategy on historical Adani Power data
downloaded from yfinance.

Charts will not be rendered here (Streamlit will handle them later).
Results and trade logs will be printed to the terminal and saved to log files.
"""

import sys
import os
import datetime
import warnings

import pandas as pd
import numpy as np
import backtrader as bt
from loguru import logger

warnings.filterwarnings("ignore")

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
# 1. CHANGE DATA HERE
DATA_FILE = "Tata_Power_TATAPOWER.csv"

# 2. CHANGE STRATEGY HERE
STRATEGY_FILE = "Test_Strat_1"             # The python module name
STRATEGY_CLASS = "TrendPullbackStrategy"   # The class name inside the module

# ---------------------------------------------------------------------------
# Dynamic Strategy Loader
# ---------------------------------------------------------------------------
import importlib
try:
    strat_module = importlib.import_module(f"Strategies.Strategy_codes.{STRATEGY_FILE}")
    StrategyClass = getattr(strat_module, STRATEGY_CLASS)
except (ImportError, AttributeError) as e:
    logger.error(f"Failed to load strategy {STRATEGY_CLASS} from {STRATEGY_FILE}.py. Error: {e}")
    sys.exit(1)

# Automatically generates the naming convention based on the file name
SYMBOL = DATA_FILE.split(".")[0]

CSV_PATH = os.path.join(
    PROJECT_ROOT,
    "Data",
    "testing_data",
    "Data_files",
    "yfinance_data",
    DATA_FILE,
)
LOG_DIR = os.path.join(PROJECT_ROOT, "Data", "Logs", "Backtesting_result_log")
STARTING_CASH = 100_000.0  # ₹1 Lakh
COMMISSION = 0.0002  # 0.02% per trade (standard equity delivery/intraday hybrid)

os.makedirs(LOG_DIR, exist_ok=True)

# ---------------------------------------------------------------------------
# Loguru setup (Sequential Naming)
# ---------------------------------------------------------------------------
def get_next_run_id(directory, symbol):
    import glob
    existing = glob.glob(os.path.join(directory, f"{symbol}_result_*.csv"))
    max_id = 0
    for f in existing:
        try:
            name = os.path.basename(f)
            num_str = name.split("_result_")[1].split(".")[0]
            max_id = max(max_id, int(num_str))
        except Exception:
            pass
    return max_id + 1

run_id = get_next_run_id(LOG_DIR, SYMBOL)
log_file = os.path.join(LOG_DIR, f"{SYMBOL}_log_{run_id}.log")

logger.remove()
logger.add(
    sys.stderr,
    level="INFO",
    format="<green>{time:HH:mm:ss}</green> | <level>{level}</level> | {message}",
)
logger.add(
    log_file,
    level="DEBUG",
    rotation="10 MB",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}",
)


# ---------------------------------------------------------------------------
# Trade Logger Analyzer
# ---------------------------------------------------------------------------
class TradeLogger(bt.Analyzer):
    """Collects closed trade details for post-processing and Streamlit display."""

    def start(self):
        self.trades = []
        self._open_dirs = {}
        self._open_qty = {}

    def notify_trade(self, trade):
        if trade.justopened:
            self._open_dirs[trade.ref] = "BUY" if trade.size > 0 else "SELL"
            self._open_qty[trade.ref] = abs(trade.size)

        if not trade.isclosed:
            return

        direction = self._open_dirs.pop(trade.ref, "BUY")
        qty = self._open_qty.pop(trade.ref, 1)
        entry_px = trade.price
        exit_px = trade.pnl / qty + entry_px if qty > 0 else entry_px

        self.trades.append(
            {
                "Entry Date": bt.num2date(trade.dtopen).strftime("%Y-%m-%d"),
                "Close Date": bt.num2date(trade.dtclose).strftime("%Y-%m-%d"),
                "Symbol": SYMBOL,
                "Direction": direction,
                "Qty": qty,
                "Entry Price": round(entry_px, 2),
                "Exit Price": round(exit_px, 2),
                "Gross P&L": round(trade.pnl, 2),
                "Net P&L": round(trade.pnlcomm, 2),
            }
        )

    def get_analysis(self):
        return self.trades


# ---------------------------------------------------------------------------
# Main Execution
# ---------------------------------------------------------------------------
def run_backtest():
    logger.info(f"=== Starting Backtest for {SYMBOL} ===")
    logger.info(f"Loading data from: {CSV_PATH}")

    if not os.path.exists(CSV_PATH):
        logger.error(f"File not found: {CSV_PATH}")
        logger.error("Please run adani_power_data.py first to download the data.")
        sys.exit(1)

    # 1. Load Data
    df = pd.read_csv(CSV_PATH, parse_dates=["Date"], index_col="Date")
    # Backtrader requires standard OHLCV names
    df = df[["Open", "High", "Low", "Close", "Volume"]]
    
    # 2. Setup Cerebro
    cerebro = bt.Cerebro(stdstats=False)
    
    # Add data feed
    data_feed = bt.feeds.PandasData(dataname=df)
    cerebro.adddata(data_feed)

    # Add Strategy
    cerebro.addstrategy(StrategyClass)
    
    # Setup Broker
    cerebro.broker.setcash(STARTING_CASH)
    cerebro.broker.setcommission(commission=COMMISSION)

    # Add Analyzers
    cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name="sharpe", riskfreerate=0.0)
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name="drawdown")
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name="trades")
    cerebro.addanalyzer(TradeLogger, _name="tradelog")

    logger.info(f"Starting Portfolio Value: ₹{cerebro.broker.getvalue():,.2f}")

    # 3. Run
    results = cerebro.run()
    strat = results[0]
    
    # 4. Extract Results
    final_val = cerebro.broker.getvalue()
    net_pnl = final_val - STARTING_CASH

    ta = strat.analyzers.trades.get_analysis()
    total_trades = ta.get("total", {}).get("total", 0)
    won = ta.get("won", {}).get("total", 0)
    lost = ta.get("lost", {}).get("total", 0)
    
    dd = strat.analyzers.drawdown.get_analysis()
    max_dd = dd.get("max", {}).get("drawdown", 0.0)
    
    sharpe = strat.analyzers.sharpe.get_analysis().get("sharperatio") or 0.0
    
    trade_list = strat.analyzers.tradelog.get_analysis()
    win_pct = (won / total_trades * 100) if total_trades > 0 else 0.0

    # 5. Log Summary
    logger.info("=" * 60)
    logger.info(f"BACKTEST RESULTS — {STRATEGY_CLASS}")
    logger.info("=" * 60)
    logger.info(f"Starting Cash     : ₹{STARTING_CASH:,.2f}")
    logger.info(f"Final Value       : ₹{final_val:,.2f}")
    logger.info(f"Net P&L           : ₹{net_pnl:,.2f} ({net_pnl/STARTING_CASH*100:.2f}%)")
    logger.info(f"Max Drawdown      : {max_dd:.2f}%")
    logger.info(f"Sharpe Ratio      : {sharpe:.4f}")
    logger.info(f"Total Trades      : {total_trades}")
    logger.info(f"Won / Lost        : {won} / {lost}")
    logger.info(f"Win Rate          : {win_pct:.2f}%")
    logger.info("=" * 60)

    # 6. Save Trade Log to CSV for Streamlit later
    if trade_list:
        trades_df = pd.DataFrame(trade_list)
        trades_csv = os.path.join(LOG_DIR, f"{SYMBOL}_result_{run_id}.csv")
        trades_df.to_csv(trades_csv, index=False)
        logger.info(f"Saved {len(trade_list)} trades to: {trades_csv}")
    else:
        logger.warning("No trades were executed during this period.")

    logger.info("Backtest Complete.")


if __name__ == "__main__":
    run_backtest()