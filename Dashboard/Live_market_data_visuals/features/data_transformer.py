from __future__ import annotations

from typing import Any

import pandas as pd

from LiveMarket.market_universes import build_ad_universes
from .indicator_engine import add_indicators


_INDEX_SPOT_SYMBOLS = {"NIFTY 50", "NIFTY BANK", "NIFTY", "BANKNIFTY"}


def normalize_symbol(value: str) -> str:
    return str(value or "").strip().upper()


def instrument_ohlc(equities: pd.DataFrame, instrument: str) -> pd.DataFrame:
    if equities.empty or "tradingsymbol" not in equities.columns:
        return pd.DataFrame()
    symbol = normalize_symbol(instrument)
    frame = equities[equities["tradingsymbol"].astype(str).str.strip().str.upper() == symbol].copy()
    if frame.empty:
        return frame
    numeric_cols = ["open", "high", "low", "close", "volume"]
    for column in numeric_cols:
        if column in frame.columns:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame = frame.dropna(subset=["timestamp", "open", "high", "low", "close"]).sort_values("timestamp")
    return add_indicators(frame)


def _score_group(group: pd.DataFrame, prev_close: dict[str, Any]) -> tuple[int, int]:
    advances = 0
    declines = 0
    for row in group.itertuples(index=False):
        try:
            token = str(int(row.instrument_token))
            close = float(row.close)
            prev = float(prev_close[token])
        except Exception:
            continue
        if close > prev:
            advances += 1
        elif close < prev:
            declines += 1
    return advances, declines


def advance_decline_series(
    equities: pd.DataFrame,
    prev_close: dict[str, Any],
    universe_name: str,
) -> pd.DataFrame:
    if equities.empty or "timestamp" not in equities.columns:
        return pd.DataFrame(columns=["timestamp", "Advance", "Decline"])

    frame = equities.copy()
    if "tradingsymbol" not in frame.columns:
        return pd.DataFrame(columns=["timestamp", "Advance", "Decline"])
    symbols = frame["tradingsymbol"].astype(str).str.strip().str.upper()
    frame = frame.loc[~symbols.isin(_INDEX_SPOT_SYMBOLS)].copy()
    if frame.empty:
        return pd.DataFrame(columns=["timestamp", "Advance", "Decline"])

    universes = build_ad_universes()
    selected_symbols = universes.get(universe_name)
    if selected_symbols:
        symbols = frame["tradingsymbol"].astype(str).str.strip().str.upper()
        frame = frame.loc[symbols.isin(selected_symbols)].copy()

    frame["instrument_token"] = pd.to_numeric(frame["instrument_token"], errors="coerce")
    frame["close"] = pd.to_numeric(frame["close"], errors="coerce")
    frame = frame.dropna(subset=["timestamp", "instrument_token", "close"]).sort_values("timestamp")
    if frame.empty:
        return pd.DataFrame(columns=["timestamp", "Advance", "Decline"])

    rows = []
    for timestamp, group in frame.groupby("timestamp", sort=True):
        advances, declines = _score_group(group, prev_close)
        rows.append({"timestamp": timestamp, "Advance": advances, "Decline": declines})
    return pd.DataFrame(rows)


def option_chain_frame(pcr_snapshot: dict[str, Any], underlying: str | None) -> pd.DataFrame:
    if not underlying:
        return pd.DataFrame()
    option_chain = pcr_snapshot.get("option_chain", {})
    if not isinstance(option_chain, dict):
        return pd.DataFrame()
    rows = option_chain.get(underlying, [])
    if not isinstance(rows, list) or not rows:
        return pd.DataFrame()
    frame = pd.DataFrame(rows)
    if "strike" in frame.columns:
        frame["strike"] = pd.to_numeric(frame["strike"], errors="coerce")
    for column in ["ce_oi", "pe_oi", "ce_ltp", "pe_ltp", "ce_volume", "pe_volume", "strike_pcr"]:
        if column in frame.columns:
            frame[column] = pd.to_numeric(frame[column], errors="coerce").fillna(0)
    return frame.dropna(subset=["strike"]).sort_values("strike")


def option_baseline_frame(options: pd.DataFrame, underlying: str | None) -> pd.DataFrame:
    if options.empty or not underlying:
        return pd.DataFrame()
    frame = options.copy()
    frame["tradingsymbol"] = frame["tradingsymbol"].astype(str).str.upper().str.strip()
    frame["option_type"] = frame["option_type"].astype(str).str.upper().str.strip()
    if underlying == "NIFTY":
        frame = frame[
            frame["tradingsymbol"].str.startswith("NIFTY")
            & ~frame["tradingsymbol"].str.startswith("BANKNIFTY")
        ].copy()
    else:
        frame = frame[frame["tradingsymbol"].str.startswith("BANKNIFTY")].copy()
    if frame.empty:
        return frame
    frame["oi"] = pd.to_numeric(frame["oi"], errors="coerce").fillna(0)
    frame["strike"] = pd.to_numeric(frame["strike"], errors="coerce")
    frame = frame.dropna(subset=["timestamp", "strike"]).sort_values("timestamp")
    first = frame.groupby("tradingsymbol", sort=False).head(1)[["tradingsymbol", "oi"]]
    first = first.rename(columns={"oi": "open_oi"})
    return first


def enrich_option_chain_with_oi_change(chain: pd.DataFrame, baseline: pd.DataFrame) -> pd.DataFrame:
    if chain.empty:
        return chain
    result = chain.copy()
    baseline_map = {}
    if not baseline.empty:
        baseline_map = dict(zip(baseline["tradingsymbol"], baseline["open_oi"]))

    def pct_change(symbol: str, current: float) -> float | None:
        base = baseline_map.get(str(symbol))
        if base is None or float(base) <= 0:
            return None
        return round(((float(current) - float(base)) / float(base)) * 100, 2)

    result["ce_oi_change_pct"] = [
        pct_change(symbol, oi)
        for symbol, oi in zip(result.get("ce_symbol", []), result.get("ce_oi", []))
    ]
    result["pe_oi_change_pct"] = [
        pct_change(symbol, oi)
        for symbol, oi in zip(result.get("pe_symbol", []), result.get("pe_oi", []))
    ]
    return result


def atm_straddle_series(options: pd.DataFrame, underlying: str | None, atm_strike: int | float | None) -> pd.DataFrame:
    if options.empty or not underlying or atm_strike is None:
        return pd.DataFrame(columns=["timestamp", "Straddle"])
    frame = options.copy()
    frame["tradingsymbol"] = frame["tradingsymbol"].astype(str).str.upper().str.strip()
    if underlying == "NIFTY":
        frame = frame[
            frame["tradingsymbol"].str.startswith("NIFTY")
            & ~frame["tradingsymbol"].str.startswith("BANKNIFTY")
        ].copy()
    else:
        frame = frame[frame["tradingsymbol"].str.startswith("BANKNIFTY")].copy()
    frame["strike"] = pd.to_numeric(frame["strike"], errors="coerce")
    frame["close"] = pd.to_numeric(frame["close"], errors="coerce")
    frame = frame[frame["strike"] == float(atm_strike)].copy()
    if frame.empty:
        return pd.DataFrame(columns=["timestamp", "Straddle"])
    pivot = frame.pivot_table(index="timestamp", columns="option_type", values="close", aggfunc="last")
    if not {"CE", "PE"}.issubset(set(pivot.columns)):
        return pd.DataFrame(columns=["timestamp", "Straddle"])
    pivot["Straddle"] = pivot["CE"] + pivot["PE"]
    return pivot.reset_index()[["timestamp", "Straddle"]].dropna()


def vix_series(vix: pd.DataFrame) -> pd.DataFrame:
    if vix.empty or not {"timestamp", "close"}.issubset(set(vix.columns)):
        return pd.DataFrame(columns=["timestamp", "IV"])
    frame = vix[["timestamp", "close"]].copy()
    frame["IV"] = pd.to_numeric(frame["close"], errors="coerce")
    return frame.dropna(subset=["timestamp", "IV"])[["timestamp", "IV"]]


__all__ = [
    "advance_decline_series",
    "atm_straddle_series",
    "enrich_option_chain_with_oi_change",
    "instrument_ohlc",
    "option_baseline_frame",
    "option_chain_frame",
    "vix_series",
]
