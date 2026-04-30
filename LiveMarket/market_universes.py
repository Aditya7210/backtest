from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
import requests

from LiveMarket import LIVE_MARKET_ROOT, PROJECT_ROOT


INDEX_DERIVATIVE_UNDERLYINGS = {
    "NIFTY",
    "BANKNIFTY",
    "FINNIFTY",
    "MIDCPNIFTY",
    "NIFTYNXT50",
    "SENSEX",
    "BANKEX",
}
UNIVERSE_ROOT = LIVE_MARKET_ROOT / "universes"
INDEX_UNIVERSE_CONFIG: dict[str, dict[str, str]] = {
    "NIFTY 50": {
        "file": "nifty50_symbols.csv",
        "url": "https://www.niftyindices.com/IndexConstituent/ind_nifty50list.csv",
    },
    "NIFTY BANK": {
        "file": "niftybank_symbols.csv",
        "url": "https://www.niftyindices.com/IndexConstituent/ind_niftybanklist.csv",
    },
    "NIFTY 100": {
        "file": "nifty100_symbols.csv",
        "url": "https://www.niftyindices.com/IndexConstituent/ind_nifty100list.csv",
    },
    "NIFTY 200": {
        "file": "nifty200_symbols.csv",
        "url": "https://www.niftyindices.com/IndexConstituent/ind_nifty200list.csv",
    },
    "NIFTY 500": {
        "file": "nifty500_symbols.csv",
        "url": "https://www.niftyindices.com/IndexConstituent/ind_nifty500list.csv",
    },
}


def default_instruments_path() -> Path:
    return PROJECT_ROOT / "Data" / "instrument_mapper_data" / "zerodha_instruments_latest.csv"


def normalize_symbols(values: pd.Series) -> set[str]:
    normalized = values.astype(str).str.strip().str.upper()
    return {
        value
        for value in normalized.tolist()
        if value and value not in {"NAN", "NONE", "NULL"}
    }


def read_symbols_csv(csv_path: Path) -> set[str]:
    if not csv_path.is_file():
        raise FileNotFoundError(f"Universe CSV not found: {csv_path}")

    universe_df = pd.read_csv(csv_path, low_memory=False)
    if universe_df.empty:
        raise ValueError(f"Universe CSV is empty: {csv_path}")

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
        raise ValueError(f"Universe CSV must contain a Symbol/tradingsymbol column: {csv_path}")

    if "series" not in normalized_columns:
        return normalize_symbols(universe_df[symbol_column])

    series_column = normalized_columns["series"]
    normalized_symbols = universe_df[symbol_column].astype(str).str.strip().str.upper()
    normalized_series = universe_df[series_column].astype(str).str.strip().str.upper()
    symbols: set[str] = set()
    for symbol, series in zip(normalized_symbols.tolist(), normalized_series.tolist()):
        if not symbol or symbol in {"NAN", "NONE", "NULL"}:
            continue
        if symbol.startswith("DUMMY"):
            continue
        if series and series not in {"EQ", "NAN", "NONE", "NULL"}:
            symbols.add(f"{symbol}-{series}")
        else:
            symbols.add(symbol)
    return symbols


def download_index_universe(index_name: str, csv_path: Path) -> None:
    config = INDEX_UNIVERSE_CONFIG[index_name]
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Referer": "https://www.niftyindices.com/",
        "Accept": "text/csv,application/csv,text/plain,*/*",
    }
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = csv_path.with_suffix(csv_path.suffix + ".tmp")
    response = requests.get(config["url"], headers=headers, timeout=20)
    response.raise_for_status()
    temp_path.write_text(response.text, encoding="utf-8")
    symbols = read_symbols_csv(temp_path)
    if len(symbols) < 10:
        raise ValueError(f"Downloaded {index_name} universe looks incomplete: symbols={len(symbols)}")
    temp_path.replace(csv_path)


def load_index_universe(index_name: str) -> set[str]:
    normalized_name = str(index_name or "").strip().upper().replace("_", " ")
    if normalized_name not in INDEX_UNIVERSE_CONFIG:
        raise ValueError(f"Unsupported index universe: {index_name}")

    config = INDEX_UNIVERSE_CONFIG[normalized_name]
    csv_path = UNIVERSE_ROOT / config["file"]
    if not csv_path.is_file():
        download_index_universe(normalized_name, csv_path)
    symbols = read_symbols_csv(csv_path)
    if len(symbols) < 10:
        raise ValueError(f"{normalized_name} universe has too few symbols: {len(symbols)}")
    return symbols


def load_fno_stock_symbols(instruments_csv_path: str | Path | None = None) -> set[str]:
    csv_path = Path(instruments_csv_path).resolve() if instruments_csv_path else default_instruments_path()
    if not csv_path.is_file():
        return set()

    instruments_df = pd.read_csv(csv_path, low_memory=False)
    required = {"exchange", "instrument_type", "name"}
    if not required.issubset(set(instruments_df.columns)):
        return set()

    exchange = instruments_df["exchange"].astype(str).str.strip().str.upper()
    instrument_type = instruments_df["instrument_type"].astype(str).str.strip().str.upper()
    name = instruments_df["name"].astype(str).str.strip().str.upper()
    futures_df = instruments_df.loc[
        (exchange == "NFO")
        & (instrument_type == "FUT")
        & name.ne("")
        & ~name.isin(INDEX_DERIVATIVE_UNDERLYINGS)
    ]
    return normalize_symbols(futures_df["name"])


def build_ad_universes(instruments_csv_path: str | Path | None = None) -> dict[str, set[str]]:
    universes: dict[str, set[str]] = {}
    for index_name in ("NIFTY 50", "NIFTY BANK", "NIFTY 100", "NIFTY 200", "NIFTY 500"):
        try:
            universes[index_name] = load_index_universe(index_name)
        except Exception as exc:
            print(f"[market_universes] failed loading {index_name}: {type(exc).__name__}: {exc}")

    fno_symbols = load_fno_stock_symbols(instruments_csv_path)
    if fno_symbols:
        universes["F&O Stocks"] = fno_symbols

    nifty500 = universes.get("NIFTY 500", set())
    if nifty500 or fno_symbols:
        universes["NIFTY500 + F&O"] = set(nifty500) | set(fno_symbols)

    return universes


__all__ = [
    "INDEX_DERIVATIVE_UNDERLYINGS",
    "build_ad_universes",
    "default_instruments_path",
    "load_fno_stock_symbols",
    "load_index_universe",
    "normalize_symbols",
    "read_symbols_csv",
]
