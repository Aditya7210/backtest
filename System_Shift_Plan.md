# System Shift Implementation Plan
## Algo Trading System — Full Stack Migration

**Date Written:** 2026-04-30  
**Target Stack:** React · Python/FastAPI · Cython · WebSocket · TradingView Lightweight Charts · MongoDB  
**Principle:** One file = One responsibility. Zero monoliths. Zero regressions.

---

## Table of Contents

1. [Pre-Execution Checks](#1-pre-execution-checks)
2. [What To Do & What NOT To Do](#2-what-to-do--what-not-to-do)
3. [Target Architecture](#3-target-architecture)
4. [New Directory Structure](#4-new-directory-structure)
5. [MongoDB Schema Design](#5-mongodb-schema-design)
6. [WebSocket Protocol Contract](#6-websocket-protocol-contract)
7. [Implementation Phases](#7-implementation-phases)
8. [Cython Migration Specifics](#8-cython-migration-specifics)
9. [Dead Code to Remove After Implementation](#9-dead-code-to-remove-after-implementation)
10. [Sanity Checklist Phases](#10-sanity-checklist-phases)
11. [Tests to Run After Implementation](#11-tests-to-run-after-implementation)
12. [Edge Cases Catalogue](#12-edge-cases-catalogue)
13. [End-to-End Risk Analysis](#13-end-to-end-risk-analysis)
14. [UI Implementation Specifications](#14-ui-implementation-specifications)
15. [Pandas-TA Migration (TA-Lib Replacement)](#15-pandas-ta-migration-ta-lib-replacement)

---

## 1. Pre-Execution Checks

**Run these before writing a single line of new code.**

### 1.1 Capture Baseline Behavior
- [ ] Run existing Streamlit dashboard — screenshot every page
- [ ] Start the collector and let it run for 10 minutes — save `collector_status.json`
- [ ] Run one complete backtest — save the output JSON
- [ ] Snapshot all 5 `Data/live_market/snapshots/*.json` files
- [ ] Record current CSV row counts: `equities_1min.csv`, `options_1min.csv`
- [ ] Note current calculation output for known instruments (NIFTY VWAP, PCR values)

### 1.2 Environment Verification
- [ ] Docker Desktop installed and running — this is the **only** runtime required for the system
- [ ] `docker --version` returns 24+ and `docker compose version` returns v2.x (not legacy `docker-compose`)
- [ ] Python 3.11+ installed locally — only needed to run migration scripts and build Cython before the first Docker build
- [ ] Node.js 20+ installed locally — only needed to run `npm install` for frontend during development
- [ ] `.env` file has valid `ZERODHA_API_KEY` and `ZERODHA_ACCESS_TOKEN`
- [ ] **MongoDB does NOT need to be installed on the host machine** — it runs exclusively inside Docker
- [ ] Cython builds inside Docker — host machine does not need MSVC or a C compiler

### 1.3 Dependency Audit
- [ ] Freeze current requirements: `pip freeze > requirements_old_snapshot.txt`
- [ ] List every import in Dashboard folder that will be deleted — confirm none bleed into backend
- [ ] Confirm `backtrader` version — pinned in requirements (it does not have frequent updates, avoid upgrading)
- [ ] Confirm `motor` (async MongoDB) is compatible with your `pymongo` version (`motor>=3.0` needs `pymongo>=4.0`)
- [ ] Confirm `fastapi[standard]>=0.111` is available (needed for built-in WebSocket)

### 1.4 Git Hygiene
- [ ] Create a new branch: `git checkout -b system-shift`
- [ ] Tag the current state: `git tag pre-shift-baseline`
- [ ] Confirm `.gitignore` includes `node_modules/`, `__pycache__/`, `*.so`, `*.pyd`, `build/`, `dist/`

### 1.5 Data Pre-Check
- [ ] Decide how far back historical data should go (e.g. 1 year) — this determines the Zerodha historical API calls needed to seed MongoDB
- [ ] List all instruments that need historical data for backtesting — map tradingsymbol → instrument_token using the instruments collection
- [ ] Verify Zerodha historical API access is working: `kite.historical_data(token, "2026-01-01", "2026-01-02", "minute")` returns rows
- [ ] Check Zerodha rate limits on historical API (60 requests/minute) — factor into ingestion planning
- [ ] Confirm `instrument_mapper_data/zerodha_instruments_latest.csv` is current — this is migrated to MongoDB `instruments` collection once, then the CSV is deleted
- [ ] One-time migration check: if live-market CSVs exist from before the shift, migrate them to MongoDB with the migration script — after that, CSVs are deleted and never written again

---

## 2. What To Do & What NOT To Do

### DO
- Keep the backtesting engine (`Backtesting/`) completely intact — it is production-quality and Backtrader-based
- Keep `LiveMarket/collector/` intact — only change where it writes (file → MongoDB)
- Keep `LiveMarket/calculations/` intact — only Cythonize the math kernels, keep orchestration in Python
- Treat MongoDB as the single source of truth for ALL data — live bars, historical bars, snapshots, backtest results, instruments
- Fetch historical backtest data from Zerodha API and store it directly in MongoDB `bars` collection on demand
- Use `motor` (async MongoDB driver) everywhere in FastAPI — never use synchronous `pymongo` in async routes
- Use Pydantic v2 models for all API request/response shapes
- Use `uvicorn` with `--reload` during development, `gunicorn + uvicorn workers` in production
- Maintain IST (Asia/Kolkata) timezone discipline throughout — every timestamp in MongoDB stored as UTC, displayed as IST in frontend
- Write one `__init__.py` per package folder that exports only its public interface
- Use environment variables for ALL secrets — never hardcode API keys
- Use MongoDB indexes on every field you query/sort/filter on
- Pin every package in `requirements.txt` to an exact version — `numpy==1.26.4` not `numpy>=1.26`. Unpinned deps silently break Cython at compile time and Backtrader at runtime

### DO NOT
- Do not use `pandas` inside Cython `.pyx` files — pass NumPy arrays instead
- Do not use `st.session_state` or any Streamlit artifact in the new codebase
- Do not have the collector write to files AND MongoDB simultaneously as a "transition" — pick one and commit
- Do not use CSV files as a data source anywhere in the production system — no CSV reads, no CSV writes, no CSV uploads. MongoDB is the only data store
- Do not store backtesting data in a separate collection — historical and live bars share the same `bars` collection, distinguished by a `data_source` field
- Do not let users upload CSV files for backtesting — the UI presents instruments and date ranges available in MongoDB; the user picks from what is there
- Do not call blocking I/O inside FastAPI `async def` routes — use `asyncio` or `run_in_executor`
- Do not store raw tick data in MongoDB — only aggregated 1-minute bars (ticks are too high volume)
- Do not use `subprocess` to run the collector from FastAPI — use a proper process manager (supervisor or a separate Docker service)
- Do not install MongoDB on the host machine — MongoDB runs only inside the `mongodb` Docker service; the host never connects to port 27017 directly
- Do not use `localhost` or `127.0.0.1` as the MongoDB host in any config — inside Docker Compose, the hostname is `mongodb` (the service name); use `MONGO_URI=mongodb://mongodb:27017/algo_trading`
- Do not put business logic in React components — all data transformation belongs in backend API
- Do not expose the MongoDB connection string or Zerodha credentials in frontend code or API responses
- Do not mix Backtrader's synchronous execution inside an async FastAPI endpoint — use `asyncio.run_in_executor` with a `ProcessPoolExecutor`
- Do not build a mega-file `api.py` — every route group gets its own file
- Do not commit `.env` with real credentials — rotate `ZERODHA_API_KEY`, `ZERODHA_ACCESS_TOKEN`, `ZERODHA_API_SECRET` before the first Docker deployment; add `.env` to `.gitignore` immediately

---

## 3. Target Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    REACT FRONTEND                        │
│  (Vite + TypeScript + TradingView Lightweight Charts)   │
│                                                          │
│  Pages: LiveMarket │ Backtests │ MarketPulse │ Auth      │
│  State: Zustand stores + React Query (REST cache)        │
│  Real-time: WebSocket client → auto-reconnect            │
└────────────────────┬─────────────────────────────────────┘
                     │ WebSocket (ws://) + REST (http://)
┌────────────────────▼─────────────────────────────────────┐
│                  FASTAPI BACKEND                          │
│                                                          │
│  ┌──────────────────┐  ┌────────────────────────────┐   │
│  │  REST Routes     │  │  WebSocket Manager         │   │
│  │  /api/market     │  │  /ws/live                  │   │
│  │  /api/backtests  │  │  /ws/backtest/{task_id}    │   │
│  │  /api/strategies │  │  Broadcaster (fan-out)     │   │
│  │  /api/instruments│  └────────────────────────────┘   │
│  │  /api/auth       │                                    │
│  └──────────────────┘                                    │
│                                                          │
│  ┌──────────────┐  ┌───────────────┐  ┌─────────────┐  │
│  │  Collector   │  │  Calculator   │  │  Backtester │  │
│  │  (process)   │  │  (process)    │  │  (process   │  │
│  │  KiteTicker  │  │  Cython math  │  │   pool)     │  │
│  │  → MongoDB   │  │  → MongoDB    │  │  Backtrader │  │
│  └──────────────┘  └───────────────┘  └─────────────┘  │
└────────────────────┬─────────────────────────────────────┘
                     │
┌────────────────────▼─────────────────────────────────────┐
│                    MONGODB                               │
│                                                          │
│  Collections:                                            │
│  bars_1min  │  bars_Nmin (3,5,10,15,30,60)              │
│  snapshots  │  instruments  │  backtest_results          │
│  collector_status  │  strategies                         │
└──────────────────────────────────────────────────────────┘
```

---

## 4. New Directory Structure

```
Algo_Trading_System/
│
├── backend/                          ← Python FastAPI server
│   ├── main.py                       # FastAPI app factory, startup/shutdown events
│   ├── config.py                     # Settings via pydantic-settings (reads .env)
│   │
│   ├── database/
│   │   ├── connection.py             # Motor AsyncIOMotorClient singleton
│   │   └── repositories/
│   │       ├── bar_repository.py     # Insert/query OHLCV bars (live + historical + resampled)
│   │       ├── snapshot_repository.py  # Insert/query calculation snapshots
│   │       ├── instrument_repository.py # Instrument master CRUD
│   │       ├── backtest_repository.py   # Backtest result CRUD
│   │       └── strategy_repository.py   # Strategy file metadata
│   │
│   ├── api/
│   │   ├── routes/
│   │   │   ├── market_data.py        # GET bars, GET snapshots, GET instruments
│   │   │   ├── historical_data.py    # POST ingest from Zerodha API, GET available data catalog
│   │   │   ├── backtests.py          # POST run (with MongoDB data selection), GET results, GET status
│   │   │   ├── strategies.py         # GET list, GET source, PUT update
│   │   │   ├── collector.py          # GET status, POST start, POST stop
│   │   │   └── auth.py               # POST zerodha credentials
│   │   └── websocket/
│   │       ├── manager.py            # ConnectionManager (register/unregister clients)
│   │       └── broadcaster.py        # Broadcasts snapshot updates to all connected clients
│   │
│   ├── collector/                    ← Migrated from LiveMarket/collector/
│   │   ├── token_loader.py           # CHANGED: reads instrument tokens from MongoDB instruments collection (not CSV)
│   │   ├── ws_collector.py           # CHANGED: writes bars to MongoDB (pymongo sync) instead of CSV; removes CSV atomic-write pattern
│   │   ├── bar_aggregator.py         # Unchanged — threading/Lock model preserved exactly
│   │   ├── prev_close_loader.py      # CHANGED: writes prev_close to MongoDB prev_close collection; preserves expected_tokens/loaded_tokens/missing_tokens fields
│   │   └── trading_calendar.py       # Unchanged
│   │
│   ├── calculations/                 ← Migrated from LiveMarket/calculations/
│   │   ├── runner.py                 # CHANGED: reads trading_date from MongoDB collector_status (not COLLECTOR_STATUS_PATH JSON); passes DataFrames to calculators instead of file paths
│   │   ├── vwap_calculator.py        # CHANGED: accepts equity/options DataFrames as args (not reads CSV internally); calls Cython compute_vwap(); formula uses close*volume (not typical price)
│   │   ├── ad_calculator.py          # CHANGED: accepts equities_df + prev_close_dict as args (not reads CSV/JSON internally); all filter logic preserved
│   │   ├── pcr_calculator.py         # CHANGED: accepts options_df as arg (not reads CSV internally); Zerodha quotes fallback path preserved unchanged
│   │   ├── atm_oi_calculator.py      # CHANGED: accepts equities_df + options_df as args (not reads CSV internally)
│   │   ├── bar_resampler.py          # CHANGED: reads 1min bars from MongoDB; preserves origin="start", closed="left", label="left", iloc[:-1] drop for incomplete current bar
│   │   ├── vix_reader.py             # CHANGED: reads VIX bars from MongoDB instead of vix_1min.csv
│   │   └── snapshot_writer.py        # CHANGED: writes to MongoDB snapshots collection via snapshot_repository
│   │
│   ├── indicators/                   ← New module (replaces Dashboard/Live_market_data_visuals/features/indicator_engine.py)
│   │   ├── sma.py                    # Calls Cython sma kernel; SMA(5,20,50) on close prices
│   │   ├── rsi.py                    # Calls Cython rsi kernel; RSI(14) with fillna(50) for NaN
│   │   └── vwap.py                   # Calls Cython vwap kernel; typical price = (H+L+C)/3 × volume (for chart overlay — different from vwap_calculator.py which uses close×volume for snapshot)
│   │
│   ├── cython_math/                  ← New Cython layer
│   │   ├── setup.py                  # Cython build: python setup.py build_ext --inplace
│   │   ├── vwap.pyx                  # Typed VWAP kernel (NumPy arrays in, float out)
│   │   ├── rsi.pyx                   # Typed RSI kernel
│   │   ├── sma.pyx                   # Typed SMA kernel
│   │   └── __init__.py               # Exports compiled kernels with Python fallback
│   │
│   ├── backtesting/                  ← Migrated from Backtesting/ (mostly unchanged)
│   │   ├── core.py                   # (was backtest_core.py) — Unchanged
│   │   ├── data_loader.py            # Replaces data_normalizer.py — queries MongoDB, returns DataFrame with TITLE-CASE columns (Date, Open, High, Low, Close, Volume) + IST DatetimeIndex to match execution_engine.py expectations exactly
│   │   ├── execution_engine.py       # CHANGED: replace pd.read_csv(path) + normalize() call with data_loader.get_dataframe(); rest unchanged
│   │   ├── execution_manager.py      # CHANGED: task dict passes {instrument_token, timeframe, date_from, date_to} instead of csv_path; task_store.json path resolved to /app/Data/Logs/ with mkdir(exist_ok=True)
│   │   └── performance_tracker.py    # Unchanged
│   │
│   ├── historical/                   ← New module for on-demand historical data ingestion
│   │   ├── zerodha_fetcher.py        # Fetches OHLCV from Zerodha historical API → inserts into bars collection
│   │   └── ingestion_manager.py      # Handles rate limiting, chunking by date, deduplication
│   │
│   ├── models/                       ← Pydantic v2 models (API contracts)
│   │   ├── bar.py                    # OHLCVBar, OHLCVBarCreate
│   │   ├── snapshot.py               # VWAPSnapshot, ADSnapshot, PCRSnapshot, etc.
│   │   ├── backtest.py               # BacktestRequest, BacktestResult, Trade
│   │   ├── instrument.py             # Instrument, InstrumentMaster
│   │   └── collector.py              # CollectorStatus
│   │
│   ├── utils/
│   │   ├── time_utils.py             # IST conversion, market hour checks (migrated)
│   │   └── data_extractor.py         # (migrated from LiveMarket/)
│   │
│   └── process_manager/
│       ├── collector_process.py      # Start/stop collector subprocess
│       └── calculator_process.py     # Start/stop calculator subprocess
│
├── frontend/                         ← React application
│   ├── package.json
│   ├── vite.config.ts
│   ├── tsconfig.json
│   └── src/
│       ├── main.tsx                  # React root
│       ├── App.tsx                   # Router setup (React Router v6)
│       │
│       ├── pages/
│       │   ├── LiveMarketPage.tsx    # Live market visuals
│       │   ├── BacktestPage.tsx      # Backtest run + results
│       │   ├── MarketPulsePage.tsx   # Collector/calculator control
│       │   ├── DashboardPage.tsx     # Backtest result history
│       │   └── AuthPage.tsx          # Zerodha auth
│       │
│       ├── components/
│       │   ├── layout/
│       │   │   ├── Navbar.tsx        # Top navigation
│       │   │   └── PageWrapper.tsx   # Consistent padding/theme
│       │   ├── charts/
│       │   │   ├── CandlestickChart.tsx  # TradingView Lightweight Charts
│       │   │   ├── LineChart.tsx         # PCR, A/D, VIX (lightweight charts)
│       │   │   └── OIHeatmap.tsx         # Strike × OI table with color coding
│       │   ├── market/
│       │   │   ├── InstrumentSelector.tsx
│       │   │   ├── TimeframeSelector.tsx
│       │   │   ├── OptionChainTable.tsx
│       │   │   ├── ADRatioPanel.tsx
│       │   │   ├── PCRPanel.tsx
│       │   │   ├── VIXPanel.tsx
│       │   │   └── ATMStraddlePanel.tsx
│       │   ├── backtesting/
│       │   │   ├── StrategyEditor.tsx    # Monaco editor
│       │   │   ├── DataSelector.tsx
│       │   │   ├── BacktestParams.tsx
│       │   │   ├── BacktestResults.tsx
│       │   │   └── BacktestTerminal.tsx  # WebSocket streaming logs
│       │   ├── collector/
│       │   │   ├── StatusBadge.tsx
│       │   │   └── CollectorControls.tsx
│       │   └── common/
│       │       ├── LoadingSpinner.tsx
│       │       ├── ErrorBoundary.tsx
│       │       └── Tooltip.tsx
│       │
│       ├── hooks/
│       │   ├── useWebSocket.ts       # Manages WS connection with auto-reconnect
│       │   ├── useMarketData.ts      # Subscribes to live snapshots via WS
│       │   ├── useBacktestStream.ts  # Streams backtest terminal output via WS
│       │   └── useQuery.ts           # React Query wrappers for REST calls
│       │
│       ├── services/
│       │   ├── api.ts                # All REST API calls (typed, centralized)
│       │   └── websocket.ts          # WebSocket client singleton
│       │
│       ├── stores/
│       │   ├── marketStore.ts        # Zustand: live snapshots, selected instrument
│       │   └── backtestStore.ts      # Zustand: backtest state, results
│       │
│       └── types/
│           ├── market.ts             # OHLCVBar, Snapshot, Instrument types
│           └── backtest.ts           # BacktestResult, Trade, Metrics types
│
├── cython_build/                     ← Compiled .pyd/.so files land here (gitignored)
│
├── Strategies/                       ← Unchanged
│   └── Strategy_codes/
│
├── Data/                             ← Keep for migration scripts, delete daily CSVs after migration
│   └── testing_data/                 ← Keep for backtesting CSV uploads
│
├── Sanity_Checklist/                 ← Unchanged structure, results updated during testing
│
├── scripts/
│   ├── migrate_csv_to_mongo.py       # One-time migration of existing live-market CSVs → MongoDB (run once, then delete CSVs)
│   └── seed_instruments.py           # One-time: load zerodha_instruments_latest.csv → MongoDB instruments collection (then delete CSV)
│
├── docker-compose.yml                # Updated: backend + frontend + MongoDB services
├── Dockerfile.backend                # Python FastAPI service
├── Dockerfile.frontend               # Node build + nginx serve
├── requirements.txt                  # Updated with FastAPI, motor, cython, etc.
├── .env                              # Secrets (gitignored)
└── System_Shift_Plan.md              # This file
```

---

## 5. MongoDB Schema Design

### Collection: `bars`
Single unified collection for ALL OHLCV data — live bars from the collector, resampled bars, and historical bars fetched from Zerodha API for backtesting. No CSVs anywhere.

```json
{
  "_id": ObjectId,
  "timestamp": ISODate("2026-04-29T04:18:00Z"),  // UTC always
  "trading_date": "2026-04-29",                   // for date-range queries
  "timeframe": "1min",                             // "1min","3min","5min","10min","15min","30min","60min"
  "instrument_type": "equity",                     // "equity" | "option" | "vix"
  "instrument_token": 193804545,
  "tradingsymbol": "RAJOOENG",
  "open": 60.25,
  "high": 60.58,
  "low": 60.14,
  "close": 60.35,
  "volume": 24143.0,
  "data_source": "live",   // "live" (from ws_collector) | "historical" (from Zerodha historical API) | "resampled" (derived from 1min)
  // option-only fields (null for equity/vix)
  "strike": null,
  "expiry": null,
  "option_type": null,
  "oi": null
}
```

**Indexes:**
```javascript
{ instrument_token: 1, timeframe: 1, timestamp: -1 }            // primary query index
{ trading_date: 1, timeframe: 1, instrument_type: 1 }           // date-range queries
{ tradingsymbol: 1, timeframe: 1, timestamp: -1 }               // symbol lookup
{ instrument_token: 1, timeframe: 1, trading_date: 1 }          // backtest data availability query
```

**Unique constraint (prevents duplicate inserts from retries):**
```javascript
{ instrument_token: 1, timeframe: 1, timestamp: 1 } — unique: true
```

### Collection: `snapshots`
Stores the latest calculated snapshot for each snapshot type.

```json
{
  "_id": ObjectId,
  "snapshot_type": "vwap",    // "vwap" | "ad" | "pcr" | "atm_oi" | "vix"
  "generated_at": ISODate,
  "trading_date": "2026-04-29",
  "data": { /* snapshot-specific payload — same structure as current JSON files */ }
}
```

**Index:** `{ snapshot_type: 1, trading_date: -1 }` (unique on type+date for latest)

### Collection: `instruments`
Instrument master — replaces `zerodha_instruments_latest.csv`.

```json
{
  "_id": ObjectId,
  "instrument_token": 193804545,
  "tradingsymbol": "RAJOOENG",
  "exchange": "NSE",
  "segment": "NSE",
  "instrument_type": "EQ",
  "strike": null,
  "expiry": null,
  "lot_size": 1,
  "tick_size": 0.05,
  "downloaded_at": ISODate
}
```

**Index:** `{ instrument_token: 1 }` (unique), `{ tradingsymbol: 1 }`

### Collection: `collector_status`
Single document, upserted on each status update.

```json
{
  "_id": "singleton",
  "collector": {
    "status": "running",
    "pid": 12345,
    "started_at": ISODate,
    "trading_date": "2026-04-29",
    "tokens_subscribed": 2500,
    "bars_written": 150000,
    "last_tick_at": ISODate,
    "last_error": null
  },
  "calculator": {
    "status": "running",
    "pid": 12346,
    "last_run_at": ISODate,
    "last_error": null
  }
}
```

### Collection: `backtest_results`

```json
{
  "_id": ObjectId,
  "task_id": "uuid-string",
  "strategy_name": "TrendPullbackStrategy",
  "symbol": "NIFTY50",
  "data_file": "NIFTY50_2025.csv",
  "config": { "initial_capital": 100000, "commission": 0.0003 },
  "status": "SUCCESS",
  "started_at": ISODate,
  "completed_at": ISODate,
  "final_value": 123456.78,
  "metrics": { /* Sharpe, drawdown, win_rate, etc. */ },
  "trades": [ /* array of trade objects */ ]
}
```

### Collection: `prev_close`
Daily previous close prices. Keys are **string** token IDs (matches Zerodha API response format). `ad_calculator.py` expects string keys — do not change to int.

```json
{
  "_id": "2026-04-29",
  "trading_date": "2026-04-29",
  "generated_at": ISODate,
  "expected_tokens": 2500,
  "loaded_tokens": 2487,
  "missing_tokens": 13,
  "data": { "193804545": 100000.0, "6068225": 1190.0 }
}
```

**Index:** `{ trading_date: -1 }` (unique — use trading_date as `_id` for guaranteed uniqueness and fast lookup)

---

## 6. WebSocket Protocol Contract

All WebSocket messages are JSON. The client connects to `ws://host:8000/ws/live`.

### Server → Client (Push)

```json
// Snapshot update (every 60s after calculator runs)
{
  "type": "snapshot_update",
  "payload": {
    "snapshot_type": "vwap",  // or "ad" | "pcr" | "atm_oi" | "vix"
    "generated_at": "2026-04-29T10:00:00+05:30",
    "data": { /* snapshot data */ }
  }
}

// Collector status update (every 5s)
{
  "type": "collector_status",
  "payload": {
    "status": "running",
    "bars_written": 150000,
    "last_tick_at": "2026-04-29T10:00:00+05:30"
  }
}

// New bar (every 1min, for the active instrument)
{
  "type": "new_bar",
  "payload": {
    "instrument_token": 193804545,
    "timeframe": "1min",
    "bar": { "timestamp": "...", "open": 60.25, "high": 60.58, "low": 60.14, "close": 60.35, "volume": 24143 }
  }
}
```

### Client → Server (Subscribe)

```json
// Subscribe to bars for a specific instrument + timeframe
{
  "type": "subscribe_bars",
  "payload": { "instrument_token": 193804545, "timeframe": "5min" }
}

// Unsubscribe
{
  "type": "unsubscribe_bars",
  "payload": { "instrument_token": 193804545 }
}
```

### Backtest WebSocket: `ws://host:8000/ws/backtest/{task_id}`

```json
// Server streams log lines
{ "type": "log", "payload": { "line": "2026-04-29 10:00:01 | INFO | Running backtest..." } }
{ "type": "complete", "payload": { "task_id": "...", "status": "SUCCESS" } }
{ "type": "error", "payload": { "message": "Strategy failed to load" } }
```

---

## 7. Implementation Phases

### Phase 0 — Foundation Setup (No Functional Change)
**Goal:** Docker Compose stack scaffolded and all three services boot cleanly.

- [ ] Write the initial `docker-compose.yml` with three services: `mongodb`, `backend`, `frontend` (see Phase 5 for full config)
- [ ] Write a minimal `Dockerfile.backend` that just starts `uvicorn` — flesh it out in Phase 3
- [ ] Write a minimal `Dockerfile.frontend` that runs `npm run dev` on port 5173 — replace with nginx in Phase 5
- [ ] Add `MONGO_URI=mongodb://mongodb:27017/algo_trading` to `.env` — the hostname `mongodb` resolves inside Docker Compose networking
- [ ] Run `docker compose up mongodb` first — verify the MongoDB container starts and data volume mounts
- [ ] Run `docker compose up` — verify all three services start without errors
- [ ] Create `backend/config.py` — reads `MONGO_URI` from env, never hardcodes a hostname
- [ ] Create `backend/database/connection.py` — motor `AsyncIOMotorClient` singleton using `config.MONGO_URI`
- [ ] Verify MongoDB ping from inside the backend container: `docker compose exec backend python -c "from backend.database.connection import db; print('ok')"`
- [ ] Install frontend deps: `cd frontend && npm install` — these run on the host during dev, inside Docker for prod

**Edge cases:**
- Motor client must be created once at startup, not per-request — use FastAPI lifespan context
- `mongodb` hostname only resolves from within the Docker network — migration scripts run via `docker compose run` so they share the same network
- MongoDB data volume (`mongo_data`) persists across container restarts — never use a bind-mount to a local path for the DB data directory
- On first `docker compose up`, the MongoDB container takes ~3s to be ready; backend must retry connection on startup (motor does this automatically, but add a startup health check)

---

### Phase 1 — One-Time Migration + Historical Data Seeding
**Goal:** MongoDB fully populated. After this phase, every CSV and JSON data file is deleted. The system never reads from or writes to any file for data again.

#### Step 1.A — Migrate Existing CSVs (if any)
Only needed if the live-market collector has already written CSV files before the shift.

- [ ] Run via Docker: `docker compose run --rm -v ./Data:/app/Data backend python scripts/migrate_csv_to_mongo.py`
- [ ] `scripts/migrate_csv_to_mongo.py` logic:
  - Walk `Data/live_market/daily/YYYY-MM-DD/`
  - For each `equities_Xmin.csv`, `options_Xmin.csv`, `vix_Xmin.csv`:
    - Detect instrument_type from filename
    - Parse timestamp column → UTC ISODate
    - Set `data_source: "live"`, set `trading_date`, set `timeframe`
    - Bulk upsert 1000 rows/batch — key: `(instrument_token, timeframe, timestamp)`
  - Print summary: X files processed, Y rows inserted, Z duplicates skipped
- [ ] Verify: row count in MongoDB matches CSV row count ± 0
- [ ] **Delete all CSVs**: `rm -rf Data/live_market/daily/`

#### Step 1.B — Seed Instruments
- [ ] Run: `docker compose run --rm -v ./Data:/app/Data backend python scripts/seed_instruments.py`
- [ ] Script reads `zerodha_instruments_latest.csv`, bulk upserts into `instruments` collection
- [ ] Verify: `GET /api/market/instruments?q=NIFTY` returns results
- [ ] **Delete the CSV**: `rm Data/instrument_mapper_data/zerodha_instruments_latest.csv` — instruments are now in MongoDB; future refreshes go direct to MongoDB via Zerodha API

#### Step 1.C — Historical Data Ingestion (Backtest Data)
This replaces the old workflow of downloading CSVs from Zerodha. Data now goes straight from Zerodha API into MongoDB.

- [ ] Build `backend/historical/zerodha_fetcher.py`:
  - Accepts: `instrument_token`, `tradingsymbol`, `from_date`, `to_date`, `interval` ("minute"|"3minute"|"5minute"|...)
  - Calls `kite.historical_data()` — Zerodha returns max 60 days per request for minute data
  - Chunks date range into ≤60-day windows automatically
  - Inserts into `bars` collection with `data_source: "historical"`
  - Upserts on `(instrument_token, timeframe, timestamp)` — safe to re-run
- [ ] Build `backend/historical/ingestion_manager.py`:
  - Rate-limits to 60 requests/minute (Zerodha limit)
  - Reports progress: `{ fetched: N, inserted: M, skipped_duplicates: K }`
  - Handles Zerodha API errors (token expired, instrument not found) without crashing — returns error per instrument
- [ ] Expose via API: `POST /api/historical/ingest` (see Phase 3.5)
- [ ] Test: ingest 1 month of NIFTY 50 minute data — verify bars appear in MongoDB

**Edge cases:**
- Timestamps from Zerodha historical API come as `datetime` objects in IST — convert to UTC before inserting
- Zerodha returns at most 60 days per minute-interval request — chunking is mandatory, not optional
- `data_source: "historical"` must be set — do not let historical bars overwrite live bars with wrong source tag
- Migration script runs only once — after that, `scripts/` folder can be deleted (or kept as ops tools)

---

### Phase 2 — Cython Math Layer
**Goal:** Core math kernels (VWAP, RSI, SMA) compiled and tested.

- [ ] Create `backend/cython_math/vwap.pyx`:
  ```cython
  import numpy as np
  cimport numpy as np
  def compute_vwap(np.ndarray[double, ndim=1] prices,
                   np.ndarray[double, ndim=1] volumes) -> np.ndarray:
      cdef int n = prices.shape[0]
      cdef np.ndarray[double, ndim=1] result = np.empty(n)
      cdef double cum_pv = 0.0, cum_v = 0.0
      for i in range(n):
          cum_pv += prices[i] * volumes[i]
          cum_v += volumes[i]
          result[i] = cum_pv / cum_v if cum_v > 0 else prices[i]
      return result
  ```
- [ ] Create `backend/cython_math/rsi.pyx` — typed RSI with Wilder smoothing
- [ ] Create `backend/cython_math/sma.pyx` — typed rolling SMA
- [ ] Create `backend/cython_math/setup.py`:
  ```python
  from Cython.Build import cythonize
  import numpy
  from setuptools import setup, Extension
  exts = [Extension("*", ["*.pyx"], include_dirs=[numpy.get_include()])]
  setup(ext_modules=cythonize(exts, compiler_directives={"language_level": "3"}))
  ```
- [ ] Build: `cd backend/cython_math && python setup.py build_ext --inplace`
- [ ] Create `backend/cython_math/__init__.py`:
  - Try to import compiled modules; fall back to pure Python if `.so/.pyd` not found
  - This ensures tests pass even without Cython compiled (CI safety net)
- [ ] Validation: run Cython output vs pandas output on same data — assert difference < 1e-10
- [ ] Add build step to `Dockerfile.backend`

**Edge cases:**
- Windows needs MSVC (`cl.exe`) — document this requirement
- NumPy version mismatch during compile breaks at runtime — pin NumPy in requirements
- Cython `.so` files are Python-version specific — do NOT commit them, always build from source
- Empty arrays (no volume) must not cause division by zero — guard with `if cum_v > 0`

---

### Phase 3 — FastAPI Backend + WebSocket Server
**Goal:** Full backend running. All data served from MongoDB. Collector + calculator work unchanged except writing to MongoDB.

#### Phase 3.1 — App Setup
- [ ] `backend/main.py`: FastAPI app with lifespan (connect MongoDB on start, close on shutdown)
- [ ] Mount all route modules under `/api`
- [ ] Mount WebSocket endpoints at `/ws/live` and `/ws/backtest/{task_id}`
- [ ] Configure CORS for `http://localhost:5173` (Vite dev server)

#### Phase 3.2 — Repositories
- [ ] `bar_repository.py`: `insert_bars()`, `get_bars(token, timeframe, date_from, date_to)`, `get_latest_bar(token, timeframe)`, `get_available_catalog()` (returns list of distinct instruments + date ranges + timeframes that have data — used to populate the backtest data selector UI)
- [ ] `snapshot_repository.py`: `upsert_snapshot(type, data)`, `get_latest_snapshot(type)`, `get_snapshot_history(type, date)`
- [ ] `instrument_repository.py`: `find_by_token(token)`, `find_by_symbol(symbol)`, `search(query)`
- [ ] `backtest_repository.py`: `create(task_id, config)`, `update_result(task_id, result)`, `get_all()`, `get_by_id(task_id)`

#### Phase 3.3 — Collector Refactor
- [ ] `backend/collector/ws_collector.py`:
  - Replace `pd.DataFrame(...).to_csv()` pattern with synchronous `pymongo` bulk upsert (NOT motor — collector is threaded, not async)
  - Use `pymongo.MongoClient` from `backend/database/sync_connection.py`
  - Preserve `threading.Lock()` around bar flush — unchanged from current code
  - Preserve volume delta logic: `volume_delta = session_volume - prev_session_volume`; zero negative deltas
  - Preserve first-minute-skip: `_first_minute_seen` dict — do NOT write the very first bar seen per token
  - Status: upsert `collector_status` MongoDB doc (singleton `_id="singleton"`) every 5s instead of writing JSON file; preserve all existing status fields including `updated_at` (used by health check with 45s stale tolerance)
  - Remove `CREATE_NO_WINDOW` flag and all Windows-specific subprocess flags (Docker runs Linux)
- [ ] `backend/collector/token_loader.py`: replace `pd.read_csv("zerodha_instruments_latest.csv")` with `pymongo` query to `instruments` collection; preserve exact return format (equity_tokens, options_meta dict, etc.) — all downstream code depends on this structure
- [ ] `backend/collector/prev_close_loader.py`: write to MongoDB `prev_close` collection; preserve `expected_tokens`, `loaded_tokens`, `missing_tokens` diagnostic fields; keep string token keys (e.g. `"193804545"`) — `ad_calculator.py` expects string keys
- [ ] After each bar flush: call `broadcaster.notify_new_bars(bars)` — the broadcaster pushes to subscribed WebSocket clients

#### Phase 3.4 — Calculator Refactor (critical: change the data access pattern, not the math)

**Refactoring pattern for ALL calculators:** Extract the data-reading code out of each calculator into `runner.py`, pass DataFrames as arguments. Each calculator's math logic is untouched.

- [ ] `backend/calculations/runner.py`:
  - Read trading date from MongoDB `collector_status` singleton doc (field: `collector.trading_date`), NOT from `COLLECTOR_STATUS_PATH` JSON file
  - Query MongoDB for today's equities 1min bars → `equities_df`
  - Query MongoDB for today's options 1min bars → `options_df`
  - Query MongoDB for today's VIX 1min bars → `vix_df`
  - Read today's `prev_close` doc from MongoDB → convert to `dict[str, float]` (string token keys preserved)
  - Pass these DataFrames/dicts as arguments to each calculator (do not let calculators read from MongoDB themselves)
- [ ] `backend/calculations/vwap_calculator.py`: change signature to `compute_all_timeframes(equities_df, options_df, vix_df)` instead of reading CSVs; replace pandas `(close*volume).cumsum() / volume.cumsum()` with Cython `compute_vwap(prices_array, volumes_array)`; round to 4 decimals (preserved)
- [ ] `backend/calculations/ad_calculator.py`: change signature to `compute(equities_df, prev_close_dict)` instead of reading CSVs/JSON; preserve index spot symbol filter; preserve string-key comparison for prev_close lookup
- [ ] `backend/calculations/pcr_calculator.py`: change signature to `compute_from_csv(options_df)` → `compute_from_dataframe(options_df)`; preserve Zerodha quotes fallback path `compute_from_quotes()` — this path reads live quotes, does not use files, is unchanged
- [ ] `backend/calculations/atm_oi_calculator.py`: change signature to `compute(equities_df, options_df)` instead of reading CSVs
- [ ] `backend/calculations/bar_resampler.py`:
  - Query MongoDB for 1min bars with `timestamp < utcnow() - 90s` (replaces `iloc[:-1]` drop for incomplete bar)
  - Preserve pandas resample params: `origin="start"`, `closed="left"`, `label="left"`
  - Write resampled bars back to MongoDB with `data_source: "resampled"` using upsert
- [ ] `backend/calculations/snapshot_writer.py`: call `snapshot_repository.upsert_snapshot()` instead of atomic JSON write; snapshot data structure is identical to current JSON files
- [ ] `backend/calculations/vix_reader.py`: query MongoDB VIX 1min bars instead of reading `vix_1min.csv`
- [ ] After each calculation cycle: call `broadcaster.broadcast_snapshot(type, data)`

#### Phase 3.5 — REST Routes

**Market Data**
- [ ] `GET /api/market/bars?token=X&timeframe=Y&date=Z` → bars for chart
- [ ] `GET /api/market/snapshots/{type}` → latest snapshot
- [ ] `GET /api/market/instruments?q=NIFTY` → instrument search (against MongoDB `instruments` collection)
- [ ] `GET /api/market/option-chain?underlying=NIFTY&date=Z` → full option chain

**Historical Data Ingestion** (`backend/api/routes/historical_data.py`)
- [ ] `POST /api/historical/ingest` — body: `{ instrument_token, tradingsymbol, from_date, to_date, timeframe }` → triggers Zerodha API fetch → inserts into MongoDB `bars`. Returns `{ job_id, status: "started" }`
- [ ] `GET /api/historical/ingest/{job_id}` → progress: `{ fetched, inserted, skipped_duplicates, status }`
- [ ] `GET /api/historical/catalog` → returns what data is available in MongoDB for backtesting:
  ```json
  [
    {
      "instrument_token": 256265,
      "tradingsymbol": "NIFTY 50",
      "timeframes_available": ["1min", "5min", "15min"],
      "date_from": "2025-01-02",
      "date_to": "2026-04-29",
      "total_bars": 98400,
      "data_source": "historical"
    }
  ]
  ```
- [ ] `DELETE /api/historical/data?token=X&timeframe=Y&date_from=A&date_to=B` → remove a date range from MongoDB (for re-ingestion if data was bad)

**Backtests** (`backend/api/routes/backtests.py`)
- [ ] `POST /api/backtests/run` — body now takes MongoDB data selection, NOT a CSV path:
  ```json
  {
    "strategy_name": "TrendPullbackStrategy",
    "instrument_token": 256265,
    "timeframe": "5min",
    "date_from": "2025-01-01",
    "date_to": "2025-12-31",
    "initial_capital": 100000,
    "commission": 0.0003,
    "enforce_market_hours": true
  }
  ```
  Backend queries `bars` collection → builds DataFrame → passes to Backtrader
- [ ] `GET /api/backtests/{task_id}` → result or status
- [ ] `GET /api/backtests` → list all results

**Chart Indicators** (`backend/api/routes/market_data.py` — add query param)
- [ ] `GET /api/market/bars?token=X&timeframe=Y&date=Z&indicators=sma,rsi,vwap` → bars enriched with indicator columns
  - Backend calls `backend/indicators/sma.py`, `rsi.py`, `vwap.py` (Cython-backed) and appends columns to response
  - VWAP for chart overlay uses typical price formula `(H+L+C)/3 × volume` — **different** from `vwap_calculator.py` which uses `close × volume` for the snapshot

**Strategies, Collector, Auth**
- [ ] `GET /api/strategies` → list strategy files
- [ ] `GET /api/strategies/{name}/source` → strategy source code
- [ ] `PUT /api/strategies/{name}` → update strategy source (writes to `Strategies/Strategy_codes/`)
- [ ] `GET /api/collector/status` → current collector+calculator status
- [ ] `POST /api/collector/start` → start collector subprocess
- [ ] `POST /api/collector/stop` → stop collector subprocess
- [ ] `POST /api/auth/zerodha` → save API key + access token to `.env`; validate token is not already expired before saving

#### Phase 3.6 — WebSocket Manager
- [ ] `backend/api/websocket/manager.py`: track all connected clients, subscription state per client
- [ ] `backend/api/websocket/broadcaster.py`: fan-out to subscribed clients on snapshot update or new bar
- [ ] Handle client disconnect gracefully (remove from registry)
- [ ] Ping/pong keepalive every 30s to detect dead connections

**Edge cases:**
- Backtest must run in `ProcessPoolExecutor` (not thread pool) — Backtrader is CPU-bound and not thread-safe
- The backtest subprocess receives a serialized DataFrame (via `multiprocessing.Queue` or temp in-memory pickle) — it does NOT reconnect to MongoDB itself; the main process fetches the data and passes it in
- WebSocket connections must not block the main event loop — all DB reads inside WS handlers must be `await`ed
- Strategy source update must sanitize the filename (prevent path traversal: `../../` attacks)
- `POST /api/backtests/run` must check data availability before starting: query `bars` for the requested token+timeframe+date range — if 0 bars found, return HTTP 400 with message "No data in MongoDB for this selection. Use /api/historical/ingest first."
- `POST /api/collector/start` must check if already running (via MongoDB status doc) before spawning subprocess
- MongoDB connection pooling: motor default pool size (100) is fine for dev; tune for prod

---

### Phase 4 — React Frontend
**Goal:** Full React frontend replacing Streamlit, feature-parity on all 5 pages.

#### Phase 4.1 — Project Setup
- [ ] Vite + React + TypeScript: `npm create vite@latest frontend -- --template react-ts`
- [ ] Install: `lightweight-charts @tanstack/react-query zustand react-router-dom axios`
- [ ] Install: `@monaco-editor/react` (strategy editor — replaces streamlit-ace)
- [ ] Install: `tailwindcss` + `shadcn/ui` components (replaces streamlit-shadcn-ui)
- [ ] Set up React Router v6 with 5 routes matching current Streamlit pages
- [ ] Set up Zustand stores: `marketStore`, `backtestStore`
- [ ] Set up React Query with base URL pointing to FastAPI backend

#### Phase 4.2 — WebSocket Client
- [ ] `frontend/src/services/websocket.ts`: WebSocket singleton with:
  - Auto-reconnect (exponential backoff, max 30s)
  - Event emitter pattern for message routing
  - Subscribe/unsubscribe for bar streams
- [ ] `frontend/src/hooks/useWebSocket.ts`: connects to `/ws/live`, dispatches to Zustand on message

#### Phase 4.3 — Page: Live Market
- [ ] `InstrumentSelector.tsx`: dropdown populated from `GET /api/market/instruments`
- [ ] `TimeframeSelector.tsx`: 1min/3min/5min/10min/15min/30min/60min buttons
- [ ] `CandlestickChart.tsx`: TradingView Lightweight Charts `createChart()`, subscribe to `new_bar` WS events to append bars in real time
- [ ] `OptionChainTable.tsx`: fetches from `GET /api/market/option-chain`, updates on `snapshot_update` WS event for PCR
- [ ] `ADRatioPanel.tsx`: renders A/D ratio as area chart using Lightweight Charts, updates on WS
- [ ] `PCRPanel.tsx`: line chart for NIFTY PCR + BANKNIFTY PCR
- [ ] `ATMStraddlePanel.tsx`: straddle value vs VIX over time
- [ ] `VIXPanel.tsx`: current VIX display + mini line chart

#### Phase 4.4 — Page: Backtests
- [ ] `StrategyEditor.tsx`: Monaco editor with Python syntax highlighting, fetches source via `GET /api/strategies/{name}/source`, saves via `PUT /api/strategies/{name}`
- [ ] `DataSelector.tsx`: **No file picker. No CSV.** Instead:
  - Calls `GET /api/historical/catalog` on mount — populates a dropdown of available instruments in MongoDB
  - User selects instrument → timeframe → date range (date picker, constrained to available range from catalog)
  - Shows data summary: "98,400 bars available · 2025-01-02 to 2026-04-29"
  - If no data available for the selection, shows inline button: "Fetch from Zerodha" → calls `POST /api/historical/ingest` with a progress indicator
- [ ] `HistoricalIngestPanel.tsx`: separate panel on the same page for power users to request data ingestion for any instrument + date range not yet in MongoDB. Shows progress via polling `GET /api/historical/ingest/{job_id}`
- [ ] `BacktestParams.tsx`: form for initial_capital, commission, enforce_market_hours
- [ ] `BacktestTerminal.tsx`: connects to `ws://host/ws/backtest/{task_id}`, streams log lines in real-time
- [ ] `BacktestResults.tsx`: displays metrics + trade table from `GET /api/backtests/{task_id}`

#### Phase 4.5 — Page: Market Pulse
- [ ] `CollectorControls.tsx`: Start/Stop buttons calling `POST /api/collector/start|stop`
- [ ] `StatusBadge.tsx`: receives real-time status from `collector_status` WS events

#### Phase 4.6 — Page: Dashboard (Backtest History)
- [ ] Calls `GET /api/backtests` to list all results
- [ ] Renders equity curve using Lightweight Charts (line chart of cumulative PnL)
- [ ] Trades table with sortable columns

#### Phase 4.7 — Page: Auth
- [ ] Form: API key + access token input
- [ ] POST to `POST /api/auth/zerodha`
- [ ] Show success/error state

**Edge cases:**
- TradingView Lightweight Charts: must call `chart.timeScale().fitContent()` after bulk data load
- TradingView candlestick series requires data sorted ascending by `time` — sort before setting data
- WebSocket reconnect: on reconnect, re-fetch the last N bars to fill the gap, then resume streaming
- Monaco editor: disable TypeScript validation for Python files
- React Query: set `staleTime: 60_000` for bar data (it changes infrequently), `staleTime: 0` for snapshots

---

### Phase 5 — Docker & Deployment (Final)
**Goal:** Single `docker compose up --build` starts the entire system. MongoDB is fully inside Docker — no host installation needed.

- [ ] `Dockerfile.backend`:
  ```dockerfile
  FROM python:3.11-slim
  # build-essential only needed for Cython compilation — no external C library dependencies (TA-Lib removed)
  RUN apt-get update && apt-get install -y build-essential && rm -rf /var/lib/apt/lists/*
  WORKDIR /app
  COPY requirements.txt .
  RUN pip install --no-cache-dir -r requirements.txt
  COPY . .
  # Build Cython modules inside the container (no host C compiler needed)
  RUN cd backend/cython_math && python setup.py build_ext --inplace
  CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
  ```

- [ ] `Dockerfile.frontend`:
  ```dockerfile
  # Stage 1: build
  FROM node:20-slim AS builder
  WORKDIR /app
  COPY frontend/package*.json ./
  RUN npm ci
  COPY frontend/ .
  RUN npm run build
  # Stage 2: serve with nginx
  FROM nginx:alpine
  COPY --from=builder /app/dist /usr/share/nginx/html
  COPY nginx.conf /etc/nginx/conf.d/default.conf
  EXPOSE 80
  ```

- [ ] `nginx.conf` (in project root):
  ```nginx
  server {
      listen 80;
      root /usr/share/nginx/html;
      index index.html;
      # Proxy API and WebSocket to backend
      location /api/ { proxy_pass http://backend:8000; }
      location /ws/ {
          proxy_pass http://backend:8000;
          proxy_http_version 1.1;
          proxy_set_header Upgrade $http_upgrade;
          proxy_set_header Connection "upgrade";
      }
      # SPA fallback
      location / { try_files $uri /index.html; }
  }
  ```

- [ ] `docker-compose.yml` (final, production-ready):
  ```yaml
  version: "3.9"
  services:
    mongodb:
      image: mongo:7
      container_name: algo_mongodb
      restart: unless-stopped
      volumes:
        - mongo_data:/data/db        # Named volume — data persists across restarts
      expose:
        - "27017"                    # Only reachable inside Docker network, NOT on host
      healthcheck:
        test: ["CMD", "mongosh", "--eval", "db.adminCommand('ping')"]
        interval: 10s
        timeout: 5s
        retries: 5

    backend:
      build:
        context: .
        dockerfile: Dockerfile.backend
      container_name: algo_backend
      restart: unless-stopped
      env_file: .env                 # Contains ZERODHA creds + MONGO_URI
      environment:
        - MONGO_URI=mongodb://mongodb:27017/algo_trading
      depends_on:
        mongodb:
          condition: service_healthy  # Wait until MongoDB is ready before starting
      volumes:
        - ./Strategies:/app/Strategies   # Strategy files editable without rebuild
        # No Data/ volume — all data lives in MongoDB, not on the host filesystem
      ports:
        - "8000:8000"

    frontend:
      build:
        context: .
        dockerfile: Dockerfile.frontend
      container_name: algo_frontend
      restart: unless-stopped
      depends_on:
        - backend
      ports:
        - "3000:80"                  # Access app at http://localhost:3000

  volumes:
    mongo_data:                      # Named volume managed by Docker — survives container deletion
  ```

- [ ] **Important: `mongo_data` is a named Docker volume, not a host folder.** To back it up: `docker run --rm -v algo_trading_system_mongo_data:/data -v $(pwd):/backup mongo:7 tar czf /backup/mongo_backup.tar.gz /data`
- [ ] Remove old `entrypoint.sh` (Streamlit-specific)
- [ ] Create `entrypoint.backend.sh` if startup tasks are needed (instrument seed on first run):
  ```bash
  #!/bin/sh
  if [ "$RUN_SEED" = "1" ]; then
    python scripts/seed_instruments.py
  fi
  exec uvicorn backend.main:app --host 0.0.0.0 --port 8000
  ```
- [ ] Single command to start everything: `docker compose up --build`
- [ ] Single command to start in background: `docker compose up -d --build`
- [ ] View logs: `docker compose logs -f backend`
- [ ] MongoDB shell access (for debugging only): `docker compose exec mongodb mongosh algo_trading`

---

## 8. Cython Migration Specifics

### What Gets Cythonized

| Module | Current | Cython Target | Reason |
|--------|---------|---------------|--------|
| `vwap_calculator.py` | pandas cumsum | `vwap.pyx` | Called every 60s on all tokens × all timeframes |
| `indicator_engine.py` (SMA) | `rolling().mean()` | `sma.pyx` | Called in frontend data transform path |
| `indicator_engine.py` (RSI) | manual rolling gain/loss | `rsi.pyx` | RSI is a tight loop, benefits from static typing |

### What Does NOT Get Cythonized

| Module | Reason |
|--------|--------|
| `ad_calculator.py` | Simple pandas groupby — not a hot loop |
| `pcr_calculator.py` | Simple aggregation — not performance-critical |
| `bar_resampler.py` | Pandas resample is already C-backed |
| `backtest_core.py` | Backtrader handles its own loop — not worth Cythonizing |

### Cython Build Process in CI / Docker
```bash
cd backend/cython_math
python setup.py build_ext --inplace
# Compiled .so (Linux) or .pyd (Windows) files appear in current directory
```

### Fallback Strategy
`cython_math/__init__.py` must do:
```python
try:
    from .vwap import compute_vwap
except ImportError:
    from ._fallback import compute_vwap_pure  as compute_vwap
```
This means pure Python fallbacks must exist in `_fallback.py` — identical math, no Cython.

---

## 9. Dead Code to Remove After Implementation

**Remove only after the new system is fully tested and verified.**

| File / Folder | Reason for Removal |
|---|---|
| `Dashboard/` (entire folder) | Replaced by React frontend |
| `LiveMarket/` (entire folder) | Migrated to `backend/collector/` and `backend/calculations/` |
| `main.py` (root) | Dependency checker — Docker handles this now |
| `entrypoint.sh` | Streamlit-specific entrypoint |
| `Data/live_market/daily/*/` (all CSVs) | Migrated to MongoDB — delete after migration verified |
| `Data/live_market/snapshots/*.json` | Replaced by MongoDB snapshots collection |
| `Data/live_market/collector_status.json` | Replaced by MongoDB |
| `Data/live_market/process_state.json` | Replaced by MongoDB |
| `Data/testing_data/` (entire folder) | No CSV-based backtesting — data lives in MongoDB |
| `Data/instrument_mapper_data/zerodha_instruments_latest.csv` | Seeded into MongoDB instruments collection — delete after seed verified |
| `Data/instrument_mapper_data/zerodha_instruments_archive.csv` | No longer needed |
| `Backtesting/` (root folder) | Migrated to `backend/backtesting/` |
| `Backtesting/data_normalizer.py` | Replaced by `backend/backtesting/data_loader.py` which reads MongoDB |
| `Dashboard/Backtesting_page/Features/data_selection_feature.py` | CSV file picker — deleted with Dashboard |
| `Dashboard/Backtesting_page/Features/live_data_selector.py` | CSV-based data selection — deleted with Dashboard |
| `Dashboard/Backtesting_page/Features/zerodha_csv_downloader.py` | Replaced by `backend/historical/zerodha_fetcher.py` which writes to MongoDB |
| `Dashboard/Backtesting_page/Features/zerodha_historical_data.py` | Rolled into `backend/historical/zerodha_fetcher.py` |
| `Data/testing_data/data_pull_scripts/adani_power_data.py` | CSV download script — no longer needed |
| `Data/testing_data/data_pull_scripts/download_16_stocks.py` | CSV download script — replaced by `POST /api/historical/ingest` |
| `Dashboard/dashboard_page/dashboard_features/talib_indicators.py` | Replaced by `backend/indicators/indicator_engine.py` using `pandas_ta` — see Section 15 |
| `requirements.txt` packages: `streamlit`, `streamlit-elements`, `streamlit-option-menu`, `streamlit-extras`, `streamlit-shadcn-ui`, `streamlit-toggle-switch`, `streamlit-ace` | Streamlit fully removed |
| `requirements.txt` package: `ta-lib` | Replaced by `pandas-ta` — TA-Lib C library compilation removed from Dockerfile |
| Any `st.` imports in remaining Python code | Streamlit imports must be zero |
| Any `import talib` or `from talib` imports | TA-Lib fully removed |
| Any `pd.read_csv()` calls in non-migration Python code | CSV reads must be zero after Phase 1 |
| Any `df.to_csv()` calls outside `scripts/` | CSV writes must be zero in production code |

**Final verification commands (must all return zero results):**
```bash
grep -r "import streamlit" backend/
grep -r "read_csv" backend/ | grep -v "scripts/"
grep -r "to_csv" backend/ | grep -v "scripts/"
grep -r "open.*\.csv" backend/ | grep -v "scripts/"
```

---

## 10. Sanity Checklist Phases

Each phase below maps to a result file in `Sanity_Checklist/Sanity_Checklist_Result/`.

### Phase 1 — Core Foundations
- [ ] FastAPI app starts without errors: `uvicorn backend.main:app --reload`
- [ ] MongoDB connection succeeds on startup (check logs for "MongoDB connected")
- [ ] All environment variables loaded: print `config.MONGO_URI`, `config.ZERODHA_API_KEY` (masked)
- [ ] Cython modules import without error: `python -c "from backend.cython_math import compute_vwap"`
- [ ] React dev server starts: `cd frontend && npm run dev` — no TypeScript errors

### Phase 2 — Data Layer
- [ ] Migration script ran successfully (if CSVs existed): row count in MongoDB matches CSV row count ± 0
- [ ] All existing CSVs deleted — `Data/live_market/daily/` is empty or removed
- [ ] Instrument seed ran: `GET /api/market/instruments?q=NIFTY` returns NIFTY50 and NIFTY BANK
- [ ] `zerodha_instruments_latest.csv` deleted — instruments served from MongoDB only
- [ ] Historical ingestion test: `POST /api/historical/ingest` for NIFTY 50, last 30 days, 1min — bars appear in MongoDB
- [ ] `GET /api/historical/catalog` returns the ingested instrument with correct date range and bar count
- [ ] Query test: `GET /api/market/bars?token=256265&timeframe=1min&date=2026-04-28` returns non-empty array
- [ ] Snapshot: `GET /api/market/snapshots/vwap` returns latest VWAP snapshot with data
- [ ] VWAP Cython output matches pandas output on same data (diff < 1e-8)
- [ ] No CSV files anywhere in the project (except `scripts/` folder during transition)

### Phase 3 — Collector & Calculator
- [ ] Start collector: `POST /api/collector/start` → status changes to "running"
- [ ] Wait 2 minutes — verify bars are appearing in MongoDB (`bars` collection count increases)
- [ ] Stop collector: `POST /api/collector/stop` → status changes to "stopped"
- [ ] Start calculator — wait 60s — verify snapshots updated in MongoDB
- [ ] Verify VWAP values match previous Streamlit dashboard for same instrument/timeframe

### Phase 4 — WebSocket
- [ ] Connect to `ws://localhost:8000/ws/live` — receive first `collector_status` message within 5s
- [ ] Subscribe to bars for one instrument — receive `new_bar` message at next minute boundary
- [ ] Verify all 5 snapshot types broadcast after calculator run
- [ ] Disconnect and reconnect — verify no server-side memory leak (check subscriptions cleared)
- [ ] Connect 10 simultaneous clients — verify all receive broadcasts

### Phase 5 — React Frontend
- [ ] Live Market page loads: candlestick chart shows correct historical bars
- [ ] Live Market page: chart updates when new bar arrives via WebSocket
- [ ] Option chain table shows correct CE/PE data for NIFTY
- [ ] A/D ratio chart shows current advance/decline counts
- [ ] Instrument selector searches and filters correctly
- [ ] Timeframe switching reloads chart with correct data

### Phase 6 — Backtesting
- [ ] Strategy editor loads existing strategy source code
- [ ] Edit strategy and save — verify file saved to disk
- [ ] Run backtest — terminal streams log output in real time via WebSocket
- [ ] Backtest completes — result appears in dashboard page
- [ ] Result metrics (PnL, Sharpe, drawdown) match previous Streamlit output for same data+strategy

### Phase 7 — Market Pulse
- [ ] Start/stop collector from React UI — status badge updates within 5s
- [ ] Start/stop calculator from React UI — status badge updates

### Phase 8 — Auth
- [ ] Submit Zerodha credentials via React form — confirm `.env` file updated
- [ ] Invalid token shows error message in UI

### Phase 9 — End-to-End Workflow
- [ ] Full trading day simulation:
  1. Start collector → bars flow into MongoDB
  2. Calculator runs → snapshots update in MongoDB
  3. WebSocket pushes to React → charts update live
  4. Run backtest while collector active → no interference
  5. Stop collector at market close → status reflects correctly
- [ ] Compare all snapshot values against pre-shift baseline snapshots (captured in Pre-Execution Checks)
- [ ] Zero Streamlit imports anywhere in `backend/`

### Phase 10 — Production Hardening
- [ ] Full cold-start: `docker compose down -v && docker compose up --build` — all 3 services start cleanly from scratch (including empty MongoDB)
- [ ] Verify `mongo_data` named volume persists after `docker compose down` (without `-v`): `docker compose down && docker compose up` — data must still be there
- [ ] Restart only the backend: `docker compose restart backend` while collector is running — verify collector reconnects/resumes
- [ ] Kill the MongoDB container: `docker compose stop mongodb` — backend must log error but not crash; restart MongoDB and backend must reconnect automatically
- [ ] Kill the MongoDB container while a bar insert is in flight — verify no data corruption or crash
- [ ] WebSocket clients auto-reconnect after backend restart
- [ ] Memory: run system for 4 hours — check for memory leaks in backend (`docker stats algo_backend`)
- [ ] Load: 20 simultaneous WebSocket clients — no message drops, latency < 200ms
- [ ] Verify MongoDB port 27017 is NOT exposed to host (`expose` not `ports` in docker-compose) — `curl localhost:27017` from host must fail
- [ ] Distribution test: copy only `docker-compose.yml`, `Dockerfile.backend`, `Dockerfile.frontend`, `nginx.conf`, `.env`, and `Strategies/` to a clean machine — `docker compose up --build` must produce a fully working system

---

## 11. Tests to Run After Implementation

### Unit Tests (per module)

```
backend/tests/
├── test_cython_vwap.py            # Cython VWAP == pandas VWAP for 10k rows
├── test_cython_rsi.py             # Cython RSI == pandas RSI
├── test_cython_sma.py             # Cython SMA == pandas SMA
├── test_bar_aggregator.py         # MinuteBarAggregator produces correct OHLCV
├── test_bar_repository.py         # Insert + query bars — run via: docker compose run --rm backend pytest tests/
├── test_snapshot_repository.py    # Upsert + fetch snapshots — uses same containerized MongoDB
├── test_data_loader.py            # MongoDB → DataFrame for Backtrader (replaces test_data_normalizer)
├── test_historical_ingest.py      # Zerodha API mock → MongoDB insert, date chunking, deduplication
├── test_trading_calendar.py       # Holiday detection, market hours
├── test_vwap_calculator.py        # VWAP orchestration (uses Cython kernel)
├── test_ad_calculator.py          # A/D ratio correctness
├── test_pcr_calculator.py         # PCR correctness
├── test_backtest_core.py          # Existing tests — must all still pass
└── test_api_routes.py             # FastAPI TestClient for all REST endpoints including /historical
```

### Key Test Cases

**Cython Math:**
- Input: `prices=[100,101,102]`, `volumes=[1000,2000,3000]` → VWAP matches manual calculation
- Input: all-zero volume array → no division by zero, returns prices
- Input: empty arrays → returns empty array, no crash
- Input: 100,000 rows → Cython is at least 5× faster than pandas

**Bar Aggregator:**
- Ticks arriving in same minute → bars aggregated correctly
- Tick arriving at minute boundary → previous bar completed, new bar started
- Out-of-order tick (late tick from previous minute) → handled without corrupting current bar

**Data Loader (MongoDB → Backtrader):**
- Query returns 0 bars → `data_loader.py` raises `NoDataError`, backtest returns HTTP 400
- Query returns bars with gaps (missing dates/minutes) → DataFrame is returned as-is; Backtrader handles gaps natively
- All bars are outside market hours in MongoDB → should not happen (Zerodha historical API already filters), but `data_loader.py` filters as a safety net
- Large date range (1 year of 1min data ≈ 90,000 rows) → DataFrame construction must complete in < 2s

**Historical Ingestion:**
- Request for date range > 60 days of minute data → chunked automatically into ≤60-day batches
- Zerodha rate limit hit (60 req/min) → ingestion_manager sleeps and retries, does not crash
- Duplicate ingestion of same date range → upsert prevents duplicate bars, count reported as `skipped_duplicates`
- Access token expired during ingestion → return partial result + error message; do not silently stop

**API Routes:**
- `GET /api/market/bars` with no data for date → returns empty array, HTTP 200 (not 404)
- `POST /api/backtests/run` when 0 bars in MongoDB for selection → HTTP 400: "No data available. Ingest first."
- `POST /api/backtests/run` with invalid strategy name → HTTP 400 with clear message
- `PUT /api/strategies/../../../secret.env` → HTTP 400 (path traversal blocked)
- `GET /api/market/snapshots/vwap` when no snapshot exists → HTTP 404
- `GET /api/historical/catalog` when MongoDB is empty → returns empty array, HTTP 200

**WebSocket:**
- Client connects → receives `collector_status` within 5s
- Client subscribes to non-existent token → no crash, no message sent
- 50 clients connected, 1 snapshot broadcast → all 50 receive it within 1s

### Frontend Tests

```
frontend/src/__tests__/
├── CandlestickChart.test.tsx      # Renders without crash, accepts bar data
├── OptionChainTable.test.tsx      # Renders CE/PE rows correctly
├── DataSelector.test.tsx          # Shows catalog from API, disables run if no data, shows ingest CTA
├── HistoricalIngestPanel.test.tsx # Ingest form submits correctly, shows progress
├── useWebSocket.test.ts           # Reconnect logic tested with mock WS server
├── api.test.ts                    # All API call functions return typed responses
```

### Regression Tests (Preserve Existing Behavior)

| Feature | Test Method |
|---|---|
| VWAP values | Compare MongoDB snapshot vs old `vwap_snapshot.json` baseline (captured in Pre-Execution Checks) |
| PCR values | Compare MongoDB vs old `pcr_snapshot.json` baseline |
| A/D ratio | Compare MongoDB vs old `ad_snapshot.json` baseline |
| Backtest PnL | Ingest same historical data into MongoDB, run same strategy — `final_value` must match within 0.01% of old CSV-based result |
| Option chain | Compare CE/PE OI values vs old snapshot baseline |
| No CSV reads | `grep -r "read_csv" backend/` returns zero results (excluding `scripts/`) |

### Performance Benchmarks

| Metric | Target |
|---|---|
| VWAP calculation (all tokens, 1 timeframe) | < 500ms (Cython) |
| Bar query (1 instrument, 1 day, 1min) | < 50ms |
| Snapshot fetch (latest) | < 20ms |
| WebSocket broadcast to 20 clients | < 100ms |
| Full calculation cycle (all snapshots) | < 30s |
| Backtest (1 strategy, 1 year data) | < 5s (unchanged from before) |

---

## 12. Edge Cases Catalogue

| Area | Edge Case | Handling |
|---|---|---|
| **Market Hours** | Pre-market ticks (before 9:15 IST) | `trading_calendar.py` gates collector start |
| **Market Hours** | Post-market ticks (after 15:30 IST) | Bar aggregator discards ticks |
| **Market Hours** | NSE holiday — collector runs | `trading_calendar.py` exits early, status set to "holiday" |
| **Zerodha API** | Access token expired mid-day | Collector catches auth error, sets status "auth_error", broadcasts to frontend |
| **Zerodha API** | KiteTicker reconnect during collection | Bar aggregator holds partial bar; on reconnect, resumes accumulation |
| **MongoDB** | Connection lost during bar insert | Motor retries automatically; if persistent, collector logs error and continues ticking |
| **MongoDB** | Disk full (Docker volume) | Motor insert fails; collector catches exception, logs, continues (does not crash); alert via status doc |
| **MongoDB** | Backend uses `localhost` instead of `mongodb` as hostname | Connection refused inside Docker — always read URI from `MONGO_URI` env var, never hardcode |
| **MongoDB** | Named volume deleted with `docker compose down -v` | All data lost — document that `-v` flag is destructive; back up before running |
| **Docker** | Port 27017 accidentally set to `ports` instead of `expose` | MongoDB reachable from host — security issue; must use `expose` only |
| **Docker** | Backend starts before MongoDB is ready | Use `depends_on: condition: service_healthy` with a MongoDB healthcheck — motor connection will succeed on first try |
| **Cython** | `.pyx` not compiled (fresh clone) | Fallback to pure Python via `__init__.py` try/except |
| **Cython** | NumPy version mismatch | Build fails — CI must test Cython compilation |
| **WebSocket** | Client disconnects mid-backtest | Server removes client from broadcaster; backtest continues |
| **WebSocket** | Server restarts mid-session | Frontend auto-reconnects; re-fetches last N bars; resumes subscription |
| **Backtesting** | Strategy file has syntax error | AST validation catches it before execution; returns HTTP 400 |
| **Backtesting** | Strategy takes > 60s | ProcessPoolExecutor timeout kills task; returns error status |
| **Backtesting** | User selects date range with 0 bars in MongoDB | `POST /api/backtests/run` returns HTTP 400: "No data. Use /api/historical/ingest first." |
| **Backtesting** | User selects partial date range (some days missing) | Allowed — Backtrader handles gaps; warn user in response: `{ "data_gaps": ["2025-03-15", "2025-03-16"] }` |
| **Historical Ingest** | Zerodha max 60-day limit for minute data | `ingestion_manager.py` auto-chunks; never let caller worry about this |
| **Historical Ingest** | Same date range requested twice | Upsert on unique index `(instrument_token, timeframe, timestamp)` — no duplicates, second call is a no-op |
| **Historical Ingest** | Token does not exist in Zerodha | Zerodha returns error — propagate to frontend as HTTP 422 with clear message |
| **Historical Ingest** | Ingest during market hours (live data also writing) | Both collector and ingestion write to same `bars` collection — unique index prevents conflicts; `data_source` field distinguishes them |
| **Data Catalog** | `GET /api/historical/catalog` on empty MongoDB | Returns `[]`, HTTP 200 — UI shows "No data yet. Use the ingest panel." |
| **React UI** | User opens DataSelector before any data ingested | Show empty state with CTA: "No instruments available. Ingest historical data first." |
| **React Charts** | TradingView receives unsorted bars | Sort by `time` ascending before calling `series.setData()` |
| **React Charts** | Empty bar array on chart init | Guard with `if (bars.length === 0) return` before calling `setData` |
| **Options** | Expiry date in past | `pcr_calculator.py` filters by active expiries only |
| **Options** | Strike not found for ATM | `atm_oi_calculator.py` returns nearest available strike with flag `is_exact: false` |
| **Data Migration** | CSV column `oi` missing | `migrate_csv_to_mongo.py` defaults to `null` — not 0 (0 would skew PCR) |
| **Data Migration** | Duplicate bars from re-run | Unique index on `(instrument_token, timeframe, timestamp)` prevents duplicates |
| **Instrument Mapper** | Bar in MongoDB has token not in instruments collection | Log warning, continue — do not crash; bar is still valid |
| **Process Manager** | `POST /api/collector/start` called twice | Check MongoDB status before spawning; return "already running" |
| **Auth** | `.env` write fails (permissions) | Return HTTP 500 with clear message; do not silently fail |
| **Timezone** | DST changes (India has no DST) | IST is always UTC+5:30 — no DST handling needed, but document this |

---

*Implementation order must follow the phases in sequence. Do not start Phase 4 (React) before Phase 3 (FastAPI) is functional — the frontend has no mock layer and depends on real API responses.*

*All sanity checklist results must be written to `Sanity_Checklist/Sanity_Checklist_Result/Phase_N_Result.md` after each phase is verified.*

---

## 13. End-to-End Risk Analysis

**How to use this section:** Every error below is tagged either **[GUARANTEED]** (will happen without the guardrail) or **[POTENTIAL]** (may happen under specific conditions). For each: read the guardrail before touching the code, run the pre-patch checks before every related commit, and run the sanity check after the patch is applied.

---

### E-01 [GUARANTEED] — Backtrader DataFrame Format Mismatch

**What breaks:** `backend/backtesting/data_loader.py` queries MongoDB and builds a DataFrame to pass to Backtrader via `bt.feeds.PandasData`. Backtrader requires a very specific format: `datetime` must be the **index** (not a column), index must be a timezone-aware `DatetimeIndex`, and columns must be exactly named `open`, `high`, `low`, `close`, `volume`. Any deviation causes Backtrader to silently produce zero trades or crash with an unhelpful `IndexError`.

**Guardrail:** *(Updated by code audit — see E-22 for full detail)* `data_loader.py` must output TITLE-CASE columns (`Date` as index name, `Open/High/Low/Close/Volume`) to match the actual output of `data_normalizer.py` that `execution_engine.py` currently expects:
  ```python
  df.index = pd.to_datetime(df["timestamp"]).dt.tz_convert("Asia/Kolkata")
  df.index.name = "Date"                                   # Title-case — NOT "datetime"
  df = df.rename(columns={"open":"Open","high":"High","low":"Low","close":"Close","volume":"Volume"})
  df = df[["Open","High","Low","Close","Volume"]].sort_index()
  df = df[~df.index.duplicated(keep="first")]
  ```
- Add an assertion before passing to Backtrader: `assert isinstance(df.index, pd.DatetimeIndex)` and `assert df.index.tzinfo is not None`

**Pre-patch checks:**
- [ ] Print `df.dtypes` and `df.index` in a test — confirm DatetimeIndex with IST timezone
- [ ] Run one backtest with a known 10-row dataset, compare trade count with old CSV-based run

**How to fix if broken:** `bt.feeds.PandasData` accepts a `datetime` column override via `params = (('datetime', None),)` if index is used. Confirm this is set. If Backtrader produces 0 trades with valid data, check index timezone — `None` tz causes silent failure.

**Post-patch sanity check:** Backtest on NIFTY 50 data produces same `final_value` ± 0.01% as the old CSV-based baseline recorded in Pre-Execution Checks.

---

### E-02 [GUARANTEED] — Cython Build Order in Dockerfile Fails

**What breaks:** `Dockerfile.backend` runs `pip install -r requirements.txt` (which installs NumPy) then immediately runs `python setup.py build_ext --inplace` for Cython. If the `COPY . .` step happens before pip install, the build tries to use a stale NumPy. On a clean Docker build layer cache, the order is correct — but if requirements are updated without rebuilding the base layer, NumPy version seen by Cython at compile time differs from runtime, causing a `numpy.dtype size changed` crash at import.

**Guardrail:**
- Pin NumPy to an exact version in `requirements.txt`: `numpy==1.26.4` (or whichever version is chosen — never `>=`)
- In `Dockerfile.backend`, the order must be:
  ```dockerfile
  COPY requirements.txt .
  RUN pip install --no-cache-dir -r requirements.txt
  COPY . .
  RUN cd backend/cython_math && python setup.py build_ext --inplace
  ```
  Never swap `COPY . .` before `pip install`

**Pre-patch checks:**
- [ ] `docker build --no-cache -f Dockerfile.backend .` — full clean build must succeed
- [ ] Inside container: `python -c "from backend.cython_math import compute_vwap; import numpy; print(numpy.__version__)"` — version must match requirements.txt

**How to fix if broken:** `docker compose build --no-cache backend` to force full rebuild. If `numpy.dtype size changed` appears, the Cython `.so` was compiled against a different NumPy than is installed — rebuild from scratch.

**Post-patch sanity check:** `docker compose exec backend python -c "from backend.cython_math.vwap import compute_vwap; print('ok')"` returns `ok` with no warnings.

---

### E-03 [GUARANTEED] — Motor (Async) Used in Threaded Collector Subprocess

**What breaks:** `ws_collector.py` runs inside a subprocess and uses KiteTicker which operates on threads (not asyncio). The plan says to use `motor` everywhere. But `motor`'s `AsyncIOMotorClient` requires an active asyncio event loop. Calling `await collection.insert_many(...)` from inside a thread that has no event loop raises `RuntimeError: no running event loop` or silently drops data.

**Guardrail:** The collector subprocess must use **synchronous `pymongo`**, not `motor`. Only the FastAPI server (which runs on an asyncio event loop) uses `motor`. The rule "use motor everywhere" applies only to FastAPI routes, not subprocesses.
- In `backend/collector/ws_collector.py`: `from pymongo import MongoClient` (sync)
- In `backend/calculations/runner.py`: same — synchronous pymongo in the calculation loop
- Create a separate `backend/database/sync_connection.py` that returns a synchronous `MongoClient` for subprocess use

**Pre-patch checks:**
- [ ] Confirm `ws_collector.py` never imports `motor` or `AsyncIOMotorClient`
- [ ] Confirm `runner.py` never uses `await` on MongoDB calls
- [ ] `grep -r "AsyncIOMotorClient" backend/collector/ backend/calculations/` — must return zero results

**How to fix if broken:** Replace all `await collection.insert_many()` in collector/calculator with synchronous `collection.insert_many()`. Use `asyncio.run()` only if an isolated async call is absolutely needed (creates a new event loop per call — acceptable for infrequent operations, not for per-tick operations).

**Post-patch sanity check:** Run collector for 2 minutes — bar count in MongoDB increases. No `RuntimeError` in `docker compose logs backend`.

---

### E-04 [GUARANTEED] — React Frontend Cannot Reach Backend During Development

**What breaks:** In development, `npm run dev` runs Vite on the host at `localhost:5173`. The backend runs at `localhost:8000`. Without a Vite proxy, `fetch('/api/...')` hits `localhost:5173/api/...` (Vite, returns 404) instead of `localhost:8000/api/...`. WebSocket `ws://backend:8000/ws/live` uses the Docker hostname `backend` which does not resolve on the host.

**Guardrail:** Add to `frontend/vite.config.ts`:
```ts
server: {
  proxy: {
    '/api': { target: 'http://localhost:8000', changeOrigin: true },
    '/ws': { target: 'ws://localhost:8000', ws: true, changeOrigin: true }
  }
}
```
And in `frontend/src/services/api.ts` and `websocket.ts`, use relative paths (`/api/...`, `/ws/...`) — never hardcode `http://backend:8000`. Nginx resolves these in production; Vite proxy resolves them in dev.

**Pre-patch checks:**
- [ ] Confirm `vite.config.ts` has the proxy block
- [ ] Confirm no `http://backend:8000` or `http://localhost:8000` hardcoded in any `.ts` or `.tsx` file — use `grep -r "localhost:8000\|backend:8000" frontend/src/`

**How to fix if broken:** Add the Vite proxy config. If already added but broken, check that Vite dev server is restarted after config change (`npm run dev` must be re-run).

**Post-patch sanity check:** With `docker compose up backend mongodb` running and `npm run dev` on host: `curl http://localhost:5173/api/market/instruments?q=NIFTY` returns JSON (not HTML 404).

---

### E-05 [GUARANTEED] — Nginx WebSocket Proxy Timeout Kills Long Backtests

**What breaks:** Nginx default `proxy_read_timeout` is 60 seconds. Backtest WebSocket connections (`/ws/backtest/{task_id}`) stream logs for the duration of the backtest. For a 1-year strategy backtest taking 90s, nginx kills the connection at 60s. Frontend shows "connection closed" mid-backtest with no result.

**Guardrail:** Add to `nginx.conf` for the `/ws/` location block:
```nginx
location /ws/ {
    proxy_pass http://backend:8000;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_read_timeout 3600s;
    proxy_send_timeout 3600s;
    proxy_connect_timeout 10s;
}
```

**Pre-patch checks:**
- [ ] Confirm `nginx.conf` has `proxy_read_timeout 3600s` in the `/ws/` block
- [ ] `grep "proxy_read_timeout" nginx.conf` — must return a result

**How to fix if broken:** Add the timeout directives to `nginx.conf`, rebuild the frontend container: `docker compose build frontend && docker compose up -d frontend`.

**Post-patch sanity check:** Run a backtest that takes > 70 seconds — the terminal in React continues streaming past 60s without disconnect.

---

### E-06 [GUARANTEED] — `backtest_results` Schema Still References CSV `data_file` Field

**What breaks:** The MongoDB `backtest_results` collection schema in Section 5 still has `"data_file": "NIFTY50_2025.csv"`. No CSV exists anymore. If this field is stored and then displayed in the Dashboard page's trades table, it will show a meaningless filename. Worse, if any code tries to re-run a backtest from a saved result using this field, it will fail with "file not found".

**Guardrail:** Update the `backtest_results` schema — replace `data_file` with the MongoDB data selection:
```json
{
  "data_selection": {
    "instrument_token": 256265,
    "tradingsymbol": "NIFTY 50",
    "timeframe": "5min",
    "date_from": "2025-01-01",
    "date_to": "2025-12-31"
  }
}
```
Update `backend/models/backtest.py` `BacktestResult` Pydantic model accordingly.

**Pre-patch checks:**
- [ ] `grep -r "data_file" backend/models/ backend/api/` — must return zero results
- [ ] `grep -r "\.csv" backend/backtesting/` — must return zero results

**How to fix if broken:** Migration script for existing `backtest_results` documents: set `data_file` to `null`, add `data_selection` field with `null` values for old results.

**Post-patch sanity check:** `GET /api/backtests` returns results where each has a `data_selection` object, no `data_file` field.

---

### E-07 [GUARANTEED] — Collector PID Staleness After Docker Restart

**What breaks:** The plan stores `collector.pid` in the MongoDB `collector_status` singleton. When the backend container restarts, the collector subprocess (if it was running) is killed. The stale PID remains in MongoDB. On next `POST /api/collector/start`, the code checks `collector.status == "running"` and returns "already running" — but the collector is actually dead. No new collector starts. Live data stops flowing.

**Guardrail:**
- On FastAPI startup (lifespan event), always upsert `collector.status = "stopped"` and `calculator.status = "stopped"` — treat restart as a clean slate
- Never rely on PID validity across restarts — PID checks (`os.kill(pid, 0)`) only work reliably within the same process lifetime
- `process_manager/collector_process.py` must check if the PID is actually alive before returning "already running": `try: os.kill(pid, 0) except ProcessLookupError: status = "dead"`

**Pre-patch checks:**
- [ ] Confirm `backend/main.py` lifespan function resets status to "stopped" on startup
- [ ] `grep -r "status.*running" backend/process_manager/` — confirm a PID liveness check exists alongside every status check

**How to fix if broken:** Add to FastAPI startup: `await db.collector_status.update_one({"_id": "singleton"}, {"$set": {"collector.status": "stopped", "calculator.status": "stopped"}}, upsert=True)`.

**Post-patch sanity check:** Start collector → restart backend container → `GET /api/collector/status` returns `"stopped"`, not `"running"`.

---

### E-08 [GUARANTEED] — `bar_resampler` Inserting Duplicate Resampled Bars Every 60s

**What breaks:** The calculation runner calls `bar_resampler.py` every 60 seconds. Each call reads 1min bars and writes resampled 5min, 15min, etc. bars to MongoDB. On the second run, the same bars are resampled again and inserted again. If `insert_many` is used instead of `update_one(upsert=True)`, MongoDB will reject the inserts (unique index violation) and raise a `BulkWriteError`, crashing the calculator.

**Guardrail:**
- `bar_resampler.py` must always use `update_one(filter={token+timeframe+timestamp}, update={$set: bar}, upsert=True)` — never `insert_many`
- Or use `pymongo`'s `ReplaceOne` with `upsert=True` in a bulk operation
- Catch `BulkWriteError` and log — do not re-raise; let the calculator continue to next cycle

**Pre-patch checks:**
- [ ] `grep -rn "insert_many\|insert_one" backend/calculations/bar_resampler.py` — confirm zero results; all writes are upserts
- [ ] Run calculator for 3 consecutive cycles (3 minutes) — MongoDB resampled bar count must not triple

**How to fix if broken:** Replace all `collection.insert_many(bars)` with `[ReplaceOne({"instrument_token": b["instrument_token"], "timeframe": b["timeframe"], "timestamp": b["timestamp"]}, b, upsert=True) for b in bars]` → `collection.bulk_write(ops, ordered=False)`.

**Post-patch sanity check:** After 5 calculator cycles, query: `db.bars.count_documents({"timeframe": "5min", "trading_date": "today"})` — count stabilizes, does not grow per cycle.

---

### E-09 [GUARANTEED] — TradingView Lightweight Charts Expects UNIX Seconds, Not Milliseconds

**What breaks:** MongoDB timestamps come out as Python `datetime` objects → serialized to ISO strings in JSON → parsed in React. TradingView Lightweight Charts `CandlestickData.time` accepts UNIX timestamps **in seconds** (number) or `{ year, month, day }` objects. If milliseconds are passed (JavaScript `Date.getTime()` / `Date.now()` returns ms), bars appear at year ~52000. If ISO strings are passed directly, the chart throws a runtime error.

**Guardrail:**
- In the FastAPI `GET /api/market/bars` response, serialize timestamps as UNIX seconds (integer):
  ```python
  "time": int(bar["timestamp"].timestamp())  # UTC datetime → UNIX seconds
  ```
- In React, the bar type must be `{ time: number; open: number; ... }` — `time` is always a UNIX second number, never a string or ms

**Pre-patch checks:**
- [ ] In React, `console.log(bars[0].time)` — value must be ~1.7 billion (2024 era), not ~1.7 trillion (milliseconds)
- [ ] `GET /api/market/bars?...` response: confirm `time` field is an integer, not a string

**How to fix if broken:** In `frontend/src/services/api.ts` bar mapping: `time: Math.floor(new Date(bar.timestamp).getTime() / 1000)` — divide by 1000 to convert ms to seconds.

**Post-patch sanity check:** Candlestick chart displays bars at correct IST times (9:15 AM onward), not at 1970 or far-future dates.

---

### E-10 [GUARANTEED] — Unique Index Conflict: Live Bar Overwrites Historical Bar

**What breaks:** The unique index is on `(instrument_token, timeframe, timestamp)`. When the collector writes a live bar for NIFTY at 9:30 AM on 2026-04-29, and historical data was also ingested for that same date (e.g., for backtesting overlap), both have the same key. With `upsert=True`, the second write silently overwrites the first. If `data_source` is not preserved correctly, a `"historical"` bar could overwrite a `"live"` bar or vice versa.

**Guardrail:**
- Use `update_one` with `$set` that only updates OHLCV fields, and `$setOnInsert` for `data_source` — so source is set only on first insert, never overwritten:
  ```python
  {"$set": {"open": bar["open"], "high": ..., "close": ..., "volume": ...},
   "$setOnInsert": {"data_source": bar["data_source"]}}
  ```
- Alternatively: treat `data_source` as append-only — if a bar exists as `"live"`, keep it as `"live"` even when historical ingestion tries to write the same bar

**Pre-patch checks:**
- [ ] Ingest historical data for today's date → start collector → verify: `db.bars.find_one({token: X, timeframe: "1min", trading_date: "today"})["data_source"]` is `"live"`, not `"historical"`

**How to fix if broken:** Run a one-time update: `db.bars.update_many({"data_source": "historical", "trading_date": {$in: [dates_collector_was_running]}}, {$set: {"data_source": "live"}})`.

**Post-patch sanity check:** `db.bars.distinct("data_source")` returns `["live", "historical", "resampled"]` — no unexpected values.

---

### E-11 [GUARANTEED] — Ingestion Job Progress Has No Persistence

**What breaks:** The plan defines `GET /api/historical/ingest/{job_id}` to return progress. If job progress is stored in a Python in-memory dict (`jobs: dict[str, JobState]`), it is lost on any backend restart or container restart. A user who triggers ingestion, waits 5 minutes, and the backend restarts (Docker OOM, etc.) will get 404 on `GET /api/historical/ingest/{job_id}`. Worse, the ingestion subprocess is also killed — no data is committed for that run.

**Guardrail:**
- Store ingestion job state in MongoDB — a new `ingestion_jobs` collection:
  ```json
  { "_id": "job_id", "status": "running", "fetched": 240, "inserted": 235, "skipped": 5, "error": null, "started_at": ISODate, "completed_at": null }
  ```
- `ingestion_manager.py` updates this document every 60s and on completion
- Job documents expire automatically via a TTL index: `{ "completed_at": 1 }, expireAfterSeconds: 86400` — purged after 24h

**Pre-patch checks:**
- [ ] `grep -rn "jobs\[" backend/historical/` — confirm no in-memory dict is used for job state
- [ ] Restart backend mid-ingestion — `GET /api/historical/ingest/{job_id}` still returns status

**How to fix if broken:** Move job state from dict to `db.ingestion_jobs.update_one({_id: job_id}, {$set: state}, upsert=True)`.

**Post-patch sanity check:** Kill backend container mid-ingestion → restart → `GET /api/historical/ingest/{job_id}` returns last known state.

---

### E-12 [GUARANTEED] — DO NOT List Contradicts Directory Structure (Subprocess)

**What breaks:** The DO NOT list says "Do not use subprocess to run the collector from FastAPI — use supervisor or a separate Docker service." But the directory structure includes `backend/process_manager/collector_process.py` and the REST route `POST /api/collector/start` implies the backend controls the collector lifecycle. This is an architectural contradiction that, if left unresolved, leads to two teams implementing it differently.

**Guardrail — Choose one and document it:**

**Option A (Separate Docker service — recommended):** Add a `collector` service to `docker-compose.yml` that runs `python -m backend.collector.ws_collector` directly. `POST /api/collector/start|stop` sends a signal to this service (e.g., via a MongoDB flag the collector polls). Delete `process_manager/`.

**Option B (Subprocess — simpler, acceptable for single-machine):** Keep `process_manager/` but add explicit guardrails: only one subprocess per service, PID tracked in MongoDB, liveness check before start. Remove "do not use subprocess" from DO NOT list.

**The plan must pick one.** The architecture diagram shows Collector as a separate process — Option A is more correct for Docker. Update `docker-compose.yml` accordingly.

**Pre-patch checks:**
- [ ] Confirm `docker-compose.yml` has a `collector` service OR confirm `process_manager/collector_process.py` uses subprocess with PID liveness checks — never both
- [ ] `grep -r "subprocess.Popen" backend/` — if found, confirms Option B is in use

**Post-patch sanity check:** `POST /api/collector/start` correctly starts the collector regardless of which option is chosen. `GET /api/collector/status` reflects the correct running state within 5s.

---

### E-13 [POTENTIAL] — Race: `bar_resampler` Reads Before Collector Writes This Minute

**What breaks:** The collector flushes completed 1min bars every second. The calculator runs every 60s. If the calculator's bar_resampler runs at 9:31:30 and reads 1min bars, but the 9:31 bar was flushed at 9:31:59 (just missed), the resampled 5min bar for 9:25–9:30 is computed without the 9:30 1min bar. The 5min bar is wrong. Next run at 9:32:30 will recompute and overwrite correctly — but there is a 60s window of stale data.

**Guardrail:**
- The calculator should only resample bars with `trading_date` where timestamp < `now - 60s` (i.e., only bars at least 1 minute old)
- Add a `cutoff = datetime.utcnow() - timedelta(seconds=90)` filter to bar_resampler queries

**Pre-patch checks:**
- [ ] Verify bar_resampler query includes a timestamp upper bound: `{"timestamp": {"$lt": cutoff}}`

**Post-patch sanity check:** Check 5min bar at 9:30 — it must include all five 1min bars from 9:26–9:30 inclusive, not just four.

---

### E-14 [POTENTIAL] — Zerodha Historical API Interval Limits Differ Per Timeframe

**What breaks:** The plan says "60 days per request for minute data." Zerodha's actual limits are different per interval and must be respected:

| Interval | Max days per request |
|---|---|
| `minute` | 60 |
| `3minute` | 100 |
| `5minute` | 100 |
| `15minute` | 200 |
| `30minute` | 200 |
| `60minute` | 400 |
| `day` | 2000 |

Using 60 days for a `60minute` request works (conservative), but wastes API calls — the user requests 1 year and gets 7 chunks instead of 2. Using 60 days for `day` interval is massively inefficient.

**Guardrail:** In `ingestion_manager.py`, define a `MAX_DAYS_PER_INTERVAL` dict:
```python
MAX_DAYS_PER_INTERVAL = {
    "minute": 60, "3minute": 100, "5minute": 100,
    "15minute": 200, "30minute": 200, "60minute": 400, "day": 2000
}
```
Use `MAX_DAYS_PER_INTERVAL[interval]` for chunking, not a hardcoded 60.

**Pre-patch checks:**
- [ ] `grep -rn "60" backend/historical/ingestion_manager.py` — confirm no magic number 60 is used as the chunk size for all intervals

**Post-patch sanity check:** Ingest 1 year of 60min NIFTY data — confirm only 1 API call is made (365 days < 400 limit), not 7 calls.

---

### E-15 [POTENTIAL] — Docker Volume Name Mismatch Breaks Backup Command

**What breaks:** The plan's backup command uses `algo_trading_system_mongo_data` as the volume name. Docker names volumes as `{compose_project_name}_{volume_name}`. The compose project name defaults to the **directory name** of the project folder. If the project is cloned into `Algo-Trading-System` (hyphen) or `algo_trading` (different casing), the volume name changes. The backup command silently backs up nothing.

**Guardrail:** Pin the project name in `docker-compose.yml`:
```yaml
name: algo_trading_system
```
This makes the volume name always `algo_trading_system_mongo_data` regardless of directory name.

**Pre-patch checks:**
- [ ] `docker compose config | grep "name:"` — confirms project name is `algo_trading_system`
- [ ] `docker volume ls | grep mongo_data` — confirms the volume name matches

**Post-patch sanity check:** After `docker compose up`, run `docker volume inspect algo_trading_system_mongo_data` — returns valid volume info with correct mountpoint.

---

### E-16 [POTENTIAL] — Cython Fallback Runs Silently in Production

**What breaks:** If Cython `.so` files fail to compile (broken Docker layer, NumPy mismatch, missing build tools), the `__init__.py` fallback silently imports pure Python. VWAP calculation runs 10–50× slower. With 2500 tokens × 7 timeframes = 17,500 VWAP calculations every 60s, pure Python takes 30–90s — longer than the 60s cycle. Calculator falls behind, snapshots stop updating.

**Guardrail:**
- `cython_math/__init__.py` must log a **WARNING** when falling back:
  ```python
  except ImportError:
      import warnings
      warnings.warn("Cython VWAP not available — using pure Python fallback. Performance degraded.", RuntimeWarning)
      from ._fallback import compute_vwap_pure as compute_vwap
  ```
- At FastAPI startup, log whether Cython modules are active or fallback is in use

**Pre-patch checks:**
- [ ] `docker compose exec backend python -c "import backend.cython_math; print('using cython')"` — no warnings printed

**Post-patch sanity check:** `docker compose logs backend | grep -i "cython\|fallback"` — confirms "Cython active" message at startup, no fallback warnings.

---

### E-17 [POTENTIAL] — Frontend CORS Breaks on Non-localhost Access

**What breaks:** FastAPI CORS is configured for `http://localhost:5173`. In production via Docker, the frontend is served by nginx on port 3000 and requests come from the same origin (nginx proxies to backend — same-origin, no CORS needed). But if anyone accesses the app from another machine on the LAN (`http://192.168.1.100:3000`), the browser sends a CORS preflight. FastAPI rejects it because `192.168.1.100` is not in the allowed origins list. The app appears broken.

**Guardrail:**
- In production (Docker), CORS is irrelevant because nginx proxies all `/api/` and `/ws/` — they share origin with the frontend. Remove `CORSMiddleware` entirely for production, or configure it only for development.
- Use an env var: `CORS_ORIGINS=http://localhost:5173` (dev only); in production, leave it empty or set `CORS_ORIGINS=none`

**Pre-patch checks:**
- [ ] Access the app from a different machine on the LAN — confirm `GET /api/market/instruments` works

**Post-patch sanity check:** `curl -H "Origin: http://192.168.1.100:3000" http://192.168.1.100:3000/api/market/instruments` — returns data, no CORS error.

---

### E-18 [POTENTIAL] — `data_gaps` Detection Requires Trading Calendar (Non-Trivial)

**What breaks:** The plan promises `{ "data_gaps": ["2025-03-15", "2025-03-16"] }` in the backtest response. Detecting gaps requires knowing which dates *should* have data (trading days minus NSE holidays) vs which dates *do* have data in MongoDB. This needs `trading_calendar.py` integrated into `data_loader.py`. Without this, the gap detection either returns false positives (weekends/holidays flagged as gaps) or is skipped entirely — the response silently omits the field.

**Guardrail:** Either implement gap detection properly using `trading_calendar.py`, or don't include `data_gaps` in the initial response (return it as `null` and add it in a later iteration). Do not return an empty array `[]` when gaps may exist — that is misleading.

**Pre-patch checks:**
- [ ] Confirm `BacktestResult` Pydantic model marks `data_gaps` as `Optional[list[str]] = None`
- [ ] If implemented: test with a date range that includes a known NSE holiday — confirm holiday is NOT in `data_gaps`

**Post-patch sanity check:** Backtest on a date range spanning a weekend — `data_gaps` does not include Saturday/Sunday.

---

### E-19 [POTENTIAL] — React Query `staleTime` Too Long for Catalog

**What breaks:** `DataSelector.tsx` calls `GET /api/historical/catalog` with `staleTime: 60_000`. If a user triggers a new ingestion via `HistoricalIngestPanel.tsx` and then opens `DataSelector` within 60 seconds, the catalog still shows the old list (before the new instrument was ingested). The user thinks the ingest failed and tries again.

**Guardrail:**
- Set `staleTime: 0` specifically for the catalog query — it must always reflect the latest MongoDB state
- Or: after successful ingestion completion, call `queryClient.invalidateQueries({ queryKey: ['catalog'] })` to force a refetch

**Pre-patch checks:**
- [ ] In `DataSelector.tsx`: confirm `useQuery({ queryKey: ['catalog'], staleTime: 0 })` or equivalent invalidation logic

**Post-patch sanity check:** Trigger ingestion → wait for completion → open DataSelector → new instrument appears immediately without page reload.

---

### E-20 [POTENTIAL] — Historical Options Data Ingestion Is Structurally Different

**What breaks:** The plan's ingestion flow assumes equities (one symbol, continuous data). For NSE options (NIFTY2651221950PE), the tradingsymbol encodes strike + expiry + type. Each expiry is a different instrument. Weekly expiries mean a new set of option instruments every Thursday. Ingesting "all NIFTY options" for a year requires hundreds of API calls (one per strike × expiry). The frontend's ingestion panel has no way to handle this without a symbol search that understands options structure.

**Guardrail:** For Phase 1, limit historical ingestion to **indices and equities only** (e.g., NIFTY 50, BANKNIFTY, top 50 stocks). Options historical data is extremely large and complex — defer options backtesting to a later phase. Add a clear note in the UI: "Options historical data not supported in this version."

**Pre-patch checks:**
- [ ] `POST /api/historical/ingest` with an options token (e.g., NIFTY24APR25000CE) — returns HTTP 400 with message "Options historical ingestion not yet supported."

**Post-patch sanity check:** Attempting to ingest an options symbol shows a clear error in `HistoricalIngestPanel.tsx`, not a spinner that runs forever.

---

### E-21 [POTENTIAL] — `process_state.json` Still Written by Some Module

**What breaks:** The dead code list includes `Data/live_market/process_state.json`. If any module still writes this file (e.g., an old `collector_controller.py` path that wasn't fully migrated), the Docker container will try to write to a path that doesn't exist in the new container (since `Data/live_market/` is no longer volume-mounted). This raises a `FileNotFoundError` silently on every write attempt, filling logs with errors.

**Guardrail:**
- `grep -rn "process_state.json" backend/` — must return zero results after migration
- `grep -rn "collector_status.json" backend/` — must return zero results after migration
- `grep -rn "open(.*\.json.*w" backend/` — confirm no file-write-open calls remain in production code

**Pre-patch checks:**
- [ ] Run the above grep commands before any PR merge

**Post-patch sanity check:** `docker compose logs backend | grep "FileNotFoundError"` — returns no results after 10 minutes of operation.

---

---

### E-22 [GUARANTEED] — `data_loader.py` Must Output Title-Case Columns, Not Lowercase

**What breaks:** The plan's E-01 says Backtrader needs `open, high, low, close, volume` (lowercase). The actual `data_normalizer.py` (confirmed by code) outputs `Date, Open, High, Low, Close, Volume` (title-case with `Date` as index name). `execution_engine.py` calls `normalize()` and then immediately passes the result to Backtrader. If `data_loader.py` outputs lowercase columns, Backtrader silently finds no OHLC data and produces zero trades.

**Guardrail:** `data_loader.py` must replicate the exact output of `data_normalizer.py`:
```python
df.index.name = "Date"
df = df.rename(columns={"open": "Open", "high": "High", "low": "Low", "close": "Close", "volume": "Volume"})
df = df[["Open", "High", "Low", "Close", "Volume"]]
df.index = pd.to_datetime(df.index).tz_localize("Asia/Kolkata")  # IST, aware
df = df[~df.index.duplicated(keep="first")]  # Dedup matches data_normalizer
df = df.between_time("09:15", "15:30")       # Market hours filter (if enforce_market_hours=True)
```

**Pre-patch checks:**
- [ ] `data_loader.py` output: `df.columns.tolist()` returns `["Open", "High", "Low", "Close", "Volume"]`
- [ ] `df.index.name` returns `"Date"`
- [ ] `df.index.tzinfo` is not None (IST-aware)
- [ ] Run test backtest → trade count matches baseline

**Post-patch sanity check:** `execution_engine.py` receives DataFrame from `data_loader.py` — same structure as if `data_normalizer.py` had been called on the equivalent CSV.

---

### E-23 [GUARANTEED] — `token_loader.py` Reads CSV That Will Be Deleted

**What breaks:** `token_loader.py` currently does `pd.read_csv("zerodha_instruments_latest.csv")` to load equity/options tokens. The plan deletes this CSV after seeding MongoDB. After deletion, `run_collector.py` crashes at startup with `FileNotFoundError` — no live data collection possible.

**Guardrail:** `backend/collector/token_loader.py` must be rewritten to query the `instruments` MongoDB collection. The return format (dict with `equity_tokens`, `options_meta`, `token_to_symbol`, etc.) must be **identical** to current — `ws_collector.py` and `run_collector.py` depend on this structure exactly.

Key query: `db.instruments.find({"segment": "NSE", "instrument_type": "EQ"})` for equities, `find({"segment": "NFO", "instrument_type": {"$in": ["CE", "PE"]}})` for options. Apply same `LM_*` env var filters that currently apply to the CSV.

**Pre-patch checks:**
- [ ] After CSV deletion: `docker compose run --rm backend python -c "from backend.collector.token_loader import load_all_tokens; t = load_all_tokens(); print(len(t['equity_tokens']))"` — returns non-zero count
- [ ] `grep -rn "read_csv" backend/collector/token_loader.py` — returns zero results

**Post-patch sanity check:** Collector starts without errors and `tokens_subscribed` in `collector_status` matches the count before CSV deletion.

---

### E-24 [GUARANTEED] — All Calculators Read CSV Internally (Plan Marked Them "Unchanged")

**What breaks:** The plan originally marked `ad_calculator.py`, `pcr_calculator.py`, `atm_oi_calculator.py` as "Unchanged." The actual code shows all three call `pd.read_csv()` internally. After CSV deletion, all three crash with `FileNotFoundError` every 60-second calculation cycle. Snapshots stop updating. Live market page shows stale data.

**Guardrail:** (Already corrected in the directory structure above.) Each calculator's signature must be updated to accept DataFrames as arguments. `runner.py` fetches data from MongoDB once per cycle and passes DataFrames to each calculator. Math logic inside each calculator is untouched.

**Pre-patch checks:**
- [ ] `grep -rn "read_csv\|pd.read_csv" backend/calculations/` — zero results (all removed)
- [ ] Run calculation cycle manually: `runner.run_once()` completes without FileNotFoundError
- [ ] Snapshot output dict structure matches pre-shift baseline JSON files exactly (key names, nested structure)

**Post-patch sanity check:** After 3 calculation cycles with collector running, all 5 snapshot types updated in MongoDB within 65s.

---

### E-25 [GUARANTEED] — `calculation_runner.py` Reads `COLLECTOR_STATUS_PATH` JSON for Trading Date

**What breaks:** `calculation_runner.py` determines the current trading date by reading `COLLECTOR_STATUS_PATH` (a JSON file). After migration, this file doesn't exist. The runner falls back to `DAILY_ROOT` directory scan — but `DAILY_ROOT` also doesn't exist (no CSV directories). Trading date resolution fails; runner skips every calculation cycle silently.

**Guardrail:** `backend/calculations/runner.py` must read the trading date from MongoDB: `db.collector_status.find_one({"_id": "singleton"})["collector"]["trading_date"]`. Fall back to today's IST date if collector has not started yet.

**Pre-patch checks:**
- [ ] `grep -rn "COLLECTOR_STATUS_PATH\|DAILY_ROOT" backend/calculations/runner.py` — zero results
- [ ] With collector not running, `runner.run_once()` uses today's IST date as fallback — does not crash

**Post-patch sanity check:** `runner.py` logs "Trading date: 2026-04-29" at start of each cycle. Date matches what `collector_status` doc shows.

---

### E-26 [GUARANTEED] — `calculation_runner.py` Reads `prev_close.json` File

**What breaks:** `runner.py` reads `prev_close.json` and passes it to `ad_calculator.py`. File doesn't exist after migration. A/D ratio computation fails every cycle. A/D snapshot never updates.

**Guardrail:** `backend/calculations/runner.py` must query MongoDB: `db.prev_close.find_one({"_id": today_str})` → extract `data` dict → pass as `prev_close_dict` to `ad_calculator.compute()`. String token keys must be preserved.

**Pre-patch checks:**
- [ ] `grep -rn "prev_close.json" backend/calculations/` — zero results
- [ ] `db.prev_close.find_one({"_id": "2026-04-29"})["data"]["193804545"]` returns a float

**Post-patch sanity check:** `GET /api/market/snapshots/ad` returns an A/D snapshot with `advances > 0` on a trading day.

---

### E-27 [GUARANTEED] — Two Different VWAP Formulas in the System — Must Not Mix

**What breaks:** `vwap_calculator.py` computes VWAP as `close × volume` (for the snapshot broadcast). `indicator_engine.py` (being deleted) computed VWAP as `(H+L+C)/3 × volume` (typical price, for chart overlay). The Cython `vwap.pyx` as written in the plan takes a `prices` array — unclear which formula it implements. If the wrong formula is used in either place, VWAP values will disagree with user expectations.

**Guardrail:** Two distinct Cython kernels:
- `vwap_close.pyx` — `close × volume` cumsum. Used by `vwap_calculator.py` for snapshot (preserves existing behavior)
- `vwap_typical.pyx` — `(H+L+C)/3 × volume` cumsum. Used by `backend/indicators/vwap.py` for chart overlay

Both exposed from `cython_math/__init__.py` as `compute_vwap_close` and `compute_vwap_typical`.

**Pre-patch checks:**
- [ ] `vwap_calculator.py` imports `compute_vwap_close` — not `compute_vwap_typical`
- [ ] Chart overlay VWAP uses `compute_vwap_typical`
- [ ] Run both on same bar data: values differ by ~0.1% (typical ≠ close on most bars) — confirms correct kernel is used

**Post-patch sanity check:** VWAP in the snapshot JSON matches the pre-shift baseline (which used `close × volume`). Chart overlay VWAP visually matches typical TradingView VWAP behavior.

---

### E-28 [GUARANTEED] — `execution_manager.py` `task_store.json` Path Breaks in Docker

**What breaks:** `execution_manager.py` persists its task queue to `Data/Logs/task_store.json`. In Docker, this path resolves to `/app/Data/Logs/task_store.json`. The `/app/Data/Logs/` directory does not exist in the new Docker image (no `Data/` volume mounted). First backtest run crashes with `FileNotFoundError` when trying to write the task store.

**Guardrail:** In `backend/backtesting/execution_manager.py`, replace the task_store.json path with:
```python
TASK_STORE_PATH = Path(os.environ.get("TASK_STORE_PATH", "/app/data/task_store.json"))
TASK_STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
```
Add `TASK_STORE_PATH=/app/data/task_store.json` to `.env`. Add a Docker volume for `/app/data` or handle in-memory only (since tasks are ephemeral anyway).

**Pre-patch checks:**
- [ ] `docker compose exec backend ls /app/data/task_store.json` — file exists or directory writable
- [ ] `POST /api/backtests/run` → `docker compose logs backend | grep "task_store"` — no FileNotFoundError

**Post-patch sanity check:** After 3 backtest runs, `task_store.json` exists and contains valid JSON.

---

### E-29 [GUARANTEED] — No Version Pins in `requirements.txt` — Breaks Reproducibility

**What breaks:** All packages are unpinned (`backtrader`, `pandas`, `numpy`, `kiteconnect`, etc.). Any `docker compose build --no-cache` on a different day may pull a newer version. Known breakage: `backtrader` has not been updated since 2021; a minor pandas version bump (`pandas 2.x`) changes `resample` behavior and breaks `bar_resampler.py`. `numpy 2.x` breaks Cython modules compiled against `numpy 1.x` headers.

**Guardrail:** Run `pip freeze` in the current working environment, capture exact versions, pin all in `requirements.txt`. At minimum pin:
```
numpy==1.26.4
pandas==2.2.2
backtrader==1.9.78.123
kiteconnect==5.0.1
pandas-ta==0.3.14b0
motor==3.4.0
pymongo==4.7.2
fastapi==0.111.0
uvicorn==0.29.0
pydantic==2.7.1
cython==3.0.10
```
Note: `ta-lib` is removed — replaced by `pandas-ta`. This eliminates the TA-Lib C library compilation in `Dockerfile.backend` (the `wget/tar/configure/make` block is gone). `pandas-ta` is a pure-Python library installed via pip with no system-level dependencies.

**Pre-patch checks:**
- [ ] `pip freeze | grep "==" | wc -l` — all packages have `==` pins, not `>=` or nothing
- [ ] `docker compose build --no-cache backend` on two different dates produces containers with identical package versions

**Post-patch sanity check:** `docker compose exec backend pip list | grep pandas` returns the pinned version.

---

### E-30 [GUARANTEED] — `.env` File Contains Real Zerodha Credentials

**What breaks:** The `.env` file currently contains live `ZERODHA_API_KEY`, `ZERODHA_API_SECRET`, `ZERODHA_ACCESS_TOKEN`. If committed to git or included in Docker image (`COPY . .`), credentials are exposed. Additionally, access tokens expire at 6 AM IST daily — any hardcoded token in the image is already expired.

**Guardrail:**
- `.env` must be in `.gitignore` — verify with `git check-ignore -v .env`
- `Dockerfile.backend` must NOT `COPY .env` — use `env_file: .env` in docker-compose only (already correct)
- Create `.env.example` with placeholder values for documentation
- Rotate all credentials immediately: generate new API secret via Zerodha developer console; access token renews daily via KiteConnect login flow

**Pre-patch checks:**
- [ ] `git log --all --full-history -- .env` — returns no commits (file never committed)
- [ ] `git check-ignore -v .env` — returns `.gitignore` line number

**Post-patch sanity check:** `docker compose run --rm backend env | grep ZERODHA` — credentials present inside container but not embedded in image layers (`docker history algo_backend | grep ZERODHA` — returns nothing).

---

### E-31 [POTENTIAL] — `pcr_calculator.py` Zerodha Quotes Fallback Uses `kite_client`

**What breaks:** `pcr_calculator.py` has `compute_from_quotes(kite_client)` which calls `kite_client.quote()` in batches of 400. The new `runner.py` calls `compute_from_dataframe(options_df)` instead. But the quotes fallback is triggered when the CSV was empty or missing. In the new system, this fallback should trigger when the MongoDB `bars` collection has no options bars for today. If the fallback is not wired into the new runner, it silently disappears — during market open before 9:20 AM (before options bars accumulate), PCR will always return 0.

**Guardrail:** Preserve the fallback in `runner.py`:
```python
options_df = bar_repository.get_today_bars("option", "1min")
if options_df.empty:
    pcr_result = pcr_calculator.compute_from_quotes(kite_client)
else:
    pcr_result = pcr_calculator.compute_from_dataframe(options_df)
```
The `kite_client` must be passed into `runner.py` at startup.

**Pre-patch checks:**
- [ ] At 9:16 AM (before options bars accumulate): `GET /api/market/snapshots/pcr` returns non-zero PCR values
- [ ] `grep -rn "compute_from_quotes" backend/calculations/runner.py` — returns one result (fallback wired in)

**Post-patch sanity check:** PCR snapshot has non-null values within 2 minutes of market open.

---

### E-32 [POTENTIAL] — `bar_aggregator.py` Skips First Bar Per Token on Collector Start

**What breaks:** `bar_aggregator.py` uses `_first_minute_seen` dict to skip the very first bar seen per token after collector starts. This is intentional — the first bar may be incomplete (collector starts mid-minute). In the new system, this dict is in memory only. After a collector restart mid-session, all tokens lose their `_first_minute_seen` state. On restart, the first bar after restart is skipped — one minute of data is missing per restart.

**Guardrail:** This behavior is acceptable and should be preserved exactly as-is. The only risk is if someone expects zero gaps in MongoDB bars after a restart — document this: "Each collector restart causes a 1-bar gap per subscribed token (intentional, prevents partial bars)."

**Pre-patch checks:**
- [ ] Restart collector at 10:05 → check MongoDB for 10:05 bar for any token — it should NOT exist; 10:06 bar should be the first bar after restart

**Post-patch sanity check:** This behavior is documented; backtesting `data_loader.py` does NOT raise an error on gaps — gaps are passed through to Backtrader as-is.

---

### E-33 [POTENTIAL] — `execution_manager.py` Worker Thread Count Is Configurable

**What breaks:** `execution_manager.py` uses 3 worker threads by default. Each worker spawns a subprocess via `multiprocessing.spawn`. In Docker, the container may have limited CPU. Three simultaneous backtest subprocesses may cause OOM if each loads 1 year of 1min data (~90,000 rows × multiple numpy arrays). Memory spikes per subprocess: ~200–500 MB.

**Guardrail:** Set default worker count to 1 in Docker via env var: `BACKTEST_WORKER_COUNT=1`. Add this to `.env` and `config.py`. Increase only on machines with sufficient RAM.

**Pre-patch checks:**
- [ ] `docker stats algo_backend` during backtest — memory stays below 70% of container limit
- [ ] `config.BACKTEST_WORKER_COUNT` is read from env var, not hardcoded

**Post-patch sanity check:** Running 3 simultaneous backtests does not OOM the container.

---

### E-34 [POTENTIAL] — `LM_*` Environment Variables Not in Plan Config

**What breaks:** `token_loader.py` reads `LM_EQUITY_UNIVERSE`, `LM_EQUITY_UNIVERSE_PATH`, `LM_OPTION_EXPIRY_COUNT`, `LM_STRIKES_AROUND_ATM`, `LM_COLLECT_EQUITIES`, `LM_COLLECT_OPTIONS`, `LM_COLLECT_VIX` from environment. These are not in the plan's `.env` or `config.py`. In Docker, they default to their hardcoded defaults — which may cause unexpected behavior (e.g., `LM_STRIKES_AROUND_ATM=0` collects the full options chain, which is ~2500 tokens; if the user intended to limit it, the env var is silently ignored).

**Guardrail:** Add all `LM_*` vars to `.env.example` with their defaults documented:
```
LM_EQUITY_UNIVERSE=NIFTY500_PLUS_FNO
LM_OPTION_EXPIRY_COUNT=1
LM_STRIKES_AROUND_ATM=0
LM_COLLECT_EQUITIES=true
LM_COLLECT_OPTIONS=true
LM_COLLECT_VIX=true
```
Add these to `backend/config.py` `Settings` class with the same defaults.

**Pre-patch checks:**
- [ ] `grep -rn "LM_" backend/config.py` — all `LM_*` vars appear in Settings class
- [ ] `grep -rn "LM_" .env.example` — all vars documented with default values

**Post-patch sanity check:** Changing `LM_OPTION_EXPIRY_COUNT=2` in `.env` and restarting collector subscribes to 2 expiries worth of options tokens.

---

### Updated Summary Table

| ID | Type | Area | Risk Level | Phase Where It Bites |
|---|---|---|---|---|
| E-01 | GUARANTEED | Backtesting | Critical | Phase 3 |
| E-02 | GUARANTEED | Docker/Cython | High | Phase 0/2 |
| E-03 | GUARANTEED | Collector/Motor | Critical | Phase 3 |
| E-04 | GUARANTEED | Frontend/Dev | High | Phase 4 |
| E-05 | GUARANTEED | Nginx/WebSocket | Medium | Phase 5 |
| E-06 | GUARANTEED | Data Model | Medium | Phase 3 |
| E-07 | GUARANTEED | Process Manager | High | Phase 3 |
| E-08 | GUARANTEED | Calculator | High | Phase 3 |
| E-09 | GUARANTEED | Charts/Frontend | High | Phase 4 |
| E-10 | GUARANTEED | MongoDB | Medium | Phase 3 |
| E-11 | GUARANTEED | Historical Ingest | Medium | Phase 3 |
| E-12 | GUARANTEED | Architecture | Critical | Phase 0 |
| E-22 | GUARANTEED | Backtesting | Critical | Phase 3 |
| E-23 | GUARANTEED | Token Loader | Critical | Phase 3 |
| E-24 | GUARANTEED | All Calculators | Critical | Phase 3 |
| E-25 | GUARANTEED | Runner | Critical | Phase 3 |
| E-26 | GUARANTEED | Runner/A-D | High | Phase 3 |
| E-27 | GUARANTEED | Cython/VWAP | High | Phase 2 |
| E-28 | GUARANTEED | Backtest Manager | High | Phase 3 |
| E-29 | GUARANTEED | Requirements | High | Phase 0 |
| E-30 | GUARANTEED | Security | Critical | Phase 0 |
| E-13 | POTENTIAL | Calculator | Low | Phase 3 |
| E-14 | POTENTIAL | Historical Ingest | Medium | Phase 1 |
| E-15 | POTENTIAL | Docker | Low | Phase 5 |
| E-16 | POTENTIAL | Cython | High | Phase 2 |
| E-17 | POTENTIAL | Security/CORS | Low | Phase 5 |
| E-18 | POTENTIAL | Backtest UX | Low | Phase 4 |
| E-19 | POTENTIAL | Frontend Cache | Low | Phase 4 |
| E-20 | POTENTIAL | Options Data | Medium | Phase 1 |
| E-21 | POTENTIAL | Cleanup | Low | Phase 1 |
| E-31 | POTENTIAL | PCR Fallback | Medium | Phase 3 |
| E-32 | POTENTIAL | Bar Aggregator | Low | Phase 3 |
| E-33 | POTENTIAL | Backtest Memory | Medium | Phase 3 |
| E-34 | POTENTIAL | Config/Env Vars | Medium | Phase 0 |
| E-35 | GUARANTEED | Pandas-TA/Import | Critical | Phase 3 |


---

### Pre-Merge Checklist (Run Before Every PR)

```bash
# No CSV reads/writes in production code
grep -r "read_csv\|to_csv\|open.*\.csv" backend/ | grep -v "scripts/"

# No Streamlit anywhere
grep -r "import streamlit\|from streamlit" backend/

# No TA-Lib anywhere
grep -r "import talib\|from talib" backend/

# No hardcoded localhost MongoDB or file paths for status/snapshots
grep -r "localhost:27017\|127.0.0.1:27017" backend/
grep -r "collector_status\.json\|process_state\.json\|vwap_snapshot\.json" backend/

# No motor/async in subprocess code (collector and calculations use sync pymongo)
grep -r "AsyncIOMotorClient\|await.*insert\|await.*find" backend/collector/ backend/calculations/

# No hardcoded backend hostname in frontend
grep -r "localhost:8000\|backend:8000" frontend/src/

# No CSV data_file reference in backtest models
grep -r "data_file.*csv\|\"data_file\"" backend/models/ backend/api/routes/backtests.py

# Cython fallback warning is present
grep "fallback\|Cython.*not available" backend/cython_math/__init__.py

# Two VWAP kernels present (close and typical)
grep -r "compute_vwap_close\|compute_vwap_typical" backend/cython_math/__init__.py

# Nginx has WebSocket timeout
grep "proxy_read_timeout" nginx.conf

# Docker project name pinned
grep "^name:" docker-compose.yml

# All packages pinned with exact versions
grep -c "==" requirements.txt  # Should equal total number of packages

# LM_* vars in config
grep -c "LM_" backend/config.py  # Should be >= 6

# No env vars hardcoded (all read from os.environ or config)
grep -rn "ZERODHA_API_KEY\s*=" backend/ | grep -v "os.environ\|config\.\|Settings\|\.env"

# token_loader reads from MongoDB, not CSV
grep "read_csv" backend/collector/token_loader.py  # Must return nothing

# All calculators accept DataFrame arguments, not file paths
grep "read_csv\|pd.read_csv" backend/calculations/ad_calculator.py backend/calculations/pcr_calculator.py backend/calculations/atm_oi_calculator.py  # Must return nothing

# data_loader outputs Title-Case columns
grep "\"Open\"\|\"High\"\|\"Low\"\|\"Close\"\|\"Volume\"\|index\.name.*Date" backend/backtesting/data_loader.py
```

**All commands must return zero results (or the expected confirmation) before any phase is marked complete.**
# Docker project name is pinned
grep "^name:" docker-compose.yml
```

All commands above must return zero results (or the expected confirmation line) before any phase is marked complete.

---

## 14. UI Implementation Specifications

This section maps every Streamlit visual to its React equivalent, with exact color constants, data contracts, and implementation notes needed for the new frontend to match the existing dashboard behavior pixel-for-pixel.

---

### 14.1 Color Constants

Define all colors in a single file: `frontend/src/theme/colors.ts`

```typescript
export const COLORS = {
  // Candlestick / PnL direction
  UP:   "#089981",   // Bullish candle, advances, profit
  DOWN: "#f23645",   // Bearish candle, declines, loss

  // Chart overlays
  SMA_5:       "#2962FF",   // Also: primary brand color, navbar
  SMA_20:      "#F59E0B",   // Amber
  SMA_50:      "#7C3AED",   // Purple
  VWAP_CHART:  "#0F766E",   // Chart overlay VWAP (typical price)

  // Options
  CE: "#EF5350",   // Call option bars
  PE: "#26A69A",   // Put option bars

  // ATM Straddle panel
  IV:       "#3B82F6",   // Implied Volatility line (left axis)
  STRADDLE: "#EF4444",   // Straddle value line (right axis)

  // App chrome
  BG:               "#ffffff",
  BORDER:           "#e1e3e6",
  NAVBAR_PRIMARY:   "#2962FF",

  // OI Heatmap cells
  OI_HEAT_GREEN_BG: "#DCFCE7",
  OI_HEAT_GREEN_FG: "#067A46",
  OI_HEAT_RED_BG:   "#FEE2E2",
  OI_HEAT_RED_FG:   "#B91C1C",
  OI_HEAT_NEUTRAL_BG: "#F3F4F6",
  OI_HEAT_NEUTRAL_FG: "#374151",
} as const;
```

---

### 14.2 Navbar (`frontend/src/components/layout/Navbar.tsx`)

**Streamlit source:** `Dashboard/navbar.py` — `streamlit-option-menu`, 5 pages

**React spec:**
- Fixed top bar, `background: COLORS.BG`, `border-bottom: 1px solid COLORS.BORDER`
- Active tab: `COLORS.NAVBAR_PRIMARY` (#2962FF) underline + text
- Routes (React Router v6):

| Route | Page |
|---|---|
| `/auth` | Zerodha Authentication |
| `/` | Dashboard (Backtest History) |
| `/backtests` | Backtests |
| `/market-pulse` | Market Pulse |
| `/live-market` | Live Market Data Visuals |

---

### 14.3 CandlestickChart (`frontend/src/components/charts/CandlestickChart.tsx`)

**Streamlit source:** `Dashboard/Live_market_data_visuals/visuals/candlestick_chart.py`
- Plotly 2-row subplot: 74% candles, 26% volume bar
- Height: 520px, range slider hidden, scrollZoom enabled

**React spec:** TradingView Lightweight Charts

```typescript
import { createChart, CandlestickSeries, HistogramSeries, LineSeries } from "lightweight-charts";

const chart = createChart(container, {
  width: container.clientWidth,
  height: 520,
  layout: { background: { color: "#ffffff" }, textColor: "#374151" },
  grid: { vertLines: { color: "#f0f0f0" }, horzLines: { color: "#f0f0f0" } },
  timeScale: { timeVisible: true, secondsVisible: false },
  crosshair: { mode: 1 },  // CrosshairMode.Magnet
});

// Candlestick series
const candleSeries = chart.addCandlestickSeries({
  upColor:        COLORS.UP,
  downColor:      COLORS.DOWN,
  borderUpColor:  COLORS.UP,
  borderDownColor: COLORS.DOWN,
  wickUpColor:    COLORS.UP,
  wickDownColor:  COLORS.DOWN,
});

// Overlay indicators on same price scale
const sma5Series   = chart.addLineSeries({ color: COLORS.SMA_5,      lineWidth: 1, title: "SMA 5"  });
const sma20Series  = chart.addLineSeries({ color: COLORS.SMA_20,     lineWidth: 1, title: "SMA 20" });
const sma50Series  = chart.addLineSeries({ color: COLORS.SMA_50,     lineWidth: 1, title: "SMA 50" });
const vwapSeries   = chart.addLineSeries({ color: COLORS.VWAP_CHART, lineWidth: 1.5, title: "VWAP" });

// Volume histogram on a separate price scale (occupies bottom 20% of chart)
const volumeSeries = chart.addHistogramSeries({
  color: "#26a69a",
  priceFormat: { type: "volume" },
  priceScaleId: "volume",
});
chart.priceScale("volume").applyOptions({ scaleMargins: { top: 0.8, bottom: 0 } });
```

**Bar data contract** (from `GET /api/market/bars?token=X&timeframe=Y&date=Z&indicators=sma,vwap`):
```typescript
type Bar = {
  time: number;    // UNIX seconds — NOT milliseconds. Backend must return int(datetime.timestamp())
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  sma5?:  number;  // Cython-backed SMA(5) on close
  sma20?: number;  // Cython-backed SMA(20) on close
  sma50?: number;  // Cython-backed SMA(50) on close
  vwap?:  number;  // Typical price VWAP: (H+L+C)/3 × volume — Cython compute_vwap_typical
};
```

**Real-time update pattern:**
```typescript
// On new_bar WS event: call .update(), NOT .setData()
ws.on("new_bar", (bar: Bar) => {
  if (bar.instrument_token === selectedToken && bar.timeframe === selectedTimeframe) {
    candleSeries.update(bar);
    if (bar.volume !== undefined) volumeSeries.update({ time: bar.time, value: bar.volume });
  }
});
```

**Critical setup guards:**
```typescript
useEffect(() => {
  if (!bars.length) return;                    // Guard: never call setData([])
  const sorted = [...bars].sort((a, b) => a.time - b.time);  // Must be ascending
  candleSeries.setData(sorted);
  chart.timeScale().fitContent();              // Fit all bars in view after load
  return () => chart.remove();                 // Critical: prevent memory leak on unmount
}, []);
```

---

### 14.4 OptionChainTable (`frontend/src/components/market/OptionChainTable.tsx`)

**Streamlit source:** `Dashboard/Live_market_data_visuals/visuals/option_chain_chart.py`
- Grouped bar chart (CE/PE OI by strike) + tabular data table

**React spec:** Two sub-components in one panel.

**Sub-component A — OI Bar Chart:**
```typescript
// Two HistogramSeries side-by-side by strike price
// CE bars: COLORS.CE = "#EF5350"
// PE bars: COLORS.PE = "#26A69A"
// X-axis: strike prices, Y-axis: OI values
```

**Sub-component B — Data Table:**

Column order: `CE LTP | CE OI | CE OI Chg% | Strike | PE LTP | PE OI | PE OI Chg% | Strike PCR`

```typescript
type OptionChainRow = {
  strike:             number;
  ce_ltp:             number;
  ce_oi:              number;
  ce_oi_change_pct:   number;  // Color: positive=COLORS.UP, negative=COLORS.DOWN
  pe_ltp:             number;
  pe_oi:              number;
  pe_oi_change_pct:   number;  // Color: positive=COLORS.UP, negative=COLORS.DOWN
  strike_pcr:         number;  // ce_oi / pe_oi for this specific strike
  is_atm:             boolean; // ATM row gets highlighted background (#2962FF at 10% opacity)
};
```

Data source: `GET /api/market/option-chain?underlying=NIFTY&date=Z`

---

### 14.5 ADRatioPanel (`frontend/src/components/market/ADRatioPanel.tsx`)

**Streamlit source:** `Dashboard/Live_market_data_visuals/visuals/ad_chart.py` — Plotly line chart

**React spec:** Lightweight Charts with two LineSeries

```typescript
const advanceSeries = chart.addLineSeries({ color: COLORS.PE,   lineWidth: 2, title: "Advances" });  // #26A69A
const declineSeries = chart.addLineSeries({ color: COLORS.CE,   lineWidth: 2, title: "Declines" });  // #EF5350
```

Data contract (`GET /api/market/snapshots/ad`):
```typescript
type ADSnapshot = {
  snapshot_type: "ad";
  generated_at: string;
  trading_date: string;
  data: {
    advances:   number;
    declines:   number;
    unchanged:  number;
    ad_ratio:   number;
    history:    Array<{ time: number; advances: number; declines: number }>;
  };
};
```

Updates via `snapshot_update` WebSocket event with `snapshot_type: "ad"`.

---

### 14.6 ATMStraddlePanel (`frontend/src/components/market/ATMStraddlePanel.tsx`)

**Streamlit source:** `Dashboard/Live_market_data_visuals/visuals/atm_straddle_chart.py` — Plotly dual Y-axis

**React spec:** Lightweight Charts with two separate price scales (left/right):

```typescript
// Left axis: IV (Implied Volatility)
const ivSeries = chart.addLineSeries({
  color: COLORS.IV,        // #3B82F6
  lineWidth: 2,
  title: "IV",
  priceScaleId: "left",
});

// Right axis: Straddle value
const straddleSeries = chart.addLineSeries({
  color: COLORS.STRADDLE,  // #EF4444
  lineWidth: 2,
  title: "Straddle",
  priceScaleId: "right",
});

chart.priceScale("left").applyOptions({ position: "left" });
chart.priceScale("right").applyOptions({ position: "right" });
```

Data contract (`GET /api/market/snapshots/atm_oi`):
```typescript
type ATMOISnapshot = {
  data: {
    nifty_atm: {
      strike: number; ce_iv: number; pe_iv: number;
      avg_iv: number; straddle_value: number;
    };
    banknifty_atm: {
      strike: number; ce_iv: number; pe_iv: number;
      avg_iv: number; straddle_value: number;
    };
    history: Array<{ time: number; iv: number; straddle: number }>;
  };
};
```

---

### 14.7 PCRPanel (`frontend/src/components/market/PCRPanel.tsx`)

**Streamlit source:** Metric cards in `Dashboard/Live_market_data_visuals/` — no chart, values only

**React spec:** Two metric cards in a flex row

```typescript
// Color logic for PCR badge:
// PCR > 1.2  → COLORS.UP   (bullish — more puts = hedging interest)
// PCR < 0.8  → COLORS.DOWN (bearish — fewer puts)
// 0.8–1.2    → neutral gray

// Layout:
// ┌───────────────────┐  ┌───────────────────┐
// │  NIFTY PCR        │  │  BANKNIFTY PCR    │
// │  1.23  [BULLISH]  │  │  0.87  [NEUTRAL]  │
// └───────────────────┘  └───────────────────┘
```

Data source: `GET /api/market/snapshots/pcr`

---

### 14.8 OIHeatmap (`frontend/src/components/charts/OIHeatmap.tsx`)

**Streamlit source:** `Dashboard/Live_market_data_visuals/visuals/oi_heatmap.py` — styled pandas DataFrame rendered as HTML table

**React spec:** HTML `<table>` with inline style cell coloring

```typescript
// Cell color logic (relative to max OI across all strikes × expiries):
// High OI (> 70% of max): { background: COLORS.OI_HEAT_GREEN_BG, color: COLORS.OI_HEAT_GREEN_FG }
// Low  OI (< 30% of max): { background: COLORS.OI_HEAT_RED_BG,   color: COLORS.OI_HEAT_RED_FG   }
// Mid  OI (30–70%):       { background: COLORS.OI_HEAT_NEUTRAL_BG, color: COLORS.OI_HEAT_NEUTRAL_FG }

function getCellStyle(oi: number, maxOI: number): React.CSSProperties {
  const ratio = oi / maxOI;
  if (ratio > 0.7) return { background: COLORS.OI_HEAT_GREEN_BG, color: COLORS.OI_HEAT_GREEN_FG };
  if (ratio < 0.3) return { background: COLORS.OI_HEAT_RED_BG,   color: COLORS.OI_HEAT_RED_FG   };
  return { background: COLORS.OI_HEAT_NEUTRAL_BG, color: COLORS.OI_HEAT_NEUTRAL_FG };
}
```

Data source: `GET /api/market/option-chain?underlying=NIFTY` (same endpoint as OptionChainTable)

---

### 14.9 DataSelector (`frontend/src/components/backtesting/DataSelector.tsx`)

**Streamlit source:** `Dashboard/Backtesting_page/Features/data_selection_feature.py`
- Had 3 tabs: CSV upload | Zerodha API download | Live Market data

**React spec — ZERO tabs, MongoDB catalog only:**

```typescript
// 1. On mount: GET /api/historical/catalog
// 2. Render instrument dropdown (populated from catalog)
// 3. On instrument select: show available timeframes as buttons
// 4. On timeframe select: date pickers, constrained to catalog's date_from/date_to
// 5. Summary line: "98,400 bars · 2025-01-02 to 2026-04-29"
// 6. If catalog is empty OR no data for selected params → CatalogEmptyState

type CatalogEntry = {
  instrument_token:      number;
  tradingsymbol:         string;
  timeframes_available:  string[];
  date_from:             string;   // "2025-01-02"
  date_to:               string;   // "2026-04-29"
  total_bars:            number;
  data_source:           "historical" | "live" | "mixed";
};
```

React Query setup for catalog — must use `staleTime: 0` (invalidated after every ingest completion):
```typescript
const { data: catalog } = useQuery({
  queryKey: ["catalog"],
  queryFn: () => api.getCatalog(),
  staleTime: 0,  // Always fresh — see E-19
});

// After successful ingest, invalidate:
queryClient.invalidateQueries({ queryKey: ["catalog"] });
```

---

### 14.10 StrategyEditor (`frontend/src/components/backtesting/StrategyEditor.tsx`)

**Streamlit source:** `Dashboard/Backtesting_page/Features/strategy_editor.py` — `streamlit-ace`

**React spec:** Monaco Editor (same engine as VS Code)

```typescript
import Editor from "@monaco-editor/react";

<Editor
  height="400px"
  language="python"
  theme="vs-light"
  value={strategySource}
  onChange={(value) => setStrategySource(value ?? "")}
  options={{
    minimap: { enabled: false },
    fontSize: 13,
    fontFamily: "'JetBrains Mono', 'Fira Code', monospace",
    wordWrap: "on",
    scrollBeyondLastLine: false,
    // Disable TypeScript/JS validation (we're editing Python)
    "editor.validate": false,
  }}
/>
```

Save flow: `PUT /api/strategies/{name}` — debounce 1000ms after last keystroke, show save indicator.

---

### 14.11 BacktestTerminal (`frontend/src/components/backtesting/BacktestTerminal.tsx`)

**Streamlit source:** No real-time equivalent — Streamlit blocked until backtest completed

**React spec:** WebSocket-backed streaming terminal

```typescript
// Connects to /ws/backtest/{task_id} immediately on backtest start
// Message handling:
//   { type: "log",      payload: { line: string } }   → append to terminal output
//   { type: "complete", payload: { task_id, status } } → fetch result + close WS
//   { type: "error",    payload: { message: string } } → show error state

// Terminal styling:
const terminalStyle = {
  background: "#1e1e1e",   // VS Code dark theme
  color: "#d4d4d4",
  fontFamily: "monospace",
  fontSize: "12px",
  padding: "12px",
  height: "300px",
  overflowY: "auto",
};

// Auto-scroll behavior: scroll to bottom on new line unless user has scrolled up
```

---

### 14.12 CollectorControls (`frontend/src/components/collector/CollectorControls.tsx`)

**Streamlit source:** `Dashboard/market_pulse_page/market_pulse_features/collector_status.py`

**React spec:**

```typescript
// 4 control buttons:
// [▶ Start Collector]  [■ Stop Collector]  [▶ Start Calculator]  [■ Stop Calculator]

// 8 metric tiles in 2 rows (4 per row):
// Row 1: Status | PID | Trading Date | Tokens Subscribed
// Row 2: Bars Written | Last Tick At | Calculator Status | Calculator Last Run

// Collapsible error expanders:
// "Last Collector Error" → shows collector.last_error if non-null
// "Last Calculator Error" → shows calculator.last_error if non-null

// Live data preview table (bottom of panel):
// Shows last 5 bars received via new_bar WS events
// Columns: Time (IST) | Symbol | Open | High | Low | Close | Volume
```

Data contract from `collector_status` WS event:
```typescript
type CollectorStatus = {
  collector: {
    status:             "running" | "stopped" | "error" | "holiday" | "auth_error";
    pid:                number | null;
    started_at:         string | null;
    trading_date:       string | null;
    tokens_subscribed:  number;
    bars_written:       number;
    last_tick_at:       string | null;
    last_error:         string | null;
  };
  calculator: {
    status:      "running" | "stopped" | "error";
    pid:         number | null;
    last_run_at: string | null;
    last_error:  string | null;
  };
};
```

---

### 14.13 New Components (No Streamlit Equivalent)

These components are required by the MongoDB-only architecture and have no Streamlit counterpart.

#### HistoricalIngestPanel (`frontend/src/components/backtesting/HistoricalIngestPanel.tsx`)
Power-user panel for requesting Zerodha historical data ingestion:

```typescript
// Instrument search: autocomplete against GET /api/market/instruments?q=...
// Timeframe select: radio buttons — 1min | 3min | 5min | 15min | 30min | 60min
// Date range: from/to date pickers (no constraint — user picks any range)
// Submit → POST /api/historical/ingest → get { job_id }
// Progress polling: GET /api/historical/ingest/{job_id} every 2s
// Progress display: "Fetching NIFTY 50 — batch 3/7 — 2,400 bars inserted"
// On complete: invalidate ["catalog"] React Query key
```

#### CatalogEmptyState (`frontend/src/components/backtesting/CatalogEmptyState.tsx`)
Shown inside DataSelector when catalog is empty:

```
┌─────────────────────────────────────────────────┐
│  No historical data in MongoDB yet.             │
│                                                  │
│  [Ingest Data from Zerodha →]                   │
└─────────────────────────────────────────────────┘
```

#### StatusBadge (`frontend/src/components/collector/StatusBadge.tsx`)
Reusable badge for collector/calculator status:

| Status | Color | Label |
|---|---|---|
| `running` | Green dot | LIVE |
| `stopped` | Gray dot | STOPPED |
| `error` | Red dot | ERROR |
| `holiday` | Blue dot | HOLIDAY |
| `auth_error` | Amber dot | AUTH EXPIRED |

---

### 14.14 Zustand Store Design

**`frontend/src/stores/marketStore.ts`:**
```typescript
type SnapshotType = "vwap" | "ad" | "pcr" | "atm_oi" | "vix";

interface MarketStore {
  snapshots:         Partial<Record<SnapshotType, unknown>>;
  collectorStatus:   CollectorStatus | null;
  selectedToken:     number | null;
  selectedTimeframe: string;  // default: "5min"
  recentBars:        Bar[];   // last 5 bars for live data preview

  setSnapshot:          (type: SnapshotType, data: unknown) => void;
  setCollectorStatus:   (status: CollectorStatus) => void;
  setSelectedToken:     (token: number) => void;
  setSelectedTimeframe: (tf: string) => void;
  appendRecentBar:      (bar: Bar) => void;
}
```

**`frontend/src/stores/backtestStore.ts`:**
```typescript
interface BacktestStore {
  activeTaskId:   string | null;
  terminalLines:  string[];
  result:         BacktestResult | null;
  dataSelection:  DataSelection | null;

  startBacktest:       (params: BacktestRequest) => Promise<void>;
  appendTerminalLine:  (line: string) => void;
  setResult:           (result: BacktestResult) => void;
  clearTerminal:       () => void;
}
```

---

### 14.15 TradingView Lightweight Charts — Critical Implementation Notes

1. **Pin library version** to `lightweight-charts@4.x` — v5 has breaking API changes
2. **Container must have explicit dimensions** — use `ResizeObserver` to handle window resize:
   ```typescript
   const ro = new ResizeObserver(() => chart.applyOptions({ width: container.clientWidth }));
   ro.observe(container);
   return () => ro.disconnect();
   ```
3. **`time` field must be UNIX seconds** (integer ~1.7 billion for 2024 dates). If `time` is in milliseconds (~1.7 trillion), bars appear in year 52000. Backend must return `int(datetime.timestamp())`, not `int(datetime.timestamp() * 1000)`.
4. **Sort before setData** — always sort bars ascending by `time` before calling `series.setData(bars)`. Unsorted data causes the chart to render with visual artifacts.
5. **Always call `chart.remove()` in useEffect cleanup** — failure causes memory leaks on component unmount; each navigation away from the chart page without cleanup leaks ~50MB.
6. **After bulk data load**, call `chart.timeScale().fitContent()` to show all bars in the visible range.
7. **`series.update()` for live bars, `series.setData()` only on initial load or timeframe change** — calling `setData()` on every new bar causes a full re-render flicker.

---

## 15. Pandas-TA Migration (TA-Lib Replacement)

### Why This Change

TA-Lib requires compiling a C shared library (`libc-ta-lib.so`) from source during the Docker build:
```bash
# OLD — removed from Dockerfile.backend:
wget http://prdownloads.sourceforge.net/ta-lib/ta-lib-0.4.0-src.tar.gz
tar -xzf ta-lib-0.4.0-src.tar.gz && cd ta-lib && ./configure --prefix=/usr && make && make install
```

This adds ~5–8 minutes to every Docker build, requires `wget curl build-essential`, and can fail on ARM builds (Apple Silicon, Raspberry Pi). `pandas-ta` is a pure Python library — `pip install pandas-ta==0.3.14b0` and done.

**TA-Lib is removed. `pandas-ta` replaces it everywhere.**

---

### 15.1 What Used TA-Lib

| File | TA-Lib Usage | Status |
|---|---|---|
| `Dashboard/dashboard_page/dashboard_features/talib_indicators.py` | `talib.get_functions()`, `talib.abstract.<NAME>` for all indicators | **Deleted** with Dashboard — replaced by `backend/indicators/indicator_engine.py` |
| `Dashboard/dashboard_section.py` | Imports from `talib_indicators.py` | **Deleted** with Dashboard |

TA-Lib was only used in the Dashboard (Streamlit). The live calculators and backtesting engine never used TA-Lib. The migration is a clean swap with no impact on collector, calculator, or Backtrader.

---

### 15.2 New Indicator Architecture

```
backend/indicators/
├── sma.py               → Calls Cython compute_sma      (performance-critical, computed every 60s)
├── rsi.py               → Calls Cython compute_rsi      (performance-critical, computed every 60s)
├── vwap.py              → Calls Cython compute_vwap_typical  (chart overlay, typical price)
└── indicator_engine.py  → pandas-ta for ALL other indicators (called on demand per chart request)
```

**Rule:** Cython handles the 3 indicators computed every 60s on thousands of tokens. `pandas-ta` handles everything else the user requests on a single instrument's chart.

---

### 15.3 `indicator_engine.py` Implementation

**File:** `backend/indicators/indicator_engine.py`

Replaces the dynamic TA-Lib dispatch in `talib_indicators.py`.

```python
import pandas as pd
import pandas_ta as ta

# Map indicator names to pandas-ta strategy calls
# This replaces talib.get_functions() enumeration

AVAILABLE_INDICATORS = {
    # Overlays (plotted on candlestick row)
    "sma":    {"kind": "sma",    "params": {"length": 20}},
    "ema":    {"kind": "ema",    "params": {"length": 20}},
    "bbands": {"kind": "bbands", "params": {"length": 20, "std": 2}},
    "vwap":   None,  # Handled by Cython compute_vwap_typical — not pandas-ta
    # Oscillators (plotted in separate sub-rows)
    "rsi":    {"kind": "rsi",    "params": {"length": 14}},
    "macd":   {"kind": "macd",   "params": {"fast": 12, "slow": 26, "signal": 9}},
    "stoch":  {"kind": "stoch",  "params": {"k": 14, "d": 3}},
    "adx":    {"kind": "adx",    "params": {"length": 14}},
    "atr":    {"kind": "atr",    "params": {"length": 14}},
}

OVERLAY_INDICATORS = {"sma", "ema", "bbands", "vwap"}
OSCILLATOR_INDICATORS = {"rsi", "macd", "stoch", "adx", "atr"}


def compute_indicators(df: pd.DataFrame, indicators: list[str]) -> pd.DataFrame:
    """
    df must have columns: Open, High, Low, Close, Volume (Title-Case — matches data_loader output).
    Returns df with additional indicator columns appended.
    """
    # pandas-ta expects lowercase column names internally
    df_lower = df.rename(columns=str.lower)

    for ind in indicators:
        if ind not in AVAILABLE_INDICATORS or AVAILABLE_INDICATORS[ind] is None:
            continue
        spec = AVAILABLE_INDICATORS[ind]
        result = df_lower.ta(kind=spec["kind"], **spec["params"], append=False)
        if result is not None:
            if isinstance(result, pd.Series):
                df[result.name] = result.values
            elif isinstance(result, pd.DataFrame):
                for col in result.columns:
                    df[col] = result[col].values

    return df
```

**Key API difference from TA-Lib:**

| Concept | TA-Lib (old) | pandas-ta (new) |
|---|---|---|
| List all indicators | `talib.get_functions()` | `df.ta.indicators()` |
| Run by name | `talib.abstract.SMA(inputs, timeperiod=20)` | `df.ta(kind="sma", length=20)` |
| Input format | Dict of arrays: `{"open": arr, ...}` | DataFrame with OHLCV columns |
| Output format | NumPy array | pandas Series or DataFrame |
| Overlay detection | Manual list | Not built-in — use `OVERLAY_INDICATORS` set above |

---

### 15.4 Indicator Output in API Response

Route: `GET /api/market/bars?token=X&timeframe=Y&date=Z&indicators=sma,rsi,macd`

```python
# backend/api/routes/market_data.py
@router.get("/market/bars")
async def get_bars(
    token: int,
    timeframe: str,
    date: str,
    indicators: str = "",   # comma-separated list: "sma,rsi,macd"
):
    bars_df = await bar_repository.get_bars(token, timeframe, date)

    if indicators:
        ind_list = [i.strip() for i in indicators.split(",") if i.strip()]

        # Cython-backed indicators (fast, always use Cython for these)
        if "sma" in ind_list:
            from backend.cython_math import compute_sma
            bars_df["sma5"]  = compute_sma(bars_df["Close"].to_numpy(), 5)
            bars_df["sma20"] = compute_sma(bars_df["Close"].to_numpy(), 20)
            bars_df["sma50"] = compute_sma(bars_df["Close"].to_numpy(), 50)
            ind_list.remove("sma")

        if "vwap" in ind_list:
            from backend.cython_math import compute_vwap_typical
            bars_df["vwap"] = compute_vwap_typical(
                bars_df["High"].to_numpy(),
                bars_df["Low"].to_numpy(),
                bars_df["Close"].to_numpy(),
                bars_df["Volume"].to_numpy(),
            )
            ind_list.remove("vwap")

        # pandas-ta for all other indicators
        if ind_list:
            from backend.indicators.indicator_engine import compute_indicators
            bars_df = compute_indicators(bars_df, ind_list)

    return bars_df.to_dict(orient="records")
```

---

### 15.5 Dockerfile.backend (Final — No TA-Lib)

```dockerfile
FROM python:3.11-slim

# build-essential is needed only for Cython compilation
# No wget, no curl, no external C library compilation
RUN apt-get update && apt-get install -y build-essential && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
# Build Cython kernels inside the container — no host compiler needed
RUN cd backend/cython_math && python setup.py build_ext --inplace

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

**Build time improvement:** Removing TA-Lib C compilation saves ~5–8 minutes per fresh Docker build.

---

### 15.6 requirements.txt Changes

```diff
- ta-lib==0.4.28
+ pandas-ta==0.3.14b0
```

Verify the exact available version before pinning: `pip index versions pandas-ta`

---

### 15.7 Dead Code Removal (TA-Lib Specific)

After implementing `backend/indicators/indicator_engine.py`:

```bash
# Must all return zero results after migration
grep -r "import talib"    backend/
grep -r "from talib"      backend/
grep -r "talib.abstract"  backend/
grep -r "ta-lib"          requirements.txt  # Must return zero results
```

`Dashboard/dashboard_page/dashboard_features/talib_indicators.py` is deleted along with the entire `Dashboard/` folder (Section 9). No separate cleanup step needed — it is already in the dead code list.

---

### 15.8 E-35 [GUARANTEED] — TA-Lib Import Crash After Dockerfile Cleanup

**What breaks:** If any Python file in `backend/` still has `import talib` after the Dockerfile removes the TA-Lib C library, the import will raise `ImportError: libtalib.so.0: cannot open shared object file`. This crashes the entire FastAPI process at startup.

**Guardrail:**
```bash
grep -r "import talib\|from talib" backend/   # Must return zero results
```
Run this check as part of the pre-merge checklist (already added to Section 13 pre-merge commands).

**Pre-patch checks:**
- [ ] Confirm `talib_indicators.py` is deleted or not present in `backend/`
- [ ] Confirm `indicator_engine.py` is present in `backend/indicators/`

**Post-patch sanity check:** `docker compose exec backend python -c "import backend.indicators.indicator_engine; print('ok')"` returns `ok` with no ImportError.

---

**Add E-35 to the Summary Table (Section 13):**

| E-35 | GUARANTEED | Pandas-TA/Import | Critical | Phase 3 |
