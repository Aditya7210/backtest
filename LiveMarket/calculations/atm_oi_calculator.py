from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd


def _empty_payload() -> dict[str, Any]:
    return {
        "generated_at": pd.Timestamp.now().isoformat(),
        "nifty_atm_strike": None,
        "nifty_atm_call_oi": 0,
        "nifty_atm_put_oi": 0,
        "banknifty_atm_strike": None,
        "banknifty_atm_call_oi": 0,
        "banknifty_atm_put_oi": 0,
    }


def _latest_underlying_price(equities_df: pd.DataFrame, symbol_candidates: list[str]) -> float | None:
    if equities_df.empty or "tradingsymbol" not in equities_df.columns:
        return None
    subset = equities_df[equities_df["tradingsymbol"].isin(symbol_candidates)]
    if subset.empty:
        return None
    return float(subset.sort_values("timestamp")["close"].iloc[-1])


def _nearest_strike(options_df: pd.DataFrame, underlying_prefix: str, price: float | None) -> float | None:
    subset = options_df[options_df["tradingsymbol"].str.startswith(underlying_prefix, na=False)]
    if subset.empty:
        return None
    strikes = sorted(set(subset["strike"].dropna().tolist()))
    if not strikes:
        return None
    if price is None:
        # Fallback to center strike if spot is unavailable.
        return float(strikes[len(strikes) // 2])
    return float(min(strikes, key=lambda x: abs(float(x) - float(price))))


def _atm_oi(options_df: pd.DataFrame, prefix: str, strike: float | None) -> tuple[int, int]:
    if strike is None:
        return 0, 0
    subset = options_df[
        options_df["tradingsymbol"].str.startswith(prefix, na=False)
        & (options_df["strike"] == strike)
    ]
    if subset.empty:
        return 0, 0
    call_oi = int(subset.loc[subset["option_type"] == "CE", "oi"].sum())
    put_oi = int(subset.loc[subset["option_type"] == "PE", "oi"].sum())
    return call_oi, put_oi


def compute(options_1min_csv: Path, equities_1min_csv: Path) -> dict[str, Any]:
    if not options_1min_csv.is_file():
        return _empty_payload()

    options_df = pd.read_csv(options_1min_csv)
    if options_df.empty:
        return _empty_payload()
    required = {"tradingsymbol", "option_type", "strike", "oi"}
    if not required.issubset(set(options_df.columns)):
        return _empty_payload()

    if "timestamp" in options_df.columns:
        options_df["timestamp"] = pd.to_datetime(options_df["timestamp"], errors="coerce")
        options_df = options_df.dropna(subset=["timestamp"]).sort_values("timestamp")
    if "instrument_token" in options_df.columns:
        token_numeric = pd.to_numeric(options_df["instrument_token"], errors="coerce")
        options_df = options_df.loc[token_numeric.notna()].copy()
        options_df["instrument_token"] = token_numeric.loc[options_df.index].astype("int64")
        options_df = options_df.groupby("instrument_token", sort=False).tail(1)

    options_df["strike"] = pd.to_numeric(options_df["strike"], errors="coerce")
    options_df["oi"] = pd.to_numeric(options_df["oi"], errors="coerce").fillna(0)
    options_df["option_type"] = options_df["option_type"].astype(str).str.upper().str.strip()
    options_df["tradingsymbol"] = options_df["tradingsymbol"].astype(str).str.upper().str.strip()

    equities_df = pd.DataFrame()
    if equities_1min_csv.is_file():
        equities_df = pd.read_csv(equities_1min_csv)
        if not equities_df.empty and {"tradingsymbol", "close", "timestamp"}.issubset(set(equities_df.columns)):
            equities_df["timestamp"] = pd.to_datetime(equities_df["timestamp"], errors="coerce")
            equities_df["close"] = pd.to_numeric(equities_df["close"], errors="coerce")
            equities_df["tradingsymbol"] = equities_df["tradingsymbol"].astype(str).str.upper().str.strip()
            equities_df = equities_df.dropna(subset=["timestamp", "close"]).sort_values("timestamp")
        else:
            equities_df = pd.DataFrame()

    nifty_spot = _latest_underlying_price(equities_df, ["NIFTY 50", "NIFTY"])
    bank_spot = _latest_underlying_price(equities_df, ["NIFTY BANK", "BANKNIFTY"])

    nifty_strike = _nearest_strike(options_df, "NIFTY", nifty_spot)
    bank_strike = _nearest_strike(options_df, "BANKNIFTY", bank_spot)

    nifty_call_oi, nifty_put_oi = _atm_oi(options_df, "NIFTY", nifty_strike)
    bank_call_oi, bank_put_oi = _atm_oi(options_df, "BANKNIFTY", bank_strike)

    return {
        "generated_at": pd.Timestamp.now().isoformat(),
        "nifty_atm_strike": int(nifty_strike) if nifty_strike is not None else None,
        "nifty_atm_call_oi": nifty_call_oi,
        "nifty_atm_put_oi": nifty_put_oi,
        "banknifty_atm_strike": int(bank_strike) if bank_strike is not None else None,
        "banknifty_atm_call_oi": bank_call_oi,
        "banknifty_atm_put_oi": bank_put_oi,
    }


__all__ = ["compute"]

