from __future__ import annotations

from datetime import date, timedelta
import os
from pathlib import Path
from typing import Any

import pandas as pd
import requests

from LiveMarket import PROJECT_ROOT
from LiveMarket.time_utils import today_ist


# Collection universe controls.
COLLECT_EQUITIES = True
COLLECT_OPTIONS = True
COLLECT_VIX = True
COLLECT_INDEX_SPOT_TOKENS = True
EQUITY_UNIVERSE = "NIFTY500_PLUS_FNO"
EQUITY_UNIVERSE_PATH = (
    PROJECT_ROOT
    / "Data"
    / "live_market"
    / "universes"
    / "nifty500_symbols.csv"
)
NIFTY500_CONSTITUENTS_URL = (
    "https://www.niftyindices.com/IndexConstituent/ind_nifty500list.csv"
)

# Only these option underlyings are retained.
OPTION_UNDERLYINGS = {"NIFTY", "BANKNIFTY"}

# Number of nearest expiries to include per underlying.
EXPIRY_COUNT = 1

# Keep CE/PE strikes around ATM. Set to 0 to collect the full selected expiry chain.
STRIKES_AROUND_ATM = 0

# Optional index spot tokens used to estimate ATM strikes.
INDEX_SPOT_SYMBOLS = ("NIFTY 50", "NIFTY BANK", "NIFTY", "BANKNIFTY")
INDEX_DERIVATIVE_UNDERLYINGS = {
    "NIFTY",
    "BANKNIFTY",
    "FINNIFTY",
    "MIDCPNIFTY",
    "NIFTYNXT50",
    "SENSEX",
    "BANKEX",
}

# Safety cap. Kite docs recommend max 3000 instruments per WebSocket connection.
MAX_SUBSCRIPTION_TOKENS = 3000


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


def _env_bool(name: str, default: bool) -> bool:
    raw = str(os.getenv(name, "")).strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "y", "on"}


def _env_int(name: str, default: int, minimum: int = 0) -> int:
    raw = str(os.getenv(name, "")).strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return max(minimum, value)


def _resolve_env_path(name: str, default: Path) -> Path:
    raw = str(os.getenv(name, "")).strip()
    path = Path(raw) if raw else default
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path.resolve()


def _normalize_symbol_set(values: pd.Series) -> set[str]:
    normalized = values.astype(str).str.strip().str.upper()
    return {
        value
        for value in normalized.tolist()
        if value and value not in {"NAN", "NONE", "NULL"}
    }


def _read_universe_symbols(csv_path: Path) -> set[str]:
    if not csv_path.is_file():
        raise FileNotFoundError(f"Equity universe CSV not found: {csv_path}")

    universe_df = pd.read_csv(csv_path, low_memory=False)
    if universe_df.empty:
        raise ValueError(f"Equity universe CSV is empty: {csv_path}")

    normalized_columns = {
        str(column).strip().lower().replace(" ", "_"): column
        for column in universe_df.columns
    }
    symbol_column = None
    for candidate in ("symbol", "tradingsymbol", "trading_symbol"):
        if candidate in normalized_columns:
            symbol_column = normalized_columns[candidate]
            break

    if symbol_column is None:
        raise ValueError(
            "Equity universe CSV must contain a Symbol/tradingsymbol column: "
            f"{csv_path}"
        )

    if "series" in normalized_columns:
        series_column = normalized_columns["series"]
        normalized_symbols = universe_df[symbol_column].astype(str).str.strip().str.upper()
        normalized_series = universe_df[series_column].astype(str).str.strip().str.upper()
        symbols = set()
        for symbol, series in zip(normalized_symbols.tolist(), normalized_series.tolist()):
            if not symbol or symbol in {"NAN", "NONE", "NULL"}:
                continue
            # Nifty Indices can include temporary non-tradable placeholder rows.
            if symbol.startswith("DUMMY"):
                continue
            if series and series not in {"EQ", "NAN", "NONE", "NULL"}:
                symbols.add(f"{symbol}-{series}")
            else:
                symbols.add(symbol)
    else:
        symbols = _normalize_symbol_set(universe_df[symbol_column])

    if len(symbols) < 50:
        raise ValueError(
            "Equity universe CSV has too few symbols to be valid: "
            f"{csv_path} symbols={len(symbols)}"
        )
    return symbols


def _download_nifty500_universe(csv_path: Path) -> None:
    url = str(os.getenv("LM_NIFTY500_CONSTITUENTS_URL") or NIFTY500_CONSTITUENTS_URL).strip()
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Referer": "https://www.niftyindices.com/",
        "Accept": "text/csv,application/csv,text/plain,*/*",
    }
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = csv_path.with_suffix(csv_path.suffix + ".tmp")
    response = requests.get(url, headers=headers, timeout=20)
    response.raise_for_status()
    temp_path.write_text(response.text, encoding="utf-8")
    symbols = _read_universe_symbols(temp_path)
    if len(symbols) < 400:
        raise ValueError(
            "Downloaded NIFTY500 universe looks incomplete: "
            f"url={url} symbols={len(symbols)}"
        )
    temp_path.replace(csv_path)


def _extract_fno_stock_symbols(instruments_df: pd.DataFrame) -> set[str]:
    exchange = _normalize_str_column(instruments_df, "exchange").str.upper()
    instrument_type = _normalize_str_column(instruments_df, "instrument_type").str.upper()
    name = _normalize_str_column(instruments_df, "name").str.upper()
    futures_df = instruments_df.loc[
        (exchange == "NFO")
        & (instrument_type == "FUT")
        & name.ne("")
        & ~name.isin(INDEX_DERIVATIVE_UNDERLYINGS)
    ]
    return _normalize_symbol_set(futures_df["name"])


def _load_equity_universe_symbols(
    universe_name: str,
    universe_path: Path,
) -> tuple[set[str] | None, dict[str, Any]]:
    normalized_name = str(universe_name or "").strip().upper()
    if normalized_name in {"", "ALL", "FULL"}:
        return None, {
            "name": "ALL",
            "path": "",
            "symbols": None,
            "source": "all_nse_equities",
        }

    if normalized_name in {
        "NIFTY500",
        "NIFTY_500",
        "NIFTY500_PLUS_FNO",
        "NIFTY500+FNO",
        "NIFTY_500_PLUS_FNO",
    }:
        if not universe_path.is_file():
            try:
                _download_nifty500_universe(universe_path)
                source = "downloaded"
            except Exception as exc:
                raise RuntimeError(
                    "NIFTY500 universe cache is missing and automatic download failed. "
                    f"Create the CSV at {universe_path} with a Symbol column, or set "
                    "LM_EQUITY_UNIVERSE_PATH to a valid file. "
                    f"Download error: {type(exc).__name__}: {exc}"
                ) from exc
        else:
            source = "cache"

        symbols = _read_universe_symbols(universe_path)
        return symbols, {
            "name": normalized_name,
            "path": str(universe_path),
            "symbols": len(symbols),
            "source": source,
        }

    symbols = _read_universe_symbols(universe_path)
    return symbols, {
        "name": normalized_name or "CUSTOM",
        "path": str(universe_path),
        "symbols": len(symbols),
        "source": "custom_file",
    }


def _option_underlying_from_symbol(symbol: str) -> str:
    value = str(symbol or "").strip().upper()
    if value.startswith("BANKNIFTY"):
        return "BANKNIFTY"
    if value.startswith("NIFTY"):
        return "NIFTY"
    return ""


def _filter_to_nearest_expiries(
    options_df: pd.DataFrame,
    *,
    expiry_count: int,
) -> pd.DataFrame:
    if options_df.empty:
        return options_df

    selected_frames: list[pd.DataFrame] = []
    for underlying, group in options_df.groupby("underlying", sort=False):
        expiries = sorted(set(group["expiry"].dropna().tolist()))
        if not expiries:
            continue
        keep_expiries = set(expiries[:expiry_count])
        selected_frames.append(group[group["expiry"].isin(keep_expiries)])

    if not selected_frames:
        return options_df.iloc[0:0].copy()
    return pd.concat(selected_frames, ignore_index=True)


def _compute_index_spot_by_underlying(index_df: pd.DataFrame) -> dict[str, float]:
    spot_map: dict[str, float] = {}
    if index_df.empty:
        return spot_map

    if "last_price" in index_df.columns:
        price_series = pd.to_numeric(index_df["last_price"], errors="coerce")
    elif "strike" in index_df.columns:
        price_series = pd.to_numeric(index_df["strike"], errors="coerce")
    else:
        price_series = pd.Series([float("nan")] * len(index_df))

    index_df = index_df.copy()
    index_df["spot_value"] = price_series

    for row in index_df.itertuples(index=False):
        symbol = str(getattr(row, "tradingsymbol", "")).strip().upper()
        spot = float(getattr(row, "spot_value", float("nan")))
        if not pd.notna(spot) or spot <= 0:
            continue
        if symbol in {"NIFTY 50", "NIFTY"}:
            spot_map["NIFTY"] = spot
        elif symbol in {"NIFTY BANK", "BANKNIFTY"}:
            spot_map["BANKNIFTY"] = spot
    return spot_map


def _apply_strike_window(
    options_df: pd.DataFrame,
    *,
    strikes_around_atm: int,
    spot_by_underlying: dict[str, float],
) -> pd.DataFrame:
    if options_df.empty or strikes_around_atm <= 0:
        return options_df

    selected_frames: list[pd.DataFrame] = []
    per_side = int(strikes_around_atm)

    for underlying, group in options_df.groupby("underlying", sort=False):
        strikes_series = pd.to_numeric(group["strike"], errors="coerce").dropna()
        unique_strikes = sorted(set(float(v) for v in strikes_series.tolist()))
        if not unique_strikes:
            continue

        spot = spot_by_underlying.get(underlying)
        if spot is not None:
            atm_strike = min(unique_strikes, key=lambda x: abs(x - float(spot)))
        else:
            # Fallback: center strike when spot is unavailable.
            atm_strike = unique_strikes[len(unique_strikes) // 2]

        try:
            atm_idx = unique_strikes.index(atm_strike)
        except ValueError:
            atm_idx = len(unique_strikes) // 2

        low = max(0, atm_idx - per_side)
        high = min(len(unique_strikes), atm_idx + per_side + 1)
        keep = set(unique_strikes[low:high])
        selected_frames.append(group[group["strike"].isin(keep)])

    if not selected_frames:
        return options_df.iloc[0:0].copy()
    return pd.concat(selected_frames, ignore_index=True)


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

    collect_equities = _env_bool("LM_COLLECT_EQUITIES", COLLECT_EQUITIES)
    collect_options = _env_bool("LM_COLLECT_OPTIONS", COLLECT_OPTIONS)
    collect_vix = _env_bool("LM_COLLECT_VIX", COLLECT_VIX)
    collect_index_spots = _env_bool("LM_COLLECT_INDEX_SPOT_TOKENS", COLLECT_INDEX_SPOT_TOKENS)
    equity_universe_name = str(os.getenv("LM_EQUITY_UNIVERSE") or EQUITY_UNIVERSE).strip()
    equity_universe_path = _resolve_env_path("LM_EQUITY_UNIVERSE_PATH", EQUITY_UNIVERSE_PATH)
    expiry_count = _env_int("LM_OPTION_EXPIRY_COUNT", EXPIRY_COUNT, minimum=1)
    strikes_around_atm = _env_int("LM_STRIKES_AROUND_ATM", STRIKES_AROUND_ATM, minimum=0)

    equity_mask = (segment == "NSE") & (instrument_type == "EQ")
    if not bool(equity_mask.any()):
        # Fallback for some datasets where equity rows are tagged by exchange.
        equity_mask = (exchange == "NSE") & (instrument_type == "EQ")
    equity_df = df.loc[equity_mask].copy()
    equity_universe_symbols: set[str] | None = None
    equity_universe_meta: dict[str, Any] = {
        "name": "DISABLED",
        "path": "",
        "symbols": 0,
        "source": "disabled",
    }

    index_spot_df = df.loc[tradingsymbol.isin(set(INDEX_SPOT_SYMBOLS))].copy()
    index_spot_df["instrument_token"] = _coerce_token_series(index_spot_df["instrument_token"])
    index_spot_df = index_spot_df.dropna(subset=["tradingsymbol"])

    if not collect_equities:
        equity_df = equity_df.iloc[0:0].copy()
    else:
        equity_universe_symbols, equity_universe_meta = _load_equity_universe_symbols(
            equity_universe_name,
            equity_universe_path,
        )
        normalized_equity_universe_name = str(equity_universe_name or "").strip().upper()
        if (
            equity_universe_symbols is not None
            and normalized_equity_universe_name
            in {
                "NIFTY500_PLUS_FNO",
                "NIFTY500+FNO",
                "NIFTY_500_PLUS_FNO",
            }
        ):
            base_symbols = set(equity_universe_symbols)
            fno_symbols = _extract_fno_stock_symbols(df)
            equity_universe_symbols = base_symbols | fno_symbols
            equity_universe_meta.update(
                {
                    "name": "NIFTY500_PLUS_FNO",
                    "source": f"{equity_universe_meta.get('source', 'cache')}+fno_from_instruments",
                    "symbols": len(equity_universe_symbols),
                    "nifty500_symbols": len(base_symbols),
                    "fno_stock_symbols": len(fno_symbols),
                    "fno_added_to_universe": len(fno_symbols - base_symbols),
                }
            )
        if equity_universe_symbols is not None:
            equity_symbols = _normalize_str_column(equity_df, "tradingsymbol").str.upper()
            before_count = len(equity_df)
            equity_df = equity_df.loc[equity_symbols.isin(equity_universe_symbols)].copy()
            missing_count = len(equity_universe_symbols) - len(set(equity_symbols.tolist()) & equity_universe_symbols)
            equity_universe_meta.update(
                {
                    "matched": int(len(equity_df)),
                    "missing_from_instruments": int(max(0, missing_count)),
                    "source_equity_rows": int(before_count),
                }
            )
    if collect_index_spots:
        if equity_df.empty:
            equity_df = index_spot_df.copy()
        else:
            equity_df = pd.concat([equity_df, index_spot_df], ignore_index=True)

    equity_df["instrument_token"] = _coerce_token_series(equity_df["instrument_token"])
    equity_df = equity_df.dropna(subset=["tradingsymbol"])

    equity_tokens = {int(token) for token in equity_df["instrument_token"].tolist()}
    equity_symbol_by_token = {
        int(row.instrument_token): str(row.tradingsymbol).strip().upper()
        for row in equity_df.itertuples(index=False)
        if str(row.tradingsymbol).strip()
    }

    vix_token: int | None = None
    if collect_vix:
        vix_mask = tradingsymbol.isin({"INDIA VIX", "INDIAVIX"})
        vix_df = df.loc[vix_mask].copy()
        if not vix_df.empty:
            token_series = _coerce_token_series(vix_df["instrument_token"])
            if not token_series.empty:
                vix_token = int(token_series.iloc[0])
        else:
            print("[token_loader] WARNING: INDIA VIX token not found in instruments CSV.")

    options_df = df.iloc[0:0].copy()
    if collect_options:
        options_mask = (
            (exchange == "NFO")
            & instrument_type.isin(["CE", "PE"])
        )
        options_df = df.loc[options_mask].copy()
        options_df["underlying"] = options_df["tradingsymbol"].astype(str).map(
            _option_underlying_from_symbol
        )
        options_df = options_df[options_df["underlying"].isin(set(OPTION_UNDERLYINGS))]
        options_df["expiry"] = pd.to_datetime(options_df["expiry"], errors="coerce").dt.date
        today = today_ist()
        max_day = today + timedelta(days=31)
        options_df = options_df[
            options_df["expiry"].notna()
            & (options_df["expiry"] >= today)
            & (options_df["expiry"] <= max_day)
        ]
        options_df["strike"] = pd.to_numeric(options_df["strike"], errors="coerce")
        options_df = options_df.dropna(subset=["strike"])

        options_df = _filter_to_nearest_expiries(
            options_df,
            expiry_count=expiry_count,
        )

        spot_by_underlying = _compute_index_spot_by_underlying(index_spot_df)
        options_df = _apply_strike_window(
            options_df,
            strikes_around_atm=strikes_around_atm,
            spot_by_underlying=spot_by_underlying,
        )

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

    total_tokens = len(equity_tokens) + len(options_tokens) + (1 if vix_token is not None else 0)
    print(f"[token_loader] Config: equities={collect_equities}, options={collect_options}, vix={collect_vix}, "
          f"index_spots={collect_index_spots}, expiry_count={expiry_count}, strikes_around_atm={strikes_around_atm}")
    print(f"[token_loader] Equity universe: {equity_universe_meta}")
    print(f"[token_loader] NSE equity/index tokens: {len(equity_tokens)}")
    print(f"[token_loader] NFO options tokens: {len(options_tokens)}")
    print(f"[token_loader] VIX token: {vix_token}")
    print(f"[token_loader] TOTAL subscription tokens: {total_tokens}")

    if total_tokens > MAX_SUBSCRIPTION_TOKENS:
        raise RuntimeError(
            "Too many tokens selected for one WebSocket connection. "
            f"selected={total_tokens}, limit={MAX_SUBSCRIPTION_TOKENS}. "
            "Reduce underlyings/expiries/strike window."
        )

    return {
        "equity_tokens": equity_tokens,
        "equity_symbol_by_token": equity_symbol_by_token,
        "options_tokens": options_tokens,
        "options_meta": options_meta,
        "option_symbol_by_token": option_symbol_by_token,
        "token_to_symbol": token_to_symbol,
        "vix_token": vix_token,
        "token_counts": {
            "equity": len(equity_tokens),
            "options": len(options_tokens),
            "vix": 1 if vix_token is not None else 0,
            "total": total_tokens,
        },
        "equity_universe": equity_universe_meta,
    }


__all__ = ["load_all_tokens", "resolve_default_instruments_path"]
