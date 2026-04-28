from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd


def _load_frame(path: Path) -> pd.DataFrame:
    if not path.is_file():
        return pd.DataFrame()
    df = pd.read_csv(path)
    if df.empty:
        return df
    required = {"timestamp", "instrument_token", "close", "volume"}
    if not required.issubset(set(df.columns)):
        return pd.DataFrame()
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    df = df.dropna(subset=["timestamp"]).sort_values("timestamp")
    df["close"] = pd.to_numeric(df["close"], errors="coerce")
    df["volume"] = pd.to_numeric(df["volume"], errors="coerce").fillna(0)
    df["instrument_token"] = pd.to_numeric(df["instrument_token"], errors="coerce")
    df = df.dropna(subset=["instrument_token", "close"])
    if df.empty:
        return df
    df["instrument_token"] = df["instrument_token"].astype("int64")
    return df


def compute_vwap_snapshot(frame: pd.DataFrame) -> dict[str, float]:
    if frame.empty:
        return {}
    payload: dict[str, float] = {}
    for token, token_df in frame.groupby("instrument_token", sort=False):
        token_df = token_df.sort_values("timestamp")
        cumulative_volume = token_df["volume"].cumsum()
        if cumulative_volume.iloc[-1] <= 0:
            continue
        cumulative_value = (token_df["close"] * token_df["volume"]).cumsum()
        vwap_series = cumulative_value / cumulative_volume
        vwap_value = float(vwap_series.iloc[-1])
        payload[str(int(token))] = round(vwap_value, 4)
    return payload


def compute_all_timeframes(
    live_day_dir: Path,
    *,
    base_name: str = "equities",
    timeframes: list[int] | None = None,
) -> dict[str, dict[str, float]]:
    tf_values = [1, 3, 5, 10, 15, 30, 60] if timeframes is None else sorted(set(int(v) for v in timeframes))
    results: dict[str, dict[str, float]] = {}
    for tf in tf_values:
        path = live_day_dir / f"{base_name}_{tf}min.csv"
        frame = _load_frame(path)
        results[f"{tf}min"] = compute_vwap_snapshot(frame)
    return results


__all__ = ["compute_all_timeframes", "compute_vwap_snapshot"]

