# Live Market Data Pipeline — Implementation Plan

**Date:** 2026-04-28  
**Scope:** Add a real-time market data collection system (WebSocket → CSV → calculations → Streamlit) as a new "Market Pulse" page, built alongside the existing backtesting system without modifying any existing UI components.

---

## 1. System Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│  PROCESS A: WebSocket Collector (background, always-on subprocess)   │
│  KiteTicker → on_ticks → bar_aggregator → equities_1min.csv        │
│                                         → options_1min.csv          │
│                                         → vix_1min.csv              │
└─────────────────────────────────────────────────────────────────────┘
                              ↓ (files written every minute)
┌─────────────────────────────────────────────────────────────────────┐
│  PROCESS B: Calculation Runner (background, runs every 60s)          │
│  equities_1min.csv → VWAP per stock → vwap_snapshot.json           │
│  equities_1min.csv + prev_close.json → A/D → ad_snapshot.json      │
│  options_1min.csv → PCR, ATM OI → pcr_snapshot.json               │
│  vix_1min.csv → current VIX → vix_snapshot.json                    │
└─────────────────────────────────────────────────────────────────────┘
                              ↓ (snapshots read on page load)
┌─────────────────────────────────────────────────────────────────────┐
│  PROCESS C: Streamlit (existing, unchanged except new page added)    │
│  Market Pulse page reads JSON snapshots — no WebSocket, no blocking │
└─────────────────────────────────────────────────────────────────────┘
```

The three processes are **completely decoupled**. Streamlit crashing does not affect the collector. The collector crashing shows stale data in Streamlit but does not break it.

---

## 2. File Map — What to Create, What to Modify

### 2.1 New Files (each file has exactly one purpose)

```
LiveMarket/
├── __init__.py                                  # Package marker only
├── run_collector.py                             # Entry point for subprocess A
├── run_calculations.py                          # Entry point for subprocess B
│
├── collector/
│   ├── __init__.py
│   ├── token_loader.py                          # Reads instruments CSV → returns token groups
│   ├── prev_close_loader.py                     # Fetches yesterday's close for all equity tokens
│   ├── bar_aggregator.py                        # 1-min OHLCV state machine (keyed by token)
│   └── ws_collector.py                          # KiteTicker connection + tick routing
│
└── calculations/
    ├── __init__.py
    ├── vwap_calculator.py                       # VWAP from equities_1min.csv
    ├── ad_calculator.py                         # Advance/Decline from equities_1min + prev_close
    ├── pcr_calculator.py                        # PCR from options_1min.csv
    ├── atm_oi_calculator.py                     # ATM OI from options_1min.csv
    ├── vix_reader.py                            # Current VIX from vix_1min.csv
    ├── snapshot_writer.py                       # Atomic JSON write for all snapshots
    └── calculation_runner.py                    # Orchestrates all calcs, loops every 60s

Dashboard/
└── market_pulse_page/
    ├── __init__.py
    ├── market_pulse_section.py                  # Streamlit render function for Market Pulse page
    └── features/
        ├── __init__.py
        └── collector_controller.py              # Start/stop/status of subprocesses A and B

Data/
└── live_market/                                 # (created at runtime by collector)
    ├── equities_1min.csv
    ├── options_1min.csv
    ├── vix_1min.csv
    ├── prev_close.json
    ├── collector_status.json
    └── snapshots/
        ├── vwap_snapshot.json
        ├── ad_snapshot.json
        ├── pcr_snapshot.json
        ├── atm_oi_snapshot.json
        └── vix_snapshot.json
```

### 2.2 Existing Files to Modify (minimal, additive only)

| File | What Changes | What Does NOT Change |
|---|---|---|
| `Dashboard/navbar.py` | Add `"Market Pulse"` to options list and `"activity"` icon | All existing styles, color constants, existing options |
| `Dashboard/dashboard.py` | Add import + `elif selected == "Market Pulse"` branch | All existing page routes |
| `requirements.txt` | No changes — `kiteconnect` already installed | Everything |

---

## 3. Data File Schemas

### `Data/live_market/equities_1min.csv`
```
timestamp,instrument_token,tradingsymbol,open,high,low,close,volume
2026-04-28 09:15:00+05:30,256265,NIFTY50-EQ,22100.0,22150.0,22090.0,22120.0,145000
```

### `Data/live_market/options_1min.csv`
```
timestamp,instrument_token,tradingsymbol,strike,expiry,option_type,open,high,low,close,volume,oi
2026-04-28 09:15:00+05:30,8979714,NIFTY24500CE,24500,2026-05-01,CE,150.0,155.0,148.0,153.0,45000,1200000
```

### `Data/live_market/vix_1min.csv`
```
timestamp,open,high,low,close
2026-04-28 09:15:00+05:30,14.20,14.30,14.10,14.25
```

### `Data/live_market/prev_close.json`
```json
{
  "generated_at": "2026-04-28T09:00:00",
  "date": "2026-04-25",
  "data": {
    "256265": 22050.5,
    "260105": 498.2
  }
}
```

### `Data/live_market/collector_status.json`
```json
{
  "status": "running",
  "started_at": "2026-04-28T09:14:55",
  "tokens_subscribed": 2487,
  "last_tick_at": "2026-04-28T09:22:31",
  "bars_written": 14922
}
```

### `Data/live_market/snapshots/ad_snapshot.json`
```json
{
  "generated_at": "2026-04-28T09:22:00",
  "advances": 1243,
  "declines": 891,
  "unchanged": 353,
  "ad_ratio": 1.39
}
```

### `Data/live_market/snapshots/vix_snapshot.json`
```json
{
  "generated_at": "2026-04-28T09:22:00",
  "vix": 14.25,
  "vix_open": 14.20
}
```

### `Data/live_market/snapshots/pcr_snapshot.json`
```json
{
  "generated_at": "2026-04-28T09:22:00",
  "nifty_pcr": 0.87,
  "banknifty_pcr": 1.12,
  "total_call_oi": 45000000,
  "total_put_oi": 39150000
}
```

### `Data/live_market/snapshots/atm_oi_snapshot.json`
```json
{
  "generated_at": "2026-04-28T09:22:00",
  "nifty_atm_strike": 24500,
  "nifty_atm_call_oi": 1200000,
  "nifty_atm_put_oi": 980000,
  "banknifty_atm_strike": 52000,
  "banknifty_atm_call_oi": 450000,
  "banknifty_atm_put_oi": 390000
}
```

### `Data/live_market/snapshots/vwap_snapshot.json`
```json
{
  "generated_at": "2026-04-28T09:22:00",
  "data": {
    "256265": 22115.4,
    "260105": 499.8
  }
}
```

---

## 4. Per-File Implementation Specifications

---

### `LiveMarket/collector/token_loader.py`

**Single purpose:** Read the Zerodha instruments CSV and return three token groups.

**Inputs:** Path to `Data/instrument_mapper_data/zerodha_instruments_latest.csv`

**Outputs:**
- `equity_tokens`: set of int — all tokens where `segment == "NSE"` and `instrument_type == "EQ"`
- `options_tokens`: set of int — tokens where `segment == "NFO"` and `instrument_type in ["CE", "PE"]`, filtered to near-term expiry only (next 2 expiry dates from today)
- `vix_token`: int — token for INDIA VIX (search `tradingsymbol == "INDIA VIX"` in NSE segment)
- `options_meta`: dict mapping `token → {strike, expiry, option_type, tradingsymbol}` — needed by calculators

**Edge cases:**
- If instruments CSV does not exist → raise `FileNotFoundError` with clear message, do not start collector
- If no INDIA VIX token found → `vix_token = None`, log warning, skip VIX collection
- If options CSV has no near-term expiry rows → return empty options set, log warning
- Expiry filtering: parse `expiry` column as date, keep rows where expiry is within the next 14 calendar days from today

**What to check before writing this file:**
- Open `Data/instrument_mapper_data/zerodha_instruments_latest.csv` manually and confirm column names: `instrument_token`, `segment`, `instrument_type`, `tradingsymbol`, `expiry`, `strike`
- Confirm INDIA VIX appears in the CSV (search it)
- Confirm NSE EQ segment rows exist and have integer `instrument_token` values

---

### `LiveMarket/collector/prev_close_loader.py`

**Single purpose:** Fetch previous trading day close price for all equity tokens using Zerodha `/quote` endpoint.

**Inputs:** `equity_tokens` (set of int), Kite client instance

**Outputs:** `prev_close.json` written to `Data/live_market/`

**Logic:**
1. Batch equity_tokens into groups of 500 (Zerodha `/quote` limit)
2. For each batch, call `kite.quote(["NSE:" + sym for sym in batch_syms])`
3. Extract `ohlc.close` from each quote response as yesterday's close
4. Write all results to `prev_close.json` with ISO timestamp

**Edge cases:**
- `/quote` call fails for a batch → log which tokens failed, skip them (do not crash)
- Token has no `ohlc.close` in response → skip, it will be excluded from A/D calculation
- Rate limit hit (429) → sleep 1s, retry once per batch
- If prev_close.json already exists and was written today → skip the fetch, return cached data
- Market is closed at startup (pre-9:15) → this is expected and normal, fetch still works

**What to check before writing this file:**
- Test manually: `kite.quote(["NSE:RELIANCE"])` — confirm `ohlc.close` is in the response dict
- Confirm the Kite client initialization pattern from `zerodha_historical_data.py` `get_kite_client()` method and reuse it verbatim

---

### `LiveMarket/collector/bar_aggregator.py`

**Single purpose:** Maintain an in-memory 1-minute OHLCV bar state for each instrument token.

**State:** Single dict `bars: dict[int, dict]` keyed by `instrument_token`

**Each bar dict has:** `open`, `high`, `low`, `close`, `volume`, `oi`, `bar_start` (datetime, minute-truncated)

**Public methods:**
- `update(token, ltp, volume, oi, tick_time)` → updates or initializes the bar for `token`
- `close_bar(token, minute_start)` → returns the completed bar as a dict and resets bar state for that token
- `get_completed_bars(current_minute)` → returns list of `(token, bar_dict)` for all tokens whose `bar_start < current_minute`, resets those tokens

**Bar transition logic:**
- Each tick carries a timestamp. Truncate to minute: `tick_time.replace(second=0, microsecond=0)`
- If `bars[token]` does not exist → initialize new bar: `open=ltp, high=ltp, low=ltp, close=ltp`
- If `bar_start == current_minute` → update: `high=max(high, ltp)`, `low=min(low, ltp)`, `close=ltp`, `volume+=delta_volume`
- If `bar_start < current_minute` → old bar is complete, move to completed list, start new bar

**Edge cases:**
- First tick of session starts mid-minute (e.g., collector starts at 09:17:34) → discard partial bar for that first minute. Only emit bars where you received the full 60-second window (bar_start != first observed minute for each token)
- Volume delta: Zerodha sends cumulative session volume in ticks. Delta = `current_volume - prev_volume`. Store `prev_session_volume` per token. If delta is negative (session rollover at market open) → treat it as 0
- `oi` field: only present in options and VIX ticks in FULL mode. Default to 0 for equity ticks
- Token appears in tick but not in `bars` dict → initialize normally (handles late subscriptions)

**What to check before writing this file:**
- Confirm what fields are present in a Zerodha FULL mode tick dict by running a test subscription with 2-3 tokens and printing the raw tick structure
- Confirm volume is cumulative (not per-tick) in Zerodha ticks

---

### `LiveMarket/collector/ws_collector.py`

**Single purpose:** Manage KiteTicker connection, receive ticks, route to bar_aggregator, flush completed bars to CSV files.

**Inputs:** `equity_tokens`, `options_tokens`, `vix_token`, `options_meta`, Kite credentials from `.env`

**Startup sequence:**
1. Load credentials from `.env` using the same `get_kite_client()` pattern from `zerodha_historical_data.py`
2. Create KiteTicker instance
3. Register callbacks: `on_ticks`, `on_connect`, `on_close`, `on_error`, `on_reconnect`
4. `on_connect`: subscribe all tokens with `MODE_FULL` for options+VIX, `MODE_QUOTE` for equities
5. Start ticker in background thread: `ticker.connect(threaded=True)`
6. Main thread runs a 60-second loop: call `bar_aggregator.get_completed_bars()`, route to correct CSV writer

**`on_ticks` callback:**
```
for tick in ticks:
    token = tick["instrument_token"]
    ltp = tick.get("last_price", 0)
    volume = tick.get("volume_traded", 0) or tick.get("volume", 0)
    oi = tick.get("oi", 0)
    tick_time = tick.get("timestamp") or datetime.now(IST)
    bar_aggregator.update(token, ltp, volume, oi, tick_time)
```

**CSV flushing (main thread, every 60s):**
1. Call `bar_aggregator.get_completed_bars(current_minute)`
2. For each `(token, bar)`:
   - If `token in equity_tokens` → append row to `equities_1min.csv`
   - If `token in options_tokens` → append row to `options_1min.csv` (include strike, expiry, option_type from options_meta)
   - If `token == vix_token` → append row to `vix_1min.csv`
3. Update `collector_status.json` with last_tick_at and bars_written count

**Edge cases:**
- KiteTicker disconnects → `on_close` fires, KiteTicker has built-in reconnect; set max reconnect_max_tries in constructor
- `on_error` fires → log error, do NOT crash the process
- CSV file does not exist yet → write header row first, then data row
- Collector is already running (double-start) → check `collector_status.json` for a running PID; if it exists and process is alive, refuse to start second instance
- Options token count exceeds 3000 per connection → filter to only the two nearest expiry dates (already handled in token_loader.py)
- `on_ticks` is called from the ticker thread; CSV writes happen from the main thread — no shared mutable state except `bar_aggregator` dict. Protect with a `threading.Lock`

**What to check before writing this file:**
- Run the Zerodha WebSocket sample from the official docs with just 5 tokens, confirm connection works with current API key/access token
- Confirm `KiteTicker` constructor signature: `KiteConnect.ticker` or `kiteconnect.KiteTicker` depending on SDK version
- Confirm reconnect parameters: `reconnect_max_tries`, `reconnect_max_delay`

---

### `LiveMarket/run_collector.py`

**Single purpose:** Entry point script that wires together token_loader → prev_close_loader → ws_collector.

**No business logic here.** Just:
1. Load `.env`
2. Call `token_loader.load_all_tokens(instruments_csv_path)` → get three token groups
3. Call `prev_close_loader.fetch_and_save(equity_tokens, kite_client)` → write prev_close.json
4. Call `ws_collector.start(equity_tokens, options_tokens, vix_token, options_meta)` → blocks forever

**Edge cases:**
- Instruments CSV missing → `token_loader` raises, process exits with code 1, Streamlit controller shows error
- Market is not open (before 9:00 or after 16:00) → warn in log but do NOT block startup. User may want to test the system. Bar data will just be empty until market opens.

---

### `LiveMarket/calculations/vwap_calculator.py`

**Single purpose:** Read `equities_1min.csv` and compute session VWAP for each token.

**Formula:** `VWAP = cumsum(close × volume) / cumsum(volume)`, reset at each new trading day.

**Output:** Dict `{token: vwap_value}` for all tokens that have at least one bar today.

**Edge cases:**
- Token has zero total volume for the session → exclude from output dict (VWAP undefined)
- CSV is empty or has only the header → return empty dict
- CSV is being written by collector at the same moment (race condition) → read with `pd.read_csv(..., on_bad_lines='skip')`, catch `pd.errors.EmptyDataError`, return last valid result

---

### `LiveMarket/calculations/ad_calculator.py`

**Single purpose:** Read `equities_1min.csv` + `prev_close.json` and compute Advance/Decline.

**Logic:**
1. Load `prev_close.json` → get `{token: prev_close_price}` map
2. Load equities_1min.csv, filter to today's date, get last `close` per token
3. For each token: if `close > prev_close` → advance; if `close < prev_close` → decline; else → unchanged
4. Return `{advances, declines, unchanged, ad_ratio}` where `ad_ratio = advances / declines`

**Edge cases:**
- Token in CSV but not in prev_close map → exclude from count (no baseline to compare)
- `declines == 0` → `ad_ratio = advances` (avoid division by zero)
- CSV has no data for today (market closed or collector not running) → return all zeros with a note field `"status": "no_data"`

---

### `LiveMarket/calculations/pcr_calculator.py`

**Single purpose:** Read `options_1min.csv` and compute Put/Call Ratio for NIFTY and BANKNIFTY.

**Logic:**
1. Load options_1min.csv, filter to today's date, get last `oi` per token
2. Separate CE and PE rows using `option_type` column
3. Group by underlying (parsed from `tradingsymbol`): NIFTY vs BANKNIFTY
4. For each underlying: `PCR = sum(PUT OI) / sum(CALL OI)`

**Edge cases:**
- CALL OI is zero for an underlying → PCR = 0 for that underlying, flag in output
- Options data not yet collected (options_1min.csv empty) → return `{"status": "no_data"}`
- Tradingsymbol parsing: NIFTY options tradingsymbol format is `NIFTY{DDMMMYY}{STRIKE}{CE/PE}` — use regex `^(NIFTY|BANKNIFTY)` to identify underlying

---

### `LiveMarket/calculations/atm_oi_calculator.py`

**Single purpose:** Read `options_1min.csv` and identify ATM strike OI for NIFTY and BANKNIFTY.

**Logic:**
1. Load options_1min.csv, filter to today, get last OI per token
2. Get current NIFTY/BANKNIFTY price (read from equities_1min.csv or vwap_snapshot.json)
3. ATM strike = round current price to nearest 50 (NIFTY step) or nearest 100 (BANKNIFTY step)
4. Filter options rows to ATM strike, return CE OI and PUT OI separately

**Edge cases:**
- Equities price not yet available → use the most recent bar's close from equities_1min.csv
- ATM strike has no matching option row in CSV → return None for that strike's OI
- Multiple expiries have the same ATM strike → use nearest expiry only

---

### `LiveMarket/calculations/vix_reader.py`

**Single purpose:** Read `vix_1min.csv` and return the latest VIX value.

**Output:** `{vix: float, vix_open: float}` — today's latest close and today's open bar value.

**Edge cases:**
- CSV empty → return `{"status": "no_data"}`
- Only one bar available → `vix_open` equals `vix`

---

### `LiveMarket/calculations/snapshot_writer.py`

**Single purpose:** Write a Python dict to a JSON snapshot file atomically (write temp file then rename, same pattern as existing atomic writes in the codebase).

**Method:** `write_snapshot(data: dict, path: Path) → None`

1. Serialize `data` to JSON string with `indent=2`
2. Write to `path.with_suffix(".tmp")`
3. `os.replace(tmp_path, path)` — atomic on both Windows and Linux

**Edge cases:**
- `Data/live_market/snapshots/` directory does not exist → create it before writing
- JSON serialization fails (non-serializable type) → convert offending values to str, log warning

---

### `LiveMarket/calculations/calculation_runner.py`

**Single purpose:** Run all five calculators in sequence every 60 seconds and write snapshots.

**Loop:**
```
while True:
    run all calculators
    write all snapshots
    sleep until next 60s boundary
```

**Edge cases:**
- A calculator raises an exception → catch, log, continue to next calculator (partial snapshot is acceptable)
- Snapshot directory does not exist → `snapshot_writer.py` handles this
- Runner is already running (double-start) → same PID-check pattern as ws_collector

---

### `LiveMarket/run_calculations.py`

**Single purpose:** Entry point for the calculation subprocess. Calls `calculation_runner.start()` and blocks.

---

### `Dashboard/market_pulse_page/features/collector_controller.py`

**Single purpose:** Start, stop, and report health of the two background subprocesses (collector + calculator).

**Uses:** `subprocess.Popen` — same pattern as `execution_manager.py` already uses for backtest subprocesses.

**State file:** `Data/live_market/collector_status.json` — check `status` field to know if running.

**Methods:**
- `start_collector()` → `subprocess.Popen(["python", "LiveMarket/run_collector.py"])`
- `start_calculator()` → `subprocess.Popen(["python", "LiveMarket/run_calculations.py"])`
- `stop_collector()` → read PID from status file, `os.kill(pid, signal.SIGTERM)`
- `is_collector_running()` → check status file + verify PID is still alive with `psutil.pid_exists(pid)` or `os.kill(pid, 0)`
- `get_status()` → return full `collector_status.json` as dict

**Edge cases:**
- Status file missing → collector is not running
- PID in status file but process is dead → stale status file; overwrite with `status: stopped`
- Stopping on Windows: `SIGTERM` may not work; use `process.terminate()` on the stored Popen handle. Store handle in `st.session_state` to retain across reruns within the same Streamlit session.

**What to check before writing this file:**
- Confirm `psutil` is available (it is not in requirements.txt — add it)
- Test `subprocess.Popen` with a simple script to confirm working directory resolution is correct relative to the project root

---

### `Dashboard/market_pulse_page/market_pulse_section.py`

**Single purpose:** Render the Market Pulse Streamlit page.

**Layout (do not mix metric cards with chart area — keep them separated):**

```
┌─────────────────────────────────────────────────────────┐
│ CONTROL BAR: [Start Collector] [Stop Collector] [Status] │
│ Status badge: LIVE / STOPPED / STALE (last updated X ago)│
├────────────────────────────────────────────────────────-─┤
│ ROW 1 — Market Breadth (4 cards)                         │
│  VIX: 14.25  │  A/D: 1243 / 891  │  AD Ratio: 1.39  │  │
├─────────────────────────────────────────────────────────-┤
│ ROW 2 — Options Snapshot (3 cards)                       │
│  NIFTY PCR: 0.87  │  NIFTY ATM CE OI  │  ATM PUT OI    │
├─────────────────────────────────────────────────────────-┤
│ ROW 3 — BANKNIFTY Options (3 cards)                      │
│  BANKNIFTY PCR: 1.12  │  ATM CE OI    │  ATM PUT OI    │
├─────────────────────────────────────────────────────────-┤
│ ROW 4 — Data Freshness                                   │
│  Last updated: 09:22:00  │  Bars collected: 14,922       │
│  Tokens subscribed: 2487 │  Last tick: 09:22:31          │
└─────────────────────────────────────────────────────────-┘
```

**Snapshot reading:**
- Read each JSON snapshot file with `json.load()` inside a `try/except`
- If file missing or stale (generated_at > 2 minutes ago) → show `st.warning("Data unavailable — collector may not be running")`
- Use `st.metric()` for KPI cards to get automatic delta display
- Add `st.button("Refresh")` that calls `st.rerun()` — no auto-refresh (Streamlit does not support it cleanly)

**Uses:** `navbar.TV_UP`, `TV_DOWN`, `PRIMARY_BLUE`, `BG_COLOR`, `BORDER_COLOR` from `navbar.py` — import these for consistent styling.

**What to check before writing this file:**
- Confirm all snapshot JSON schemas are finalized (they are — documented in Section 3)
- Confirm `collector_controller.py` API is stable before calling it from here

---

### `Dashboard/navbar.py` — Modification

Add `"Market Pulse"` to the `options` list and `"pulse"` to the `icons` list:

```python
# Before:
options=["Zerodha Authentication", "Dashboard", "Backtests"],
icons=["shield-lock", "activity", "bar-chart-steps"],

# After:
options=["Zerodha Authentication", "Dashboard", "Backtests", "Market Pulse"],
icons=["shield-lock", "activity", "bar-chart-steps", "pulse"],
```

No other changes.

---

### `Dashboard/dashboard.py` — Modification

Add import and routing branch:

```python
# Add import:
from market_pulse_page.market_pulse_section import render as render_market_pulse

# Add routing (after existing elif blocks):
elif selected == "Market Pulse":
    render_market_pulse()
```

No other changes.

---

### `requirements.txt` — Modification

Add one line:
```
psutil
```

(Needed by `collector_controller.py` to check if subprocess PID is alive.)

---

## 5. Edge Cases Catalog

| # | Scenario | File Responsible | Handling |
|---|---|---|---|
| 1 | Collector starts before market open (< 9:00) | `ws_collector.py` | Allow it — warn in log, bars stay empty until 9:15 |
| 2 | Collector starts mid-minute | `bar_aggregator.py` | Discard first partial bar per token |
| 3 | KiteTicker disconnects mid-session | `ws_collector.py` | Built-in reconnect via `reconnect_max_tries`; log each reconnect |
| 4 | Volume tick is negative (session rollover) | `bar_aggregator.py` | Clamp delta to 0 |
| 5 | equities_1min.csv read while collector is writing | All calculators | Use `on_bad_lines='skip'`, catch `EmptyDataError`, return last valid result |
| 6 | Snapshot JSON file absent when Streamlit reads it | `market_pulse_section.py` | Show warning card, do not crash |
| 7 | Snapshot is stale (> 2 min old) | `market_pulse_section.py` | Show yellow warning badge next to the metric |
| 8 | Double-start of collector (user clicks Start twice) | `collector_controller.py` | Check status JSON PID; if alive, show "already running" toast |
| 9 | Instruments CSV missing | `token_loader.py` | Raise `FileNotFoundError` with message telling user to run the instrument update first |
| 10 | INDIA VIX token not found in instruments | `token_loader.py` | `vix_token = None`, skip VIX collection, log warning |
| 11 | Options token count > 3000 | `token_loader.py` | Filter to nearest 2 expiry dates only — keeps count under 1000 |
| 12 | PCR: CALL OI is zero | `pcr_calculator.py` | Return `pcr = None`, mark field as unavailable |
| 13 | ATM strike not in options CSV | `atm_oi_calculator.py` | Return `None` for that OI field |
| 14 | prev_close fetch fails for some tokens | `prev_close_loader.py` | Skip failed tokens, write partial map — those tokens excluded from A/D |
| 15 | Windows SIGTERM does not kill subprocess | `collector_controller.py` | Use `process.terminate()` on stored Popen handle |
| 16 | CSV file grows indefinitely during session | `ws_collector.py` | Rotate file at market open each day: rename to `equities_1min_YYYYMMDD.csv`, start fresh |
| 17 | Tick timestamp is None (some Zerodha modes omit it) | `ws_collector.py` | Fall back to `datetime.now(IST)` |
| 18 | NSE bhav copy for FII/DII | Not yet — Phase 2 | Separate daily downloader, out of scope for Phase 1 |

---

## 6. Development Phases and Gate Checks

### Phase 0 — Environment Verification (do this before writing any code)

**Check 1: Instruments CSV columns**
```python
import pandas as pd
df = pd.read_csv("Data/instrument_mapper_data/zerodha_instruments_latest.csv")
print(df.columns.tolist())
print(df[df["tradingsymbol"] == "INDIA VIX"])
print(df[df["segment"] == "NSE"].head(3))
print(df[df["instrument_type"] == "CE"].head(3))
```
Expected: columns include `instrument_token`, `segment`, `instrument_type`, `tradingsymbol`, `expiry`, `strike`, `lot_size`

**Check 2: Kite `/quote` response shape**
```python
from kiteconnect import KiteConnect
kite = KiteConnect(api_key="YOUR_KEY")
kite.set_access_token("YOUR_TOKEN")
r = kite.quote(["NSE:RELIANCE"])
print(r["NSE:RELIANCE"]["ohlc"])
print(r["NSE:RELIANCE"]["instrument_token"])
```
Expected: `ohlc.close` exists with a float value

**Check 3: KiteTicker tick shape (run during market hours)**
```python
from kiteconnect import KiteTicker
# Connect with 3-5 tokens, MODE_FULL, print first tick
```
Expected: tick dict has `instrument_token`, `last_price`, `volume_traded`, `oi`, `timestamp`

**Check 4: psutil install**
```
pip install psutil
```
Then confirm `psutil.pid_exists(os.getpid())` returns True.

**Do not proceed to Phase 1 until all four checks pass.**

---

### Phase 1 — Token Loader + Prev Close (no WebSocket yet)

**Build:** `token_loader.py`, `prev_close_loader.py`, `run_collector.py` (stub that only does steps 1-3)

**Gate checks before Phase 2:**
- Run `python LiveMarket/run_collector.py` (with WebSocket start commented out)
- Confirm printed output shows equity count (~1800-2200 tokens), options count (~200-800 tokens), VIX token found
- Confirm `Data/live_market/prev_close.json` exists and has > 100 token entries
- Confirm all token values are integers, not strings
- Confirm prev_close values are reasonable (NIFTY ~22000-25000, RELIANCE ~1000-3000)

**Do not proceed to Phase 2 until all gate checks pass.**

---

### Phase 2 — Bar Aggregator + WebSocket Collector

**Build:** `bar_aggregator.py`, `ws_collector.py`, complete `run_collector.py`

**Gate checks before Phase 3:**
- Run collector for exactly 3 minutes during market hours
- Confirm `equities_1min.csv` exists with rows
- Confirm row count ≈ (elapsed minutes × number of active equity tokens)
- Open `equities_1min.csv` and verify: open ≤ high, low ≤ open, close is within high-low range
- Confirm `options_1min.csv` has rows with non-zero OI values
- Confirm `vix_1min.csv` has rows with reasonable VIX values (5.0 - 40.0)
- Confirm `collector_status.json` shows `status: running` and `last_tick_at` is recent
- Check Python process memory usage does not grow unboundedly after 10 minutes (check with Task Manager)
- Try stopping collector via Ctrl+C and confirm it exits cleanly (no zombie process)

**Do not proceed to Phase 3 until all gate checks pass.**

---

### Phase 3 — Calculation Layer

**Build:** All calculators, `snapshot_writer.py`, `calculation_runner.py`, `run_calculations.py`

**Gate checks before Phase 4:**
- Run `python LiveMarket/run_calculations.py` with collector running
- After 2 minutes, confirm all 5 snapshot files exist in `Data/live_market/snapshots/`
- Open each snapshot and verify:
  - `ad_snapshot.json`: advances + declines + unchanged = total tokens tracked (within 5% tolerance for tokens with no ticks)
  - `pcr_snapshot.json`: NIFTY PCR is between 0.1 and 5.0 (sane range)
  - `vwap_snapshot.json`: VWAP values are within high-low range of each stock's bars
  - `vix_snapshot.json`: VIX value between 5.0 and 40.0
  - `atm_oi_snapshot.json`: CE OI and PUT OI are both > 0
- Confirm `generated_at` field in all snapshots is within last 2 minutes
- Stop the collector (kill it), wait 2 min, confirm calculator continues running and snapshots `generated_at` becomes stale — this is expected behavior

**Do not proceed to Phase 4 until all gate checks pass.**

---

### Phase 4 — Streamlit UI

**Build:** `collector_controller.py`, `market_pulse_section.py`, modify `navbar.py` and `dashboard.py`

**Gate checks before declaring complete:**
- Open Streamlit, confirm "Market Pulse" appears in navbar without breaking other tabs
- Click "Zerodha Authentication" — confirm it still renders correctly
- Click "Dashboard" — confirm it still renders correctly
- Click "Backtests" — confirm it still renders correctly
- Click "Market Pulse" — confirm page renders without crash even when snapshots are absent (should show warning cards)
- Click "Start Collector" — confirm subprocess starts, status changes to LIVE
- Wait 2 min — confirm metric cards populate with real data
- Click "Stop Collector" — confirm subprocess stops, status changes to STOPPED
- Refresh page — confirm no crash, stale data warning appears
- Click "Start Collector" again while already running — confirm "already running" toast appears, no duplicate process spawned

---

## 7. Directory Creation Order

Create these directories before writing any files (they do not exist yet):

```
LiveMarket/
LiveMarket/collector/
LiveMarket/calculations/
Dashboard/market_pulse_page/
Dashboard/market_pulse_page/features/
Data/live_market/
Data/live_market/snapshots/
```

The `Data/live_market/` subdirectories can also be created programmatically at runtime by `snapshot_writer.py` — but creating them manually first prevents errors during early testing.

---

## 8. Dependencies Map

```
token_loader.py
    ↓
prev_close_loader.py (needs token_loader output)
    ↓
ws_collector.py (needs token_loader + bar_aggregator)
    ↓
bar_aggregator.py (standalone, no deps)

run_collector.py → token_loader + prev_close_loader + ws_collector

vwap_calculator.py → equities_1min.csv (written by ws_collector)
ad_calculator.py → equities_1min.csv + prev_close.json
pcr_calculator.py → options_1min.csv
atm_oi_calculator.py → options_1min.csv + equities_1min.csv
vix_reader.py → vix_1min.csv
snapshot_writer.py → standalone

calculation_runner.py → all calculators + snapshot_writer
run_calculations.py → calculation_runner

collector_controller.py → run_collector.py + run_calculations.py (as subprocesses)
market_pulse_section.py → collector_controller + snapshot JSON files
```

No circular dependencies. Each module reads from files or takes simple arguments — nothing imports from Streamlit or the backtesting pipeline.

---

## 9. What This Does NOT Change

- `Backtesting/` — zero modifications
- `Dashboard/dashboard_section.py` — zero modifications
- `Dashboard/Backtesting_page/` — zero modifications
- `Dashboard/navbar.py` styles and color constants — zero modifications
- `Data/testing_data/` — untouched
- `Data/Logs/` — untouched
- `docker-compose.yml`, `Dockerfile`, `entrypoint.sh` — untouched (Docker support is Phase 2 scope)
- `.env` structure — untouched; collector uses same keys already present

---

## 10. Total New Files Count

| Category | Count |
|---|---|
| LiveMarket package files | 12 |
| Dashboard UI files | 4 |
| Data runtime files (auto-created) | 8 |
| **Modified existing files** | **3** (navbar.py, dashboard.py, requirements.txt) |
| **Total new .py files** | **16** |

---

## 11. Multi-Timeframe Bar Architecture

### 11.1 Design Decision

The WebSocket collector always collects at **1-minute resolution** — this is the base layer. All higher timeframes (3min, 5min, 10min, 15min, 30min, 60min) are derived by **resampling the 1-min CSV in the calculation layer**, not in the collector itself.

This keeps the collector simple (one job: write 1-min bars) and makes timeframe generation deterministic and testable offline without a live WebSocket connection.

### 11.2 How Resampling Works

Pandas `.resample()` on a datetime index handles OHLCV aggregation correctly:

| Column | Aggregation Rule |
|---|---|
| open | first |
| high | max |
| low | min |
| close | last |
| volume | sum |
| oi | last (point-in-time, not cumulative) |

**Market-hour alignment:** All resampling uses `origin='start'` anchored to the first 1-min bar of the session (09:15 IST). This ensures 5-min bars land at 09:15, 09:20, 09:25... and 15-min bars at 09:15, 09:30, 09:45... — matching exchange-standard bar boundaries.

**Incomplete bar handling:** The most recent bar in the resampled output may be incomplete (e.g., a 5-min bar that only has 3 minutes of data). The resampler always **drops the last bar** from output so only fully closed bars are written.

### 11.3 New File: `LiveMarket/calculations/bar_resampler.py`

**Single purpose:** Read a 1-min CSV and produce resampled CSVs for all target timeframes.

**Target timeframes:** `[3, 5, 10, 15, 30, 60]` (minutes)

**Inputs:** Path to a 1-min CSV file, list of target timeframes, output directory path

**Outputs:** One CSV file per timeframe, same schema as the 1-min source file

**Method signature:**
```python
def resample_to_timeframes(
    source_csv: Path,
    timeframes: list[int],
    output_dir: Path,
    group_by_token: bool = True,
) -> dict[int, Path]:
    ...
```

**Logic per timeframe:**
1. Load 1-min CSV, parse `timestamp` as DatetimeIndex
2. Filter to today's date only (do not resample historical accumulation)
3. Group by `instrument_token` (resample must happen per-token, not across tokens)
4. For each token group, call `.resample(f"{tf}T", origin="start", closed="left", label="left").agg({...})`
5. Drop the last bar (incomplete)
6. Concatenate all token groups back into one DataFrame
7. Write to `equities_{tf}min.csv` (or `options_{tf}min.csv` etc.)

**Edge cases:**
- Source 1-min CSV has fewer rows than one full bar window (e.g., only 2 rows of 1-min data for a 5-min resample) → return empty DataFrame for that timeframe, do not crash
- A token has gaps in 1-min data (missed ticks) → the resample naturally handles it; the bar for that window just uses whatever 1-min bars are available
- Output file already exists → overwrite it entirely (resampling is idempotent from today's 1-min data)

### 11.4 Updated File Structure

```
Data/live_market/
├── equities_1min.csv          ← written by collector
├── equities_3min.csv          ← written by bar_resampler
├── equities_5min.csv
├── equities_10min.csv
├── equities_15min.csv
├── equities_30min.csv
├── equities_60min.csv
├── options_1min.csv           ← written by collector
├── options_3min.csv           ← written by bar_resampler
├── options_5min.csv
├── options_10min.csv
├── options_15min.csv
├── options_30min.csv
├── options_60min.csv
├── vix_1min.csv               ← written by collector
├── vix_5min.csv               ← written by bar_resampler (3 timeframes enough for VIX)
├── vix_15min.csv
├── vix_60min.csv
├── prev_close.json
├── collector_status.json
└── snapshots/
    ├── vwap_snapshot.json     ← updated schema (see below)
    ├── ad_snapshot.json
    ├── pcr_snapshot.json
    ├── atm_oi_snapshot.json
    └── vix_snapshot.json
```

### 11.5 Updated `calculation_runner.py` Execution Order

The runner now runs the resampler **before** the calculators on each 60-second cycle:

```
Every 60 seconds:
  1. bar_resampler.resample_to_timeframes(equities_1min.csv, [3,5,10,15,30,60])
  2. bar_resampler.resample_to_timeframes(options_1min.csv, [3,5,10,15,30,60])
  3. bar_resampler.resample_to_timeframes(vix_1min.csv, [5,15,60])
  4. vwap_calculator.compute_all_timeframes(equities_1min.csv, [3,5,10,15,30,60])
  5. ad_calculator.compute(equities_1min.csv, prev_close.json)
  6. pcr_calculator.compute(options_1min.csv)
  7. atm_oi_calculator.compute(options_1min.csv, equities_1min.csv)
  8. vix_reader.read(vix_1min.csv)
  9. snapshot_writer.write_all(results)
```

### 11.6 Updated VWAP Snapshot Schema

VWAP is session-cumulative. Technically the session VWAP value is the same regardless of bar timeframe (it's a running cumsum from open). However, displaying VWAP on a 15-min chart requires the VWAP anchored to 15-min bar timestamps. The snapshot stores VWAP keyed by timeframe:

```json
{
  "generated_at": "2026-04-28T09:45:00",
  "timeframes": {
    "1min":  { "256265": 22115.4, "260105": 499.8 },
    "3min":  { "256265": 22114.9, "260105": 499.5 },
    "5min":  { "256265": 22113.8, "260105": 499.1 },
    "10min": { "256265": 22112.0, "260105": 498.7 },
    "15min": { "256265": 22108.2, "260105": 498.3 },
    "30min": { "256265": 22100.5, "260105": 497.9 },
    "60min": { "256265": 22095.1, "260105": 497.2 }
  }
}
```

### 11.7 Updated `vwap_calculator.py` Specification

**New method:** `compute_all_timeframes(source_1min_csv, timeframes) → dict`

**Logic per timeframe:**
1. Load the corresponding resampled CSV (e.g., `equities_5min.csv` for 5min VWAP)
2. Filter to today's date, sort by timestamp ascending
3. Group by `instrument_token`
4. For each token: `vwap = (close × volume).cumsum() / volume.cumsum()` — take the last value as current VWAP
5. Return `{token: vwap_value}`

**Uses 1min CSV for 1min VWAP, and the pre-resampled CSVs for higher timeframes** — this means the resampler must run before the VWAP calculator in each cycle.

### 11.8 Updated Streamlit UI — Timeframe Selector

Add a timeframe dropdown to the Market Pulse page control bar:

```
CONTROL BAR: [Start Collector] [Stop Collector] [Status] | Timeframe: [1min ▼]
```

Options: `1min`, `3min`, `5min`, `10min`, `15min`, `30min`, `60min`

The VWAP metric cards update to show the VWAP value for the selected timeframe from `vwap_snapshot.json["timeframes"][selected_tf]`.

A/D, PCR, ATM OI, VIX — these are point-in-time snapshots, not bar-based, so they do **not** change with the timeframe selector.

### 11.9 Impact on File Count

| Addition | Count |
|---|---|
| `bar_resampler.py` | 1 new file |
| Additional CSV files (runtime, auto-created) | 16 (6 timeframes × equities/options + 3 for VIX) |
| Updated files (vwap_calculator.py logic expanded) | 1 existing file modified |

---

## 12. Detailed Post-Phase Sanity Checks

These are the specific checks to run **after completing each phase** before writing a single line of the next phase. Each check includes: what to run, what the acceptable output looks like, what a failure means, and how to diagnose it.

---

### Phase 0 Sanity Checks — After Environment Verification

#### Check 0-A: Instruments CSV Column Validation

**Run:**
```python
import pandas as pd
df = pd.read_csv("Data/instrument_mapper_data/zerodha_instruments_latest.csv")
print("Columns:", df.columns.tolist())
print("Total rows:", len(df))
print("Segments:", df["segment"].unique())
print("NSE EQ count:", len(df[(df["segment"] == "NSE") & (df["instrument_type"] == "EQ")]))
print("NFO CE count:", len(df[(df["segment"] == "NFO") & (df["instrument_type"] == "CE")]))
print("VIX row:", df[df["tradingsymbol"] == "INDIA VIX"][["instrument_token","tradingsymbol","segment"]].to_string())
print("Sample expiry values:", df[df["instrument_type"] == "CE"]["expiry"].dropna().head(5).tolist())
print("Token dtype:", df["instrument_token"].dtype)
```

**Acceptable output:**
- Columns list contains: `instrument_token`, `segment`, `instrument_type`, `tradingsymbol`, `expiry`, `strike`, `lot_size`, `name`, `exchange`
- Total rows: 50,000 — 200,000 (Zerodha instruments master is large)
- NSE EQ count: 1,800 — 2,500
- NFO CE count: 500 — 5,000 (varies by expiry density)
- VIX row: exactly one row returned, `segment` is `NSE` or `BSE`
- `expiry` values are parseable dates (e.g., `2026-05-01` or `2026-05-01 00:00:00`)
- Token dtype: `int64` (not object/string)

**Red flags and diagnosis:**
- `instrument_token` dtype is object → the CSV has mixed types; add `df["instrument_token"] = pd.to_numeric(df["instrument_token"], errors="coerce")` in token_loader.py
- VIX row empty → VIX is sometimes listed as `INDIAVIX` without space; check: `df[df["tradingsymbol"].str.contains("VIX", na=False)]`
- expiry column looks like `NaT` for all options → parse with `pd.to_datetime(df["expiry"], errors="coerce")` and check
- NSE EQ count < 500 → instruments file is outdated or corrupted; run instrument_mapper_updater.py first

---

#### Check 0-B: Kite `/quote` API Response Shape

**Run (during or outside market hours — both work):**
```python
from kiteconnect import KiteConnect
import os
from dotenv import load_dotenv
load_dotenv(override=True)
kite = KiteConnect(api_key=os.environ["ZERODHA_API_KEY"])
kite.set_access_token(os.environ["ZERODHA_ACCESS_TOKEN"])
r = kite.quote(["NSE:RELIANCE", "NSE:INFY"])
for key, val in r.items():
    print(f"\n--- {key} ---")
    print("instrument_token:", val.get("instrument_token"))
    print("ohlc:", val.get("ohlc"))
    print("last_price:", val.get("last_price"))
```

**Acceptable output:**
- Two instrument entries returned
- Each has `ohlc` dict with keys: `open`, `high`, `low`, `close` — all floats > 0
- `instrument_token` is an integer
- No exception raised

**Red flags and diagnosis:**
- `TokenException` or `InputException` → access token is expired; re-authenticate via Zerodha Authentication page
- `ohlc.close` is 0.0 outside market hours → this is normal for some instruments; during market hours it should be non-zero. Do not block on this.
- KeyError on `"NSE:RELIANCE"` → the quote key format may differ; print `list(r.keys())` to check actual format

---

#### Check 0-C: KiteTicker Connection Test (must run during market hours)

**Run as a standalone script:**
```python
from kiteconnect import KiteTicker
import os
from dotenv import load_dotenv
load_dotenv(override=True)

kt = KiteTicker(os.environ["ZERODHA_API_KEY"], os.environ["ZERODHA_ACCESS_TOKEN"])

tick_received = []

def on_ticks(ws, ticks):
    tick_received.extend(ticks)
    if len(tick_received) >= 3:
        print("Sample tick keys:", list(ticks[0].keys()))
        print("instrument_token:", ticks[0].get("instrument_token"))
        print("last_price:", ticks[0].get("last_price"))
        print("volume_traded:", ticks[0].get("volume_traded"))
        print("oi:", ticks[0].get("oi"))
        print("timestamp:", ticks[0].get("timestamp"))
        ws.close()

def on_connect(ws, response):
    ws.subscribe([738561])  # NIFTY 50 index token
    ws.set_mode(ws.MODE_FULL, [738561])

kt.on_ticks = on_ticks
kt.on_connect = on_connect
kt.connect(threaded=True)

import time; time.sleep(30)
print(f"Total ticks received: {len(tick_received)}")
```

**Acceptable output:**
- `Total ticks received` > 0
- Tick dict has key `instrument_token` as int
- `last_price` is float > 0
- `volume_traded` is int ≥ 0 (cumulative session volume)
- `timestamp` is a `datetime` object or parseable string (not None) in MODE_FULL
- `oi` field exists (may be 0 for equity indices)

**Red flags and diagnosis:**
- 0 ticks received → market is closed. Run this check only between 09:15–15:30 IST Monday–Friday
- `timestamp` is `None` → Zerodha omits timestamp in MODE_LTP; ensure you're using MODE_FULL or MODE_QUOTE. Document which mode provides timestamps.
- `volume_traded` key not present, only `volume` → note this alternate key name, update `ws_collector.py` to check both
- Connection refused → IP not whitelisted in Zerodha developer console

---

#### Check 0-D: psutil Verification

**Run:**
```python
import psutil, os
pid = os.getpid()
print("Current PID:", pid)
print("PID exists:", psutil.pid_exists(pid))
print("Fake PID exists:", psutil.pid_exists(9999999))
p = psutil.Process(pid)
print("Process name:", p.name())
print("Process status:", p.status())
```

**Acceptable output:**
- `PID exists: True`
- `Fake PID exists: False`
- `Process status: running`

**Red flags:** `ModuleNotFoundError` → `pip install psutil` was not run or not run in the correct environment.

---

### Phase 1 Sanity Checks — After Token Loader + Prev Close

#### Check 1-A: Token Group Counts and Types

**Run:** `python LiveMarket/run_collector.py` with the WebSocket start line commented out. It should print counts and exit.

**Acceptable output:**
```
[token_loader] NSE equity tokens: 1847
[token_loader] NFO options tokens (near-term 14 days): 412
[token_loader] VIX token: 264969
[token_loader] Options meta loaded: 412 entries
[prev_close_loader] Fetching prev_close in 4 batches of 500
[prev_close_loader] Prev close loaded: 1831 tokens (16 skipped — no ohlc data)
[prev_close_loader] Written to Data/live_market/prev_close.json
```

**Acceptable ranges:**
- Equity tokens: 1,500 — 2,500 (NSE EQ segment)
- Options tokens: 200 — 2,000 (near-term expiry filter keeps it under 1,000 normally)
- VIX token: any non-zero integer
- Prev_close coverage: ≥ 90% of equity tokens (some illiquid stocks may have no quote)

**Red flags and diagnosis:**
- Options tokens = 0 → the 14-day expiry filter is too narrow; check today's date and the expiry dates in the CSV. Print `df["expiry"].unique()` to see available dates.
- Prev_close coverage < 70% → the quote API may be using wrong symbol format (check if `NSE:RELIANCE` or `NSE:RELIANCE-EQ` is the expected format)
- VIX token not found → run `df[df["tradingsymbol"].str.contains("VIX", na=False)]` on the instruments CSV to find the actual tradingsymbol

#### Check 1-B: prev_close.json Integrity

**Run:**
```python
import json
with open("Data/live_market/prev_close.json") as f:
    data = json.load(f)

values = list(data["data"].values())
tokens = list(data["data"].keys())

print("Generated at:", data["generated_at"])
print("Date:", data["date"])
print("Token count:", len(values))
print("Min price:", min(values))
print("Max price:", max(values))
print("Zero prices:", sum(1 for v in values if v == 0))
print("None/null prices:", sum(1 for v in values if v is None))
print("Sample tokens are strings:", isinstance(tokens[0], str))
```

**Acceptable output:**
- `Token count` > 1,000
- `Min price` > 0.5 (no zero or near-zero prev_close values — would corrupt A/D)
- `Max price` < 200,000 (sanity ceiling)
- `Zero prices` = 0
- `None/null prices` = 0
- `Sample tokens are strings: True` — JSON keys are always strings; token_loader must cast them to `int` when reading back

**Red flags and diagnosis:**
- Many zero prices → the quote API call is outside market hours and some instruments return 0 for ohlc.close; add a check in `prev_close_loader.py` to skip tokens where ohlc.close == 0
- Token count < 500 → API batching logic is broken; add print inside each batch loop to see which batches are failing

---

### Phase 2 Sanity Checks — After Bar Aggregator + WebSocket Collector

Run the following checks **after letting the collector run for exactly 5 minutes during market hours (09:15–15:30 IST).**

#### Check 2-A: CSV Row Counts

**Run:**
```python
import pandas as pd
eq = pd.read_csv("Data/live_market/equities_1min.csv")
opt = pd.read_csv("Data/live_market/options_1min.csv")
vix = pd.read_csv("Data/live_market/vix_1min.csv")

print("Equities rows:", len(eq))
print("Unique equity tokens:", eq["instrument_token"].nunique())
print("Options rows:", len(opt))
print("VIX rows:", len(vix))
print("Equities minutes covered:", eq["timestamp"].nunique())
```

**Acceptable output (after 5 minutes of collection):**
- Equities rows: (active tokens) × (4 complete minutes) ≈ 5,000 — 10,000
  - Not all 1,800 tokens are active — only actively traded ones get ticks
- Unique equity tokens: 500 — 1,800 (depends on market activity)
- VIX rows: 4 — 5 (one per complete minute)
- Equities minutes covered: 4 — 5

**Red flags and diagnosis:**
- Equities rows = 0 → collector is not writing. Check if `get_completed_bars()` is being called or if the main loop is blocked. Add a debug print inside the flush loop.
- VIX rows = 0 → VIX token subscription failed. Check if vix_token was correctly found and subscribed in `on_connect`.
- Equities minutes covered = 1 → bar flushing is only triggering once; the 60-second loop in the main thread is stuck or sleeping too long.

#### Check 2-B: OHLCV Sanity (No Corrupt Bars)

**Run:**
```python
import pandas as pd
eq = pd.read_csv("Data/live_market/equities_1min.csv")

bad_high = eq[eq["high"] < eq["open"]]
bad_low = eq[eq["low"] > eq["open"]]
bad_close = eq[(eq["close"] > eq["high"]) | (eq["close"] < eq["low"])]
neg_volume = eq[eq["volume"] < 0]

print("Bars where high < open:", len(bad_high))
print("Bars where low > open:", len(bad_low))
print("Bars where close outside high/low:", len(bad_close))
print("Bars with negative volume:", len(neg_volume))
print("Zero volume bars:", len(eq[eq["volume"] == 0]))
```

**Acceptable output:**
- All bad counts = 0
- Zero volume bars may exist (stock had no trades during that minute) — this is normal, not a bug

**Red flags and diagnosis:**
- `high < open` or `low > open` → the bar_aggregator initialization is wrong; when a new bar starts, `open=high=low=close=ltp` must all be set to the same value
- `close outside high/low` → tick update logic is wrong; `high = max(high, ltp)`, `low = min(low, ltp)` must be applied before setting `close = ltp`
- Negative volume → the volume delta clamp to 0 is not working; check the `prev_session_volume` logic

#### Check 2-C: Memory and CPU Stability

**After 10 minutes of collection:**
```python
import psutil, os
p = psutil.Process(os.getpid())  # or get the collector's PID from collector_status.json
mem_mb = p.memory_info().rss / 1024 / 1024
print(f"Collector memory: {mem_mb:.1f} MB")
```

**Acceptable output:**
- Memory ≤ 300 MB after 10 minutes
- Memory growth should plateau after the first 2 minutes (once all token bars are initialized)

**Red flags and diagnosis:**
- Memory grows linearly with time → `bar_aggregator` bars dict is not being cleared after `get_completed_bars()`. Confirm that completed bars are removed from the dict.
- Memory > 500 MB → the completed bars list from `get_completed_bars()` is being accumulated instead of cleared per cycle

#### Check 2-D: Collector Status File

**Run:**
```python
import json, datetime
with open("Data/live_market/collector_status.json") as f:
    s = json.load(f)
print(s)
last_tick = datetime.datetime.fromisoformat(s["last_tick_at"])
age = (datetime.datetime.now() - last_tick).total_seconds()
print(f"Last tick age: {age:.0f} seconds")
```

**Acceptable output (during market hours):**
- `status: "running"`
- `last_tick_at` age ≤ 30 seconds
- `tokens_subscribed` matches expected count from Phase 1
- `bars_written` increases between checks

**Red flags:** `last_tick_at` age > 120 seconds during market hours → KiteTicker has disconnected and reconnect is not working. Check `on_reconnect` callback is registered.

---

### Phase 3 Sanity Checks — After Calculation Layer

Run the following checks **after letting both collector and calculation runner run simultaneously for 5 minutes during market hours.**

#### Check 3-A: Snapshot File Existence and Freshness

**Run:**
```python
import os, json, datetime
from pathlib import Path

snapshots = ["vwap_snapshot.json", "ad_snapshot.json", "pcr_snapshot.json",
             "atm_oi_snapshot.json", "vix_snapshot.json"]

for name in snapshots:
    path = Path("Data/live_market/snapshots") / name
    if not path.exists():
        print(f"MISSING: {name}")
        continue
    with open(path) as f:
        data = json.load(f)
    gen_at = datetime.datetime.fromisoformat(data["generated_at"])
    age = (datetime.datetime.now() - gen_at).total_seconds()
    print(f"{name}: age={age:.0f}s, keys={list(data.keys())}")
```

**Acceptable output:**
- All 5 files exist
- Age ≤ 90 seconds for all snapshots
- No `MISSING` lines

**Red flags and diagnosis:**
- A snapshot file is missing → that calculator raised an exception. Check the calculation_runner.py log to see which calculator failed. Run that calculator independently with the current CSV as input.
- Age > 120 seconds → calculation_runner loop is stuck. Check if a calculator call is blocking (e.g., a stuck `pd.read_csv` on a locked file).

#### Check 3-B: A/D Snapshot Logic Validation

**Run:**
```python
import json, pandas as pd

with open("Data/live_market/snapshots/ad_snapshot.json") as f:
    ad = json.load(f)
with open("Data/live_market/prev_close.json") as f:
    pc = json.load(f)

print("Advances:", ad["advances"])
print("Declines:", ad["declines"])
print("Unchanged:", ad["unchanged"])
print("AD Ratio:", ad["ad_ratio"])
print("Total covered:", ad["advances"] + ad["declines"] + ad["unchanged"])
print("Prev close token count:", len(pc["data"]))

eq = pd.read_csv("Data/live_market/equities_1min.csv")
today = pd.Timestamp.now().normalize().isoformat()[:10]
eq_today = eq[eq["timestamp"].str[:10] == today]
unique_tokens_today = eq_today["instrument_token"].nunique()
print("Unique equity tokens with data today:", unique_tokens_today)
```

**Acceptable output:**
- `Total covered` ≈ `Unique tokens with data today` (within 5%)
- `AD Ratio` > 0 (not division by zero)
- During a bullish session: advances > declines; bearish: declines > advances
- Neither `advances` nor `declines` is 0 in a normally active market

**Red flags and diagnosis:**
- `Total covered` is 0 → equities_1min.csv has no rows for today. The collector wrote timestamps in a different timezone and the date filter is failing. Check the timestamp timezone in the CSV.
- `AD Ratio` is missing or `None` → declines was 0, the division-by-zero guard was not triggered correctly

#### Check 3-C: VWAP Sanity Validation

**Run:**
```python
import json, pandas as pd

with open("Data/live_market/snapshots/vwap_snapshot.json") as f:
    vwap = json.load(f)

eq = pd.read_csv("Data/live_market/equities_1min.csv")
today = pd.Timestamp.now().normalize().isoformat()[:10]
eq_today = eq[eq["timestamp"].str[:10] == today]

violations = 0
for token_str, vwap_val in list(vwap["timeframes"]["1min"].items())[:50]:
    token = int(token_str)
    token_bars = eq_today[eq_today["instrument_token"] == token]
    if token_bars.empty:
        continue
    day_high = token_bars["high"].max()
    day_low = token_bars["low"].min()
    if not (day_low <= vwap_val <= day_high):
        print(f"VWAP violation: token={token}, vwap={vwap_val}, high={day_high}, low={day_low}")
        violations += 1

print(f"VWAP violations: {violations} / 50 sampled tokens")
print(f"Total tokens in 1min VWAP snapshot: {len(vwap['timeframes']['1min'])}")
print(f"Total timeframes in snapshot: {list(vwap['timeframes'].keys())}")
```

**Acceptable output:**
- VWAP violations = 0 (VWAP must always be within the day's high-low range)
- All 7 timeframe keys present: `1min`, `3min`, `5min`, `10min`, `15min`, `30min`, `60min`
- Total tokens count ≈ unique tokens in equities_1min.csv for today

**Red flags and diagnosis:**
- VWAP > high for a token → the cumsum logic is using raw `close` without weighting by volume. Check the formula: `(close × volume).cumsum() / volume.cumsum()`
- Timeframes missing from snapshot → `bar_resampler.py` returned empty DataFrame for that timeframe (not enough 1-min data yet). Normal in the first 60 minutes of trading for 60min VWAP.

#### Check 3-D: Resampled CSV Validation

**Run:**
```python
import pandas as pd
from pathlib import Path

timeframes = [3, 5, 10, 15, 30, 60]
eq_1min = pd.read_csv("Data/live_market/equities_1min.csv")
today = pd.Timestamp.now().normalize().isoformat()[:10]
eq_1min_today = eq_1min[eq_1min["timestamp"].str[:10] == today]
rows_1min = len(eq_1min_today)

for tf in timeframes:
    path = Path(f"Data/live_market/equities_{tf}min.csv")
    if not path.exists():
        print(f"MISSING: equities_{tf}min.csv")
        continue
    df = pd.read_csv(path)
    today_df = df[df["timestamp"].str[:10] == today]
    ratio = len(today_df) / rows_1min if rows_1min > 0 else 0
    expected_ratio = 1 / tf
    print(f"equities_{tf}min.csv: rows={len(today_df)}, ratio={ratio:.3f}, expected≈{expected_ratio:.3f}")
```

**Acceptable output:**
- All 6 resampled files exist
- Row ratio for each timeframe ≈ `1/tf` (within 20% tolerance)
  - 3min should have ~1/3 the rows of 1min
  - 60min should have ~1/60 the rows of 1min
- No file has more rows than the 1min source

**Red flags and diagnosis:**
- Resampled CSV has MORE rows than 1min → resample is happening across multiple days. The date filter in bar_resampler.py is not filtering to today before resampling.
- Ratio is exactly 1.0 for all timeframes → resampling did nothing; check that the resample frequency string is correct (`"3T"` not `"3"` or `"3min"` — pandas accepts `"3T"` or `"3min"` depending on version; test which works)

#### Check 3-E: PCR and ATM OI Sanity

**Run:**
```python
import json

with open("Data/live_market/snapshots/pcr_snapshot.json") as f:
    pcr = json.load(f)
with open("Data/live_market/snapshots/atm_oi_snapshot.json") as f:
    atm = json.load(f)

print("PCR snapshot:", json.dumps(pcr, indent=2))
print("ATM OI snapshot:", json.dumps(atm, indent=2))
```

**Acceptable output:**
- NIFTY PCR: 0.3 — 3.0 (extreme values signal a data error)
- BANKNIFTY PCR: 0.3 — 3.0
- `nifty_atm_strike` is a multiple of 50 and within ±500 of current NIFTY level
- `banknifty_atm_strike` is a multiple of 100 and within ±1000 of current BANKNIFTY level
- All OI values > 100,000 (very low OI would indicate wrong strike selection)

**Red flags and diagnosis:**
- PCR = 0 → CALL OI is zero; options data for that underlying is not in options_1min.csv. Check that options tokens for that underlying were subscribed (check options_meta in token_loader output).
- ATM strike is `null` → equities price for NIFTY/BANKNIFTY was not found in equities_1min.csv. NIFTY index (NIFTY 50) may not be in the NSE EQ segment filter; check the instruments CSV for its segment value.

---

### Phase 4 Sanity Checks — After Streamlit UI

#### Check 4-A: Navbar Rendering (All 4 Tabs)

**Test sequence:**
1. Open Streamlit in browser (`http://localhost:8501`)
2. Confirm 4 tabs visible: `Zerodha Authentication`, `Dashboard`, `Backtests`, `Market Pulse`
3. Click each tab in sequence — confirm no `AttributeError`, `ImportError`, or Streamlit crash
4. Return to `Market Pulse` tab

**What a pass looks like:** All 4 tabs render their content without red error boxes. The `Market Pulse` tab shows warning cards (not crash) when collector is not running.

**Red flags and diagnosis:**
- `ImportError: cannot import name 'render' from 'market_pulse_page.market_pulse_section'` → file path mismatch; confirm `Dashboard/market_pulse_page/market_pulse_section.py` exists and has a `def render()` function
- `option_menu` shows only 3 tabs → navbar.py edit was not saved or Streamlit is serving a cached version; hard-refresh (Ctrl+Shift+R) or restart Streamlit

#### Check 4-B: Snapshot Absence Handling

**Test:** With collector NOT running and no snapshot files present, open Market Pulse tab.

**Acceptable behavior:**
- Page renders (no Python exception)
- Each metric card area shows a warning message like "Data unavailable — collector may not be running"
- Control bar shows `Status: STOPPED` badge
- No red Streamlit error box

**Red flags:** Any Python traceback in the Streamlit UI → a snapshot read is not wrapped in try/except. Find the specific `json.load()` call that is not protected and wrap it.

#### Check 4-C: Collector Start/Stop Lifecycle

**Test sequence:**
1. Click "Start Collector" → wait 5 seconds → check status badge changes to `LIVE`
2. Verify `Data/live_market/collector_status.json` shows `status: running`
3. Check Task Manager / Process Explorer for a new `python.exe` process
4. Wait 2 minutes → confirm metric cards populate (advance/decline, VIX, etc.)
5. Click "Stop Collector" → wait 5 seconds → check status badge changes to `STOPPED`
6. Verify the `python.exe` process from step 3 is gone
7. Click "Start Collector" immediately again (double-start test) → confirm toast appears saying already running or second process is NOT spawned

**Acceptable output:** Exactly one `python.exe` process running the collector at any time, controlled cleanly by the UI buttons.

**Red flags and diagnosis:**
- Status stays `STOPPED` after clicking Start → subprocess is failing immediately. Run `python LiveMarket/run_collector.py` manually in terminal to see the error message.
- Process cannot be stopped → the Popen handle was lost across a Streamlit rerun. Confirm the handle is stored in `st.session_state` with a consistent key.
- Double-start spawns two processes → the PID check in `is_collector_running()` is not working. Manually print `psutil.pid_exists(pid)` for the stored PID to debug.

#### Check 4-D: Timeframe Selector Behavior

**Test:**
1. With collector running and data populated, open Market Pulse tab
2. Select timeframe `1min` from dropdown → note the VWAP values displayed
3. Select timeframe `5min` → VWAP values should change (slightly different cumsum granularity)
4. Select timeframe `60min` → if less than 60 minutes of data exists, cards should show "Insufficient data" or the previous valid value, not crash

**Acceptable behavior:** VWAP cards update on timeframe change; no crash on any timeframe selection.

#### Check 4-E: Stale Data Warning

**Test:**
1. Stop the collector
2. Do NOT stop the calculation runner
3. Wait 3 minutes
4. Refresh the Market Pulse page

**Acceptable behavior:**
- Metric cards show last known values (not blank)
- A yellow warning appears: "Data is stale — last updated X minutes ago"
- The status badge shows `STALE` (not `LIVE`)

**Red flags:** Cards show blank/0/None values without explanation → the stale detection logic (`generated_at > 2 minutes ago`) is not comparing timestamps correctly. Confirm that `datetime.fromisoformat()` handles the timezone offset in `generated_at` correctly (use `datetime.fromisoformat(s).replace(tzinfo=None)` for naive comparison if needed).

---

### Summary: Go/No-Go Decision Table

| Phase | All checks pass? | Action |
|---|---|---|
| Phase 0 | Yes | Proceed to Phase 1 |
| Phase 0 | No | Fix failing environment check before writing any code |
| Phase 1 | Yes | Proceed to Phase 2 |
| Phase 1 | Token counts wrong | Fix token_loader.py filter logic, recheck |
| Phase 1 | Prev_close missing | Fix prev_close_loader.py batch/format logic, recheck |
| Phase 2 | Yes | Proceed to Phase 3 |
| Phase 2 | OHLCV violations | Fix bar_aggregator.py before any other work |
| Phase 2 | Memory grows | Fix bar cleanup in get_completed_bars(), recheck |
| Phase 3 | Yes | Proceed to Phase 4 |
| Phase 3 | VWAP violations | Fix vwap_calculator.py formula, recheck |
| Phase 3 | Resampled rows wrong | Fix bar_resampler.py resample frequency string, recheck |
| Phase 4 | Yes | System is complete — document in Changes.md |
| Phase 4 | Subprocess lifecycle broken | Fix collector_controller.py session_state handle, recheck |

---

## 13. Daily File Organization and Holiday Detection

> **This section supersedes the flat file structure described in Sections 2.1 and 11.4.** All paths in Section 12 sanity checks that reference `Data/live_market/equities_1min.csv` etc. should be read as `Data/live_market/daily/YYYY-MM-DD/equities_1min.csv`.

### 13.1 Why Per-Day Files

A single growing CSV file has three problems: it can't be used for backtesting across a date range without filtering, it grows unbounded across sessions, and a corrupted write mid-day contaminates all prior data. Per-day files solve all three: each file is a complete, self-contained trading session, can be loaded as-is by the backtest pipeline, and a bad day can be deleted without losing other days.

### 13.2 Updated Folder Structure

```
Data/live_market/
├── nse_holidays.json                        # Holiday calendar — user maintains annually
├── collector_status.json                    # Current session health (not date-scoped)
├── snapshots/                               # Live snapshots, overwritten every minute
│   ├── vwap_snapshot.json
│   ├── ad_snapshot.json
│   ├── pcr_snapshot.json
│   ├── atm_oi_snapshot.json
│   └── vix_snapshot.json
├── extracted/                               # Temp single-instrument CSVs for backtesting
│   └── 2026-04-28_RELIANCE_5min.csv        # auto-generated by data_extractor.py
└── daily/                                   # One subdirectory per trading day
    ├── 2026-04-28/
    │   ├── prev_close.json                  # That day's baseline prices
    │   ├── equities_1min.csv
    │   ├── equities_3min.csv
    │   ├── equities_5min.csv
    │   ├── equities_10min.csv
    │   ├── equities_15min.csv
    │   ├── equities_30min.csv
    │   ├── equities_60min.csv
    │   ├── options_1min.csv
    │   ├── options_3min.csv
    │   ├── options_5min.csv
    │   ├── options_10min.csv
    │   ├── options_15min.csv
    │   ├── options_30min.csv
    │   ├── options_60min.csv
    │   ├── vix_1min.csv
    │   ├── vix_5min.csv
    │   ├── vix_15min.csv
    │   └── vix_60min.csv
    ├── 2026-04-29/
    │   └── ...
    └── 2026-04-30/
        └── ...
```

### 13.3 Holiday Detection

#### `nse_holidays.json` Schema

```json
{
  "2026": [
    "2026-01-26",
    "2026-03-25",
    "2026-04-02",
    "2026-04-14",
    "2026-04-18",
    "2026-05-01",
    "2026-08-15",
    "2026-10-02",
    "2026-10-24",
    "2026-11-14",
    "2026-11-27",
    "2026-12-25"
  ],
  "2027": []
}
```

**User maintenance requirement:** This file must be updated once per year with the NSE-published holiday list. The NSE website publishes the full-year list in December/January at [nseindia.com](https://www.nseindia.com). The collector will log a warning if the current year has no entries in this file but will not crash — it will simply collect on days that are technically holidays.

#### New File: `LiveMarket/collector/trading_calendar.py`

**Single purpose:** Determine whether a given date is a valid NSE trading day.

**Method signature:**
```python
def is_trading_day(check_date: datetime.date, holidays_path: Path) -> bool
def get_market_open(check_date: datetime.date) -> datetime.time   # returns 09:15
def get_market_close(check_date: datetime.date) -> datetime.time  # returns 15:30
def minutes_until_market_open(now: datetime.datetime) -> int
```

**Logic for `is_trading_day`:**
1. If `check_date.weekday() >= 5` (Saturday=5, Sunday=6) → return `False`
2. Load `nse_holidays.json`; if file missing → log warning, treat all weekdays as trading days
3. If `check_date.isoformat()` in `holidays[str(check_date.year)]` → return `False`
4. Return `True`

**Edge cases:**
- `nse_holidays.json` does not exist → warn in log, assume trading day (fail open rather than fail closed)
- Current year not in JSON → warn in log, assume trading day
- JSON is malformed → warn in log, assume trading day

### 13.4 Updated Collector Startup Sequence

```
run_collector.py starts
  │
  ├─ Check is_trading_day(today) via trading_calendar.py
  │    ├─ NOT a trading day (weekend or holiday):
  │    │    Print "Today is not a trading day. Collector will not start."
  │    │    Write collector_status.json: {status: "not_trading_day", date: today}
  │    │    Exit with code 0
  │    │
  │    └─ IS a trading day: continue
  │
  ├─ Create directory: Data/live_market/daily/YYYY-MM-DD/
  │
  ├─ Check if Data/live_market/daily/YYYY-MM-DD/equities_1min.csv already has data
  │    └─ If yes (collector was restarted mid-day): append mode, do not overwrite
  │
  ├─ Load token groups (token_loader.py)
  ├─ Fetch prev_close → write to Data/live_market/daily/YYYY-MM-DD/prev_close.json
  ├─ Start WebSocket collector (ws_collector.py)
  └─ Start calculation loop (writes snapshots + date-scoped CSVs every 60s)
```

### 13.5 Updated Write Paths

Every write in `ws_collector.py` and `bar_resampler.py` now targets the date-scoped directory:

```python
TODAY_DIR = Path("Data/live_market/daily") / date.today().isoformat()
TODAY_DIR.mkdir(parents=True, exist_ok=True)

EQUITIES_1MIN = TODAY_DIR / "equities_1min.csv"
OPTIONS_1MIN  = TODAY_DIR / "options_1min.csv"
VIX_1MIN      = TODAY_DIR / "vix_1min.csv"
```

At session end (15:30 IST or manual stop), the calculation runner performs one final resample of all timeframes to ensure the day's higher-timeframe files are complete before the collector shuts down.

### 13.6 Impact on Section 12 Sanity Check Paths

All sanity check scripts in Section 12 that reference flat paths need the date prefix added:

| Old path (Section 12) | New path |
|---|---|
| `Data/live_market/equities_1min.csv` | `Data/live_market/daily/2026-04-28/equities_1min.csv` |
| `Data/live_market/options_1min.csv` | `Data/live_market/daily/2026-04-28/options_1min.csv` |
| `Data/live_market/vix_1min.csv` | `Data/live_market/daily/2026-04-28/vix_1min.csv` |
| `Data/live_market/prev_close.json` | `Data/live_market/daily/2026-04-28/prev_close.json` |
| `Data/live_market/equities_5min.csv` | `Data/live_market/daily/2026-04-28/equities_5min.csv` |

The `snapshots/` and `collector_status.json` paths remain unchanged (they are not date-scoped).

### 13.7 New Files Added by This Section

| File | Purpose |
|---|---|
| `LiveMarket/collector/trading_calendar.py` | Holiday/weekend check, market hours |
| `Data/live_market/nse_holidays.json` | User-maintained holiday list |

---

## 14. Backtesting Page Integration — Live Data Selection

### 14.1 Goal

The user must be able to:
1. See which trading days have been collected (only dates that have CSV files in `daily/`)
2. Select a date, then select an instrument from that day's data
3. Select a timeframe (1min through 60min)
4. Run a full backtest using that collected data via the existing execution pipeline

No changes to the existing CSV mode or Zerodha API mode. The live market data is a third independent data source.

### 14.2 New and Modified Files

#### New Files

| File | Purpose |
|---|---|
| `Dashboard/Backtesting_page/Features/live_data_selector.py` | UI panel for date/instrument/timeframe selection |
| `LiveMarket/data_extractor.py` | Extracts one instrument from multi-instrument daily CSV → writes temp CSV |

#### Modified Files (additive only)

| File | What is Added | What Does NOT Change |
|---|---|---|
| `Dashboard/Backtesting_page/Backtests_section.py` | New `"live_market"` branch in data mode selector, new session_state keys | All existing CSV and Zerodha UI panels |
| `Dashboard/Backtesting_page/Features/backtest_data_service.py` | New loading path for `mode == "live_market"` | All existing loading paths |

### 14.3 `LiveMarket/data_extractor.py`

**Single purpose:** Given a date, instrument token, and timeframe, extract that instrument's bars from the multi-instrument daily CSV and write them to a single-instrument temp CSV that the existing backtest pipeline can consume directly.

**Method signature:**
```python
def extract_instrument_data(
    date_str: str,            # "2026-04-28"
    instrument_token: int,
    tradingsymbol: str,
    timeframe: str,           # "1min", "5min", "15min" etc.
    data_type: str,           # "equities" or "options"
    live_data_root: Path,
) -> Path:
    """Returns path to the extracted single-instrument CSV."""
```

**Logic:**
1. Build source path: `live_data_root / "daily" / date_str / f"{data_type}_{timeframe}.csv"`
2. If source file does not exist → raise `FileNotFoundError` with message telling user to check if collector ran on that date
3. Load CSV with pandas, filter rows where `instrument_token == instrument_token`
4. If result is empty → raise `ValueError(f"No data for {tradingsymbol} on {date_str} at {timeframe}")`
5. Select and rename columns to match `data_normalizer.py` input format:
   - Keep: `timestamp`, `open`, `high`, `low`, `close`, `volume`
   - Rename `timestamp` → `Date` (matches existing CSV conventions)
6. Write to `live_data_root / "extracted" / f"{date_str}_{tradingsymbol}_{timeframe}.csv"`
7. Return the written path

**Output CSV schema (matches existing Zerodha CSV format):**
```
Date,open,high,low,close,volume
2026-04-28 09:15:00+05:30,22100.0,22150.0,22090.0,22120.0,145000
2026-04-28 09:20:00+05:30,22120.0,22180.0,22105.0,22160.0,132000
```

**Edge cases:**
- `extracted/` directory does not exist → create it before writing
- File was already extracted (same date/symbol/timeframe) → overwrite it (extraction is idempotent)
- `tradingsymbol` contains characters invalid for filenames (e.g., `/`) → sanitize with `re.sub(r'[^\w\-]', '_', tradingsymbol)`

### 14.4 `Dashboard/Backtesting_page/Features/live_data_selector.py`

**Single purpose:** Render the Live Market Data selection panel in the Backtests UI.

**What it renders:**

```
┌─────────────────────────────────────────────────────────────────┐
│ LIVE MARKET DATA                                                 │
│                                                                  │
│ Available Dates        Data Type        Timeframe               │
│ [2026-04-28 ▼]        [Equities ▼]     [5min    ▼]             │
│                                                                  │
│ Instrument Search                                                │
│ [Search symbol...                                    🔍]        │
│                                                                  │
│ RELIANCE  (token: 256265)  1,287 bars  09:15–15:29             │
│ INFY      (token: 408065)  1,283 bars  09:15–15:28             │
│ HDFCBANK  (token: 341249)  1,276 bars  09:15–15:27             │
│  ↑ scroll for more                                               │
│                                                                  │
│ Selected: RELIANCE · 2026-04-28 · 5min · 1,283 bars            │
│ [✓ Use This Data for Backtest]                                  │
└─────────────────────────────────────────────────────────────────┘
```

**Key render steps:**

**Step 1 — Scan available dates:**
```python
daily_root = Path("Data/live_market/daily")
available_dates = sorted([
    d.name for d in daily_root.iterdir()
    if d.is_dir() and (d / "equities_1min.csv").exists()
], reverse=True)  # most recent first
```
If `available_dates` is empty → show `st.info("No live market data collected yet. Start the collector from the Market Pulse page.")` and return.

**Step 2 — Date + type + timeframe row:**
```python
col1, col2, col3 = st.columns(3)
selected_date = col1.selectbox("Available Dates", available_dates)
data_type = col2.selectbox("Data Type", ["equities", "options"])
timeframe = col3.selectbox("Timeframe", ["1min","3min","5min","10min","15min","30min","60min"])
```

**Step 3 — Load instrument index for selected date:**
Read `Data/live_market/daily/{selected_date}/equities_1min.csv` (only columns `instrument_token` and `tradingsymbol`), deduplicate, and build a list of `{token, tradingsymbol, bar_count}` for the search list. Cache this in `st.session_state` keyed by `(selected_date, data_type)` — avoid re-reading on every interaction.

**Step 4 — Instrument search:**
```python
query = st.text_input("Instrument Search", placeholder="Type symbol name...")
filtered = [i for i in instrument_index if query.upper() in i["tradingsymbol"]]
```
Show the filtered list as a `st.radio` or clickable `st.dataframe` with `selection_mode="single-row"`.

**Step 5 — Selection summary and confirm button:**
Show a one-line summary of the current selection. When the user clicks "Use This Data for Backtest":
```python
st.session_state["live_selected_date"] = selected_date
st.session_state["live_selected_token"] = selected_instrument["token"]
st.session_state["live_selected_symbol"] = selected_instrument["tradingsymbol"]
st.session_state["live_selected_timeframe"] = timeframe
st.session_state["live_selected_data_type"] = data_type
st.session_state["data_mode"] = "live_market"
```

**Edge cases:**
- Selected date has `equities_1min.csv` but not `equities_5min.csv` (resampler hadn't run yet when collector was stopped) → show warning: "5min data not available for this date. Only 1min is available."
- Instrument index CSV read fails (file locked or corrupt) → catch exception, show `st.error`, return without crashing
- No instruments match the search query → show "No instruments match" message, do not show empty list

### 14.5 Modifications to `Backtests_section.py`

**Location:** The data mode selector — currently renders a tab or radio for "CSV" and "Zerodha API". Find this section and add a third option.

**What to add:**

```python
# In _sync_state_contract(), add new keys to selected_data_default:
selected_data_default = {
    "mode": "csv",
    "selected_files": [],
    "zerodha_queue": [],
    "symbol": "",
    "interval": "15minute",
    "dates": (None, None),
    # NEW:
    "live_date": None,
    "live_instrument_token": None,
    "live_tradingsymbol": None,
    "live_timeframe": None,
    "live_data_type": "equities",
}
```

**In the data mode radio/tab selector, add the third option:**
```python
data_mode = st.radio(
    "Data Source",
    options=["csv", "zerodha", "live_market"],
    format_func=lambda x: {
        "csv": "Local CSV",
        "zerodha": "Zerodha API",
        "live_market": "Live Market Data",
    }[x],
    horizontal=True,
    key="data_mode",
)
```

**In the conditional rendering block, add the third branch:**
```python
if data_mode == "csv":
    # existing CSV panel — unchanged
    data_selection_feature.render(...)

elif data_mode == "zerodha":
    # existing Zerodha API panel — unchanged
    _render_zerodha_data_panel(...)

elif data_mode == "live_market":
    # NEW
    from .Features import live_data_selector
    live_data_selector.render()
```

**In the "Add to Queue" / task builder section, add the live_market path:**
```python
if data_mode == "live_market":
    token = st.session_state.get("live_selected_token")
    symbol = st.session_state.get("live_selected_symbol")
    date_str = st.session_state.get("live_selected_date")
    timeframe = st.session_state.get("live_selected_timeframe")
    data_type = st.session_state.get("live_selected_data_type", "equities")

    if not all([token, symbol, date_str, timeframe]):
        st.warning("Select a date, instrument, and timeframe from the Live Market Data panel first.")
    else:
        # data_extractor writes to extracted/ and returns the path
        from LiveMarket.data_extractor import extract_instrument_data
        extracted_path = extract_instrument_data(date_str, token, symbol, timeframe, data_type, LIVE_DATA_ROOT)
        task = backtest_data_service.build_csv_task(
            data_path=str(extracted_path),
            strategy_file=...,
            strategy_class=...,
            config=...,
        )
        # add task to queue — same flow as existing CSV mode
```

**What does NOT change:**
- All existing CSV mode task building
- All existing Zerodha API task building
- The queue display panel
- The strategy editor panel
- The execution engine section
- The terminal output section

### 14.6 Modifications to `backtest_data_service.py`

**What to add:** A helper that validates the live data selection before the task is built.

```python
def validate_live_data_selection(
    date_str: str,
    instrument_token: int,
    tradingsymbol: str,
    timeframe: str,
    data_type: str,
    live_data_root: Path,
) -> tuple[bool, str]:
    """Returns (ok, error_message). Called before building the task."""
    daily_dir = live_data_root / "daily" / date_str
    if not daily_dir.exists():
        return False, f"No data collected for {date_str}."
    source_csv = daily_dir / f"{data_type}_{timeframe}.csv"
    if not source_csv.exists():
        return False, f"{timeframe} data not available for {date_str}. Try 1min."
    return True, ""
```

No other changes to `backtest_data_service.py`.

### 14.7 UI Integration Flow (End-to-End)

```
User opens Backtests page
  │
  ├─ Clicks "Live Market Data" radio button
  │    └─ live_data_selector.render() appears
  │
  ├─ Selects date "2026-04-28" from dropdown
  │    └─ live_data_selector reads equities_1min.csv → builds instrument index
  │
  ├─ Types "RELI" in search box
  │    └─ Filters to RELIANCE, sets session state
  │
  ├─ Selects "5min" timeframe
  │
  ├─ Clicks "Use This Data for Backtest"
  │    └─ Session state updated: live_selected_* keys set
  │
  ├─ (Selects strategy from strategy panel — unchanged)
  │
  ├─ Clicks "Add to Backtest Queue"
  │    ├─ validate_live_data_selection() → (True, "")
  │    ├─ data_extractor.extract_instrument_data() → writes extracted CSV
  │    └─ build_csv_task(data_path=extracted_path) → task added to queue
  │
  └─ Clicks "Execute All"
       └─ Existing execution pipeline runs — treats it as a CSV task
            No awareness of live market data needed downstream
```

The execution pipeline (ExecutionManager → api_based_execution_engine/execution_engine → backtest_core) receives a standard CSV task. Nothing in the execution pipeline changes.

### 14.8 What the User Sees: Data Selection Panel Changes Summary

| Location | Current State | After This Change |
|---|---|---|
| Data Source selector | 2 options: Local CSV, Zerodha API | 3 options: Local CSV, Zerodha API, Live Market Data |
| Live Market panel (new) | — | Date dropdown (only days with data), Data Type, Timeframe, Instrument search |
| Queue item label | "RELIANCE · zerodha · 5minute" | "RELIANCE · live · 2026-04-28 · 5min" |
| Execution result | Same as always | Same as always — data was extracted to CSV before entering pipeline |

### 14.9 Additional Sanity Checks for This Section (Phase 5)

Run these after completing the backtesting integration on top of a working Phase 4.

**Check 5-A: Available dates scan**
```python
from pathlib import Path
daily_root = Path("Data/live_market/daily")
dates = sorted([d.name for d in daily_root.iterdir() if d.is_dir()])
print("Available dates:", dates)
for d in dates:
    files = list((daily_root / d).glob("*.csv"))
    print(f"  {d}: {len(files)} CSV files")
```
Expected: Each date directory has 19 CSV files (7 timeframes × equities/options + 3 VIX timeframes + 1min base files for each type).

**Check 5-B: Extraction correctness**
```python
from LiveMarket.data_extractor import extract_instrument_data
from pathlib import Path

path = extract_instrument_data(
    "2026-04-28", 256265, "RELIANCE", "5min", "equities",
    Path("Data/live_market")
)
import pandas as pd
df = pd.read_csv(path)
print("Columns:", df.columns.tolist())
print("Rows:", len(df))
print("Unique tokens:", df.get("instrument_token", pd.Series()).nunique() if "instrument_token" in df.columns else "column removed — correct")
print("Date range:", df["Date"].iloc[0], "→", df["Date"].iloc[-1])
```
Expected: `Columns` matches `["Date","open","high","low","close","volume"]`, rows ≈ 75 (375 minutes / 5), `Date range` from 09:15 to 15:25.

**Check 5-C: Backtest runs to completion on extracted data**
1. Add the extracted RELIANCE 5min data to the backtest queue
2. Select any valid strategy
3. Execute — confirm no crash, result appears in trade log
4. Open Dashboard tab → load the result CSV → confirm chart renders with correct timestamps

**Check 5-D: Holiday blocking**
1. Temporarily add today's date to `nse_holidays.json`
2. Run `python LiveMarket/run_collector.py`
3. Confirm output: "Today is not a trading day. Collector will not start."
4. Confirm `collector_status.json` shows `status: not_trading_day`
5. Remove today from `nse_holidays.json`
