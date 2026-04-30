from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from LiveMarket import PROJECT_ROOT
from LiveMarket.market_universes import build_ad_universes
from LiveMarket.time_utils import now_ist_iso, today_ist


_INDEX_SPOT_SYMBOLS = {"NIFTY 50", "NIFTY BANK", "NIFTY", "BANKNIFTY"}


def _empty_payload() -> dict[str, Any]:
    return {
        "generated_at": now_ist_iso(),
        "advances": 0,
        "declines": 0,
        "unchanged": 0,
        "ad_ratio": 0.0,
        "universe_observed": 0,
        "matched_prev_close": 0,
        "missing_prev_close": 0,
        "selected_universe": "All Collected",
        "universes": {},
    }


def _load_prev_close(path: Path) -> dict[str, float]:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    data = payload.get("data", {})
    if not isinstance(data, dict):
        return {}
    result: dict[str, float] = {}
    for key, value in data.items():
        try:
            result[str(key)] = float(value)
        except (TypeError, ValueError):
            continue
    return result


def _score_latest_close(
    latest_df: pd.DataFrame,
    prev_close: dict[str, float],
    *,
    universe_symbols: set[str] | None = None,
    configured_universe_size: int | None = None,
) -> dict[str, Any]:
    if universe_symbols is not None:
        symbols = latest_df["tradingsymbol"].astype(str).str.strip().str.upper()
        latest_df = latest_df.loc[symbols.isin(universe_symbols)].copy()

    advances = 0
    declines = 0
    unchanged = 0
    missing_prev_close = 0
    for row in latest_df.itertuples(index=False):
        token = int(row.instrument_token)
        close = float(row.close)
        prev = prev_close.get(str(token))
        if prev is None:
            missing_prev_close += 1
            continue
        if close > prev:
            advances += 1
        elif close < prev:
            declines += 1
        else:
            unchanged += 1

    ad_ratio = round((advances / declines), 4) if declines > 0 else float(advances)
    payload: dict[str, Any] = {
        "advances": int(advances),
        "declines": int(declines),
        "unchanged": int(unchanged),
        "ad_ratio": ad_ratio,
        "universe_observed": int(len(latest_df)),
        "matched_prev_close": int(advances + declines + unchanged),
        "missing_prev_close": int(missing_prev_close),
    }
    if configured_universe_size is not None:
        payload["configured_universe_size"] = int(configured_universe_size)
    return payload


def compute(
    equities_1min_csv: Path,
    prev_close_json: Path,
    instruments_csv_path: str | Path | None = None,
) -> dict[str, Any]:
    prev_close = _load_prev_close(prev_close_json)
    if not equities_1min_csv.is_file():
        return _empty_payload()
    df = pd.read_csv(equities_1min_csv)
    if df.empty:
        return _empty_payload()
    required = {"timestamp", "instrument_token", "close"}
    if not required.issubset(set(df.columns)):
        return _empty_payload()
    if "tradingsymbol" in df.columns:
        symbols = df["tradingsymbol"].astype(str).str.strip().str.upper()
        df = df.loc[~symbols.isin(_INDEX_SPOT_SYMBOLS)].copy()
        if df.empty:
            return _empty_payload()

    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    df = df.dropna(subset=["timestamp"])
    if df.empty:
        return _empty_payload()
    df = df[df["timestamp"].dt.date == today_ist()]
    if df.empty:
        return _empty_payload()
    df["close"] = pd.to_numeric(df["close"], errors="coerce")
    df["instrument_token"] = pd.to_numeric(df["instrument_token"], errors="coerce")
    if "tradingsymbol" not in df.columns:
        df["tradingsymbol"] = ""
    df["tradingsymbol"] = df["tradingsymbol"].astype(str).str.strip().str.upper()
    df = df.dropna(subset=["close", "instrument_token"]).sort_values("timestamp")
    if df.empty:
        return _empty_payload()

    latest_df = df.groupby("instrument_token", sort=False).tail(1).copy()
    latest_df["instrument_token"] = latest_df["instrument_token"].astype("int64")

    all_collected = _score_latest_close(latest_df, prev_close)
    universe_payloads: dict[str, Any] = {
        "All Collected": dict(all_collected),
    }

    resolved_instruments_path = (
        Path(instruments_csv_path).resolve()
        if instruments_csv_path is not None
        else PROJECT_ROOT / "Data" / "instrument_mapper_data" / "zerodha_instruments_latest.csv"
    )
    for name, symbols in build_ad_universes(resolved_instruments_path).items():
        universe_payloads[name] = _score_latest_close(
            latest_df,
            prev_close,
            universe_symbols=symbols,
            configured_universe_size=len(symbols),
        )

    payload = {
        "generated_at": now_ist_iso(),
        "selected_universe": "All Collected",
        "universes": universe_payloads,
    }
    payload.update(all_collected)
    return payload


__all__ = ["compute"]
