from __future__ import annotations

from pathlib import Path
import re

import pandas as pd


def _sanitize_symbol(symbol: str) -> str:
    return re.sub(r"[^\w\-]", "_", str(symbol or "").strip().upper())


def _validate_timeframe(timeframe: str) -> str:
    normalized = str(timeframe or "").strip().lower()
    if normalized == "minute":
        return "1min"
    if normalized.endswith("minute"):
        return f"{normalized.replace('minute', '')}min"
    if normalized.endswith("min"):
        return normalized
    raise ValueError(f"Unsupported timeframe: {timeframe}")


def extract_instrument_data(
    date_str: str,
    instrument_token: int,
    tradingsymbol: str,
    timeframe: str,
    data_type: str,
    live_data_root: Path,
) -> Path:
    normalized_date = str(date_str or "").strip()
    if not normalized_date:
        raise ValueError("date_str is required")

    token = int(instrument_token)
    safe_symbol = _sanitize_symbol(tradingsymbol) or f"TOKEN_{token}"
    safe_type = str(data_type or "equities").strip().lower()
    if safe_type not in {"equities", "options"}:
        raise ValueError("data_type must be either 'equities' or 'options'")

    tf = _validate_timeframe(timeframe)
    source_csv = live_data_root / "daily" / normalized_date / f"{safe_type}_{tf}.csv"
    if not source_csv.is_file():
        raise FileNotFoundError(
            f"Live data source not found: {source_csv}. "
            "Confirm collector ran for this date and timeframe."
        )

    frame = pd.read_csv(source_csv)
    if frame.empty:
        raise ValueError(f"Source CSV is empty: {source_csv}")

    required = {"timestamp", "instrument_token", "open", "high", "low", "close", "volume"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"Source CSV missing required columns: {sorted(missing)}")

    token_series = pd.to_numeric(frame["instrument_token"], errors="coerce")
    filtered = frame.loc[token_series == token].copy()
    if filtered.empty:
        raise ValueError(f"No data for {safe_symbol} on {normalized_date} at {tf}")

    output = filtered[["timestamp", "open", "high", "low", "close", "volume"]].copy()
    output = output.rename(columns={"timestamp": "Date"})

    extracted_dir = live_data_root / "extracted"
    extracted_dir.mkdir(parents=True, exist_ok=True)
    output_path = extracted_dir / f"{normalized_date}_{safe_symbol}_{tf}.csv"
    output.to_csv(output_path, index=False)
    return output_path


__all__ = ["extract_instrument_data"]
