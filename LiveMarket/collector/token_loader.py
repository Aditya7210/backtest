from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

from LiveMarket import PROJECT_ROOT


def resolve_default_instruments_path() -> Path:
    return (
        PROJECT_ROOT
        / "Data"
        / "instrument_mapper_data"
        / "zerodha_instruments_latest.csv"
    )


def _coerce_token_series(series: pd.Series) -> pd.Series:
    coerced = pd.to_numeric(series, errors="coerce").dropna()
    return coerced.astype("int64")


def _normalize_str_column(df: pd.DataFrame, column: str) -> pd.Series:
    if column not in df.columns:
        return pd.Series([], dtype="object")
    return df[column].astype(str).str.strip()


def load_all_tokens(instruments_csv_path: str | Path | None = None) -> dict[str, Any]:
    csv_path = (
        Path(instruments_csv_path).resolve()
        if instruments_csv_path is not None
        else resolve_default_instruments_path().resolve()
    )
    if not csv_path.is_file():
        raise FileNotFoundError(f"Instruments CSV not found: {csv_path}")

    df = pd.read_csv(csv_path, low_memory=False)
    required = {
        "instrument_token",
        "segment",
        "instrument_type",
        "tradingsymbol",
        "expiry",
        "strike",
        "exchange",
    }
    missing = sorted(required - set(df.columns))
    if missing:
        raise ValueError(f"Instruments CSV missing required columns: {missing}")

    segment = _normalize_str_column(df, "segment").str.upper()
    instrument_type = _normalize_str_column(df, "instrument_type").str.upper()
    exchange = _normalize_str_column(df, "exchange").str.upper()
    tradingsymbol = _normalize_str_column(df, "tradingsymbol").str.upper()

    equity_mask = (segment == "NSE") & (instrument_type == "EQ")
    if not bool(equity_mask.any()):
        # Fallback for some datasets where equity rows are tagged by exchange.
        equity_mask = (exchange == "NSE") & (instrument_type == "EQ")
    equity_df = df.loc[equity_mask].copy()
    equity_df["instrument_token"] = _coerce_token_series(equity_df["instrument_token"])
    equity_df = equity_df.dropna(subset=["tradingsymbol"])

    equity_tokens = {int(token) for token in equity_df["instrument_token"].tolist()}
    equity_symbol_by_token = {
        int(row.instrument_token): str(row.tradingsymbol).strip().upper()
        for row in equity_df.itertuples(index=False)
        if str(row.tradingsymbol).strip()
    }

    vix_mask = tradingsymbol.isin({"INDIA VIX", "INDIAVIX"})
    vix_df = df.loc[vix_mask].copy()
    vix_token: int | None = None
    if not vix_df.empty:
        token_series = _coerce_token_series(vix_df["instrument_token"])
        if not token_series.empty:
            vix_token = int(token_series.iloc[0])
    else:
        print("[token_loader] WARNING: INDIA VIX token not found in instruments CSV.")

    options_mask = (
        (exchange == "NFO")
        & instrument_type.isin(["CE", "PE"])
    )
    options_df = df.loc[options_mask].copy()
    options_df["expiry"] = pd.to_datetime(options_df["expiry"], errors="coerce").dt.date
    today = date.today()
    max_day = today + timedelta(days=14)
    options_df = options_df[
        options_df["expiry"].notna()
        & (options_df["expiry"] >= today)
        & (options_df["expiry"] <= max_day)
    ]

    unique_expiries = sorted(set(options_df["expiry"].tolist()))
    if unique_expiries:
        nearest_two = set(unique_expiries[:2])
        options_df = options_df[options_df["expiry"].isin(nearest_two)]
    else:
        print("[token_loader] WARNING: No near-term option expiries found in next 14 days.")

    token_numeric = _coerce_token_series(options_df["instrument_token"])
    options_df = options_df.loc[token_numeric.index].copy()
    options_df["instrument_token"] = token_numeric

    options_tokens = {int(token) for token in options_df["instrument_token"].tolist()}
    options_meta: dict[int, dict[str, Any]] = {}
    option_symbol_by_token: dict[int, str] = {}
    for row in options_df.itertuples(index=False):
        token = int(row.instrument_token)
        expiry_value = row.expiry.isoformat() if isinstance(row.expiry, date) else ""
        strike_value = float(pd.to_numeric(row.strike, errors="coerce") or 0.0)
        option_type = str(row.instrument_type).strip().upper()
        symbol = str(row.tradingsymbol).strip().upper()
        options_meta[token] = {
            "strike": strike_value,
            "expiry": expiry_value,
            "option_type": option_type,
            "tradingsymbol": symbol,
        }
        option_symbol_by_token[token] = symbol

    token_to_symbol: dict[int, str] = dict(equity_symbol_by_token)
    token_to_symbol.update(option_symbol_by_token)
    if vix_token is not None:
        token_to_symbol.setdefault(vix_token, "INDIA VIX")

    print(f"[token_loader] NSE equity tokens: {len(equity_tokens)}")
    print(f"[token_loader] NFO options tokens: {len(options_tokens)}")
    print(f"[token_loader] VIX token: {vix_token}")

    return {
        "equity_tokens": equity_tokens,
        "equity_symbol_by_token": equity_symbol_by_token,
        "options_tokens": options_tokens,
        "options_meta": options_meta,
        "option_symbol_by_token": option_symbol_by_token,
        "token_to_symbol": token_to_symbol,
        "vix_token": vix_token,
    }


__all__ = ["load_all_tokens", "resolve_default_instruments_path"]

