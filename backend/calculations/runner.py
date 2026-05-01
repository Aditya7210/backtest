"""Migrated calculation runner — reads bars from MongoDB, writes snapshots to MongoDB."""
from __future__ import annotations

import time
from typing import Any

import pandas as pd

from backend.database.sync_connection import get_sync_db
from backend.utils.time_utils import today_ist, now_ist_iso


_RESAMPLE_TIMEFRAMES = [3, 5, 10, 15, 30, 60]


def _load_bars_as_df(instrument_type: str, trading_date: str) -> pd.DataFrame:
    """Load 1-min bars from MongoDB for a given instrument type and date."""
    db = get_sync_db()
    cursor = db.bars.find({
        "instrument_type": instrument_type,
        "timeframe": "1min",
        "trading_date": trading_date,
    }).sort("timestamp", 1)

    rows = list(cursor)
    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    df = df.drop(columns=["_id"], errors="ignore")
    return df


def _compute_vwap_snapshot(equities_df: pd.DataFrame) -> dict[str, Any]:
    """Compute VWAP from equities bars."""
    if equities_df.empty:
        return {}

    payload: dict[str, float] = {}
    for token, token_df in equities_df.groupby("instrument_token", sort=False):
        token_df = token_df.sort_values("timestamp")
        cumulative_volume = token_df["volume"].cumsum()
        if cumulative_volume.iloc[-1] <= 0:
            continue
        cumulative_value = (token_df["close"] * token_df["volume"]).cumsum()
        vwap_series = cumulative_value / cumulative_volume
        payload[str(int(token))] = round(float(vwap_series.iloc[-1]), 4)

    return {"generated_at": now_ist_iso(), "data": {"1min": payload}}


def _compute_ad_snapshot(equities_df: pd.DataFrame, prev_close: dict[str, float]) -> dict[str, Any]:
    """Compute Advance/Decline from equities bars and previous close."""
    if equities_df.empty:
        return {"generated_at": now_ist_iso(), "advances": 0, "declines": 0, "unchanged": 0, "ad_ratio": 0.0}

    latest_df = equities_df.groupby("instrument_token", sort=False).tail(1).copy()
    advances = 0
    declines = 0
    unchanged = 0

    for _, row in latest_df.iterrows():
        token = str(int(row["instrument_token"]))
        close = float(row["close"])
        prev = prev_close.get(token)
        if prev is None:
            continue
        if close > prev:
            advances += 1
        elif close < prev:
            declines += 1
        else:
            unchanged += 1

    ad_ratio = round(advances / declines, 4) if declines > 0 else float(advances)

    return {
        "generated_at": now_ist_iso(),
        "advances": advances,
        "declines": declines,
        "unchanged": unchanged,
        "ad_ratio": ad_ratio,
    }


def _compute_pcr_snapshot(options_df: pd.DataFrame) -> dict[str, Any]:
    """Compute PCR from options bars."""
    if options_df.empty:
        return {"generated_at": now_ist_iso(), "nifty_pcr": 0.0, "banknifty_pcr": 0.0}

    latest_df = options_df.groupby("instrument_token", sort=False).tail(1).copy()

    def _pcr_for_underlying(df: pd.DataFrame, prefix: str) -> dict[str, Any]:
        if prefix == "NIFTY":
            subset = df[
                df["tradingsymbol"].str.startswith("NIFTY", na=False)
                & ~df["tradingsymbol"].str.startswith("BANKNIFTY", na=False)
            ]
        else:
            subset = df[df["tradingsymbol"].str.startswith("BANKNIFTY", na=False)]
        if subset.empty:
            return {"pcr": 0.0, "calls": 0, "puts": 0}
        calls = int(subset.loc[subset["option_type"] == "CE", "oi"].sum()) if "oi" in subset.columns else 0
        puts = int(subset.loc[subset["option_type"] == "PE", "oi"].sum()) if "oi" in subset.columns else 0
        pcr = round(puts / calls, 4) if calls > 0 else 0.0
        return {"pcr": pcr, "calls": calls, "puts": puts}

    nifty = _pcr_for_underlying(latest_df, "NIFTY")
    bank = _pcr_for_underlying(latest_df, "BANKNIFTY")

    return {
        "generated_at": now_ist_iso(),
        "nifty_pcr": nifty["pcr"],
        "banknifty_pcr": bank["pcr"],
        "nifty_call_oi": nifty["calls"],
        "nifty_put_oi": nifty["puts"],
        "banknifty_call_oi": bank["calls"],
        "banknifty_put_oi": bank["puts"],
    }


def _compute_vix_snapshot(vix_df: pd.DataFrame) -> dict[str, Any]:
    """Compute VIX snapshot."""
    if vix_df.empty:
        return {"generated_at": now_ist_iso(), "vix": None, "vix_open": None}
    latest = vix_df.iloc[-1]
    first = vix_df.iloc[0]
    return {
        "generated_at": now_ist_iso(),
        "vix": float(latest.get("close")) if pd.notna(latest.get("close")) else None,
        "vix_open": float(first.get("open")) if pd.notna(first.get("open")) else None,
    }


def _load_prev_close(trading_date: str) -> dict[str, float]:
    """Load prev_close from MongoDB."""
    db = get_sync_db()
    doc = db.snapshots.find_one({"snapshot_type": "prev_close", "trading_date": trading_date})
    if doc is None:
        return {}
    return doc.get("data", {})


def _write_snapshot(snapshot_type: str, trading_date: str, data: dict[str, Any]) -> None:
    """Write snapshot to MongoDB."""
    db = get_sync_db()
    db.snapshots.update_one(
        {"snapshot_type": snapshot_type, "trading_date": trading_date},
        {"$set": {
            "snapshot_type": snapshot_type,
            "trading_date": trading_date,
            "generated_at": now_ist_iso(),
            "data": data,
        }},
        upsert=True,
    )


def run_once() -> dict[str, Any]:
    """Single calculation cycle — read bars, compute snapshots, write to MongoDB."""
    trading_date = today_ist().isoformat()

    equities_df = _load_bars_as_df("equity", trading_date)
    options_df = _load_bars_as_df("option", trading_date)
    vix_df = _load_bars_as_df("vix", trading_date)
    prev_close = _load_prev_close(trading_date)

    vwap_snapshot = _compute_vwap_snapshot(equities_df)
    ad_snapshot = _compute_ad_snapshot(equities_df, prev_close)
    pcr_snapshot = _compute_pcr_snapshot(options_df)
    vix_snapshot = _compute_vix_snapshot(vix_df)

    _write_snapshot("vwap", trading_date, vwap_snapshot)
    _write_snapshot("ad", trading_date, ad_snapshot)
    _write_snapshot("pcr", trading_date, pcr_snapshot)
    _write_snapshot("vix", trading_date, vix_snapshot)

    return {"status": "ok", "trading_date": trading_date, "generated_at": now_ist_iso()}


def start_loop(interval_seconds: float = 10.0) -> None:
    """Run calculation loop."""
    wait = max(5.0, float(interval_seconds))
    print(f"[calculation_runner] started interval={wait:.1f}s")
    while True:
        started_at = time.time()
        try:
            result = run_once()
            print(f"[calculation_runner] cycle: {result}")
        except KeyboardInterrupt:
            raise
        except Exception as exc:
            print(f"[calculation_runner] failed: {type(exc).__name__}: {exc}")
        elapsed = time.time() - started_at
        sleep_time = max(0.0, wait - elapsed)
        if sleep_time > 0:
            time.sleep(sleep_time)
