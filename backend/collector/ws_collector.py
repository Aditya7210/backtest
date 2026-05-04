"""Migrated ws_collector — writes completed bars to MongoDB instead of CSV (E-03: sync pymongo)."""
from __future__ import annotations

from datetime import datetime, timezone
import os
import threading
import time
from typing import Any
from zoneinfo import ZoneInfo

from kiteconnect import KiteConnect, KiteTicker

from backend.collector.bar_aggregator import IST, MinuteBarAggregator
from backend.collector.live_tick_feature import flush_latest_ticks_to_mongo
from backend.database.sync_connection import get_sync_db

_MAX_WS_TOKENS = 3000


def _now_iso() -> str:
    return datetime.now(tz=IST).isoformat(timespec="seconds")


def _load_kite_credentials() -> tuple[str, str]:
    """Load Zerodha credentials from environment."""
    from backend.config import settings
    api_key = settings.ZERODHA_API_KEY
    access_token = settings.ZERODHA_ACCESS_TOKEN
    if not api_key:
        raise RuntimeError("Missing ZERODHA_API_KEY")
    if not access_token:
        raise RuntimeError("Missing ZERODHA_ACCESS_TOKEN")
    return api_key, access_token


def build_kite_client() -> KiteConnect:
    api_key, access_token = _load_kite_credentials()
    kite = KiteConnect(api_key=api_key)
    kite.set_access_token(access_token)
    return kite


def _write_bars_to_mongo(
    bars: list[Any],
    equity_tokens: set[int],
    futures_tokens: set[int],
    options_tokens: set[int],
    vix_token: int | None,
    token_to_symbol: dict[int, str],
    futures_meta: dict[int, dict[str, Any]],
    options_meta: dict[int, dict[str, Any]],
    trading_date: str,
) -> int:
    """Write completed bars to MongoDB bars collection using sync pymongo (E-03)."""
    from pymongo import UpdateOne

    db = get_sync_db()
    operations = []

    for bar in bars:
        token = int(bar.instrument_token)
        ts_utc = bar.bar_start.astimezone(timezone.utc)

        doc = {
            "timestamp": ts_utc,
            "trading_date": trading_date,
            "timeframe": "1min",
            "instrument_token": token,
            "tradingsymbol": str(token_to_symbol.get(token, f"TOKEN_{token}")),
            "open": round(float(bar.open), 6),
            "high": round(float(bar.high), 6),
            "low": round(float(bar.low), 6),
            "close": round(float(bar.close), 6),
            "volume": round(float(bar.volume), 6),
            "data_source": "live",
        }

        if token in equity_tokens:
            symbol_up = str(token_to_symbol.get(token, "")).upper()
            if symbol_up in {"NIFTY 50", "NIFTY", "NIFTY BANK", "BANKNIFTY"}:
                doc["instrument_type"] = "index"
            else:
                doc["instrument_type"] = "equity"
            doc["exchange"] = "NSE"
            doc["segment"] = "NSE"
        elif token in futures_tokens:
            doc["instrument_type"] = "future"
            meta = futures_meta.get(token, {})
            doc["underlying"] = meta.get("underlying")
            doc["expiry"] = meta.get("expiry")
            doc["exchange"] = meta.get("exchange", "NFO")
            doc["segment"] = meta.get("segment", "NFO-FUT")
            doc["oi"] = round(float(bar.oi), 6)
        elif token in options_tokens:
            doc["instrument_type"] = "option"
            meta = options_meta.get(token, {})
            doc["strike"] = meta.get("strike")
            doc["expiry"] = meta.get("expiry")
            doc["option_type"] = meta.get("option_type")
            doc["underlying"] = meta.get("underlying")
            doc["exchange"] = meta.get("exchange", "NFO")
            doc["segment"] = meta.get("segment", "NFO-OPT")
            doc["oi"] = round(float(bar.oi), 6)
        elif vix_token is not None and token == vix_token:
            doc["instrument_type"] = "vix"
            doc["exchange"] = "NSE"
            doc["segment"] = "INDICES"
        else:
            doc["instrument_type"] = "unknown"

        filt = {
            "instrument_token": token,
            "timeframe": "1min",
            "timestamp": ts_utc,
        }
        operations.append(UpdateOne(filt, {"$set": doc}, upsert=True))

    if not operations:
        return 0

    result = db.bars.bulk_write(operations, ordered=False)
    return result.upserted_count + result.modified_count


def start(
    *,
    equity_tokens: set[int],
    futures_tokens: set[int],
    options_tokens: set[int],
    vix_token: int | None,
    futures_meta: dict[int, dict[str, Any]],
    options_meta: dict[int, dict[str, Any]],
    token_to_symbol: dict[int, str],
    trading_date: str,
    token_counts: dict[str, Any] | None = None,
) -> None:
    """Start the WebSocket collector — writes to MongoDB instead of CSV."""
    api_key, access_token = _load_kite_credentials()
    aggregator = MinuteBarAggregator()
    status_lock = threading.Lock()
    state: dict[str, Any] = {
        "bars_written": 0,
        "ticks_seen": 0,
        "first_tick_at": None,
        "last_tick_at": None,
        "last_bar_at": None,
        "last_error": None,
        "heartbeat_at": _now_iso(),
    }
    latest_ticks_by_token: dict[int, dict[str, Any]] = {}

    all_tokens: list[int] = sorted(
        {int(t) for t in equity_tokens}
        | {int(t) for t in futures_tokens}
        | {int(t) for t in options_tokens}
        | ({int(vix_token)} if vix_token is not None else set())
    )
    if not all_tokens:
        raise RuntimeError("No instruments available for WebSocket subscription")
    if len(all_tokens) > _MAX_WS_TOKENS:
        raise RuntimeError(f"Too many tokens: {len(all_tokens)} > {_MAX_WS_TOKENS}")

    ticker = KiteTicker(api_key, access_token, reconnect=True, reconnect_max_tries=100, reconnect_max_delay=10)
    token_meta: dict[int, dict[str, Any]] = {}
    for token in equity_tokens:
        symbol_up = str(token_to_symbol.get(int(token), "")).upper()
        token_meta[int(token)] = {
            "instrument_type": "index" if symbol_up in {"NIFTY 50", "NIFTY", "NIFTY BANK", "BANKNIFTY"} else "equity",
            "exchange": "NSE",
            "segment": "NSE",
        }
    for token, meta in futures_meta.items():
        token_meta[int(token)] = {
            "instrument_type": "future",
            "exchange": meta.get("exchange", "NFO"),
            "segment": meta.get("segment", "NFO-FUT"),
            "underlying": meta.get("underlying"),
            "expiry": meta.get("expiry"),
        }
    for token, meta in options_meta.items():
        token_meta[int(token)] = {
            "instrument_type": "option",
            "exchange": meta.get("exchange", "NFO"),
            "segment": meta.get("segment", "NFO-OPT"),
            "underlying": meta.get("underlying"),
            "expiry": meta.get("expiry"),
            "strike": meta.get("strike"),
            "option_type": meta.get("option_type"),
        }
    if vix_token is not None:
        token_meta[int(vix_token)] = {
            "instrument_type": "vix",
            "exchange": "NSE",
            "segment": "INDICES",
        }

    # Update status in MongoDB
    db = get_sync_db()
    db.collector_status.update_one(
        {"_id": "singleton"},
        {"$set": {
            "collector.status": "running",
            "collector.pid": os.getpid(),
            "collector.started_at": _now_iso(),
            "collector.trading_date": trading_date,
            "collector.tokens_subscribed": len(all_tokens),
            "collector.token_counts": token_counts or {},
            "collector.bars_written": 0,
            "collector.ticks_seen": 0,
            "collector.first_tick_at": None,
            "collector.last_tick_at": None,
            "collector.last_bar_at": None,
            "collector.warming_up": True,
            "collector.heartbeat_at": _now_iso(),
            "collector.last_error": None,
        }},
        upsert=True,
    )

    def on_connect(ws, _response):
        print(f"[ws_collector] connected. subscribing tokens={len(all_tokens)}")
        ws.subscribe(all_tokens)
        equities = sorted({int(t) for t in equity_tokens})
        derivatives = sorted(
            {int(t) for t in futures_tokens}
            | {int(t) for t in options_tokens}
            | ({int(vix_token)} if vix_token is not None else set())
        )
        if equities:
            ws.set_mode(ws.MODE_QUOTE, equities)
        if derivatives:
            ws.set_mode(ws.MODE_FULL, derivatives)

    def on_ticks(_ws, ticks):
        if not ticks:
            return
        with status_lock:
            state["ticks_seen"] = int(state.get("ticks_seen", 0)) + len(ticks)
            if not state.get("first_tick_at"):
                state["first_tick_at"] = _now_iso()
            state["last_tick_at"] = _now_iso()
            state["heartbeat_at"] = _now_iso()
        for tick in ticks:
            try:
                token = int(tick.get("instrument_token"))
            except Exception:
                continue
            ltp = float(tick.get("last_price") or 0.0)
            volume = tick.get("volume_traded") or tick.get("volume")
            oi = tick.get("oi") or 0.0
            tick_ts = tick.get("timestamp")
            if tick_ts is None:
                tick_ts = datetime.now(tz=IST)
            elif isinstance(tick_ts, datetime):
                if tick_ts.tzinfo is None:
                    tick_ts = tick_ts.replace(tzinfo=IST)
            else:
                try:
                    parsed = datetime.fromisoformat(str(tick_ts))
                except Exception:
                    parsed = datetime.now(tz=IST)
                tick_ts = parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=IST)
            aggregator.update(token=token, ltp=ltp, session_volume=volume, oi=oi, tick_time=tick_ts)
            meta = token_meta.get(token, {})
            latest_ticks_by_token[token] = {
                "last_price": ltp,
                "volume_traded": float(volume or 0.0),
                "oi": float(oi or 0.0),
                "timestamp": tick_ts,
                "trading_date": trading_date,
                "tradingsymbol": token_to_symbol.get(token, f"TOKEN_{token}"),
                "instrument_type": meta.get("instrument_type", "unknown"),
                "exchange": meta.get("exchange", ""),
                "segment": meta.get("segment", ""),
                "underlying": meta.get("underlying"),
                "expiry": meta.get("expiry"),
                "strike": meta.get("strike"),
                "option_type": meta.get("option_type"),
            }

    def on_error(_ws, code, reason):
        with status_lock:
            state["last_error"] = f"[{code}] {reason}"
            state["heartbeat_at"] = _now_iso()

    ticker.on_connect = on_connect
    ticker.on_ticks = on_ticks
    ticker.on_error = on_error
    ticker.on_reconnect = lambda _ws, c: print(f"[ws_collector] reconnect attempt={c}")
    ticker.on_close = lambda _ws, c, r: print(f"[ws_collector] closed code={c} reason={r}")

    ticker.connect(threaded=True)
    print("[ws_collector] ticker thread started")

    try:
        while True:
            current_minute = datetime.now(tz=IST)
            completed = aggregator.get_completed_bars(current_minute)
            if completed:
                rows = _write_bars_to_mongo(
                    completed, equity_tokens, futures_tokens, options_tokens, vix_token,
                    token_to_symbol, futures_meta, options_meta, trading_date,
                )
                state["bars_written"] = int(state.get("bars_written", 0)) + rows
                state["last_bar_at"] = _now_iso()
            if latest_ticks_by_token:
                flush_latest_ticks_to_mongo(db, latest_ticks_by_token)
            state["heartbeat_at"] = _now_iso()
            # Update status in MongoDB
            db.collector_status.update_one(
                {"_id": "singleton"},
                {"$set": {
                    "collector.bars_written": state["bars_written"],
                    "collector.ticks_seen": state["ticks_seen"],
                    "collector.first_tick_at": state["first_tick_at"],
                    "collector.last_tick_at": state["last_tick_at"],
                    "collector.last_bar_at": state["last_bar_at"],
                    "collector.warming_up": bool(state.get("last_tick_at")) and not bool(state.get("last_bar_at")),
                    "collector.heartbeat_at": state["heartbeat_at"],
                    "collector.last_error": state["last_error"],
                }},
            )
            time.sleep(1.0)
    except KeyboardInterrupt:
        print("[ws_collector] interrupted")
    finally:
        try:
            ticker.close()
        except Exception:
            pass
        db.collector_status.update_one(
            {"_id": "singleton"},
            {"$set": {"collector.status": "stopped", "collector.pid": None}},
        )
