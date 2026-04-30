from __future__ import annotations

from pathlib import Path
import time
from typing import Any

import pandas as pd

from LiveMarket.time_utils import now_ist_iso

QUOTE_BATCH_SIZE = 400


def _empty_payload() -> dict[str, float | int | str | None]:
    return {
        "generated_at": now_ist_iso(),
        "nifty_pcr": 0.0,
        "banknifty_pcr": 0.0,
        "nifty_call_oi": 0,
        "nifty_put_oi": 0,
        "nifty_contracts": 0,
        "nifty_expiry": None,
        "nifty_strike_min": None,
        "nifty_strike_max": None,
        "banknifty_call_oi": 0,
        "banknifty_put_oi": 0,
        "banknifty_contracts": 0,
        "banknifty_expiry": None,
        "banknifty_strike_min": None,
        "banknifty_strike_max": None,
        "total_call_oi": 0,
        "total_put_oi": 0,
        "scope": "latest row per subscribed option contract",
        "source": "empty",
    }


def _compute_underlying_pcr(df: pd.DataFrame, prefix: str) -> dict[str, float | int | str | None]:
    if prefix == "NIFTY":
        subset = df[
            df["tradingsymbol"].str.startswith("NIFTY", na=False)
            & ~df["tradingsymbol"].str.startswith("BANKNIFTY", na=False)
        ]
    else:
        subset = df[df["tradingsymbol"].str.startswith("BANKNIFTY", na=False)]
    if subset.empty:
        return {
            "pcr": 0.0,
            "calls": 0,
            "puts": 0,
            "contracts": 0,
            "expiry": None,
            "strike_min": None,
            "strike_max": None,
        }
    calls = int(subset.loc[subset["option_type"] == "CE", "oi"].sum())
    puts = int(subset.loc[subset["option_type"] == "PE", "oi"].sum())
    pcr = round((puts / calls), 4) if calls > 0 else 0.0
    expiry = None
    if "expiry" in subset.columns:
        expiries = sorted(set(subset["expiry"].dropna().astype(str).tolist()))
        expiry = expiries[0] if expiries else None
    strike_min = None
    strike_max = None
    if "strike" in subset.columns:
        strikes = pd.to_numeric(subset["strike"], errors="coerce").dropna()
        if not strikes.empty:
            strike_min = int(strikes.min())
            strike_max = int(strikes.max())
    return {
        "pcr": pcr,
        "calls": calls,
        "puts": puts,
        "contracts": int(len(subset)),
        "expiry": expiry,
        "strike_min": strike_min,
        "strike_max": strike_max,
    }


def _underlying_subset(df: pd.DataFrame, underlying: str) -> pd.DataFrame:
    if underlying == "NIFTY":
        return df[
            df["tradingsymbol"].str.startswith("NIFTY", na=False)
            & ~df["tradingsymbol"].str.startswith("BANKNIFTY", na=False)
        ]
    return df[df["tradingsymbol"].str.startswith("BANKNIFTY", na=False)]


def _build_option_chain_payload(df: pd.DataFrame) -> dict[str, list[dict[str, Any]]]:
    chains: dict[str, list[dict[str, Any]]] = {}
    for underlying in ("NIFTY", "BANKNIFTY"):
        subset = _underlying_subset(df, underlying)
        if subset.empty:
            chains[underlying] = []
            continue

        rows: list[dict[str, Any]] = []
        for strike, strike_group in subset.groupby("strike", sort=True):
            ce = strike_group[strike_group["option_type"] == "CE"]
            pe = strike_group[strike_group["option_type"] == "PE"]
            ce_row = ce.iloc[0].to_dict() if not ce.empty else {}
            pe_row = pe.iloc[0].to_dict() if not pe.empty else {}
            ce_oi = int(ce_row.get("oi") or 0)
            pe_oi = int(pe_row.get("oi") or 0)
            rows.append(
                {
                    "strike": int(float(strike)),
                    "expiry": str(ce_row.get("expiry") or pe_row.get("expiry") or ""),
                    "ce_symbol": str(ce_row.get("tradingsymbol") or ""),
                    "ce_ltp": float(ce_row.get("ltp") or 0.0),
                    "ce_oi": ce_oi,
                    "ce_volume": int(ce_row.get("volume") or 0),
                    "pe_symbol": str(pe_row.get("tradingsymbol") or ""),
                    "pe_ltp": float(pe_row.get("ltp") or 0.0),
                    "pe_oi": pe_oi,
                    "pe_volume": int(pe_row.get("volume") or 0),
                    "strike_pcr": round((pe_oi / ce_oi), 4) if ce_oi > 0 else 0.0,
                }
            )
        chains[underlying] = rows
    return chains


def _build_payload(
    *,
    nifty: dict[str, float | int | str | None],
    bank: dict[str, float | int | str | None],
    scope: str,
    source: str,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "generated_at": now_ist_iso(),
        "nifty_pcr": nifty["pcr"],
        "banknifty_pcr": bank["pcr"],
        "nifty_call_oi": nifty["calls"],
        "nifty_put_oi": nifty["puts"],
        "nifty_contracts": nifty["contracts"],
        "nifty_expiry": nifty["expiry"],
        "nifty_strike_min": nifty["strike_min"],
        "nifty_strike_max": nifty["strike_max"],
        "banknifty_call_oi": bank["calls"],
        "banknifty_put_oi": bank["puts"],
        "banknifty_contracts": bank["contracts"],
        "banknifty_expiry": bank["expiry"],
        "banknifty_strike_min": bank["strike_min"],
        "banknifty_strike_max": bank["strike_max"],
        "total_call_oi": int(nifty["calls"] + bank["calls"]),
        "total_put_oi": int(nifty["puts"] + bank["puts"]),
        "scope": scope,
        "source": source,
    }
    if extra:
        payload.update(extra)
    return payload


def compute(options_1min_csv: Path) -> dict[str, Any]:
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
    if "strike" in df.columns:
        df["strike"] = pd.to_numeric(df["strike"], errors="coerce")
    if "close" in df.columns:
        df["ltp"] = pd.to_numeric(df["close"], errors="coerce").fillna(0)
    if "volume" in df.columns:
        df["volume"] = pd.to_numeric(df["volume"], errors="coerce").fillna(0).astype("int64")
    else:
        df["volume"] = 0

    nifty = _compute_underlying_pcr(df, "NIFTY")
    bank = _compute_underlying_pcr(df, "BANKNIFTY")

    return _build_payload(
        nifty=nifty,
        bank=bank,
        scope="latest row per subscribed option contract",
        source="options_1min_csv",
        extra={"option_chain": _build_option_chain_payload(df)},
    )


def compute_from_quotes(
    *,
    kite_client: Any,
    options_meta: dict[int, dict[str, Any]],
    option_symbol_by_token: dict[int, str],
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    keys_by_symbol = {
        str(symbol).strip().upper(): f"NFO:{str(symbol).strip().upper()}"
        for symbol in option_symbol_by_token.values()
        if str(symbol).strip()
    }
    keys = list(keys_by_symbol.values())
    quoted: dict[str, Any] = {}

    for start in range(0, len(keys), QUOTE_BATCH_SIZE):
        batch = keys[start : start + QUOTE_BATCH_SIZE]
        response = kite_client.quote(batch)
        if isinstance(response, dict):
            quoted.update(response)
        time.sleep(0.25)

    for token, meta in options_meta.items():
        symbol = str(meta.get("tradingsymbol") or option_symbol_by_token.get(token) or "").strip().upper()
        if not symbol:
            continue
        payload = quoted.get(f"NFO:{symbol}", {})
        if not isinstance(payload, dict):
            payload = {}
        try:
            oi = int(payload.get("oi") or 0)
        except (TypeError, ValueError):
            oi = 0
        try:
            ltp = float(payload.get("last_price") or 0.0)
        except (TypeError, ValueError):
            ltp = 0.0
        try:
            volume = int(payload.get("volume_traded") or payload.get("volume") or 0)
        except (TypeError, ValueError):
            volume = 0
        rows.append(
            {
                "tradingsymbol": symbol,
                "option_type": str(meta.get("option_type") or "").strip().upper(),
                "expiry": str(meta.get("expiry") or ""),
                "strike": float(meta.get("strike") or 0.0),
                "oi": oi,
                "ltp": ltp,
                "volume": volume,
            }
        )

    if not rows:
        payload = _empty_payload()
        payload["source"] = "zerodha_quote_snapshot_empty"
        return payload

    df = pd.DataFrame(rows)
    nifty = _compute_underlying_pcr(df, "NIFTY")
    bank = _compute_underlying_pcr(df, "BANKNIFTY")
    return _build_payload(
        nifty=nifty,
        bank=bank,
        scope="Zerodha quote snapshot for full selected option chain",
        source="zerodha_quote_snapshot",
        extra={
            "quote_contracts_requested": len(keys),
            "quote_contracts_received": len(quoted),
            "option_chain": _build_option_chain_payload(df),
        },
    )


__all__ = ["compute", "compute_from_quotes"]
