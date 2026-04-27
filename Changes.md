# Session Change Log (Full)

## 1) Zerodha Token Refresh at Runtime
- **Update:** Zerodha API authentication now reloads token data dynamically at runtime.
- **Why it was made:** The access token in `.env` was being cached in memory, so updated tokens were not picked up without restart.
- **What was done:**
  - Removed dependency on a stale cached Kite client instance in `Dashboard/Backtesting_page/Features/zerodha_historical_data.py`.
  - Added `get_kite_client()` to load `.env` with override, read latest token, create a fresh `KiteConnect`, and set access token per call.
  - Updated API call flow to fetch a fresh client per attempt and improved auth error handling for expired/invalid token cases.
- **Impact:** New `.env` token values are picked up without Docker restart; no shared stale client state across calls/threads.

## 2) Candlestick Chart Gap Removal (Non-Trading Hours)
- **Update:** Plotly candlestick x-axis now hides weekend and off-market gaps for intraday charts.
- **Why it was made:** Continuous datetime axes showed visual gaps between market sessions despite filtered data.
- **What was done:**
  - Added `fig.update_xaxes(rangebreaks=[...])` after layout setup in `Dashboard/dashboard_section.py`.
  - Added weekend break (`sat` to `mon`) and hour break (`15.5` to `9.25`).
  - Guarded to intraday mode so daily charts are unaffected.
- **Impact:** Intraday charts appear continuous (TradingView-like) while preserving zoom/pan/hover behavior.

## 3) Terminal Live Auto-Refresh
- **Update:** Execution terminal now auto-refreshes while runs are active.
- **Why it was made:** Streamlit panel did not rerender without user interaction, causing delayed log visibility.
- **What was done:**
  - Added controlled refresh state in `Dashboard/Backtesting_page/Features/terminal.py`.
  - Added 1-second throttled loop using `time.sleep(1.0)` + `st.rerun()`.
  - Refresh is gated by execution-active state and preserves filter widget state.
- **Impact:** Terminal behaves as a live log stream without manual filter toggles.

## 4) Strategy File Creation from UI
- **Update:** Added backend + UI flow to create new strategy files safely.
- **Why it was made:** Create button existed but had no file creation/validation logic.
- **What was done:**
  - Implemented file creation helpers in `Dashboard/Backtesting_page/Backtests_section.py`.
  - Added name validation (empty/invalid/duplicate checks) and safe create mode (`"x"`) to prevent overwrite.
  - Added default strategy template generation and list refresh/selection handling in UI.
- **Impact:** Users can create uniquely named strategy files directly from UI with overwrite protection.

## 5) Global Sell Guard for Invalid Sells
- **Update:** Added centralized sell-order guard in backtest pipeline.
- **Why it was made:** Strategies could issue sells without valid positions, creating unrealistic trade behavior.
- **What was done:**
  - Added guard layer in `Backtesting/backtest_core.py` around strategy order methods.
  - Enforced long-only sell checks and short-enabled behavior via explicit controls.
  - Added warning logs when invalid sell attempts are blocked.
- **Impact:** Prevents phantom sells and improves realism of simulated trade flow.

## 6) Sell Logic Separation: Long Exit vs Short Entry
- **Update:** Sell decision tree now cleanly distinguishes long exits, short entries, and short scaling.
- **Why it was made:** Previous overlap allowed ambiguous sell behavior when short mode was enabled.
- **What was done:**
  - Added tolerance-based position checks and short-scaling flags in `Backtesting/backtest_core.py`.
  - Implemented explicit branch logic:
    - long exit when position > tolerance
    - short entry from flat only if short enabled
    - short scale-in only if short scaling is enabled
  - Added explicit logs for interpretation:
    - `[OrderGuard] SELL interpreted as LONG EXIT`
    - `[OrderGuard] SELL interpreted as SHORT ENTRY`
- **Impact:** Trade intent is explicit, auditable, and less error-prone for long/short scenarios.

## 7) Closed Trade Exit Price Fix
- **Update:** Closed trade exit price calculation is now direction-aware and safer.
- **Why it was made:** Old formula was not direction-aware and could produce incorrect short-trade results.
- **What was done:**
  - Updated `_ClosedTradesAnalyzer` in `Backtesting/backtest_core.py`.
  - Used `trade.price` (entry), `trade.pnlcomm` (net pnl), and absolute qty with safe-division guards.
  - Applied direction-specific formula for long vs short exits.
- **Impact:** Reported exit prices are more realistic and consistent with long/short PnL direction.

## 8) IST Timezone Consistency Across Backtest Pipeline
- **Update:** Standardized timestamps to IST in analyzers/logs and data path.
- **Why it was made:** Backtrader date conversions can be naive and cause mixed timezone outputs.
- **What was done:**
  - Added IST conversion helpers in `Backtesting/backtest_core.py` and routed analyzer timestamps through them.
  - Updated feed preparation to use consistent timezone normalization before Backtrader ingestion.
  - Added explicit IST normalization helper path in `Backtesting/data_normalizer.py`.
- **Impact:** Trade/log/chart timestamps remain consistent and easier to correlate.

## 9) Data Normalization Loss Visibility
- **Update:** Added row-drop logging at each normalization stage.
- **Why it was made:** NaN/dedup/market-hours filtering previously dropped rows silently.
- **What was done:**
  - Added `_LOGGER` messages in `Backtesting/data_normalizer.py` for:
    - input row count
    - NaN drops
    - duplicate drops
    - market-hours filtered rows
    - final output row count
- **Impact:** Data-loss transparency improved; easier to audit preprocessing outcomes.

## 10) Retry Policy Hardened by Error Type
- **Update:** Retry now only happens for `TIMEOUT_ERROR` and `API_ERROR`.
- **Why it was made:** Retrying validation/data/strategy failures wastes time and resources.
- **What was done:**
  - Added `_is_retryable_failure(...)` in `Backtesting/execution_manager.py`.
  - Retry loop now exits early on non-retryable failures with explicit logs.
  - Corrected final retries-reported value to reflect actual retries used.
- **Impact:** Faster failure surfacing and cleaner retry behavior.

## 11) Strategy Execution Isolation Hardening
- **Update:** Backtrader execution wrapper now isolates warnings/exceptions and resets broker state.
- **Why it was made:** Better fault isolation was needed so bad strategies do not destabilize the system.
- **What was done:**
  - Added isolated run wrapper around `cerebro.run()` with warning capture in `Backtesting/backtest_core.py`.
  - Added broker reset routine before each run and reapplied cash/commission config.
  - Added controlled exception/logging path for execution failures.
- **Impact:** Reduced state leakage risk and improved resilience to strategy faults.

## 12) Immutable Task Execution Across Retries
- **Update:** Retry attempts now run on fresh deep-copied task payloads.
- **Why it was made:** Shared task mutation across attempts caused non-deterministic behavior.
- **What was done:**
  - Deep-copied task on enqueue in `Backtesting/execution_manager.py`.
  - Created immutable baseline + per-attempt deep copy in `_execute_with_retries`.
  - Kept hydration changes attempt-local and avoided input mutation in helper flows.
- **Impact:** Deterministic retries and cleaner task-state boundaries.

## 13) Hard Execution Timeout (Process-Level)
- **Update:** Replaced soft timeout detection with hard timeout enforcement.
- **Why it was made:** Post-execution timeout checks cannot stop hung strategies.
- **What was done:**
  - Added subprocess execution path in `Backtesting/execution_manager.py` using `_dispatch_task_with_hard_timeout(...)`.
  - Enforced timeout with `join(timeout)` and force-stop via `terminate()` then `kill()` fallback.
  - Removed obsolete soft timeout comparison block.
- **Impact:** Hung strategy executions are forcibly stopped; workers remain available.

## 14) Queue Wait-Time Metrics
- **Update:** Added `wait_time` tracking per task.
- **Why it was made:** Execution-only timing hid queue bottlenecks.
- **What was done:**
  - Calculated wait time from `created_at` and `start_time` with safe parsing/clamp in `Backtesting/execution_manager.py`.
  - Passed `wait_time` to metrics sink.
  - Updated `Backtesting/performance_tracker.py` to accept/store/load `wait_time` with backward-compatible fallback.
- **Impact:** Full latency visibility is now available (`wait_time + execution_time`).

## 15) Logging Exception Swallow Removed
- **Update:** Removed silent exception swallowing in execution logging helper.
- **Why it was made:** Silent logging failures hide diagnosable operational issues.
- **What was done:**
  - In `Backtesting/execution_engine.py`, replaced `except Exception: pass` with:
    - `except Exception as exc: print(f"[LoggingError] {exc}")`
- **Impact:** Logging failures are visible while still non-fatal.

## 16) CSV Memory Safety Guard
- **Update:** Added CSV file-size validation before loading into pandas.
- **Why it was made:** Large unbounded `pd.read_csv(...)` can risk memory exhaustion.
- **What was done:**
  - Added `MAX_CSV_SIZE_MB = 200.0` in `Backtesting/execution_engine.py`.
  - Added pre-read size check via `os.path.getsize(...)`.
  - Kept existing error pipeline and classified size failures as `DATA_ERROR`.
- **Impact:** Prevents oversized-file memory spikes and protects runtime stability.

## 17) Strategy Loading Security Hardening
- **Update:** Hardened dynamic strategy loading against path traversal and unsafe code patterns.
- **Why it was made:** Dynamic module execution without strict validation can execute unintended code.
- **What was done:**
  - In `Dashboard/Backtesting_page/Features/backtest_data_service.py`:
    - Added strict strategy path resolution and allowed-root enforcement.
    - Blocked traversal/symlink escape outside strategy directory.
    - Added AST checks for disallowed dynamic execution primitives and import override attempts.
    - Added class-name validation and safer `sys.modules` handling around module load.
  - In `Backtesting/execution_manager.py`:
    - Added safe-path resolution before class hydration in both regular and subprocess paths.
- **Impact:** Stronger strategy execution security boundaries with preserved valid strategy workflows.
