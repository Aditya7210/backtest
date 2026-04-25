# 🏗️ Algo Trading System — Architecture & Specifications

This document outlines the high-level architecture, technology stack, and engineering design of the Algorithmic Trading System.

---

## 1. High-Level Architecture

The system is built as a highly modular, decoupled environment encapsulated entirely within a **Docker Container** (`algo_trading_app`). The architecture separates the heavy calculation (Strategy & Execution) from the visualization (Dashboard), bridging them via standardized CSV and Log files.

### Core Modules:

1. **Execution Engine (`Backtesting/execution_engine.py`)**
   - The master script responsible for orchestrating backtests.
   - Dynamically loads a selected Strategy script (from `Strategies/Strategy_codes/`) and Data file (from `Data_files/`).
   - Executes the backtest using the Backtrader engine.
   - Outputs unified, standardized Trade Logs (`.csv`) and System Logs (`.log`) into the `/Data/Logs/` directory.

2. **Streamlit UI Dashboard (`Dashboard/dashboard.py`)**
   - An independent visualization layer that constantly listens to the `/Data/Logs/` and `/Data_files/` directory.
   - It reads the CSV results pushed out by the Execution Engine and renders dynamic graphical interfaces without needing to re-run heavy Python backtesting loops.

3. **Data Acquisition Pipeline (`Data/` tree)**
   - Responsible for fetching data using libraries like `yfinance` or `jugaad-data`.
   - Raw datasets are piped into local `.csv` files inside `/Data/testing_data/Data_files/`.

---

## 2. Technology Stack & Library Ecosystem

The project relies heavily on the Python data science stack, specifically tailored for time-series evaluation and interactive web rendering.

### Core Trading & Math

- `backtrader`: The backbone execution engine evaluating strategy rules, handling broker simulation, commissions, position sizing, and extracting metrics (Sharpe, Drawdowns).
- `pandas` & `numpy`: Heavy matrix math, data manipulation, and vector calculations.
- `ta-lib`: High-performance technical analysis library mapping out hundreds of indicators (RSI, MACD, etc.).

### Visuals & UI Framework

- `streamlit`: The overarching web framework allowing native python to be rendered as an interactive web-app without needing React/JS knowledge.
- `plotly`: Used for high-fidelity, interactive, sub-plotted Candlestick and Volume charts.

### Streamlit "Phase 2" UI & Polish Components

These libraries map modern web components into the Streamlit dashboard:

- `streamlit-option-menu`: High-quality top horizontal navigation tabs.
- `streamlit_shadcn_ui`: Modern, crisp UI buttons and components.
- `streamlit-elements`, `streamlit-extras`, `hydralit-components`, `streamlit-toggle-switch`: Additional frontend wrappers handling advanced flexbox layouts and seamless data-grid tables.

### Utility

- `loguru`: Handles sophisticated, color-coded, rotating log files instead of using messy native python prints.
- `kiteconnect` / `requests`: Reserved for live-market API execution natively via Zerodha.
- `ruff` & `black`: Next-gen lightning fast python linting and code formatting.

---

## 3. The Dashboard System: Design & Mechanics

### **The "Dynamic Comparator" Philosophy**

The dashboard (`Dashboard/dashboard.py`) is designed as a **Multi-Instance Comparator**. Instead of a rigid, single-page application, it utilizes Streamlit's `st.session_state` to render isolated instances of the system UI.

1. **Instance Spawning Engine:**
   - A variable `st.session_state.dashboard_count` starts at 1.
   - The entire UI is wrapped in a `render_dashboard_instance(instance_id)` function.
   - Users can press a button at the bottom of the dashboard ("➕ Add Another Result Comparator Module") to increment the counter, which naturally spawns a completely independent replica of the dashboard directly below the first one.
   - This allows users to compare **Strategy A** vs **Strategy B** flawlessly on the same screen.

2. **The Control Panel:**
   - Evaluates the `/Data/` directory automatically.
   - Allows users to select their `Price Data`, `Backtest Result Log`, and desired `Overlays`.
   - The indicator selector automatically filters out indicators that are impossible to plot (e.g., if Volume data is missing, the Volume selector acts dynamically).

3. **Intelligent Plotly Visual Engine:**
   - **Sub-Axing Scale Protection:** The charting engine prevents price candles from being "squashed". If an indicator evaluates Price (like Moving Averages), it overlays directly on the Candlestick plot. If the indicator is an Oscillator (like RSI or MACD), the system actively calculates how many oscillators are active and builds proportionate sub-plots beneath the main chart.
   - **Conditional Trade Markers:** When the "Plot Buy/Sell Actions" toggle is activated, the engine parses the loaded trade `.csv` file. It hunts for Entry/Exit timestamps and overlays mathematically accurate triangles (`TV_UP` green / `TV_DOWN` red) on top of the candlestick wicks, allowing the user to visually inspect execution points.

4. **Performance KPIs & Log Feed:**
   - Above the charts, CSS-styled flexbox cards display critical stats: _Win Rate, Total P&L, Trades Executed, Average Yield_.
   - Below the charts, a dynamic Ag-grid style DataFrame renders the full trade-book, color coding the _Gross P&L_ cell row by row.
   - Terminal Execution Blocks render the last 15 lines of the `loguru` output live on the screen, with a button to expand an isolated native modal to review full historic logs without cluttering the screen real-estate.

### Summary

The dashboard perfectly executes read-only evaluations of the engine's outputs, freeing up terminal power while providing incredibly dense, premium graphical feedback comparable to institutional trading platforms like TradingView.
