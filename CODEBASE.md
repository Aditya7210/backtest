# CODEBASE.md

## 1. Project Overview
This repository is a Python-based algorithmic trading workstation centered on a Streamlit UI, Backtrader strategy execution, and dual data modes (local CSV and Zerodha API). It lets users select/edit strategy files, queue runs, execute backtests with retries/timeouts, and inspect charts/trade logs in one interface. The system solves the workflow gap between strategy authoring, data sourcing, and repeatable execution/analysis. Primary users are strategy developers and quantitative traders working on Indian-market instruments (NSE/Zerodha).  
Current status: active prototyping with production-oriented hardening features already present (path safety, retry classification, hard process timeouts, atomic writes, cached market data, task persistence).

## 2. Tech Stack
| Layer | Technology | Version | Purpose |
|---|---|---|---|
| Language | Python | 3.11 (Docker base image) | Main application/runtime code |
| Runtime | CPython | 3.11-slim image | Container runtime |
| UI Framework | Streamlit | Unpinned in `requirements.txt` | Dashboard, editor, backtest control panels |
| UI Components | `streamlit-ace`, `streamlit-option-menu`, `streamlit-shadcn-ui`, `streamlit-elements`, `streamlit-extras`, `streamlit-toggle-switch` | Unpinned | Code editor, nav/menu, UI widgets |
| Backtesting Engine | Backtrader | Unpinned | Strategy simulation and broker model |
| Data Processing | Pandas, NumPy | Unpinned | Data normalization, OHLCV transforms, CSV I/O |
| Market Data APIs | KiteConnect (Zerodha), yfinance, jugaad-data | Unpinned | Historical market data retrieval |
| Charting | Plotly, Matplotlib | Unpinned | Candlestick/indicator rendering, plotting support |
| TA Indicators | TA-Lib (`ta-lib`) | Built from source in Docker | Technical indicators |
| Logging | Loguru + stdlib logging | Unpinned/stdlib | Script and pipeline logs |
| File Watchers | watchdog | Unpinned | Detect strategy/data file changes in UI |
| Config Loading | python-dotenv | Unpinned | `.env` loading/refresh |
| Persistence | JSON + CSV files | N/A | Task store, metrics, trade artifacts, datasets |
| Build/Container | Docker + Docker Compose | Compose v3.9 file format | Reproducible environment and startup orchestration |
| Lint/Format | Ruff, Black | Unpinned | Developer tooling |
| Auth | Zerodha request-token/access-token flow | N/A | Session authentication for Kite API |
| Database | None | N/A | No relational/NoSQL DB used |
| Cache | CSV file cache (`Data/testing_data/Data_files/Zerodha_data`) | N/A | API response caching/fallback |
| Queue | In-memory + persisted JSON queue | N/A | Backtest task scheduling/state |
| Deployment Config | `Dockerfile`, `docker-compose.yml`, `entrypoint.sh` | N/A | Container build/run definition |

## 3. Project Structure
```text
/
├── .git/                                                     # Git metadata directory (excluded from deep enumeration; tool-generated internals)
├── .env                                                      # Runtime secrets/config (Zerodha API key/secret/access token/token date)
├── CODEBASE.md                                               # This generated architecture/context document for developers and LLMs
├── .gitattributes                                            # Line-ending policy for shell/PowerShell scripts
├── .gitignore                                                # Ignore policy for env/data/log/csv/IDE artifacts
├── =                                                         # Empty stray placeholder file [inferred]
├── Changes.md                                                # Session-by-session architectural/behavior change log
├── compose-up.ps1                                            # Windows helper: `docker compose up -d`, health poll, browser open
├── compose-up.sh                                             # Unix helper: compose up, health poll, open URL
├── docker-compose.yml                                        # Single-service compose setup (`algo_trading_app`) with bind mount + port 8501
├── Dockerfile                                                # Python 3.11 image build, TA-Lib compile, dependency install, Streamlit entrypoint wiring
├── Docker_Commands.md                                        # Operator guide for Docker workflows in this repo
├── entrypoint.sh                                             # Container start script: optional instrument refresh then Streamlit launch
├── main.py                                                   # Dependency smoke-test script (imports critical packages)
├── Report.md                                                 # Empty report placeholder
├── requirements.txt                                          # Python dependency manifest (unpinned)
├── skills-lock.json                                          # Skill lock metadata for local tooling
├── system_map.md                                             # Empty system-map placeholder
├── Zerodha_API_Documentation.md                              # Local architecture/process notes and UI behavior rules
├── Backtesting/                                              # Core backtest execution pipeline modules
│   ├── api_based_execution_engine.py                         # API-mode task runner (Zerodha fetch/cache/normalize/execute)
│   ├── backtest_core.py                                      # Shared execution core: runtime config, Backtrader run, analyzers, artifacts
│   ├── data_normalizer.py                                    # Canonical OHLCV normalization/timezone/market-hour filtering
│   ├── execution_engine.py                                   # CSV-mode execution engine + routing facade (`ExecutionEngine`)
│   ├── execution_manager.py                                  # Task queue manager with retries, worker threads, subprocess hard timeout
│   ├── performance_tracker.py                                # Thread-safe metrics aggregator persisted to JSON
│   └── __pycache__/                                          # Generated Python bytecode cache folder
│      ├── api_based_execution_engine.cpython-311.pyc        # Bytecode cache for API engine (generated)
│      ├── backtest_core.cpython-311.pyc                     # Bytecode cache for core execution module (generated)
│      ├── data_normalizer.cpython-311.pyc                   # Bytecode cache for normalization module (generated)
│      ├── execution_engine.cpython-311.pyc                  # Bytecode cache for CSV execution engine (generated)
│      ├── execution_manager.cpython-311.pyc                 # Bytecode cache for manager module (generated)
│      └── performance_tracker.cpython-311.pyc               # Bytecode cache for metrics tracker (generated)
├── Dashboard/                                                # Streamlit application package
│   ├── backtesting_page_wireframe.png                        # Static UI wireframe image (581x602)
│   ├── dashboard.py                                          # Streamlit entry file and page router
│   ├── dashboard_section.py                                  # Chart/dashboard rendering, indicator overlays, trade marker alignment
│   ├── navbar.py                                             # Global style constants + top navigation menu
│   ├── Backtesting_page/                                     # Backtest UI section modules
│   │   ├── Backtests_section.py                              # Main backtest UI: data mode, strategy editor, queue, execute, progress
│   │   ├── zerodha_authentication_page.py                    # Zerodha login/token generation UI and token persistence
│   │   ├── __init__.py                                       # Package marker
│   │   ├── Features/                                         # Reusable backtesting feature services
│   │   │   ├── backtest_data_service.py                      # Strategy-safe loading, env/session validation, task builders, cache path helpers
│   │   │   ├── data_selection_feature.py                     # CSV data source scanning/filtering/watchdog-driven cache refresh
│   │   │   ├── instrument_mapper.py                          # Zerodha instrument master sync/search/token resolution
│   │   │   ├── instrument_mapper_updater.py                  # CLI updater wrapper for instrument mapper refresh
│   │   │   ├── name_indicator_saver_versioner.py             # Save/rename/version logic with atomic writes and validation
│   │   │   ├── strategy_editor.py                            # Editor state sync/dirty tracking against selected strategy file
│   │   │   ├── strategy_selection.py                         # Strategy file discovery/watchdog + class extraction
│   │   │   ├── terminal.py                                   # In-memory execution terminal model + Streamlit panel rendering
│   │   │   ├── zerodha_auth.py                               # `.env` parsing + Zerodha token generation/persistence helpers
│   │   │   ├── zerodha_csv_downloader.py                     # Save fetched Zerodha dataframe to normalized filename/path
│   │   │   ├── zerodha_historical_data.py                    # Zerodha historical fetcher with chunking/retries/gap-refetch/coverage checks
│   │   │   ├── __init__.py                                   # Features package marker
│   │   │   └── __pycache__/                                  # Generated feature bytecode caches
│   │   │      ├── backtest_data_service.cpython-311.pyc     # Generated bytecode
│   │   │      ├── data_selection_feature.cpython-311.pyc    # Generated bytecode
│   │   │      ├── instrument_mapper.cpython-311.pyc         # Generated bytecode
│   │   │      ├── instrument_mapper_updater.cpython-311.pyc # Generated bytecode
│   │   │      ├── name_indicator_saver_versioner.cpython-311.pyc # Generated bytecode
│   │   │      ├── strategy_editor.cpython-311.pyc           # Generated bytecode
│   │   │      ├── strategy_selection.cpython-311.pyc        # Generated bytecode
│   │   │      ├── terminal.cpython-311.pyc                  # Generated bytecode
│   │   │      ├── zerodha_auth.cpython-311.pyc              # Generated bytecode
│   │   │      ├── zerodha_csv_downloader.cpython-311.pyc    # Generated bytecode
│   │   │      ├── zerodha_historical_data.cpython-311.pyc   # Generated bytecode
│   │   │      └── __init__.cpython-311.pyc                  # Generated bytecode
│   │   └── __pycache__/                                      # Generated module bytecode cache
│   │      ├── Backtests_section.cpython-311.pyc             # Generated bytecode
│   │      ├── zerodha_authentication_page.cpython-311.pyc   # Generated bytecode
│   │      └── __init__.cpython-311.pyc                       # Generated bytecode
│   ├── dashboard_page/                                       # Dashboard-specific feature package
│   │   └── dashboard_features/
│   │      ├── talib_indicators.py                            # TA-Lib discovery/input prep/safe execution helpers
│   │      └── __pycache__/
│   │         └── talib_indicators.cpython-311.pyc            # Generated bytecode
│   └── __pycache__/                                           # Generated dashboard module bytecode cache
│      ├── dashboard.cpython-311.pyc                           # Generated bytecode
│      ├── dashboard_section.cpython-311.pyc                   # Generated bytecode
│      └── navbar.cpython-311.pyc                              # Generated bytecode
├── Data/                                                     # Runtime data, caches, logs, and sample datasets
│   ├── instrument_mapper_data/
│   │   ├── metadata.json                                     # Instrument mapper update metadata (date + row counts)
│   │   ├── zerodha_instruments_archive.csv                   # Historical/archive instrument dump from Zerodha
│   │   └── zerodha_instruments_latest.csv                    # Latest instrument dump from Zerodha
│   ├── Logs/
│   │   ├── task_store.json                                   # Persisted execution queue/results snapshot
│   │   ├── Backtesting_result_log/                           # Backtest outputs (trade CSVs + logs + execution-error logs)
│   │   │   ├── ADANIPOWER_log_1.log                          # Historical Adani Power backtest run log
│   │   │   ├── ADANIPOWER_log_10.log                         # Historical Adani Power backtest run log
│   │   │   ├── ADANIPOWER_log_11.log                         # Historical Adani Power backtest run log
│   │   │   ├── ADANIPOWER_log_12.log                         # Historical Adani Power backtest run log
│   │   │   ├── ADANIPOWER_log_2.log                          # Historical Adani Power backtest run log
│   │   │   ├── ADANIPOWER_log_3.log                          # Historical Adani Power backtest run log
│   │   │   ├── ADANIPOWER_log_4.log                          # Historical Adani Power backtest run log
│   │   │   ├── ADANIPOWER_log_5.log                          # Historical Adani Power backtest run log
│   │   │   ├── ADANIPOWER_log_6.log                          # Historical Adani Power backtest run log
│   │   │   ├── ADANIPOWER_log_7.log                          # Historical Adani Power backtest run log
│   │   │   ├── ADANIPOWER_log_8.log                          # Historical Adani Power backtest run log
│   │   │   ├── ADANIPOWER_log_9.log                          # Historical Adani Power backtest run log
│   │   │   ├── ADANIPOWER_result_10.csv                      # Trade ledger output for a run
│   │   │   ├── ADANIPOWER_result_11.csv                      # Trade ledger output for a run
│   │   │   ├── ADANIPOWER_result_12.csv                      # Trade ledger output for a run
│   │   │   ├── ADANIPOWER_result_2.csv                       # Trade ledger output for a run
│   │   │   ├── ADANIPOWER_result_3.csv                       # Trade ledger output for a run
│   │   │   ├── ADANIPOWER_result_4.csv                       # Trade ledger output for a run
│   │   │   ├── ADANIPOWER_result_5.csv                       # Trade ledger output for a run
│   │   │   ├── ADANIPOWER_result_6.csv                       # Trade ledger output for a run
│   │   │   ├── ADANIPOWER_result_7.csv                       # Trade ledger output for a run
│   │   │   ├── ADANIPOWER_result_8.csv                       # Trade ledger output for a run
│   │   │   ├── ADANIPOWER_result_9.csv                       # Trade ledger output for a run
│   │   │   ├── NIFTYIETF_execution_20260425_125139_286545.log # Execution summary log for NIFTYIETF run
│   │   │   ├── NIFTYIETF_execution_error_20260425_123236_053753.log # Failure log for NIFTYIETF run
│   │   │   ├── NIFTYIETF_execution_error_20260425_123258_896611.log # Failure log for NIFTYIETF run
│   │   │   ├── NIFTYIETF_execution_error_20260425_123321_762022.log # Failure log for NIFTYIETF run
│   │   │   ├── NIFTYIETF_execution_error_20260425_124957_668750.log # Failure log for NIFTYIETF run
│   │   │   ├── NIFTYIETF_execution_error_20260425_124958_134802.log # Failure log for NIFTYIETF run
│   │   │   ├── NIFTYIETF_execution_error_20260425_124958_723241.log # Failure log for NIFTYIETF run
│   │   │   ├── NIFTYIETF_execution_error_20260425_125138_673378.log # Failure log for NIFTYIETF run
│   │   │   ├── RELIANCE_execution_error_20260425_123606_974367.log # Failure log for RELIANCE run
│   │   │   ├── RELIANCE_execution_error_20260425_123609_047140.log # Failure log for RELIANCE run
│   │   │   ├── RELIANCE_execution_error_20260425_123610_780863.log # Failure log for RELIANCE run
│   │   │   ├── RELIANCE_execution_error_20260425_124030_218503.log # Failure log for RELIANCE run
│   │   │   ├── RELIANCE_execution_error_20260425_124032_022979.log # Failure log for RELIANCE run
│   │   │   ├── RELIANCE_execution_error_20260425_124034_002464.log # Failure log for RELIANCE run
│   │   │   ├── RELIANCE_execution_error_20260425_131356_770176.log # Failure log for RELIANCE run
│   │   │   ├── RELIANCE_log_20260425_131357_616044.log      # Success log for RELIANCE run
│   │   │   ├── RELIANCE_result_20260425_131357_616044.csv   # Trade ledger output for RELIANCE run
│   │   │   ├── TATAPOWER_log_1.log                           # Historical Tata Power backtest run log
│   │   │   └── TATAPOWER_result_1.csv                        # Trade ledger output for Tata Power run
│   │   ├── live_market_trade_log/                            # Reserved live-trading log folder; currently empty
│   │   └── Script_logs/
│   │      └── adani_power_data.log                           # Log file from Yahoo data pull script
│   └── testing_data/
│      ├── Data_files/
│      │   ├── yfinance_data/
│      │   │   ├── ADANIPOWER_daily_since_2022.csv            # Yahoo daily OHLCV for ADANIPOWER
│      │   │   ├── Adani_Enterprises_ADANIENT.csv             # Yahoo max-history OHLCV sample
│      │   │   ├── Adani_Green_Energy_ADANIGREEN.csv          # Yahoo max-history OHLCV sample
│      │   │   ├── Axis_Bank_AXISBANK.csv                     # Yahoo max-history OHLCV sample
│      │   │   ├── Bajaj_Finance_BAJFINANCE.csv               # Yahoo max-history OHLCV sample
│      │   │   ├── Bharat_Electronics_BEL_BEL.csv             # Yahoo max-history OHLCV sample
│      │   │   ├── Deepak_Nitrite_DEEPAKNTR.csv               # Yahoo max-history OHLCV sample
│      │   │   ├── HAL_Hindustan_Aeronautics_HAL.csv          # Yahoo max-history OHLCV sample
│      │   │   ├── HDFC_Bank_HDFCBANK.csv                     # Yahoo max-history OHLCV sample
│      │   │   ├── ICICI_Bank_ICICIBANK.csv                   # Yahoo max-history OHLCV sample
│      │   │   ├── Mazagon_Dock_MAZDOCK.csv                   # Yahoo max-history OHLCV sample
│      │   │   ├── MTAR_Technologies_MTARTECH.csv             # Yahoo max-history OHLCV sample
│      │   │   ├── Reliance_Industries_RELIANCE.csv           # Yahoo max-history OHLCV sample
│      │   │   ├── State_Bank_of_India_SBIN.csv               # Yahoo max-history OHLCV sample
│      │   │   └── Tata_Power_TATAPOWER.csv                   # Yahoo max-history OHLCV sample
│      │   └── Zerodha_data/
│      │      ├── NIFTYIETF_day_2026-01-01_2026-04-25.csv     # Zerodha day-interval cache/export
│      │      ├── NIFTYIETF_day_2026-03-26_2026-04-25.csv     # Zerodha day-interval cache/export
│      │      ├── RELIANCE_day_2025-01-01_2026-04-25.csv      # Zerodha day-interval cache/export
│      │      ├── RELIANCE_minute_2020-03-07_2026-04-24.csv   # Zerodha minute-interval cache/export (large historical)
│      │      ├── RELIANCE_minute_2026-03-25_2026-04-24.csv   # Zerodha minute-interval cache/export
│      │      └── RELIANCE_minute_2026-03-26_2026-04-25.csv   # Zerodha minute-interval cache/export
│      └── data_pull_scripts/
│         ├── adani_power_data.py                             # Script to download/normalize ADANIPOWER Yahoo daily data since 2022
│         └── download_16_stocks.py                           # Batch downloader for 16 predefined Yahoo/NSE tickers
├── Guide/                                                    # Reference notes for libraries/usage
│   ├── readme.md                                             # Guide folder description
│   ├── BackTrader/
│   │   └── backtrader_guide.md                               # Backtrader quick reference/tutorial content
│   └── Zerodha/
│      └── zerodha_kite_guide.md                              # Empty Zerodha guide placeholder
├── Indicators/                                               # Placeholder for custom indicator modules (currently empty)
└── Strategies/
   ├── Strategy_codes/
   │   ├── Renamed_Check_2.py                                 # Minimal test/debug script (`print(2)`)
   │   ├── strategy_versioning/
   │   │   ├── Test_Strat_2_v1.py                             # Backtrader `TrendPullbackStrategy` implementation
   │   │   └── __pycache__/
   │   │      └── Test_Strat_2_v1.cpython-311.pyc             # Generated strategy bytecode
   │   └── __pycache__/
   │      ├── Renamed_Check_2.cpython-311.pyc                 # Generated strategy bytecode
   │      ├── Test_Strat_1.cpython-311.pyc                    # Generated bytecode for strategy not present in source tree [inferred stale artifact]
   │      └── Test_Strat_2.cpython-311.pyc                    # Generated bytecode for strategy not present in source tree [inferred stale artifact]
   └── Strategy_files/
      └── Nifty_1day_strat.md                                 # Narrative strategy specification using options-chain signals
```

## 4. Architecture Overview
- Pattern: modular monolith with layered architecture (UI layer, feature/service layer, execution/orchestration layer, file-based persistence layer).
- Primary style: event-driven UI state machine (Streamlit session state) + asynchronous task orchestration (threaded queue, optional subprocess execution).
- External systems:
  - Zerodha Kite API (`KiteConnect`) for historical data and instrument metadata.
  - Yahoo Finance (`yfinance`) for offline CSV dataset pulls.
  - Local filesystem for strategy source, caches, artifacts, task store, and metrics.

```text
+---------------------------+
| Streamlit UI (Dashboard)  |
| dashboard.py              |
+------------+--------------+
             |
             v
+---------------------------+
| Backtesting UI Features   |
| Backtests_section.py      |
| strategy/data services    |
+------------+--------------+
             |
             v
+---------------------------+
| Execution Orchestration   |
| ExecutionManager          |
| (queue/retries/timeouts)  |
+------------+--------------+
             |
   +---------+---------+
   |                   |
   v                   v
+----------------+  +----------------------------+
| CSV Engine      |  | API Engine                |
| execution_engine|  | api_based_execution_engine|
+--------+-------+  +-------------+--------------+
         |                        |
         v                        v
+-----------------------------+   +-----------------------+
| data_normalizer +           |   | ZerodhaHistoricalData |
| backtest_core (Backtrader)  |   | + instrument mapper   |
+-------------+---------------+   +-----------+-----------+
              |                               |
              v                               v
    Data/Logs + Data/testing_data      Zerodha API / instrument API
```

## 5. Module / Component Breakdown

### `main.py`
- **Purpose**: quick runtime dependency smoke test.
- **Responsibilities**: imports critical libraries, prints installed/missing package names.
- **Key exports**: none (script style).
- **Internal dependencies**: none.
- **External dependencies**: `importlib`, `backtrader`, `pandas`, `numpy`, `loguru`, `jugaad_data`.
- **Side effects**: stdout printing.
- **Configuration**: none.

### `Backtesting/backtest_core.py`
- **Purpose**: central backtest execution primitive shared by CSV/API modes.
- **Responsibilities**:
  - runtime config validation (`initial_capital`, `commission`, market-hour enforcement),
  - result object creation/normalization,
  - Backtrader run lifecycle,
  - strategy sell-guard wrapper for long/short semantics,
  - analyzers for trade events and closed-trade rows,
  - artifact writing (result CSV + log file).
- **Key exports**: `execute_backtest_dataframe`, `extract_runtime_config`, `validate_strategy_class`, `validate_result`, `build_failed_result`, `build_success_result`.
- **Internal dependencies**: none direct; consumed by `execution_engine.py`, `api_based_execution_engine.py`, `execution_manager.py`.
- **External dependencies**: `backtrader`, `pandas`.
- **Side effects**: writes to `Data/Logs/Backtesting_result_log/*`, terminal logging via provided terminal object.
- **Configuration**: `initial_capital`, `commission`, `enforce_market_hours` (task/config dict).

### `Backtesting/data_normalizer.py`
- **Purpose**: normalize arbitrary OHLCV tabular data into execution-safe format.
- **Responsibilities**: column renaming, datetime index normalization (IST), numeric coercion, NaN/dedup handling, optional market-hours filter.
- **Key exports**: `normalize`, `prepare_ohlcv_for_plot`, `should_normalize`.
- **Internal dependencies**: used by `execution_engine.py`, `api_based_execution_engine.py`, `dashboard_section.py`.
- **External dependencies**: `pandas`.
- **Side effects**: logging via stdlib logger.
- **Configuration**: `enforce_market_hours` function argument.

### `Backtesting/execution_engine.py`
- **Purpose**: CSV task executor and mode router wrapper.
- **Responsibilities**: CSV path validation/sandboxing, CSV size guard, parse/validation/normalization, invocation of `backtest_core`.
- **Key exports**: `run_csv_task`, `run_task`, `ExecutionEngine`.
- **Internal dependencies**: `Backtesting.api_based_execution_engine`, `Backtesting.backtest_core`, `Backtesting.data_normalizer`.
- **External dependencies**: `pandas`.
- **Side effects**: reads CSV files, forwards logs to terminal sink.
- **Configuration**: `MAX_CSV_SIZE_MB`, `task.mode`, runtime config keys.

### `Backtesting/api_based_execution_engine.py`
- **Purpose**: API task executor for Zerodha-sourced datasets.
- **Responsibilities**:
  - validate API task payload,
  - cache lookup/validation/merge/refetch fallback,
  - Zerodha session validation and fetch orchestration,
  - normalization and handoff to `backtest_core`,
  - failure classification (`API_ERROR`, `DATA_ERROR`, etc.).
- **Key exports**: `run_task`, `run_api_task`.
- **Internal dependencies**: `Backtesting.backtest_core`, `Backtesting.data_normalizer`, `Dashboard.Backtesting_page.Features.backtest_data_service`, `zerodha_historical_data`.
- **External dependencies**: `pandas`.
- **Side effects**: reads/writes cache CSVs under `Data/testing_data/Data_files/Zerodha_data`, logs to terminal.
- **Configuration**: task fields (`instrument_token`, `interval`, `start_date`, `end_date`, `continuous`, `oi`, `enforce_market_hours`).

### `Backtesting/execution_manager.py`
- **Purpose**: queue-based orchestration across backtest tasks.
- **Responsibilities**:
  - queue lifecycle (`PENDING`/`RUNNING`/`SUCCESS`/`FAILED`),
  - worker thread management,
  - retry policy by error type,
  - hard timeout via subprocess isolation,
  - persistence to `task_store.json`,
  - metrics handoff to `PerformanceTracker`.
- **Key exports**: `ExecutionManager`.
- **Internal dependencies**: `Backtesting.execution_engine`, `Backtesting.backtest_core`, `Backtesting.performance_tracker`, `Dashboard...backtest_data_service` (for strategy hydration).
- **External dependencies**: stdlib `threading`, `multiprocessing`, `json`, etc.
- **Side effects**: updates persisted task store JSON, spawns subprocesses, terminal logging.
- **Configuration**: `max_retries`, `task_timeout_seconds`/`timeout_seconds`, `worker_count`, base runtime config.

### `Backtesting/performance_tracker.py`
- **Purpose**: thread-safe task metrics registry.
- **Responsibilities**: track per-task metrics, aggregate success/failure/rate/median, atomic JSON persistence.
- **Key exports**: `PerformanceTracker`.
- **Internal dependencies**: consumed by `ExecutionManager`.
- **External dependencies**: stdlib only.
- **Side effects**: writes metrics JSON file.
- **Configuration**: `metrics_path` (optional override).

### `Dashboard/dashboard.py`
- **Purpose**: Streamlit app entry and top-level router.
- **Responsibilities**: page config, navbar render, route to auth/dashboard/backtests views.
- **Key exports**: none (script-style entry).
- **Internal dependencies**: `navbar`, `Backtesting_page.zerodha_authentication_page`, `dashboard_section`, `Backtesting_page.Backtests_section`.
- **External dependencies**: `streamlit`.
- **Side effects**: UI rendering.
- **Configuration**: none directly (reads session state downstream).

### `Dashboard/navbar.py`
- **Purpose**: nav bar and shared visual constants.
- **Responsibilities**: inject CSS, render option-menu tab bar.
- **Key exports**: `render_navbar`, color constants (`TV_UP`, `TV_DOWN`, `PRIMARY_BLUE`, `BORDER_COLOR`, `BG_COLOR`).
- **Internal dependencies**: used by `dashboard.py`, `dashboard_section.py`.
- **External dependencies**: `streamlit`, `streamlit_option_menu`.
- **Side effects**: UI CSS injection.
- **Configuration**: none.

### `Dashboard/dashboard_section.py`
- **Purpose**: analytical dashboard for charting price/trade outputs.
- **Responsibilities**:
  - discover CSV/log files,
  - load/normalize price and trade data,
  - align trade timestamps to candle grid,
  - render Plotly chart with TA-Lib indicators and trade markers,
  - show KPI cards and log previews.
- **Key exports**: `render`.
- **Internal dependencies**: `Backtesting.data_normalizer`, `navbar` constants, `dashboard_page.dashboard_features.talib_indicators`.
- **External dependencies**: `streamlit`, `plotly`, `pandas`, `streamlit_shadcn_ui`.
- **Side effects**: reads files from `Data/testing_data/Data_files` and `Data/Logs/Backtesting_result_log`.
- **Configuration**: implicit via discovered files and user-selected UI filters.

### `Dashboard/dashboard_page/dashboard_features/talib_indicators.py`
- **Purpose**: TA-Lib abstraction utilities for indicator discovery/execution.
- **Responsibilities**: list loadable indicators by available OHLCV inputs, split overlays vs oscillators, execute safely.
- **Key exports**: `get_loadable_indicators`, `split_indicators`, `build_talib_inputs`, `run_indicator`.
- **Internal dependencies**: used by `dashboard_section.py`.
- **External dependencies**: `talib`, `pandas`.
- **Side effects**: none.
- **Configuration**: none.

### `Dashboard/Backtesting_page/Backtests_section.py`
- **Purpose**: primary UI workflow for data selection, strategy editing, and execution control.
- **Responsibilities**:
  - initialize/maintain Streamlit state contract,
  - support CSV vs Zerodha mode,
  - instrument search and queue management,
  - strategy selection/class selection/editor integration,
  - save/version/create strategy flows,
  - execution trigger + progress + results + terminal panel.
- **Key exports**: `render`.
- **Internal dependencies**: all modules under `Dashboard/Backtesting_page/Features`, plus `Backtesting.execution_manager` (runtime import).
- **External dependencies**: `streamlit`, `streamlit_ace`, `backtrader` (for template class import section).
- **Side effects**: session state mutation, queue/task start/stop, file creation for new strategies.
- **Configuration**: many UI-bound keys (`bt_initial_capital`, `bt_commission`, `bt_max_retries`, `bt_task_timeout_seconds`, mode toggles, selections).

### `Dashboard/Backtesting_page/zerodha_authentication_page.py`
- **Purpose**: UI for Zerodha auth handshake and access token persistence.
- **Responsibilities**: load credentials, generate login URL, capture request token, exchange for access token, store token to `.env`.
- **Key exports**: `render`.
- **Internal dependencies**: `Features.zerodha_auth`.
- **External dependencies**: `streamlit`.
- **Side effects**: writes `.env`, mutates query params/session state.
- **Configuration**: `.env` values and returned query param `request_token`.

### `Dashboard/Backtesting_page/Features/backtest_data_service.py`
- **Purpose**: shared service layer for path resolution, session validation, task construction, and safe strategy loading.
- **Responsibilities**:
  - resolve project/env/strategy/cache paths,
  - enforce strategy path sandbox and AST safety checks,
  - load Zerodha credentials/session metadata,
  - construct queue tasks for CSV/API modes,
  - ensure instrument mapper bootstrap availability.
- **Key exports**: `load_strategy_class`, `build_csv_tasks`, `build_zerodha_queue_tasks`, `create_queue_item`, `validate_zerodha_session`, and path helpers.
- **Internal dependencies**: `zerodha_auth`, `instrument_mapper` (dynamic import).
- **External dependencies**: `pandas`, stdlib AST/import utilities.
- **Side effects**: reads `.env`, may update instrument mapper CSVs when bootstrapping.
- **Configuration**: env vars `ZERODHA_API_KEY`, `ZERODHA_ACCESS_TOKEN`, `ZERODHA_TOKEN_DATE`.

### `Dashboard/Backtesting_page/Features/data_selection_feature.py`
- **Purpose**: CSV data source indexing/filtering with optional filesystem watch refresh.
- **Responsibilities**: cache source/file metadata, sanitize selected file IDs, refresh cache on watchdog events.
- **Key exports**: `initialize_data_layer`, `refresh_if_needed`, `get_data_sources`, `get_data_files`, `filter_data_files`, `validate_selection`.
- **Internal dependencies**: consumed by `Backtests_section.py`.
- **External dependencies**: `streamlit`, optional `watchdog`.
- **Side effects**: background observer thread (if watchdog available).
- **Configuration**: fixed source mapping for `yfinance_data` and `Zerodha_data`.

### `Dashboard/Backtesting_page/Features/instrument_mapper.py`
- **Purpose**: local searchable index of Zerodha instruments.
- **Responsibilities**: fetch instruments from API, persist latest/archive datasets, metadata updates, token lookup by symbol/exchange/segment.
- **Key exports**: `InstrumentMapper` class.
- **Internal dependencies**: used by `Backtests_section.py`, `instrument_mapper_updater.py`, and service bootstrap.
- **External dependencies**: `kiteconnect`, `pandas`.
- **Side effects**: writes `Data/instrument_mapper_data/*.csv` and `metadata.json`, calls Zerodha API.
- **Configuration**: API key/access token constructor args.

### `Dashboard/Backtesting_page/Features/instrument_mapper_updater.py`
- **Purpose**: startup/CLI wrapper to refresh instrument map if creds are present.
- **Responsibilities**: read env vars, run mapper update, print status.
- **Key exports**: `main`.
- **Internal dependencies**: `instrument_mapper.InstrumentMapper`.
- **External dependencies**: stdlib only.
- **Side effects**: updates instrument CSV files.
- **Configuration**: `ZERODHA_API_KEY`, `ZERODHA_ACCESS_TOKEN`.

### `Dashboard/Backtesting_page/Features/name_indicator_saver_versioner.py`
- **Purpose**: strategy file naming/validation/save/version control service.
- **Responsibilities**: validate names, rename strategy files safely, create versioned copies, atomic writes, synchronize save indicator state.
- **Key exports**: `save_strategy`, `validate_strategy_name`, `clean_strategy_name`, `create_version_file`, `rename_strategy_file`, `get_indicator_color`, state init/sync helpers.
- **Internal dependencies**: `strategy_editor`, `strategy_selection`.
- **External dependencies**: `streamlit`, stdlib `tempfile`, `re`.
- **Side effects**: filesystem writes/renames in `Strategies/Strategy_codes`, session-state updates.
- **Configuration**: max name length constant, session flags.

### `Dashboard/Backtesting_page/Features/strategy_editor.py`
- **Purpose**: editor/session synchronization abstraction.
- **Responsibilities**: initialize editor state, load selected file content, clear editor for invalid selection, update dirty flag on edits.
- **Key exports**: internal-style functions used by `Backtests_section.py` and saver module.
- **Internal dependencies**: `strategy_selection`.
- **External dependencies**: `streamlit`.
- **Side effects**: reads strategy file content, mutates session state.
- **Configuration**: session keys (`current_strategy_file`, `editor_content`, `saved_content`, etc.).

### `Dashboard/Backtesting_page/Features/strategy_selection.py`
- **Purpose**: strategy file index/class discovery with optional watchdog invalidation.
- **Responsibilities**: scan strategy directory, classify versioned/base files, parse module classes inheriting `bt.Strategy`.
- **Key exports**: `initialize_strategy_layer`, `refresh_if_needed`, `get_strategy_files`, `filter_strategy_files`, `get_strategy_classes`.
- **Internal dependencies**: consumed by backtests UI and saver/editor modules.
- **External dependencies**: `streamlit`, optional `watchdog`, optional `backtrader`.
- **Side effects**: background observer thread, dynamic import execution of strategy files.
- **Configuration**: strategy root constants and session keys.

### `Dashboard/Backtesting_page/Features/terminal.py`
- **Purpose**: in-memory terminal log model + UI panel.
- **Responsibilities**: store structured logs, filter by symbol/level, render HTML/text terminal views, auto-refresh while execution active.
- **Key exports**: `ExecutionTerminal`, `render_terminal`, `render_terminal_panel`.
- **Internal dependencies**: used by `Backtests_section.py`, `ExecutionManager`/engines log into terminal interface.
- **External dependencies**: `streamlit` (runtime import inside render functions).
- **Side effects**: UI reruns for auto-refresh.
- **Configuration**: refresh throttle and max line count.

### `Dashboard/Backtesting_page/Features/zerodha_auth.py`
- **Purpose**: Zerodha auth utility functions around `.env`.
- **Responsibilities**: parse env file, generate login URL, exchange request token, persist access token and token date.
- **Key exports**: `load_env_variables`, `get_login_url`, `generate_access_token`, `save_access_token_to_env`, `is_token_expired`.
- **Internal dependencies**: used by auth page and service module.
- **External dependencies**: `kiteconnect`.
- **Side effects**: writes `.env`.
- **Configuration**: `.env` keys `ZERODHA_API_KEY`, `ZERODHA_API_SECRET`, `ZERODHA_ACCESS_TOKEN`, `ZERODHA_TOKEN_DATE`.

### `Dashboard/Backtesting_page/Features/zerodha_csv_downloader.py`
- **Purpose**: consistent exporter for Zerodha dataframe snapshots.
- **Responsibilities**: validate args/dataframe/index and save to deterministic filename in Zerodha data folder.
- **Key exports**: `download_and_save_data`.
- **Internal dependencies**: none currently wired directly in UI flow [inferred helper].
- **External dependencies**: `pandas`.
- **Side effects**: writes CSV files.
- **Configuration**: output root path constant.

### `Dashboard/Backtesting_page/Features/zerodha_historical_data.py`
- **Purpose**: robust Zerodha historical API adapter.
- **Responsibilities**:
  - dynamic env reload for fresh tokens,
  - chunked fetch by interval limits,
  - retry/backoff and auth diagnostics,
  - timezone/market-hours normalization,
  - missing-candle detection and gap-refetch passes,
  - coverage/integrity checks.
- **Key exports**: `ZerodhaHistoricalData` class (including `interval_to_timedelta` utility).
- **Internal dependencies**: used by API execution engine.
- **External dependencies**: `kiteconnect`, `python-dotenv`, `pandas`.
- **Side effects**: Zerodha API calls, console logging.
- **Configuration**: env vars (`ZERODHA_API_KEY`, `ZERODHA_ACCESS_TOKEN`, fallback `api_key`, `access_token`), class-level retry/chunk constants.

### `Data/testing_data/data_pull_scripts/adani_power_data.py`
- **Purpose**: one-off Yahoo pull script for ADANIPOWER daily data since 2022.
- **Responsibilities**: fetch, normalize columns/index, write CSV, write script log.
- **Key exports**: none (script).
- **Internal dependencies**: none.
- **External dependencies**: `yfinance`, `pandas`, `loguru`.
- **Side effects**: writes CSV and log file.
- **Configuration**: hard-coded ticker/date/output paths.

### `Data/testing_data/data_pull_scripts/download_16_stocks.py`
- **Purpose**: bulk Yahoo downloader for 16 predefined Indian symbols.
- **Responsibilities**: fetch max history per symbol, flatten columns, save CSV files.
- **Key exports**: `download_historical_data`.
- **Internal dependencies**: none.
- **External dependencies**: `yfinance`, `pandas`.
- **Side effects**: writes many CSV files to local directory.
- **Configuration**: static stock ticker map.

### `Strategies/Strategy_codes/strategy_versioning/Test_Strat_2_v1.py`
- **Purpose**: concrete sample strategy used by backtests (`TrendPullbackStrategy`).
- **Responsibilities**: trend/pullback entries, RSI/ATR filters, risk-based position sizing, TP/SL/RSI exits, optional short selling and trailing SL.
- **Key exports**: `TrendPullbackStrategy`.
- **Internal dependencies**: consumed dynamically by strategy loader.
- **External dependencies**: `backtrader`.
- **Side effects**: print logging.
- **Configuration**: Backtrader `params` dictionary.

### `Strategies/Strategy_codes/Renamed_Check_2.py`
- **Purpose**: minimal debug/test strategy file placeholder.
- **Responsibilities**: prints `2`.
- **Key exports**: none.
- **Internal dependencies**: none.
- **External dependencies**: none.
- **Side effects**: stdout.
- **Configuration**: none.

### `Dashboard/Backtesting_page/__init__.py`, `Dashboard/Backtesting_page/Features/__init__.py`
- **Purpose**: package markers.
- **Responsibilities**: package initialization metadata only.
- **Key exports**: none meaningful.
- **Internal dependencies**: N/A.
- **External dependencies**: N/A.
- **Side effects**: none.
- **Configuration**: none.

### Non-module but operational files
- `entrypoint.sh`: startup control (instrument update gate + Streamlit run).
- `docker-compose.yml`, `Dockerfile`, `compose-up.*`: build/run/deploy ergonomics.
- `requirements.txt`: dependency source of truth.
- `Data/*` CSV/log/JSON artifacts: runtime data plane and execution evidence.
- `__pycache__/*.pyc`: generated bytecode artifacts; not source of truth.

## 6. Connection Map

### UI Layer -> Feature Services
- `Dashboard/dashboard.py` → `Dashboard/navbar.py` (navigation)
- `Dashboard/dashboard.py` → `Dashboard/dashboard_section.py` (dashboard rendering)
- `Dashboard/dashboard.py` → `Dashboard/Backtesting_page/zerodha_authentication_page.py` (auth page)
- `Dashboard/dashboard.py` → `Dashboard/Backtesting_page/Backtests_section.py` (backtest workflow page)
- `Dashboard/Backtesting_page/Backtests_section.py` → `Features/*` modules (data, strategy, terminal, auth, save/version services)

### Feature Services -> Execution Layer
- `Backtests_section.py` → `Backtesting.execution_manager.ExecutionManager` (queue orchestration)
- `Backtests_section.py` → `backtest_data_service.load_strategy_class` (safe dynamic strategy import)
- `backtest_data_service.py` → `instrument_mapper.py` (bootstrap mapper update/search)

### Execution Layer Internal
- `execution_manager.py` → `execution_engine.py` (task dispatch)
- `execution_manager.py` → `performance_tracker.py` (metrics)
- `execution_manager.py` → `backtest_core.py` (result validation/failure scaffolding)
- `execution_engine.py` → `data_normalizer.py` (CSV normalization)
- `execution_engine.py` → `backtest_core.py` (actual backtest run)
- `execution_engine.py` → `api_based_execution_engine.py` (API mode route)
- `api_based_execution_engine.py` → `zerodha_historical_data.py` (API fetch)
- `api_based_execution_engine.py` → `backtest_data_service.py` (session validation, cache dir helper)
- `api_based_execution_engine.py` → `backtest_core.py` (backtest run)

### Dashboard Analytics Layer
- `dashboard_section.py` → `Backtesting/data_normalizer.py` (plot-ready OHLC normalization)
- `dashboard_section.py` → `talib_indicators.py` (indicator metadata/execution)

### Logical Layer Grouping
- Presentation: `dashboard.py`, `navbar.py`, `dashboard_section.py`, `Backtests_section.py`, `zerodha_authentication_page.py`, `terminal.py`.
- Application services: `backtest_data_service.py`, `strategy_selection.py`, `strategy_editor.py`, `name_indicator_saver_versioner.py`, `data_selection_feature.py`, `instrument_mapper.py`, `zerodha_auth.py`.
- Domain/execution: `execution_manager.py`, `execution_engine.py`, `api_based_execution_engine.py`, `backtest_core.py`, `data_normalizer.py`, `performance_tracker.py`.
- Infrastructure/data: `entrypoint.sh`, docker files, `Data/*` artifacts.

## 7. Data Flow

### Flow A: Execute Backtest From Local CSV
1. `Dashboard/dashboard.py` routes to `Backtests_section.render()`.
2. `Backtests_section.py` loads CSV selections via `data_selection_feature`.
3. Strategy file/class chosen via `strategy_selection`; class loaded by `backtest_data_service.load_strategy_class`.
4. `Backtests_section.py` builds CSV tasks (`mode=csv`) and starts `ExecutionManager`.
5. `ExecutionManager` dequeues task, optionally retries/isolates timeout in subprocess.
6. `execution_engine.run_csv_task()` resolves and validates CSV path/size/readability.
7. `data_normalizer.normalize()` standardizes OHLCV+datetime to IST.
8. `backtest_core.execute_backtest_dataframe()` runs Backtrader, collects analyzers, writes result/log artifacts.
9. `ExecutionManager` updates task status/store/metrics and pushes logs to `ExecutionTerminal`.
10. UI polls queue state and renders progress/results/terminal.

### Flow B: Execute Backtest Using Zerodha API
1. User authenticates token in `zerodha_authentication_page.py` (token persisted to `.env`).
2. In `Backtests_section.py` (Zerodha mode), user searches symbol; `InstrumentMapper` resolves instrument.
3. Queue item built by `backtest_data_service.create_queue_item`, later transformed into `mode=api` tasks.
4. `ExecutionManager` dispatches to `api_based_execution_engine.run_task()`.
5. API engine validates payload and cache state; reads cached CSV if valid.
6. If cache insufficient, `backtest_data_service.validate_zerodha_session()` verifies token date and credentials.
7. `ZerodhaHistoricalData.fetch_data()` chunks requests, retries failures, fills gaps, normalizes timestamps/hours.
8. API dataframe normalized/sanitized then executed via `backtest_core.execute_backtest_dataframe`.
9. Result/log artifacts written; queue/result/metrics persisted.

### Flow C: Strategy Save / Rename / Version
1. Editor changes tracked in `strategy_editor._on_editor_change()`.
2. Save action triggers `name_indicator_saver_versioner.save_strategy()`.
3. Name validation and potential rename are performed safely within strategy root.
4. If versioning enabled, a new `strategy_versioning/<name>_vN.py` file is atomically written.
5. Strategy cache dirty flag set; selection/editor state re-synced.

### Flow D: Dashboard Visualization
1. `dashboard_section.render()` discovers price/trade CSV files from data/log folders.
2. Price CSV normalized via `data_normalizer.prepare_ohlcv_for_plot`.
3. Trade timestamps aligned to nearest candle indices.
4. TA-Lib indicator functions selected and executed.
5. Plotly renders candles, indicators, volumes, and trade markers; log snippets and KPI stats shown.

## 8. State & Data Model

### Persistent Data Models
- `Data/Logs/task_store.json`:
  - `task_counter`, `queue[]`, `completed_tasks[]`, `failed_tasks[]`, `results_by_task_id`.
  - Queue item schema: `task_id`, `task`, `status`, `result`, `created_at/start_time/end_time`, `execution_time`, `retries`.
- `Data/Logs/execution_metrics.json` [inferred path from code]:
  - aggregate metrics + `tasks` map with status/timeouts/errors.
- Backtest result CSV schema (`*_result_*.csv`):
  - `Entry Date`, `Close Date`, `Symbol`, `Direction`, `Qty`, `Entry Price`, `Exit Price`, `Gross P&L`, `Net P&L`.
- Strategy source files:
  - Backtrader classes loaded dynamically with safety checks.
- Instrument mapper CSV schema:
  - `instrument_token`, `tradingsymbol`, `name`, `exchange`, `segment`, `expiry`, `strike`, `instrument_type`, `lot_size`.

### Runtime State Locations
- Streamlit session state:
  - selection state (`selected_data_files`, `selected_strategy_file`, `selected_strategy_class`, etc.),
  - execution state (`execution_running`, `execution_status`, `progress`, `results`),
  - editor lifecycle (`editor_content`, `saved_content`, `is_dirty`, `versioning_enabled`),
  - terminal object (`ExecutionTerminal`).
- In-memory queue:
  - `ExecutionManager._queue` and worker threads.
- Filesystem cache:
  - Zerodha cached CSV ranges in `Data/testing_data/Data_files/Zerodha_data`.

### Relationships
- Strategy class + dataset -> task -> execution result -> result CSV/log artifacts.
- Queue item status transitions tracked both in-memory and persisted JSON.
- Dashboard references persisted result artifacts, not in-memory engine internals.

## 9. API Surface (if applicable)
No HTTP API endpoints exist in this repo. Exposed interfaces are internal Python and Streamlit actions.

| Method | Path | Handler | What it does | Auth required |
|---|---|---|---|---|
| UI Action | `/` (Streamlit app root) | `Dashboard/dashboard.py` | Routes among Authentication, Dashboard, Backtests pages | Zerodha auth required only for API mode |
| Function | N/A | `Backtesting.execution_engine.run_csv_task` | Execute one CSV backtest task | No |
| Function | N/A | `Backtesting.api_based_execution_engine.run_task` | Execute one API-backed backtest task | Yes (Zerodha token/session) |
| Class Method | N/A | `ExecutionManager.add_task/start_worker/get_queue_snapshot` | Queue and process tasks asynchronously | Depends on task mode |
| Function | N/A | `backtest_data_service.load_strategy_class` | Safely load selected strategy class from file | No |
| Function | N/A | `zerodha_auth.generate_access_token` | Exchange request token for access token | Yes (API key/secret + request token) |

## 10. Configuration & Environment

| Variable | Used in | Required | Default | Purpose |
|---|---|---|---|---|
| `ZERODHA_API_KEY` | `zerodha_auth.py`, `backtest_data_service.py`, `zerodha_historical_data.py`, `instrument_mapper_updater.py` | Yes for Zerodha mode | None | Zerodha app key |
| `ZERODHA_API_SECRET` | `zerodha_auth.py`, auth UI flow | Yes for token exchange | None | Zerodha app secret |
| `ZERODHA_ACCESS_TOKEN` | `zerodha_auth.py`, `backtest_data_service.py`, `zerodha_historical_data.py`, updater | Yes for Zerodha mode execution | None | Session token for Kite API calls |
| `ZERODHA_TOKEN_DATE` | `zerodha_auth.py`, `backtest_data_service.py` | Yes for Zerodha mode | None | Enforces same-day token validity |
| `api_key` | `zerodha_historical_data.py` | Optional | Fallback empty | Legacy fallback env key [inferred compatibility] |
| `access_token` | `zerodha_historical_data.py` | Optional | Fallback empty | Legacy fallback env key [inferred compatibility] |
| `SKIP_INSTRUMENT_UPDATE` | `entrypoint.sh` | No | `0` | Skip startup instrument refresh when set to `1` |

Non-env runtime configuration keys (session/config dict):
- `initial_capital`, `commission`, `max_retries`, `task_timeout_seconds`, `worker_count`.

## 11. Key Design Decisions & Patterns
- File-system-as-source-of-truth: strategy files, task store, data cache, and artifacts are all persisted to files rather than DB records.
- Defensive strategy loading: strategy path sandboxing and AST checks block traversal and dangerous dynamic execution primitives.
- Execution isolation: hard timeout enforcement via subprocess kill path prevents hung strategies from stalling workers.
- Error taxonomy + retry policy: retries are limited to `TIMEOUT_ERROR` and `API_ERROR`, reducing wasted retries on validation/data bugs.
- Market-time correctness: explicit IST normalization and market-hours assertions exist in both normalization and execution layers.
- UI and execution separation: Streamlit initiates tasks but execution is delegated to manager/engine modules.
- Atomic write patterns: `.tmp` + replace used for task store, metrics, env token updates, and strategy saves.
- Watchdog-driven refresh: data/strategy selection layers invalidate cache only when filesystem events occur.
- Cache-aware API fetching: partial cache merge and fallback reduce API dependency and improve resilience.
- Non-obvious choice [inferred]: retaining `__pycache__`, logs, and large datasets in repo suggests this repo doubles as a working lab environment, not only source distribution.

## 12. System Behavior & Failure Handling

### 12.1 Execution Behavior Baseline
- Tasks are created in UI/service code and handed to `ExecutionManager`.
- `ExecutionManager` owns lifecycle, retries, timeout enforcement, result normalization, persistence, and terminal logging.
- Actual strategy execution is delegated to:
  - `execution_engine.py` for `mode=csv`
  - `api_based_execution_engine.py` for `mode=api`
- Both engines converge on `backtest_core.execute_backtest_dataframe()` for Backtrader execution and artifact creation.

### 12.2 Failure Types

#### `API_ERROR`
- **Where it originates**:
  - API-fetch path in `api_based_execution_engine.py` (Zerodha session/fetch/cache refresh path).
  - Timeout/network/token/rate-limit related failures surfaced from Zerodha client calls.
- **How it is detected**:
  - `_classify_fetch_error()` in API engine checks exception class names and message markers (`token`, `kite`, `zerodha`, `rate limit`, `network`).
  - `ExecutionManager` can also classify message patterns as `API_ERROR` when enriching failures.
- **How it is handled**:
  - Engine builds structured failed payload (`status=FAILED`, `error_type=API_ERROR`, stage typically `data_fetch`).
  - Cache fallback is attempted before final failure when usable cached data exists.
  - Manager may retry this failure type (see retry rules).

#### `DATA_ERROR`
- **Where it originates**:
  - CSV read/parse/empty/size checks in `execution_engine.py`.
  - Dataframe validation/normalization failures in both engines.
  - Missing/invalid OHLCV or unusable normalized datasets in `backtest_core.py`.
- **How it is detected**:
  - `execution_engine.py` classifiers (`_classify_fetch_error`, `_classify_validation_error`, `_classify_execution_error`) map data-shape and parsing failures to `DATA_ERROR`.
  - API engine similarly classifies empty/malformed datasets as `DATA_ERROR`.
- **How it is handled**:
  - Failure is normalized into structured result with stage (`data_fetch`, `validation`, or `execution`).
  - Marked non-retryable at manager level.

#### `VALIDATION_ERROR`
- **Where it originates**:
  - Invalid task payload (missing `strategy_class`, invalid mode, invalid path/date/token fields).
  - Strategy hydration/path safety checks in `ExecutionManager` + `backtest_data_service`.
- **How it is detected**:
  - Explicit validation in `execution_engine.py`, `api_based_execution_engine.py`, and manager hydration path.
  - Classifiers map missing/invalid/unsupported input conditions to `VALIDATION_ERROR`.
- **How it is handled**:
  - Task fails fast with normalized error payload.
  - No retry is attempted.

#### `STRATEGY_ERROR`
- **Where it originates**:
  - Strategy runtime exceptions during Backtrader run in `backtest_core._run_cerebro_with_isolation()`.
- **How it is detected**:
  - Backtrader exceptions are trapped and re-raised as `RuntimeError("Strategy execution failed: ...")`.
  - Engine/manager classifiers map strategy-related execution failures to `STRATEGY_ERROR`.
- **How it is handled**:
  - Failed result is emitted with execution stage and strategy error message.
  - Non-retryable by manager.

#### `TIMEOUT_ERROR`
- **Where it originates**:
  - Hard timeout path in `ExecutionManager._dispatch_task_with_hard_timeout()`.
  - Explicit timeout exceptions propagated from lower layers.
- **How it is detected**:
  - Process join timeout expiry triggers `TimeoutError("Task exceeded hard timeout ...")`.
  - Classifiers map timeout phrases/exceptions to `TIMEOUT_ERROR`.
- **How it is handled**:
  - Child process is terminated/killed; queue resources are closed.
  - Failed result is built with `TIMEOUT_ERROR` and `execution` stage.
  - Retry is allowed if retry budget remains.

### 12.3 Retry Behavior
- Retry owner: `ExecutionManager._execute_with_retries()`.
- Attempt count: `max_retries + 1` total attempts.
- Default retry limit: `1` (from manager config when not overridden).
- Retryable failure types: only `TIMEOUT_ERROR` and `API_ERROR`.
- Non-retryable: `DATA_ERROR`, `VALIDATION_ERROR`, `STRATEGY_ERROR`, `SYSTEM_ERROR`.
- Backoff:
  - Manager-level retries are immediate (no explicit sleep/backoff between attempts).
  - API fetch internals still apply their own retry/backoff inside `ZerodhaHistoricalData._fetch_with_retry()` (`sleep(min(2**attempt, 8))`, max 5 tries) within a single task attempt.

### 12.4 State Transitions
- Queue-level lifecycle:
  - `PENDING` -> `RUNNING` -> `SUCCESS` or `FAILED`
- Retry lifecycle (logical, within `RUNNING`):
  - `RUNNING` -> failed attempt -> retry check -> next attempt (still `RUNNING`) -> final `SUCCESS` or `FAILED`
- Persisted task status is updated to final terminal state only after all attempts complete.

### 12.5 System Guarantees
- **Deterministic attempt input**:
  - Tasks are deep-copied at enqueue and deep-copied again per attempt.
  - Retries execute from immutable baseline task payload, preventing cross-attempt mutation leakage.
- **Safe persistence semantics**:
  - Task store writes are atomic (`.tmp` then replace), reducing partial-write risk.
  - Queue transitions and final results are persisted after lock-protected updates.
- **Failure normalization guarantee**:
  - `validate_result()` and manager enrichment paths force consistent result schema (`status`, `error_type`, `stage`, `execution_time`, `retries`).
- **Execution isolation**:
  - Optional hard-timeout mode runs execution in subprocess, preventing hung strategies from blocking worker loop indefinitely.
  - In-process backtest run is additionally sandboxed with warning capture and controlled exception wrapping.

### 12.6 Timeout Handling
- Hard timeout is activated when `task_timeout_seconds` (or `timeout_seconds`) is set to a positive value.
- Manager starts a subprocess (`spawn` context), waits `join(timeout)`, then:
  - `terminate()` + short join
  - `kill()` fallback if still alive
- After timeout cleanup:
  - result queue is closed/joined,
  - `TimeoutError` is raised and mapped to `TIMEOUT_ERROR`,
  - retry policy is evaluated (retry only if budget remains),
  - task ends as `FAILED` if retries exhausted.

## 13. Task Execution Lifecycle

1. Task creation in UI/service layer
- Tasks are assembled in `Dashboard/Backtesting_page/Backtests_section.py` when `Execute Strategy` is clicked.
- Task payloads are built via:
  - `backtest_data_service.build_csv_tasks(...)` for CSV mode
  - `backtest_data_service.build_zerodha_queue_tasks(...)` for API mode
- Required baseline fields:
  - `mode` (`csv` or `api`)
  - `symbol`
  - strategy metadata (`strategy_class`, plus `strategy_file_path` and `strategy_class_name` attached before enqueue)
- Mode-specific required fields:
  - CSV: `data` (relative/absolute CSV reference)
  - API: `instrument_token`, `interval`, `start_date`, `end_date`, optional `continuous`, `oi`, `instrument_type`
- Runtime config is passed separately (`initial_capital`, `commission`, `max_retries`, `task_timeout_seconds`).

2. Queue insertion and initial state
- `ExecutionManager.add_task(task)` deep-copies the task and assigns `task_id` (`TASK-xxxx`).
- A queue item is created with:
  - `status="PENDING"`
  - timestamps (`created_at`, others unset)
  - `result=None`, `execution_time=0.0`, `retries=0`
- Queue state is atomically persisted to `Data/Logs/task_store.json`.

3. Worker pickup and concurrency model
- Workers are started by `ExecutionManager.start_worker()` / `start_workers()`.
- Concurrency model:
  - multiple daemon worker threads are supported (`worker_count`, default 3),
  - each thread loops, picks the oldest `PENDING` task (`created_at`, then `task_id`), and marks it `RUNNING`.
- On pickup, `start_time` is set, state is persisted, and task-update callbacks/logging are emitted.

4. Execution phase (per attempt)
- `ExecutionManager._execute_with_retries()` drives each attempt.
- Strategy loading/hydration:
  - if `strategy_class` is absent, manager resolves `strategy_file_path` + `strategy_class_name` through `backtest_data_service.load_strategy_class(...)` with path safety checks.
- Dispatch:
  - mode `csv` -> `execution_engine.run_csv_task(...)`
  - mode `api` -> `api_based_execution_engine.run_task(...)`
- CSV data path:
  - resolve path, file-size/parse checks, dataframe validation, normalization via `data_normalizer.normalize(...)`.
- API data path:
  - validate session, inspect cache, fetch missing data from Zerodha when needed, sanitize/normalize dataframe.
- Backtest run:
  - both engines call `backtest_core.execute_backtest_dataframe(...)`,
  - Backtrader runs with analyzers, guarded sell behavior, and broker config.

5. Retry loop behavior
- Total attempts = `max_retries + 1`.
- After each failed attempt, result is normalized/classified.
- Retry condition: only failures typed as `TIMEOUT_ERROR` or `API_ERROR`.
- Non-retryable failures (`DATA_ERROR`, `VALIDATION_ERROR`, `STRATEGY_ERROR`, `SYSTEM_ERROR`) end the loop immediately.
- Each attempt uses a fresh deep copy of the immutable baseline task, preventing cross-attempt mutation.

6. Result handling and artifact generation
- Engine results are passed through `validate_result(...)` and manager-level failure enrichment.
- Success path:
  - `backtest_core` writes artifacts in `Data/Logs/Backtesting_result_log/`:
    - trade result CSV (`*_result_*.csv`)
    - execution log (`*_log_*.log`)
- Failure path:
  - structured failure payload is returned with `error`, `error_type`, and `stage`,
  - error logs may be written (`*_execution_error_*.log`) by core failure builders.

7. Metrics recording
- After final attempt, manager computes:
  - `execution_time` (monotonic elapsed for task processing),
  - `wait_time` (`start_time - created_at`),
  - `retries` used.
- `PerformanceTracker.record_task(...)` stores:
  - status, timing, retries, timeout flag, error type/message, stage, start/end timestamps.
- Metrics are persisted atomically (default path `Data/Logs/execution_metrics.json` [inferred]).

8. Final state and persistence
- Final queue state is terminal:
  - `SUCCESS` or `FAILED`
- Queue item is updated with final `result`, `end_time`, `execution_time`, `retries`.
- `results_by_task_id` is updated, task store is persisted atomically, and terminal/UI progress is refreshed.
- If all tasks finish, workers stop (or remain idle depending on lifecycle call path), and UI shows completed results.

## 14. Data Contracts

### 14.1 Input DataFrame Contract (Execution-Ready OHLCV)
Applies to data consumed by `backtest_core.execute_backtest_dataframe()` after engine normalization.

- Required logical fields:
  - `Open`
  - `High`
  - `Low`
  - `Close`
  - `Volume` (created as `0` when absent upstream)
- Accepted pre-normalization aliases:
  - datetime: `date`, `datetime`, `timestamp`, `time`
  - OHLCV: lowercase variants (`open`, `high`, `low`, `close`, `volume`)
- Datetime index contract:
  - Must be parseable into a `DatetimeIndex`.
  - Mixed aware + naive timestamps are rejected.
  - Invalid/unparseable timestamps are dropped; dataset must still remain non-empty.
- Timezone contract:
  - Normalization target is IST (`Asia/Kolkata` / `Asia/Calcutta` equivalent zone semantics).
  - Naive timestamps are treated as IST.
  - Aware timestamps are converted to IST.
- Ordering and uniqueness:
  - Index must be sorted ascending.
  - Duplicate timestamps are removed (`keep="first"`).
- Market-hours contract:
  - Intraday datasets are filtered/validated to `09:15` to `15:30` IST when `enforce_market_hours=True`.
  - Daily-like datasets (single midnight-like time pattern) may bypass market-hour filtering.
- Minimum execution density:
  - Final execution dataframe must contain `> 50` rows for backtest execution.
- Nullability:
  - `Open/High/Low/Close` must be non-null after normalization.
  - `Volume` may be synthesized and filled (`0`) but must be numeric.

### 14.2 Strategy Contract
Applies to strategy classes loaded and executed by the backtesting pipeline.

- Type requirements:
  - `strategy_class` must be a Python class object (`type`) at execution time.
  - Practical compatibility requirement: class must be a valid Backtrader strategy (`bt.Strategy` subclass).  
    Enforcement note: UI discovery (`strategy_selection`) filters by `issubclass(bt.Strategy)`; direct low-level callers can still bypass this and fail at runtime.
- Required behavior:
  - Must implement Backtrader-compatible lifecycle methods; `next()` is effectively required for meaningful execution.
  - Should handle `notify_order` / `notify_trade` safely if overridden.
- Safety constraints:
  - Strategy source is path-sandboxed to `Strategies/Strategy_codes`.
  - AST safety checks block dangerous primitives: `eval`, `exec`, `compile`, `__import__` override attempts.
- State constraints:
  - Strategy execution is expected to be self-contained per task attempt.
  - External mutable side effects are not prohibited by runtime, but are outside safe contract and can break determinism.

### 14.3 Task Schema Contract
Applies to items passed into `ExecutionManager.add_task()` and engines.

| Field | Required | Type | Applies to | Rules |
|---|---|---|---|---|
| `mode` | Yes | `str` | all tasks | Must be `csv` or `api` (case-insensitive route resolution). |
| `symbol` | Yes | `str` | all tasks | Normalized uppercase fallback to `UNKNOWN` when missing. |
| `strategy_class` | Yes* | `type` | all tasks | Required at execution time. May be hydrated from `strategy_file_path` + `strategy_class_name` if absent. |
| `strategy_file_path` | Conditionally | `str` | all tasks | Required for hydration path when `strategy_class` not pre-attached. Must resolve inside strategy root. |
| `strategy_class_name` | Conditionally | `str` | all tasks | Required with `strategy_file_path` for hydration. Must be valid identifier and present in module. |
| `data` | Yes | `str` / `DataFrame` | `csv` / optional `api` | CSV mode: path/reference required. API mode: may provide pre-fetched DataFrame. |
| `instrument_token` | Yes | `int`-coercible | `api` | Required unless `data` already supplied as DataFrame. |
| `interval` | Yes | `str` | `api` | Normalized interval string (`minute`, `3minute`, ..., `day`). |
| `start_date` | Yes | datetime-like | `api` | Must parse; must be `<= end_date`. |
| `end_date` | Yes | datetime-like | `api` | Must parse; must be `>= start_date`. |
| `instrument_type` | Optional | `str` | `api` | Controls `continuous` applicability (`FUT` only). |
| `continuous` | Optional | `bool` | `api` | Forced false unless instrument type is `FUT`. |
| `oi` | Optional | `bool` | `api` | Include Open Interest data when available. |
| `enforce_market_hours` | Optional | `bool` | both modes | Defaults true in normalization paths. |
| `config` | Optional | `dict` | both modes | Runtime overrides (`initial_capital`, `commission`, etc.). |

Additional validation rules:
- CSV relative paths must remain inside `Data/testing_data/Data_files`.
- API tasks fail validation if required datetime/token fields are missing or invalid.
- Unsupported `mode` yields `VALIDATION_ERROR`.

### 14.4 Result Schema Contract
Two result layers are produced: execution payload (in-memory/JSON) and trade artifact CSV.

Execution result payload contract:
- Required keys:
  - `symbol: str`
  - `status: "SUCCESS" | "FAILED"`
  - `final_value: float | null`
  - `log_file: str`
  - `error: str | null`
  - `execution_time: float` (>= 0)
  - `retries: int` (>= 0)
- On failure, normalized enrichment adds:
  - `error_type` in `{DATA_ERROR, API_ERROR, STRATEGY_ERROR, TIMEOUT_ERROR, VALIDATION_ERROR, SYSTEM_ERROR}`
  - `error_message`
  - `stage` in `{data_fetch, validation, execution}`

Backtest result CSV contract (`*_result_*.csv`):

| Column | Type | Nullability | Notes |
|---|---|---|---|
| `Entry Date` | timestamp string (IST-formatted) | non-null per row | `YYYY-MM-DD HH:MM:SS` string format from analyzers |
| `Close Date` | timestamp string (IST-formatted) | non-null per row | exit timestamp |
| `Symbol` | string | non-null | task symbol propagated into rows |
| `Direction` | string | non-null | `BUY` or `SELL` |
| `Qty` | int/float | non-null | integer when close to whole units |
| `Entry Price` | float | non-null | rounded to 2 decimals |
| `Exit Price` | float | non-null | rounded to 2 decimals |
| `Gross P&L` | float | non-null | rounded to 2 decimals |
| `Net P&L` | float | non-null | rounded to 2 decimals |

Guarantees:
- CSV file is always written with fixed column order.
- Empty trade sets still produce a valid CSV with headers (and zero rows).
- Timestamps are generated from Backtrader timeline converted to IST formatting.

### 14.5 API Data Contract (Zerodha Fetch -> Normalized Frame)
Expected raw Zerodha row shape (before normalization):
- `date`, `open`, `high`, `low`, `close`, `volume`
- optional `oi`

Normalization expectations:
- Rename to canonical columns: `Date`, `Open`, `High`, `Low`, `Close`, `Volume`, optional `OI`.
- `Date` parsed as UTC-aware and converted to IST index.
- Index sorted ascending and deduplicated.
- Intraday market-hour filter enforced when configured.
- Numeric coercion applied; invalid OHLC rows dropped.
- Final dataframe supplied to execution uses:
  - required columns: `Open`, `High`, `Low`, `Close`, `Volume`
  - optional `OI` may exist in fetch-normalized forms but execution path standardizes to OHLCV for backtest core.

Cache contract (`Data/testing_data/Data_files/Zerodha_data/*.csv`):
- Cache files are considered valid only if:
  - required OHLC columns present,
  - index parseable and unique,
  - no disqualifying internal timestamp gaps for interval checks,
  - date coverage satisfies requested range (or partial fallback rules apply).

## 15. Performance Characteristics

### 15.1 Execution Performance
Task execution time is dominated by three sequential phases: dataset acquisition, normalization, and Backtrader runtime. For CSV mode, `pd.read_csv` and normalization are usually the largest fixed overhead before strategy logic runs. For API mode, fetch latency and chunk stitching dominate, then normalize/execute costs are similar to CSV mode.

The system records per-task execution duration (`execution_time`) and persists it with each queue item and in performance metrics. `PerformanceTracker` also computes `avg_execution_time` and `median_execution_time`, so runtime behavior is measurable across runs rather than inferred.

From currently persisted data in [`Data/Logs/task_store.json`](/c:/Users/aggar/PROJECTS/Algo_Trading_System/Data/Logs/task_store.json), the visible sample run (`TASK-0001`, API/day, RELIANCE) completed in about `0.956s`; treat this as a single-point observation, not a stable benchmark.

Primary factors that increase execution time:
- Larger row counts (longer date ranges, lower intervals like `minute`).
- More complex strategy logic per bar (`next()` compute cost).
- Retry-triggering instability (API/network/token events or timeouts).
- Additional gap-refetch passes in API coverage reconciliation.

### 15.2 Queue Performance
Queue latency and execution latency are tracked separately. `ExecutionManager` stores:
- `wait_time`: derived from `created_at` to `start_time`.
- `execution_time`: active run duration from dispatch start to final attempt completion.

This separation is important under load: high wait with normal execution means capacity saturation; high execution with low wait means heavy task bodies.

Worker behavior is cooperative threaded polling:
- Configurable worker pool (`worker_count`, default `3`).
- Workers repeatedly pick the oldest `PENDING` task and mark it `RUNNING`.
- If no task exists, workers sleep for `poll_interval_seconds` (default `0.2s`), trading minimal latency for low idle CPU.

### 15.3 Memory Usage Characteristics
Memory pressure is dataset-driven:
- CSV mode loads full files into memory (`pd.read_csv`) and then creates normalized copies.
- API mode accumulates fetched chunks (`all_rows`) before DataFrame normalization, then may build additional structures for missing-candle refetch and merge.

Practical effects:
- Peak memory grows with total bars in scope and can exceed final DataFrame size due to intermediate objects.
- A hard CSV guard (`MAX_CSV_SIZE_MB = 200`) prevents pathological local file loads, but API mode can still grow large via long-range minute data.

### 15.4 API Performance Profile
API fetches are optimized for resilience and bounded request size:
- Requests are chunked by interval-specific day windows (`_get_chunk_days`), avoiding oversized single calls.
- Each chunk uses retry with exponential backoff (`sleep(min(2**attempt, 8))`, bounded retry count).
- Coverage checks detect missing timestamps and run targeted gap-refetch passes.

Caching materially changes performance:
- Valid cache: fetch phase is mostly bypassed, so API mode approaches CSV-mode timings.
- Partial cache: only uncovered ranges are fetched, reducing request volume.
- Missing/invalid cache: full fetch path runs, highest latency and variability.

### 15.5 CSV vs API: Speed and Reliability
CSV mode is typically faster and more predictable because it avoids network round-trips and token/session dependencies. Its failure surface is mostly local I/O and schema quality.

API mode is more variable:
- Slower on cold fetches due to chunk loops and retries.
- More robust for fresh market history and auto-gap handling.
- More operationally fragile (auth expiry, rate limits, network faults), partially mitigated by retry classification and cache fallback.

In short: CSV mode favors deterministic throughput; API mode favors freshness and broader data availability.

### 15.6 Bottlenecks and Scaling Limits
Key bottlenecks under load are:
- Python threading and GIL: worker threads improve concurrency for I/O-bound phases, but CPU-bound strategy execution does not scale linearly with thread count.
- File I/O: repeated CSV reads/writes (input, cache, artifacts, task store) add latency, especially with larger files.
- Large datasets: normalization, sorting, deduplication, and Backtrader iteration all scale with bar count.
- Retry overhead: repeated API failures amplify tail latency and reduce effective throughput per worker.

The architecture mitigates some risk with subprocess hard timeouts and atomic persistence, but throughput tuning still depends on right-sizing `worker_count`, reducing task data scope, and maximizing cache hit rate.

## 16. Known Limitations

### 16.1 Execution Limitations
- No slippage model is applied during fills; executions effectively assume bar-price fill behavior from Backtrader defaults/config.
- No order book or market microstructure simulation exists (no depth, spread dynamics, queue position, or partial-fill realism).
- Transaction-cost modeling is limited to configured commission; advanced execution frictions are not modeled.

### 16.2 Data Limitations
- Historical correctness depends on upstream provider quality (Zerodha/Yahoo) and local cache integrity.
- No real-time market data streaming pipeline is implemented; workflows are batch/historical.
- API-mode freshness is bounded by token validity, API availability, and rate-limit behavior.

### 16.3 Architecture Limitations
- Persistence is file-based (JSON/CSV/log files), not database-backed.
- No relational/NoSQL storage layer exists for multi-user querying, transactional guarantees, or indexed analytics.
- Execution is single-machine oriented; there is no distributed worker cluster or remote execution fabric.
- Operational state (queue, metrics, artifacts) is local filesystem state, which limits horizontal scalability.

### 16.4 Performance Limitations
- Worker concurrency uses Python threads; CPU-bound strategy code is constrained by the GIL.
- Large datasets increase memory pressure because data is loaded and transformed in-memory (with intermediate copies).
- File I/O (CSV read/write, artifact persistence, cache merges) is a recurring throughput bottleneck under heavier task volume.

### 16.5 Strategy Limitations
- Task execution is strategy-centric: one strategy class per task execution path.
- There is no native portfolio-level coordinator for cross-symbol capital allocation, net exposure controls, or multi-strategy optimization in a single unified run.
- Portfolio analytics must be derived post-hoc from multiple independent task outputs rather than one portfolio simulation engine.

## 17. Design Philosophy

### 17.1 Modular Monolith vs Microservices
- What was chosen:
  - A modular monolith: one deployable application with clear internal layers (UI, services, execution, data artifacts).
- Why it was chosen:
  - The core workflow (strategy selection -> data prep -> execution -> artifact review) is tightly coupled and benefits from low-friction in-process calls.
  - It minimizes operational overhead for a single-team, fast-iteration environment.
- Trade-offs:
  - Simpler to develop and debug end-to-end.
  - Harder to scale individual subsystems independently compared with service decomposition.

### 17.2 File-Based Persistence vs Database
- What was chosen:
  - JSON/CSV/log files as the persistence layer (`task_store.json`, metrics JSON, result CSVs, data caches).
- Why it was chosen:
  - Backtesting outputs are naturally file-oriented artifacts, and local persistence keeps the runtime setup lightweight.
  - Avoids schema migrations and database operations during rapid product evolution.
- Trade-offs:
  - Fast to bootstrap and easy to inspect manually.
  - Limited querying, weaker concurrent-access guarantees, and weaker scale characteristics than a database-backed design.

### 17.3 Backtrader as Execution Engine
- What was chosen:
  - Backtrader is the strategy execution core, wrapped by `backtest_core.py`.
- Why it was chosen:
  - Provides a mature strategy lifecycle, broker abstraction, and analyzer ecosystem without building a custom simulator from scratch.
  - Aligns with Python-based quant workflows already used in the project.
- Trade-offs:
  - Accelerates feature delivery for standard backtest mechanics.
  - Constrains behavior to Backtrader’s execution model and abstractions; advanced market microstructure modeling remains limited.

### 17.4 Retry Classification System
- What was chosen:
  - Typed failures (`API_ERROR`, `DATA_ERROR`, `VALIDATION_ERROR`, `STRATEGY_ERROR`, `TIMEOUT_ERROR`, `SYSTEM_ERROR`) with selective retry policy.
- Why it was chosen:
  - Not all failures are recoverable; classification avoids wasting retries on deterministic failures (e.g., invalid input/data shape).
  - Focuses retries on transient classes (`API_ERROR`, `TIMEOUT_ERROR`) where repeated attempts can succeed.
- Trade-offs:
  - Improves throughput and failure clarity under instability.
  - Requires ongoing maintenance of classification heuristics as new failure modes appear.

### 17.5 Hard Timeout Enforcement
- What was chosen:
  - Optional hard timeout using subprocess isolation and forced termination (`terminate` / `kill`) in `ExecutionManager`.
- Why it was chosen:
  - Prevents hung strategy runs from blocking workers indefinitely.
  - Preserves queue liveness in long-running or faulty strategy scenarios.
- Trade-offs:
  - Strong safety boundary for execution control.
  - Added process-spawn overhead and extra complexity in inter-process result handling.

### 17.6 Data Normalization Strictness
- What was chosen:
  - Centralized, strict OHLCV normalization with timezone alignment (IST), sorting, deduplication, numeric coercion, and market-hours handling.
- Why it was chosen:
  - Strategy behavior and PnL are highly sensitive to subtle data inconsistencies.
  - A strict contract reduces silent corruption and improves reproducibility across CSV/API sources.
- Trade-offs:
  - Better execution consistency and clearer failures.
  - Some raw rows are dropped or transformed, and stricter validation can reject marginal datasets that might otherwise “run.”

### 17.7 Streamlit UI Choice
- What was chosen:
  - Streamlit as the primary interactive UI framework.
- Why it was chosen:
  - Enables fast delivery of a Python-native interface for strategy editing, queue control, and chart review without a separate frontend stack.
  - Keeps UI logic close to the backtesting/runtime code.
- Trade-offs:
  - High iteration speed and low frontend complexity.
  - Less suited than custom web stacks for highly complex multi-user workflows, fine-grained client state control, or large-scale frontend performance tuning.

## 18. Edge Case Handling

### 18.1 Partial API Data
- Scenario:
  - Zerodha returns incomplete candle coverage for the requested range (missing timestamps/chunks).
- System behavior:
  - `ZerodhaHistoricalData.fetch_data()` builds an expected timestamp index and computes missing timestamps.
  - It performs targeted refetch on missing segments, with bounded passes (`MAX_GAP_REFETCH_PASSES = 2`) and per-pass segment cap (`MAX_GAP_SEGMENTS_PER_PASS = 500`).
  - After refetch passes, if gaps remain, the system logs coverage warnings and proceeds with integrity checks; it does not automatically hard-fail solely because some gaps remain.
- Safeguards:
  - Missing-gap detection and segmented refetch reduce partial-data risk.
  - Integrity guards still fail on critical shape issues (empty dataset, non-monotonic index, duplicate timestamps), preventing obviously broken execution input.

### 18.2 Duplicate Task Submission
- Scenario:
  - The same logical task payload is submitted multiple times from UI/service layer.
- System behavior:
  - `ExecutionManager.add_task()` always allocates a new `task_id` and appends a new `PENDING` queue item.
  - No semantic deduplication is performed against existing queue entries.
- Safeguards:
  - Queue ordering and locking keep duplicate submissions isolated and deterministic.
  - Each duplicate runs as an independent task, with separate artifacts/results.

### 18.3 Cache Corruption
- Scenario:
  - API cache file exists but is malformed, unparsable, or structurally invalid.
- System behavior:
  - `api_based_execution_engine._inspect_cache()` marks cache as `invalid` when `read_csv` or schema sanitation fails.
  - Invalid cache triggers warning + best-effort deletion (`cache_path.unlink()`), then full API refetch.
  - If refetch fails and no usable fallback slice exists, task fails through normal classified error flow.
- Safeguards:
  - Cache sanitation requires parseable datetime index, required OHLC columns, numeric coercion, and non-empty payload.
  - Cache-write failures are non-fatal (execution continues) to avoid turning cache I/O into hard runtime failure.

### 18.4 Empty Dataset After Normalization
- Scenario:
  - All rows are dropped during parsing/coercion/market-hours filtering.
- System behavior:
  - `data_normalizer.normalize()` raises `ValueError("No valid OHLCV rows after normalization")`.
  - Engines convert this into structured failure payload (`status=FAILED`, typed as validation/data error path) and surface it through manager/result pipeline.
- Safeguards:
  - Early and explicit failure avoids running Backtrader on degenerate data.
  - `validate_result()` normalizes final failure schema so UI/persistence receive consistent error shape.

### 18.5 Strategy Produces No Trades
- Scenario:
  - Strategy runs successfully but opens/closes no trades.
- System behavior:
  - `backtest_core.execute_backtest_dataframe()` still returns `SUCCESS` if run completes and final portfolio value is available.
  - `_write_dashboard_artifacts()` always writes result/log artifacts; trade CSV is created with fixed headers and zero rows when `closed_trades` is empty.
  - Log file includes `total_closed_trades=0` and `No trade events captured.` when applicable.
- Safeguards:
  - Artifact schema remains stable even for zero-trade runs, avoiding downstream parser breakage.

### 18.6 Extremely Large Dataset
- Scenario:
  - Very large CSV/API datasets are requested for backtest execution.
- System behavior:
  - CSV mode applies file-size guard (`MAX_CSV_SIZE_MB = 200.0`); oversized files fail before load.
  - Within allowed size, data is fully loaded/normalized in memory; large row counts increase latency and memory usage.
  - API mode can still produce large in-memory frames (chunk accumulation + merge/normalization), so degradation is mostly gradual unless hard failures occur.
- Safeguards:
  - CSV hard size cap prevents worst local-file cases.
  - API chunking bounds per-request slice size, but total memory still scales with requested range.

### 18.7 Concurrent Worker Behavior
- Scenario:
  - Multiple workers poll queue concurrently and attempt to pick tasks.
- System behavior:
  - `ExecutionManager` uses `threading.RLock`; `_pick_next_pending_task()` acquires lock, selects oldest `PENDING`, and atomically flips it to `RUNNING` before releasing.
  - This prevents two workers from claiming the same queue item.
  - On restart/load, any persisted `RUNNING` items are reset to `PENDING`, so stranded in-flight tasks are recoverable.
- Safeguards:
  - Lock-protected queue state transitions + atomic store writes (`.tmp` then replace) reduce race/corruption risk.
  - Worker loop isolation keeps failures per task from collapsing whole queue processing.

## 19. End-to-End Execution Sequence

**Sequence**
User -> UI (`Backtests_section`) -> ExecutionManager -> ExecutionEngine -> Backtest Core -> Storage (CSV/Logs/Metrics/Task Store) -> UI (terminal/progress/results)

### 19.1 User Action
1. User selects:
- strategy file + strategy class
- data mode (`csv` or `api`) and dataset/instrument/date range
- runtime options (capital, commission, retries, timeout)
2. User clicks `Execute Strategy`.

### 19.2 UI Layer
1. `Dashboard/Backtesting_page/Backtests_section.py` validates current selections and session-state prerequisites.
2. It builds tasks using:
- `build_csv_tasks(...)` for CSV mode
- `build_zerodha_queue_tasks(...)` for API mode
3. It updates session state for execution lifecycle (running flag, progress context, terminal binding, queue tracking).
4. It instantiates/configures `ExecutionManager` with runtime config and starts workers.

### 19.3 Execution Manager
1. `add_task(...)` deep-copies each task, assigns `task_id`, marks it `PENDING`, and persists to `task_store.json`.
2. Worker loop picks oldest `PENDING` item under lock, marks it `RUNNING`, and emits task update callbacks.
3. `_execute_with_retries(...)` runs attempts (`max_retries + 1`), hydrates strategy class when needed, and dispatches execution.
4. Retry decision is applied after each failed attempt (retry only for retryable error classes).

### 19.4 Execution Engine
1. Manager routes by mode:
- `csv` -> `execution_engine.run_csv_task(...)`
- `api` -> `api_based_execution_engine.run_task(...)`
2. CSV path:
- validates path/size/schema
- loads dataframe
- normalizes OHLCV/timezone
3. API path:
- validates task fields/session
- inspects/uses cache when possible
- fetches and merges missing ranges when needed
- normalizes final dataframe

### 19.5 Backtest Core
1. Engine calls `backtest_core.execute_backtest_dataframe(...)`.
2. Core validates prepared dataframe and runtime config.
3. Backtrader is executed with strategy + analyzers.
4. Trade events and closed-trade rows are extracted; final portfolio value is computed.
5. Result is normalized to `SUCCESS` or structured `FAILED` payload.

### 19.6 Persistence Layer
1. Core writes run artifacts:
- result CSV (`*_result_*.csv`)
- execution log (`*_log_*.log`) or failure log (`*_execution_error_*.log`)
2. Manager persists queue/result state atomically in `Data/Logs/task_store.json`.
3. `PerformanceTracker` records execution metrics (execution time, wait time, retries, timeout/error classification) and persists metrics JSON.

### 19.7 UI Update
1. Terminal stream receives structured log lines throughout validation/fetch/execute/finalize phases.
2. Task status callbacks and queue snapshots drive progress updates (`PENDING` -> `RUNNING` -> `SUCCESS/FAILED`).
3. Completed artifacts are surfaced in UI:
- backtest completion/results panel
- dashboard visualizations from generated CSV/log files.

## 20. Security Model

### 20.1 Strategy Execution Safety
- Path sandboxing:
  - Strategy loading resolves paths with `resolve_strategy_file_path(...)` and enforces `relative_to(resolve_strategy_root())`, so strategies must stay under `Strategies/Strategy_codes`.
  - Non-existent paths and non-`.py` files are rejected.
- AST validation:
  - `_validate_strategy_source_safety(...)` parses strategy source with `ast.parse(...)`.
  - Blocked dynamic execution calls: `eval`, `exec`, `compile`, `__import__`.
  - Blocking also covers assignment-based import override attempts (`__import__` rebinding).
- Controlled import behavior:
  - Strategies are loaded via `importlib.util.spec_from_file_location(...)` with a deterministic hashed module name.
  - Temporary `sys.modules` insertion is restored after execution to limit module-state leakage.
  - Class name must be a valid identifier and must map to a class object in the loaded module.

### 20.2 File System Protection
- Path traversal prevention:
  - Strategy path traversal outside strategy root is blocked.
  - Relative CSV paths are constrained to `Data/testing_data/Data_files` (`resolved.relative_to(data_root)`).
- CSV access restriction boundary:
  - Relative CSV references are sandboxed.
  - Absolute CSV paths are accepted if the file exists; this is a broader trust boundary than relative-path mode.
- Safe write locations:
  - Backtest artifacts are written to `Data/Logs/Backtesting_result_log`.
  - Queue state persists to `Data/Logs/task_store.json`.
  - API cache writes go to `Data/testing_data/Data_files/Zerodha_data`.
  - Generated symbol/file names are sanitized before artifact filenames are constructed.

### 20.3 Execution Isolation
- Subprocess timeout isolation:
  - `ExecutionManager._dispatch_task_with_hard_timeout(...)` runs task execution in a spawned subprocess when timeout is enabled.
  - Hard timeout enforcement uses `join(timeout)` then `terminate()`, followed by `kill()` fallback if needed.
- Hung-strategy containment:
  - Timeout converts to `TIMEOUT_ERROR` for that task only.
  - Worker loop continues serving other tasks instead of blocking indefinitely.

### 20.4 Environment Variable Safety
- `.env` and environment usage:
  - Credentials/tokens are read from env vars and `.env` helpers; runtime logic avoids hardcoded API keys/secrets/tokens.
- Token freshness and refresh:
  - `validate_zerodha_session()` requires API key, access token, and current-day `ZERODHA_TOKEN_DATE`.
  - `zerodha_historical_data.get_kite_client()` calls `load_dotenv(..., override=True)` per client creation, so refreshed `.env` values are picked up on subsequent attempts.
- Safe token persistence:
  - `save_access_token_to_env(...)` writes via temp file (`.tmp`) and atomic `replace(...)`, reducing partial-write risk.

### 20.5 Failure Containment
- Task-level containment:
  - Tasks are deep-copied at enqueue and per retry attempt, limiting shared-mutation side effects.
  - Errors are normalized into per-task `FAILED` results with typed metadata, rather than escalating to global failure.
- Worker-level containment:
  - Worker loop has `try/except` around processing; unexpected exceptions are logged and loop continues.
- Store-level containment:
  - Task store writes are atomic (`.tmp` -> `replace`).
  - Corrupt persisted store payloads are quarantined to `.corrupt.*.json`, and in-memory queue state is safely reset.

## 21. Testing Strategy

### 21.1 Unit Testing
- Scope:
  - `data_normalizer.py` core transforms (`normalize`, timezone conversion, OHLC coercion, sorting, dedupe, market-hours filtering).
  - Validation helpers in execution engines (task schema checks, date-range checks, symbol/interval checks, strategy/class validation gates).
  - Task building logic in UI/feature layer (`build_csv_tasks`, `build_zerodha_queue_tasks`, and task payload defaults).
- How it should be done:
  - Use `pytest` with small, deterministic dataframe fixtures.
  - Cover both valid and invalid inputs; assert exact exception class/message where behavior is contract-critical.
  - Parametrize edge combinations (missing columns, mixed dtypes, duplicate timestamps, NaNs, empty rows, out-of-hours rows).
  - Add filesystem-isolated tests (`tmp_path`) for path validation functions to verify traversal blocking and allowed-root enforcement.
- Correctness criteria:
  - Normalizer outputs stable schema and monotonic timestamp index.
  - Validators reject malformed tasks early with typed/structured failures.
  - Task builders always produce engine-ready payloads with required keys.

### 21.2 Integration Testing
- Scope:
  - Full execution flow for both `csv` and `api` task modes.
  - Strategy resolution/loading and class hydration.
  - Backtest execution and artifact generation (result CSV + logs + metrics/task-store updates).
- How it should be done:
  - Run `ExecutionManager` with a test worker configuration and controlled fixture strategies/data.
  - For CSV flow, run end-to-end against known sample datasets and assert final task status plus generated artifacts.
  - For API flow, mock Zerodha client responses at adapter boundaries (`get_kite_client` / historical fetch service), then validate cache + normalization + core execution sequence.
  - Assert task-state transitions (`PENDING -> RUNNING -> SUCCESS/FAILED`) and persistence to `task_store.json`.
- Reliability criteria:
  - No silent success with missing artifacts.
  - Deterministic status transitions and retry accounting.
  - Stable result schema across runs.

### 21.3 Failure Testing
- Scope:
  - API failure simulation.
  - Timeout simulation.
  - Corrupted CSV simulation.
  - Invalid strategy simulation.
- How it should be done:
  - API failure: mock transient and terminal API exceptions (network error, auth/session invalid, empty candle response) and assert retry/no-retry classification behavior.
  - Timeout: run a deliberately hanging strategy and verify subprocess timeout path produces `TIMEOUT_ERROR` and worker continuity.
  - Corrupted CSV: feed malformed delimiters, bad timestamps, non-numeric OHLC cells, huge file (size cap breach), and assert explicit validation/data failure.
  - Invalid strategy: include blocked AST constructs (`eval`/`exec`) and bad class names; assert load rejection before runtime execution.
- Robustness criteria:
  - Failures are contained per task.
  - Error payloads remain structured and user-facing logs remain informative.
  - Queue continues processing subsequent tasks after each induced failure.

### 21.4 Regression Testing
- Scope:
  - Protect previously working features while introducing changes in engine, normalizer, strategy loader, or UI task orchestration.
  - Validate output consistency across known baselines.
- How it should be done:
  - Maintain a golden-suite of representative strategies and datasets (CSV + mocked API snapshots).
  - On each change, run the suite and compare:
    - task outcome (`SUCCESS/FAILED`)
    - trade count and closed-trade records
    - key metrics tolerances (final value, drawdown, win rate) where deterministic.
  - Include contract tests for artifact filenames/columns and task-store schema to catch accidental format drift.
- Stability criteria:
  - No unintentional change in result semantics for unchanged inputs.
  - Any intentional metric shift must be reviewed and explicitly approved.

### 21.5 Performance Testing
- Scope:
  - Large dataset execution behavior.
  - Multi-task queue stress behavior.
- How it should be done:
  - Large dataset tests:
    - Benchmark near-threshold CSV sizes (just below `MAX_CSV_SIZE_MB`) and varied candle densities.
    - Measure total runtime, peak memory, and normalization/backtest phase timings.
    - Confirm graceful rejection for oversized CSV inputs.
  - Queue stress tests:
    - Enqueue high-volume mixed workloads (fast/slow/failing tasks) with multiple workers.
    - Track throughput, queue wait-time distribution, retry amplification, and timeout handling under load.
    - Verify no duplicate task pickup, no deadlock, and stable task-store persistence.
- Performance criteria:
  - Throughput scales with worker count up to expected limits.
  - Memory growth is bounded/understood for target dataset sizes.
  - Degradation is gradual and observable rather than abrupt failure.

## 22. Observability & Monitoring

### 22.1 Logging System
- Terminal logging (`ExecutionTerminal`):
  - The UI initializes a shared in-session terminal object (`execution_terminal`) and passes it into `ExecutionManager`.
  - Manager, engines, and core emit structured terminal entries via `terminal.log(message, level, task_id, symbol)`.
  - Log levels are normalized to a fixed set: `INFO`, `SUCCESS`, `WARNING`, `ERROR`.
  - Terminal supports symbol/level filtering, task-specific log views, and export (`Download Logs`).
- Log levels and semantics:
  - `INFO`: queueing, validation progress, execution milestones.
  - `WARNING`: retries, partial/fallback conditions, non-fatal instrumentation issues.
  - `ERROR`: classified failures, worker-loop crashes, timeout/fetch/execution errors.
  - `SUCCESS`: terminal success milestones (task completion, full run completion).
- Log persistence (files):
  - Per-run artifacts are persisted in `Data/Logs/Backtesting_result_log`:
    - `*_log_*.log` for successful/complete execution summaries and trade events.
    - `*_execution_error_*.log` for failed runs.
    - `*_result_*.csv` for normalized closed-trade output.
  - Queue state is persisted to `Data/Logs/task_store.json` (atomic `.tmp` then `replace`).
  - Metrics are persisted to `Data/Logs/execution_metrics.json` (also atomic write pattern).

### 22.2 Metrics Tracking
- Source:
  - `ExecutionManager` computes and records metrics per completed task through `PerformanceTracker.record_task(...)`.
- Tracked per-task fields:
  - `execution_time`: measured runtime from task start to final result normalization.
  - `wait_time`: computed as `start_time - created_at` (queue delay).
  - `retries`: retries consumed before final status.
  - `status`: `SUCCESS` or `FAILED`.
  - `timeout`: explicit timeout flag derived from `error_type == TIMEOUT_ERROR`.
  - `error_type`, `error_message`, `stage` for failure analytics.
- Aggregated metrics:
  - `total_tasks`
  - `success_rate`, `failure_rate`
  - `avg_execution_time`, `median_execution_time`
  - `retry_count`, `timeout_count`
- Robustness of metrics store:
  - Corrupt metrics file is quarantined to `.corrupt.<timestamp>.json` and rebuilt.
  - Thread-safe updates use `RLock`; persistence is atomic.

### 22.3 Error Visibility
- Structured error model:
  - Failures are normalized to include:
    - `status=FAILED`
    - `error_type` (`DATA_ERROR`, `API_ERROR`, `STRATEGY_ERROR`, `TIMEOUT_ERROR`, `VALIDATION_ERROR`, `SYSTEM_ERROR`)
    - `error_message`
    - `stage` (`validation`, `data_fetch`, `execution`)
  - Engines and manager enrich raw exceptions through classification helpers and sanitizers.
- Failure stage tracking:
  - Validation failures are tagged at `validation`.
  - Data acquisition/normalization issues are tagged at `data_fetch`.
  - Strategy/backtest runtime issues are tagged at `execution`.
- User-visible error paths:
  - Terminal entries include error type and stage context.
  - Per-task result payload in queue/results contains structured failure fields.
  - Error log files are written for failed runs and linked by `log_file` in result payload.

### 22.4 Debugging Workflow
- Recommended trace path for a failed task:
  1. Inspect UI terminal task logs (`Task Logs` expander) for first failing stage and message.
  2. Open queue state in `Data/Logs/task_store.json` and locate the task by `task_id`:
  - confirm `status`, `error_type`, `stage`, `error_message`, `retries`, `execution_time`.
  3. Open referenced run artifact in `Data/Logs/Backtesting_result_log`:
  - `*_execution_error_*.log` for failure details, or `*_log_*.log` for partial-success context.
  4. Check `Data/Logs/execution_metrics.json`:
  - validate wait-time spikes, retry amplification, timeout frequency, and task-level anomalies.
  5. Correlate by boundary:
  - `validation` -> task payload/strategy metadata/path safety.
  - `data_fetch` -> CSV/API input, cache state, normalization constraints.
  - `execution` -> strategy runtime, Backtrader processing, timeout behavior.
- Practical code inspection points:
  - Queue + retry + classification: `Backtesting/execution_manager.py`
  - CSV path and execution flow: `Backtesting/execution_engine.py`
  - API fetch/cache execution flow: `Backtesting/api_based_execution_engine.py`
  - Run artifact writing and result normalization: `Backtesting/backtest_core.py`
  - Terminal UI/log behavior: `Dashboard/Backtesting_page/Features/terminal.py`

### 22.5 UI Observability
- Terminal panel behavior:
  - Real-time stream rendered in `Backtests_section` via `render_terminal_panel(...)`.
  - Filters by symbol/level, error-only toggle, task-wise log segmentation, clear/export actions.
  - Auto-refresh loop reruns while execution is active, giving near-real-time log updates.
- Real-time state updates:
  - Periodic queue tick recomputes `execution_task_states`, `progress`, `results`, and overall status.
  - Status transitions are explicit (`IDLE` -> `RUNNING` -> `COMPLETED` or `COMPLETED_WITH_ERRORS`).
  - Completion markers are logged to terminal (`Execution completed` / `Execution completed with errors`).
- Operational visibility outcome:
  - Users can observe queue health, per-task lifecycle, failure concentration, and completion quality without leaving the UI.

## 23. Scaling Limits & Bottleneck Analysis

### 23.1 CPU Bottlenecks
- Cause:
  - Backtrader execution (`cerebro.run()`) is CPU-heavy and runs bar-by-bar strategy logic.
  - Worker orchestration is thread-based; in-process CPU work is constrained by the Python GIL.
  - When hard timeout is enabled, each attempt uses spawned subprocess execution, which improves isolation but adds process start/IPC overhead.
- Impact:
  - Increasing `worker_count` does not scale linearly for CPU-bound strategies.
  - Throughput flattens once CPU cores are saturated; beyond that, context switching and spawn overhead can reduce net throughput.
  - Retry-heavy CPU tasks amplify contention and queue wait time.
- Possible mitigation:
  - Keep worker count near physical core count (not far above it).
  - Favor process-based pools for sustained CPU workloads (instead of thread-driven dispatch only).
  - Reduce per-task CPU cost (shorter date ranges, lighter strategy logic, fewer analyzers per run).
  - Add adaptive concurrency based on host CPU load and queue depth.

### 23.2 Memory Bottlenecks
- Cause:
  - CSV mode reads entire files into memory (`pd.read_csv`), then normalization creates additional copies.
  - API mode accumulates raw chunk rows, then creates DataFrames, cache sanitization copies, merge frames, and normalization outputs.
  - Backtest prep duplicates and reshapes frames before handing full datasets to Backtrader.
- Impact:
  - Peak memory is materially higher than final OHLCV frame size due to intermediate objects.
  - Large Zerodha ranges (especially minute-level multi-month/multi-year pulls) can cause memory pressure and GC churn.
  - High memory pressure increases latency variance and raises OOM risk under concurrent tasks.
- Possible mitigation:
  - Stream/chunk process large CSVs where possible; avoid unnecessary full-frame copies.
  - Normalize once and reuse canonical frames across stages.
  - Enforce tighter API date-window defaults for minute intervals.
  - Introduce memory-aware admission control (reject/defer tasks when projected memory exceeds threshold).

### 23.3 I/O Bottlenecks
- Cause:
  - Frequent disk I/O: CSV reads, cache reads/writes, result CSV/log writes.
  - `task_store.json` is rewritten atomically on every queue mutation/state transition.
  - `execution_metrics.json` is also atomically rewritten after task metric updates.
- Impact:
  - With larger queues, full JSON rewrite frequency becomes a non-trivial overhead.
  - Disk-bound environments see increased end-to-end latency and jitter.
  - UI refresh cycles can observe transient delays while persistence catches up.
- Possible mitigation:
  - Move task/metric persistence to append-friendly or indexed storage (SQLite/Postgres).
  - Batch queue state flushes instead of writing on every small transition.
  - Keep atomic writes but reduce payload size (incremental/delta persistence).
  - Separate hot-path runtime state from archival logs.

### 23.4 API Bottlenecks
- Cause:
  - Zerodha calls are network/rate-limit constrained; failures trigger retry/backoff loops.
  - Per-chunk retries (`MAX_RETRIES=5`) and exponential backoff increase tail latency on unstable links.
  - Chunking and safeguards impose hard bounds (`MAX_ALLOWED_CHUNKS=500`, gap-refetch pass/segment caps).
- Impact:
  - Cold API runs have high latency variance versus CSV mode.
  - Retry storms reduce effective throughput and can stall queue progression.
  - Large requested windows can fail early due to chunk safety limits.
- Possible mitigation:
  - Increase cache hit ratio (reuse valid/partial cache aggressively).
  - Add global API-rate coordination across workers.
  - Use adaptive chunk sizing by interval and observed failure rate.
  - Pre-warm likely datasets off critical user paths.

### 23.5 Queue Bottlenecks
- Cause:
  - Single in-memory queue per manager instance; no distributed broker.
  - Central `RLock` protects queue state transitions and persistence operations.
  - One local machine owns execution lifecycle and state files.
- Impact:
  - Horizontal scaling is not available; capacity is bounded by one host.
  - Under heavy enqueue/dequeue churn, lock contention and serialization overhead increase wait time.
  - Recovery/state coordination across multiple hosts is unsupported.
- Possible mitigation:
  - Externalize queue to Redis/RabbitMQ/Kafka with explicit worker leases.
  - Move to multi-process/multi-host workers with idempotent task claims.
  - Reduce lock scope and split state domains (queue vs metrics vs logs).

### 23.6 UI Bottlenecks
- Cause:
  - Streamlit rerun model refreshes script state frequently during active execution.
  - Terminal panel and execution polling rely on timed reruns (`sleep` + `st.rerun()` behavior).
  - Session-state-centric design is optimized for interactive single-session workflows, not high-concurrency multi-user loads.
- Impact:
  - Concurrent active users increase server CPU overhead and state churn.
  - Heavy execution sessions can make UI refresh less smooth under load.
  - Real-time responsiveness degrades before backend compute is fully saturated.
- Possible mitigation:
  - Decouple UI refresh cadence from backend task cadence (event push/websocket layer).
  - Shift long-running execution to backend service workers and keep UI thin.
  - Add per-session throttling and reduce rerun frequency during stable phases.

### 23.7 Overall Scaling Ceiling
- Cause:
  - Combined constraints from CPU-bound Backtrader runs, in-memory data handling, file-based persistence, API variability, and single-host queue design.
- Impact:
  - Current architecture is suitable for single-machine, low-to-moderate parallel batch execution, but not for high-scale distributed workloads.
  - Throughput and latency become increasingly sensitive to dataset size, retry rate, and queue length.
- Possible mitigation:
  - Introduce distributed task infrastructure, database-backed state, and dedicated execution services.
  - Add workload classification (light/heavy tasks) with separate worker pools.
  - Implement autoscaling and observability-driven concurrency controls.
- Realistic current limits:
  - Hard coded limits:
    - CSV input guard: `MAX_CSV_SIZE_MB = 200`.
    - API request guard: `MAX_ALLOWED_CHUNKS = 500`.
    - Gap refetch cap: `MAX_GAP_REFETCH_PASSES = 2`, `MAX_GAP_SEGMENTS_PER_PASS = 500`.
    - API per-chunk retry cap: `MAX_RETRIES = 5`.
  - Soft operational limits (single host):
    - `worker_count` is best kept near available CPU cores; larger values show diminishing returns.
    - Queue can hold many tasks, but very large backlogs increase JSON rewrite overhead and UI status latency.
    - Large minute-level multi-month/multi-year tasks are the first to hit memory and API-latency ceilings.

## 24. Architectural Trade-offs Summary

| Decision Made | Alternative | Why Chosen | Pros | Cons |
|---|---|---|---|---|
| File-based persistence (`task_store.json`, `execution_metrics.json`, CSV/log artifacts) | Database-backed persistence (SQLite/Postgres/Redis) | Minimize setup/ops burden and keep a single-machine developer workflow simple. | Easy to run locally, zero external infra dependency, human-readable artifacts, straightforward backup by copying files. | Weak concurrency/scaling characteristics, frequent full-file rewrites, weaker queryability/analytics, harder multi-user consistency, no built-in transactional guarantees across components. |
| Threaded worker orchestration (with optional subprocess hard-timeout execution) | Full multiprocessing pool for task execution | Threads are simple for queue orchestration and I/O phases; subprocess path added only where hard isolation is required. | Lower orchestration complexity, cheaper than process-per-task in light workloads, easy shared in-memory queue state. | CPU-bound scaling limited by GIL for in-process phases, contention under high load, subprocess timeout path adds spawn overhead and complexity. |
| Local execution on one host | Cloud/distributed execution workers | Prioritize fast iteration and predictable local control over infrastructure complexity. | Low cost, easy debugging, no deployment dependency for core backtests, deterministic local environment control. | No horizontal scaling, single-node failure domain, capacity constrained by one machine’s CPU/RAM/disk/network. |
| Streamlit UI | Custom web frontend (React/Vue + backend API) | Deliver Python-native UI quickly with minimal frontend stack overhead. | Very fast feature iteration, tight coupling with Python runtime, low frontend maintenance for small teams. | Rerun model is less efficient for high concurrency, limited UI architecture flexibility at scale, harder to support rich multi-user real-time UX patterns. |
| Backtrader execution engine | Custom proprietary backtest engine | Reuse mature framework primitives (broker, analyzers, strategy lifecycle) instead of rebuilding core mechanics. | Faster time-to-value, battle-tested abstractions, lower initial implementation risk. | Framework constraints limit deep engine-level optimization/customization, CPU-heavy bar loop, harder to tailor internals for specialized scaling/performance goals. |
| API fetch + local cache hybrid (Zerodha + cached CSV slices) | Fully stored historical data warehouse (always-local canonical dataset) | Balance freshness (API) with speed/resilience (cache) without building full data platform upfront. | Better freshness than static-only storage, cache reduces repeated API cost/latency, partial-cache fallback improves resilience. | API dependency remains a runtime risk (rate limits/auth/network), cache coherence/integrity handling adds complexity, cold-start latency is higher than fully-local datasets. |

## 25. Failure Impact Analysis

### 25.1 `API_ERROR`
- Scope of impact:
  - Primary: single task.
  - Secondary: worker time is consumed by retries/backoff while handling that task.
  - System-wide impact is indirect (queue slowdown), not immediate global failure.
- User impact:
  - Visible in UI terminal and task result (`FAILED`, `error_type=API_ERROR`, stage context).
  - Not a silent failure.
  - Retry behavior: automatic retry is enabled (retryable class).
- Recovery behavior:
  - Automatic: yes, up to configured retry limit.
  - Manual intervention: needed if persistent root cause (expired token, API outage, prolonged rate limiting).
- Risk level:
  - Medium.
- Worst-case scenario if repeated:
  - Many tasks repeatedly hit API retries, causing long queue delays and reduced throughput; execution may finish as `COMPLETED_WITH_ERRORS` with high failure count.

### 25.2 `DATA_ERROR`
- Scope of impact:
  - Usually single task (bad CSV, malformed/insufficient dataset, normalization failure).
  - Worker remains healthy and continues next tasks.
  - No direct full-system crash path.
- User impact:
  - Visible in UI terminal, task status, and failure log artifact.
  - Not silent.
  - Retry behavior: no automatic retry (non-retryable class).
- Recovery behavior:
  - Automatic: no.
  - Manual intervention: required (fix input file/data range/cache integrity, then rerun task).
- Risk level:
  - Low to Medium (low for isolated files, medium if shared dataset/cache is broadly bad).
- Worst-case scenario if repeated:
  - Large portions of queue fail quickly with deterministic errors; user gets fast feedback but low successful completion ratio.

### 25.3 `STRATEGY_ERROR`
- Scope of impact:
  - Single task in normal cases (strategy exception, invalid runtime behavior).
  - Worker and manager continue serving other tasks.
  - Can become multi-task impact if the same broken strategy is reused across many queued tasks.
- User impact:
  - Visible in terminal and structured result payload (`error_type=STRATEGY_ERROR`, stage usually `execution`).
  - Not silent.
  - Retry behavior: no automatic retry.
- Recovery behavior:
  - Automatic: no.
  - Manual intervention: required (fix strategy code/parameters, then rerun).
- Risk level:
  - Medium.
- Worst-case scenario if repeated:
  - System keeps running, but all tasks using that strategy fail, producing widespread `FAILED` results and little useful output.

### 25.4 `TIMEOUT_ERROR`
- Scope of impact:
  - Single task primary impact.
  - Subprocess hard-timeout path contains hung executions and prevents worker deadlock.
  - System remains available; queue progression continues after timeout handling.
- User impact:
  - Visible in terminal and structured task result.
  - Not silent.
  - Retry behavior: automatic retry is enabled.
- Recovery behavior:
  - Automatic: yes, until retry limit is exhausted.
  - Manual intervention: often needed if strategy/data workload is consistently too heavy for timeout settings.
- Risk level:
  - Medium to High (high when repeated on many heavy tasks).
- Worst-case scenario if repeated:
  - Repeated timeout/retry cycles create long queue stalls, poor throughput, and high resource churn while still eventually failing tasks.

### 25.5 `SYSTEM_ERROR`
- Scope of impact:
  - Typically starts as single-task failure classification for unexpected exceptions.
  - Potentially broader impact than other types because root causes may be infrastructure/runtime defects.
  - Worker loop has guard rails (`try/except`) to prevent immediate full-system collapse.
- User impact:
  - Visible in terminal and task results with `SYSTEM_ERROR`.
  - Not silent.
  - Retry behavior: no automatic retry by default (non-retryable class).
- Recovery behavior:
  - Automatic: generally no.
  - Manual intervention: required (code fix, environment repair, dependency/runtime correction).
- Risk level:
  - High.
- Worst-case scenario if repeated:
  - Many tasks fail across symbols/modes, turning runs into mostly failed outcomes; if the underlying bug is in a central path, practical system usability degrades severely until fixed.

### 25.6 Resilience Summary
- Failure containment:
  - Current design is task-centric; most failures are isolated to one task result.
  - Worker loop resilience prevents one crash from taking down the entire queue processor.
- Visibility quality:
  - Failures are surfaced through terminal logs, structured task payloads (`error_type`, `stage`, `error_message`), and persisted logs.
- Recovery model:
  - Automatic retry is intentionally narrow (`API_ERROR`, `TIMEOUT_ERROR`) to avoid wasting cycles on deterministic failures.
  - Other classes prioritize fast fail + explicit user/developer correction.

## 26. System Complexity Analysis

### 26.1 Data Normalization
- Time complexity:
  - Cleaning/coercion/filtering passes are mostly linear: `O(n)`.
  - Sorting by timestamp is `O(n log n)`, which usually dominates for large inputs.
  - Dedup/dropna checks are linear scans on top of that.
- Engineering interpretation:
  - For small datasets, normalization is fast.
  - As candle count grows, sort cost becomes the main driver.
  - Multiple normalization passes (fallback paths) add extra linear work.

### 26.2 Backtest Execution
- Time complexity:
  - Baseline strategy loop is approximately `O(n)` over bars for one run.
  - Real runtime is `O(n * c)` where `c` is per-bar strategy/indicator logic cost.
  - More indicators, heavier `next()` logic, and analyzer work increase `c`.
- Engineering interpretation:
  - Doubling bars roughly doubles runtime if strategy logic is unchanged.
  - Complex strategies can be much slower than simple ones even on same data.

### 26.3 Queue Processing
- Time complexity:
  - Total work is roughly proportional to task count: `O(t)` tasks.
  - Each task has its own execution cost (data + strategy runtime).
  - Pending-task selection currently scans queue state, so scheduler overhead grows with queue size.
- Parallel execution effect:
  - Multiple workers reduce wall-clock time for mixed workloads.
  - Speedup is sub-linear due to GIL-constrained phases, lock contention, I/O, and retry stalls.

### 26.4 API Fetch
- Time complexity:
  - Fetch work scales with chunk count: `O(k)` where `k` is number of API chunks.
  - Gap refetch adds additional segment fetches on top of base chunks.
  - Retry policy multiplies cost in failure cases (worst-case up to retry cap per chunk/segment).
- Engineering interpretation:
  - Larger date ranges and lower intervals increase `k`.
  - Network instability can turn one logical fetch into many API calls.

### 26.5 Memory Complexity
- Space complexity:
  - Core dataset footprint is `O(n)` with row count.
  - Practical peak memory is higher than one dataset because of intermediate copies (raw load, sanitize, normalize, merge, prepared feed).
- Engineering interpretation:
  - Memory grows roughly linearly with candles, but with a multiplier from copies.
  - Large API/CSV tasks can pressure memory sooner than expected from final output size alone.

### 26.6 Practical Scaling Behavior
- End-to-end runtime is driven by:
  - `O(n log n)` normalization (sort-heavy) +
  - `O(n * c)` backtest loop +
  - `O(k * retries)` API acquisition cost (API mode).
- In plain terms:
  - More rows always cost more.
  - Strategy complexity changes per-row cost materially.
  - API instability amplifies fetch time non-linearly.

## 27. LLM Context Summary
This codebase is a Streamlit-first algo-trading backtesting workbench that combines strategy editing, data selection, execution orchestration, and result visualization. The main UI entry is `Dashboard/dashboard.py`, with the heavy workflow in `Dashboard/Backtesting_page/Backtests_section.py`: users pick CSV or Zerodha API mode, choose a strategy file/class, execute tasks, and monitor progress/logs. Strategy lifecycle logic is split across `Features/strategy_selection.py`, `Features/strategy_editor.py`, and `Features/name_indicator_saver_versioner.py`, including safe rename/versioning and dirty-state handling. Execution runs through `Backtesting/execution_manager.py` (queue, retries, hard timeout subprocess mode, task persistence) into either `Backtesting/execution_engine.py` (CSV mode) or `Backtesting/api_based_execution_engine.py` (API mode), both converging on `Backtesting/backtest_core.py` where Backtrader execution, sell-guard wrapping, analyzers, and artifact writing happen. Data normalization and timezone safety are centralized in `Backtesting/data_normalizer.py` and mirrored by API fetch logic in `Features/zerodha_historical_data.py`, which implements chunked fetch, retry/backoff, missing-candle detection, and cache fallback behavior. Persistent operational state is file-based: `Data/Logs/task_store.json`, result logs/CSVs, and cached datasets in `Data/testing_data/Data_files`. No HTTP API or database exists; internal callable surfaces and Streamlit events are the integration boundary. For modifications, prioritize `Backtests_section.py`, `execution_manager.py`, `backtest_core.py`, and feature service modules under `Dashboard/Backtesting_page/Features`, while preserving path-safety checks, atomic writes, and session-state contract invariants.

---

