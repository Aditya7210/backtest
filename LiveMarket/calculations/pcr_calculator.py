from __future__ import annotations

from pathlib import Path

import pandas as pd


def _empty_payload() -> dict[str, float | int | str]:
    return {
        "generated_at": pd.Timestamp.now().isoformat(),
        "nifty_pcr": 0.0,
        "banknifty_pcr": 0.0,
        "total_call_oi": 0,
        "total_put_oi": 0,
    }


def _compute_underlying_pcr(df: pd.DataFrame, prefix: str) -> tuple[float, int, int]:
    if prefix == "NIFTY":
        subset = df[
            df["tradingsymbol"].str.startswith("NIFTY", na=False)
            & ~df["tradingsymbol"].str.startswith("BANKNIFTY", na=False)
        ]
    else:
        subset = df[df["tradingsymbol"].str.startswith("BANKNIFTY", na=False)]
    if subset.empty:
        return 0.0, 0, 0
    calls = int(subset.loc[subset["option_type"] == "CE", "oi"].sum())
    puts = int(subset.loc[subset["option_type"] == "PE", "oi"].sum())
    pcr = round((puts / calls), 4) if calls > 0 else 0.0
    return pcr, calls, puts


def compute(options_1min_csv: Path) -> dict[str, float | int | str]:
    if not options_1min_csv.is_file():
        return _empty_payload()
    df = pd.read_csv(options_1min_csv)
    if df.empty:
        return _empty_payload()
    required = {"tradingsymbol", "option_type", "oi"}
    if not required.issubset(set(df.columns)):
        return _empty_payload()

    if "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
        df = df.dropna(subset=["timestamp"]).sort_values("timestamp")
    if "instrument_token" in df.columns:
        token_numeric = pd.to_numeric(df["instrument_token"], errors="coerce")
        df = df.loc[token_numeric.notna()].copy()
        df["instrument_token"] = token_numeric.loc[df.index].astype("int64")
        df = df.groupby("instrument_token", sort=False).tail(1)

    df["option_type"] = df["option_type"].astype(str).str.upper().str.strip()
    df["tradingsymbol"] = df["tradingsymbol"].astype(str).str.upper().str.strip()
    df["oi"] = pd.to_numeric(df["oi"], errors="coerce").fillna(0)

    nifty_pcr, nifty_calls, nifty_puts = _compute_underlying_pcr(df, "NIFTY")
    bank_pcr, bank_calls, bank_puts = _compute_underlying_pcr(df, "BANKNIFTY")

    return {
        "generated_at": pd.Timestamp.now().isoformat(),
        "nifty_pcr": nifty_pcr,
        "banknifty_pcr": bank_pcr,
        "total_call_oi": int(nifty_calls + bank_calls),
        "total_put_oi": int(nifty_puts + bank_puts),
    }


__all__ = ["compute"]

