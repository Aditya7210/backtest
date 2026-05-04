"""Migrated calculation runner — reads bars from MongoDB, writes snapshots to MongoDB."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
import time
from typing import Any

import pandas as pd

from backend.database.sync_connection import get_sync_db
from backend.utils.time_utils import today_ist, now_ist_iso


_RESAMPLE_TIMEFRAMES = [3, 5, 10, 15, 30, 60]
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_UNIVERSE_FILES = {
    "NIFTY 50": _PROJECT_ROOT / "Data" / "live_market" / "universes" / "nifty50_symbols.csv",
    "NIFTY BANK": _PROJECT_ROOT / "Data" / "live_market" / "universes" / "niftybank_symbols.csv",
}


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
        return {"generated_at": now_ist_iso(), "data": {"1min": {}}, "warning": "equity bars unavailable"}

    payload: dict[str, float] = {}
    skipped_tokens = 0
    for token, token_df in equities_df.groupby("instrument_token", sort=False):
        token_df = token_df.sort_values("timestamp").copy()
        token_df["high"] = pd.to_numeric(token_df["high"], errors="coerce")
        token_df["low"] = pd.to_numeric(token_df["low"], errors="coerce")
        token_df["close"] = pd.to_numeric(token_df["close"], errors="coerce")
        token_df["volume"] = pd.to_numeric(token_df["volume"], errors="coerce")
        token_df = token_df.dropna(subset=["high", "low", "close", "volume"])
        if token_df.empty:
            skipped_tokens += 1
            continue
        token_df = token_df[token_df["volume"] > 0]
        if token_df.empty:
            skipped_tokens += 1
            continue

        typical_price = (token_df["high"] + token_df["low"] + token_df["close"]) / 3.0
        cumulative_volume = token_df["volume"].cumsum()
        if cumulative_volume.iloc[-1] <= 0:
            skipped_tokens += 1
            continue
        cumulative_value = (typical_price * token_df["volume"]).cumsum()
        vwap_series = cumulative_value / cumulative_volume
        payload[str(int(token))] = round(float(vwap_series.iloc[-1]), 4)

    warning = None
    if not payload:
        warning = "No valid volume rows for VWAP."
    elif skipped_tokens > 0:
        warning = f"Skipped {skipped_tokens} symbols with invalid/zero volume."
    return {"generated_at": now_ist_iso(), "data": {"1min": payload}, "warning": warning}


def _normalize_symbol(value: str) -> str:
    symbol = str(value or "").strip().upper()
    if not symbol:
        return ""
    for suffix in ("-EQ", "-BE", "-BZ", "-BL"):
        if symbol.endswith(suffix):
            return symbol[: -len(suffix)]
    return symbol


@lru_cache(maxsize=16)
def _load_universe_symbols(name: str) -> set[str]:
    path = _UNIVERSE_FILES.get(name)
    if path is None or not path.exists():
        return set()
    df = pd.read_csv(path, low_memory=False)
    if df.empty:
        return set()
    columns = {str(col).strip().lower(): col for col in df.columns}
    symbol_col = columns.get("symbol") or columns.get("tradingsymbol")
    if symbol_col is None:
        return set()
    symbols = {_normalize_symbol(str(v)) for v in df[symbol_col].tolist()}
    return {s for s in symbols if s}


def _compute_ad_for_universe(
    latest_df: pd.DataFrame,
    prev_close: dict[str, float],
    universe_symbols: set[str] | None,
) -> dict[str, Any]:
    advances = 0
    declines = 0
    unchanged = 0
    covered = 0
    missing_prev_close = 0
    total = 0

    for row in latest_df.itertuples(index=False):
        symbol = _normalize_symbol(getattr(row, "tradingsymbol", ""))
        if universe_symbols is not None and symbol not in universe_symbols:
            continue
        total += 1
        try:
            token_key = str(int(getattr(row, "instrument_token")))
        except Exception:
            continue
        prev = prev_close.get(token_key)
        if prev is None:
            missing_prev_close += 1
            continue
        close_value = pd.to_numeric(getattr(row, "close", None), errors="coerce")
        if not pd.notna(close_value):
            continue
        close = float(close_value)
        covered += 1
        if close > prev:
            advances += 1
        elif close < prev:
            declines += 1
        else:
            unchanged += 1

    ad_ratio = None
    ad_ratio_state = "ok"
    if covered > 0:
        if declines > 0:
            ad_ratio = round(advances / declines, 4)
        elif advances > 0:
            ad_ratio_state = "infinite"
        else:
            ad_ratio_state = "flat"
            ad_ratio = None

    warning = None
    if covered == 0:
        warning = "prev_close unavailable"
    elif missing_prev_close > 0:
        warning = f"prev_close partial coverage ({covered}/{total})"

    return {
        "advances": advances if covered > 0 else None,
        "declines": declines if covered > 0 else None,
        "unchanged": unchanged if covered > 0 else None,
        "ad_ratio": ad_ratio,
        "ad_ratio_state": ad_ratio_state,
        "covered_symbols": covered,
        "total_symbols": total,
        "missing_prev_close": missing_prev_close,
        "warning": warning,
    }


def _compute_ad_snapshot(equities_df: pd.DataFrame, prev_close: dict[str, float]) -> dict[str, Any]:
    """Compute Advance/Decline from equities bars and previous close."""
    if equities_df.empty:
        return {
            "generated_at": now_ist_iso(),
            "advances": None,
            "declines": None,
            "unchanged": None,
            "ad_ratio": None,
            "warning": "equity bars unavailable",
        }

    latest_df = equities_df.groupby("instrument_token", sort=False).tail(1).copy()
    latest_df["close"] = pd.to_numeric(latest_df["close"], errors="coerce")
    latest_df = latest_df.dropna(subset=["close"])

    all_stats = _compute_ad_for_universe(latest_df, prev_close, None)
    nifty50_stats = _compute_ad_for_universe(latest_df, prev_close, _load_universe_symbols("NIFTY 50"))
    bank_stats = _compute_ad_for_universe(latest_df, prev_close, _load_universe_symbols("NIFTY BANK"))

    return {
        "generated_at": now_ist_iso(),
        "advances": all_stats["advances"],
        "declines": all_stats["declines"],
        "unchanged": all_stats["unchanged"],
        "ad_ratio": all_stats["ad_ratio"],
        "ad_ratio_state": all_stats["ad_ratio_state"],
        "covered_symbols": all_stats["covered_symbols"],
        "total_symbols": all_stats["total_symbols"],
        "missing_prev_close": all_stats["missing_prev_close"],
        "warning": all_stats["warning"],
        "universes": {
            "ALL": all_stats,
            "NIFTY 50": nifty50_stats,
            "NIFTY BANK": bank_stats,
        },
    }


def _compute_pcr_snapshot(options_df: pd.DataFrame) -> dict[str, Any]:
    """Compute PCR from options bars."""
    if options_df.empty:
        return {
            "generated_at": now_ist_iso(),
            "nifty_pcr": None,
            "banknifty_pcr": None,
            "warning": "options data unavailable",
            "expiry_breakdown": {"NIFTY": [], "BANKNIFTY": []},
        }

    latest_df = options_df.groupby("instrument_token", sort=False).tail(1).copy()
    latest_df["underlying"] = latest_df.apply(
        lambda r: str(r.get("underlying") or _underlying_from_symbol(str(r.get("tradingsymbol") or ""))).upper(),
        axis=1,
    )
    latest_df = latest_df[latest_df["underlying"].isin(["NIFTY", "BANKNIFTY"])]
    latest_df["expiry"] = pd.to_datetime(latest_df["expiry"], errors="coerce").dt.date.astype("string")
    latest_df["oi"] = pd.to_numeric(latest_df["oi"], errors="coerce").fillna(0)
    latest_df["option_type"] = latest_df["option_type"].astype(str).str.upper()

    def _build_breakdown(df: pd.DataFrame, underlying: str) -> list[dict[str, Any]]:
        subset = df[df["underlying"] == underlying]
        if subset.empty:
            return []
        rows: list[dict[str, Any]] = []
        for expiry, part in subset.groupby("expiry", sort=True):
            ce_oi = float(part.loc[part["option_type"] == "CE", "oi"].sum())
            pe_oi = float(part.loc[part["option_type"] == "PE", "oi"].sum())
            strike_pcr = round(pe_oi / ce_oi, 4) if ce_oi > 0 else None
            warning = None if ce_oi > 0 else "call_oi_zero"
            rows.append(
                {
                    "expiry": str(expiry),
                    "call_oi": int(ce_oi),
                    "put_oi": int(pe_oi),
                    "pcr": strike_pcr,
                    "warning": warning,
                }
            )
        return rows

    nifty_breakdown = _build_breakdown(latest_df, "NIFTY")
    bank_breakdown = _build_breakdown(latest_df, "BANKNIFTY")

    def _pick_primary(breakdown: list[dict[str, Any]]) -> dict[str, Any]:
        if not breakdown:
            return {"pcr": None, "calls": 0, "puts": 0, "expiry": None, "warning": "no_expiry_data"}
        first = breakdown[0]
        return {
            "pcr": first.get("pcr"),
            "calls": int(first.get("call_oi") or 0),
            "puts": int(first.get("put_oi") or 0),
            "expiry": first.get("expiry"),
            "warning": first.get("warning"),
        }

    nifty = _pick_primary(nifty_breakdown)
    bank = _pick_primary(bank_breakdown)

    chain = _latest_option_chain_by_underlying(options_df)
    warnings: list[str] = []
    if nifty.get("warning"):
        warnings.append(f"NIFTY: {nifty['warning']}")
    if bank.get("warning"):
        warnings.append(f"BANKNIFTY: {bank['warning']}")

    return {
        "generated_at": now_ist_iso(),
        "nifty_pcr": nifty["pcr"],
        "banknifty_pcr": bank["pcr"],
        "nifty_call_oi": nifty["calls"],
        "nifty_put_oi": nifty["puts"],
        "banknifty_call_oi": bank["calls"],
        "banknifty_put_oi": bank["puts"],
        "nifty_primary_expiry": nifty.get("expiry"),
        "banknifty_primary_expiry": bank.get("expiry"),
        "expiry_breakdown": {"NIFTY": nifty_breakdown, "BANKNIFTY": bank_breakdown},
        "option_chain": chain,
        "warning": ", ".join(warnings) if warnings else None,
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
    def _extract(raw_doc: dict[str, Any] | None) -> dict[str, float]:
        if not isinstance(raw_doc, dict):
            return {}
        raw = raw_doc.get("data", {})
        if isinstance(raw, dict) and isinstance(raw.get("data"), dict):
            raw = raw.get("data")
        if not isinstance(raw, dict):
            return {}
        out: dict[str, float] = {}
        for key, value in raw.items():
            try:
                out[str(key)] = float(value)
            except Exception:
                continue
        return out

    db = get_sync_db()
    doc = db.snapshots.find_one({"snapshot_type": "prev_close", "trading_date": trading_date})
    extracted = _extract(doc)
    if extracted:
        return extracted
    fallback = db.snapshots.find_one({"snapshot_type": "prev_close"}, sort=[("trading_date", -1)])
    return _extract(fallback)


def _latest_previous_closes(tokens: list[int], trading_date: str) -> dict[str, float]:
    if not tokens:
        return {}
    db = get_sync_db()
    cursor = db.bars.aggregate(
        [
            {
                "$match": {
                    "instrument_token": {"$in": tokens},
                    "timeframe": "1min",
                    "trading_date": {"$lt": trading_date},
                    "instrument_type": {"$in": ["equity", "index"]},
                }
            },
            {"$sort": {"instrument_token": 1, "trading_date": -1, "timestamp": -1}},
            {
                "$group": {
                    "_id": "$instrument_token",
                    "close": {"$first": "$close"},
                    "source_trading_date": {"$first": "$trading_date"},
                }
            },
        ]
    )
    out: dict[str, float] = {}
    for row in cursor:
        try:
            out[str(int(row["_id"]))] = float(row["close"])
        except Exception:
            continue
    return out


def _build_prev_close_snapshot(equities_df: pd.DataFrame, trading_date: str) -> tuple[dict[str, Any], dict[str, float]]:
    if equities_df.empty:
        payload = {
            "generated_at": now_ist_iso(),
            "data": {},
            "coverage": {"expected_tokens": 0, "resolved_tokens": 0, "missing_tokens": 0},
            "warning": "equity bars unavailable",
        }
        return payload, {}

    latest_df = equities_df.groupby("instrument_token", sort=False).tail(1).copy()
    expected_tokens = [int(x) for x in latest_df["instrument_token"].tolist() if pd.notna(x)]
    existing = _load_prev_close(trading_date)
    historical = _latest_previous_closes(expected_tokens, trading_date)
    merged: dict[str, float] = {}
    for token in expected_tokens:
        key = str(token)
        if key in historical:
            merged[key] = historical[key]
        elif key in existing:
            merged[key] = existing[key]

    missing = max(0, len(set(expected_tokens)) - len(merged))
    warning = None
    if not merged:
        warning = "prev_close unavailable"
    elif missing > 0:
        warning = f"prev_close partial coverage ({len(merged)}/{len(set(expected_tokens))})"

    payload = {
        "generated_at": now_ist_iso(),
        "data": merged,
        "coverage": {
            "expected_tokens": len(set(expected_tokens)),
            "resolved_tokens": len(merged),
            "missing_tokens": missing,
        },
        "warning": warning,
    }
    return payload, merged


def _underlying_from_symbol(symbol: str) -> str:
    value = str(symbol or "").strip().upper()
    if value.startswith("BANKNIFTY"):
        return "BANKNIFTY"
    if value.startswith("NIFTY") and not value.startswith("BANKNIFTY"):
        return "NIFTY"
    return ""


def _latest_option_chain_by_underlying(options_df: pd.DataFrame) -> dict[str, list[dict[str, Any]]]:
    if options_df.empty:
        return {"NIFTY": [], "BANKNIFTY": []}

    latest_df = options_df.groupby("instrument_token", sort=False).tail(1).copy()
    latest_df["underlying"] = latest_df["tradingsymbol"].astype(str).map(_underlying_from_symbol)
    latest_df = latest_df[latest_df["underlying"].isin(["NIFTY", "BANKNIFTY"])]
    if latest_df.empty:
        return {"NIFTY": [], "BANKNIFTY": []}

    latest_df["strike"] = pd.to_numeric(latest_df["strike"], errors="coerce")
    latest_df["close"] = pd.to_numeric(latest_df["close"], errors="coerce")
    latest_df["oi"] = pd.to_numeric(latest_df["oi"], errors="coerce").fillna(0)
    latest_df = latest_df.dropna(subset=["strike"])

    latest_df["expiry"] = pd.to_datetime(latest_df["expiry"], errors="coerce").dt.date

    rows: dict[str, dict[tuple[str, float], dict[str, Any]]] = {"NIFTY": {}, "BANKNIFTY": {}}
    for row in latest_df.itertuples(index=False):
        underlying = str(getattr(row, "underlying", "")).strip().upper()
        strike = float(getattr(row, "strike", 0.0))
        expiry_obj = getattr(row, "expiry", None)
        expiry = expiry_obj.isoformat() if hasattr(expiry_obj, "isoformat") else ""
        side = str(getattr(row, "option_type", "")).strip().upper()
        if underlying not in rows or side not in {"CE", "PE"} or not expiry:
            continue
        key = (expiry, strike)
        bucket = rows[underlying].setdefault(
            key,
            {
                "underlying": underlying,
                "expiry": expiry,
                "strike": strike,
                "ce_ltp": None,
                "ce_oi": 0.0,
                "pe_ltp": None,
                "pe_oi": 0.0,
                "strike_pcr": None,
            },
        )
        if side == "CE":
            bucket["ce_ltp"] = float(getattr(row, "close", 0.0) or 0.0)
            bucket["ce_oi"] = float(getattr(row, "oi", 0.0) or 0.0)
        else:
            bucket["pe_ltp"] = float(getattr(row, "close", 0.0) or 0.0)
            bucket["pe_oi"] = float(getattr(row, "oi", 0.0) or 0.0)

    chain: dict[str, list[dict[str, Any]]] = {"NIFTY": [], "BANKNIFTY": []}
    for underlying in ("NIFTY", "BANKNIFTY"):
        strike_rows: list[dict[str, Any]] = []
        for key in sorted(rows[underlying].keys(), key=lambda x: (x[0], x[1])):
            row = dict(rows[underlying][key])
            ce_oi = float(row.get("ce_oi", 0.0) or 0.0)
            pe_oi = float(row.get("pe_oi", 0.0) or 0.0)
            row["strike_pcr"] = round(pe_oi / ce_oi, 4) if ce_oi > 0 else None
            strike_rows.append(row)
        chain[underlying] = strike_rows
    return chain


def _spot_from_equities(equities_df: pd.DataFrame) -> dict[str, float]:
    if equities_df.empty:
        return {}
    latest_df = equities_df.groupby("instrument_token", sort=False).tail(1).copy()
    mapping: dict[str, float] = {}
    for row in latest_df.itertuples(index=False):
        symbol = str(getattr(row, "tradingsymbol", "")).strip().upper()
        close = pd.to_numeric(getattr(row, "close", None), errors="coerce")
        if not pd.notna(close):
            continue
        if symbol in {"NIFTY 50", "NIFTY"}:
            mapping["NIFTY"] = float(close)
        elif symbol in {"NIFTY BANK", "BANKNIFTY"}:
            mapping["BANKNIFTY"] = float(close)
    return mapping


def _closest_atm_strike(strikes: list[float], spot: float | None) -> float | None:
    if not strikes:
        return None
    if spot is None:
        return None
    return min(strikes, key=lambda v: abs(v - float(spot)))


def _compute_atm_oi_snapshot(options_df: pd.DataFrame, equities_df: pd.DataFrame) -> dict[str, Any]:
    chain = _latest_option_chain_by_underlying(options_df)
    spots = _spot_from_equities(equities_df)

    def _primary_expiry(rows: list[dict[str, Any]]) -> str | None:
        expiries = sorted({str(r.get("expiry") or "") for r in rows if r.get("expiry")})
        return expiries[0] if expiries else None

    nifty_expiry = _primary_expiry(chain.get("NIFTY", []))
    bank_expiry = _primary_expiry(chain.get("BANKNIFTY", []))
    nifty_rows = [r for r in chain.get("NIFTY", []) if not nifty_expiry or r.get("expiry") == nifty_expiry]
    bank_rows = [r for r in chain.get("BANKNIFTY", []) if not bank_expiry or r.get("expiry") == bank_expiry]
    nifty_strikes = [float(row["strike"]) for row in nifty_rows]
    bank_strikes = [float(row["strike"]) for row in bank_rows]
    nifty_atm = _closest_atm_strike(nifty_strikes, spots.get("NIFTY"))
    bank_atm = _closest_atm_strike(bank_strikes, spots.get("BANKNIFTY"))
    warnings: list[str] = []
    if spots.get("NIFTY") is None:
        warnings.append("NIFTY spot unavailable")
    if spots.get("BANKNIFTY") is None:
        warnings.append("BANKNIFTY spot unavailable")
    if nifty_expiry is None:
        warnings.append("NIFTY option expiry unavailable")
    if bank_expiry is None:
        warnings.append("BANKNIFTY option expiry unavailable")

    return {
        "generated_at": now_ist_iso(),
        "nifty_spot": spots.get("NIFTY"),
        "banknifty_spot": spots.get("BANKNIFTY"),
        "nifty_atm_strike": nifty_atm,
        "banknifty_atm_strike": bank_atm,
        "nifty_primary_expiry": nifty_expiry,
        "banknifty_primary_expiry": bank_expiry,
        "option_chain": chain,
        "warning": ", ".join(warnings) if warnings else (None if (chain.get("NIFTY") or chain.get("BANKNIFTY")) else "options data unavailable"),
    }


def _update_calculator_status(
    *,
    status: str,
    trading_date: str,
    last_error: str | None = None,
    snapshots_written: list[str] | None = None,
) -> None:
    db = get_sync_db()
    db.collector_status.update_one(
        {"_id": "singleton"},
        {"$set": {
            "calculator.status": status,
            "calculator.heartbeat_at": now_ist_iso(),
            "calculator.last_cycle_at": now_ist_iso(),
            "calculator.trading_date": trading_date,
            "calculator.snapshots_written": list(snapshots_written or []),
            "calculator.last_error": last_error,
        }},
        upsert=True,
    )


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
    prev_close_payload, prev_close = _build_prev_close_snapshot(equities_df, trading_date)

    has_equity_bars = not equities_df.empty
    if not has_equity_bars:
        print("[runner] No equity bars - skipping VWAP and A/D")

    pcr_snapshot = _compute_pcr_snapshot(options_df)
    atm_oi_snapshot = _compute_atm_oi_snapshot(options_df, equities_df)
    vix_snapshot = _compute_vix_snapshot(vix_df)

    _write_snapshot("prev_close", trading_date, prev_close_payload)
    if has_equity_bars:
        vwap_snapshot = _compute_vwap_snapshot(equities_df)
        ad_snapshot = _compute_ad_snapshot(equities_df, prev_close)
        _write_snapshot("vwap", trading_date, vwap_snapshot)
        _write_snapshot("ad", trading_date, ad_snapshot)
    _write_snapshot("pcr", trading_date, pcr_snapshot)
    _write_snapshot("atm_oi", trading_date, atm_oi_snapshot)
    _write_snapshot("vix", trading_date, vix_snapshot)
    snapshots_written = ["prev_close", "pcr", "atm_oi", "vix"]
    if has_equity_bars:
        snapshots_written = ["vwap", "prev_close", "ad", "pcr", "atm_oi", "vix"]

    return {
        "status": "ok",
        "trading_date": trading_date,
        "generated_at": now_ist_iso(),
        "snapshots_written": snapshots_written,
    }


def start_loop(interval_seconds: float = 10.0) -> None:
    """Run calculation loop."""
    wait = max(5.0, float(interval_seconds))
    print(f"[calculation_runner] started interval={wait:.1f}s")
    trading_date = today_ist().isoformat()
    _update_calculator_status(status="running", trading_date=trading_date, last_error=None, snapshots_written=[])
    while True:
        started_at = time.time()
        try:
            result = run_once()
            _update_calculator_status(
                status="running",
                trading_date=str(result.get("trading_date") or today_ist().isoformat()),
                last_error=None,
                snapshots_written=list(result.get("snapshots_written") or []),
            )
            print(f"[calculation_runner] cycle: {result}")
        except KeyboardInterrupt:
            _update_calculator_status(status="stopped", trading_date=today_ist().isoformat(), last_error=None, snapshots_written=[])
            raise
        except Exception as exc:
            _update_calculator_status(
                status="running",
                trading_date=today_ist().isoformat(),
                last_error=f"{type(exc).__name__}: {exc}",
                snapshots_written=[],
            )
            print(f"[calculation_runner] failed: {type(exc).__name__}: {exc}")
        elapsed = time.time() - started_at
        sleep_time = max(0.0, wait - elapsed)
        if sleep_time > 0:
            time.sleep(sleep_time)
