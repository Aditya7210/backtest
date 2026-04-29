from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from LiveMarket.time_utils import today_ist


IST = "Asia/Kolkata"


def _normalize_timestamp_column(series: pd.Series) -> pd.Series:
    parsed = pd.to_datetime(series, errors="coerce", utc=True)
    return parsed.dt.tz_convert(IST)


def _today_ist_date() -> datetime.date:
    return today_ist()


def _build_agg_map(df: pd.DataFrame) -> dict[str, str]:
    agg: dict[str, str] = {}
    base_agg: dict[str, str] = {
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "volume": "sum",
    }
    for column, mode in base_agg.items():
        if column in df.columns:
            agg[column] = mode
    if "oi" in df.columns:
        agg["oi"] = "last"
    passthrough = ["tradingsymbol", "strike", "expiry", "option_type"]
    for column in passthrough:
        if column in df.columns:
            agg[column] = "last"
    return agg


def _resample_single_frame(df: pd.DataFrame, timeframe: int) -> pd.DataFrame:
    if df.empty:
        return df
    agg_map = _build_agg_map(df)
    resampled = (
        df.resample(
            f"{int(timeframe)}min",
            origin="start",
            closed="left",
            label="left",
        )
        .agg(agg_map)
        .dropna(subset=["open", "high", "low", "close"], how="any")
    )
    if not resampled.empty:
        # Drop most-recent potentially incomplete bar.
        resampled = resampled.iloc[:-1]
    return resampled


def _source_prefix(source_csv: Path) -> str:
    stem = source_csv.stem
    if stem.endswith("_1min"):
        return stem[:-5]
    return stem


def resample_to_timeframes(
    source_csv: Path,
    timeframes: list[int],
    output_dir: Path,
    group_by_token: bool = True,
) -> dict[int, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    if not source_csv.is_file():
        return {}

    raw_df = pd.read_csv(source_csv)
    if raw_df.empty or "timestamp" not in raw_df.columns:
        return {}

    raw_df["timestamp"] = _normalize_timestamp_column(raw_df["timestamp"])
    raw_df = raw_df.dropna(subset=["timestamp"]).copy()
    if raw_df.empty:
        return {}

    raw_df = raw_df.sort_values("timestamp")
    raw_df = raw_df[raw_df["timestamp"].dt.date == _today_ist_date()].copy()
    if raw_df.empty:
        return {}

    outputs: dict[int, Path] = {}
    base_prefix = _source_prefix(source_csv)

    for tf in sorted({int(v) for v in timeframes if int(v) > 1}):
        if group_by_token and "instrument_token" in raw_df.columns:
            chunks: list[pd.DataFrame] = []
            for token, token_df in raw_df.groupby("instrument_token", sort=False):
                token_indexed = token_df.set_index("timestamp").sort_index()
                resampled = _resample_single_frame(token_indexed, tf)
                if resampled.empty:
                    continue
                resampled["instrument_token"] = int(token)
                chunks.append(resampled.reset_index())
            out_df = pd.concat(chunks, ignore_index=True) if chunks else pd.DataFrame()
        else:
            indexed = raw_df.set_index("timestamp").sort_index()
            resampled = _resample_single_frame(indexed, tf)
            out_df = resampled.reset_index() if not resampled.empty else pd.DataFrame()

        output_path = output_dir / f"{base_prefix}_{tf}min.csv"
        if out_df.empty:
            # Keep file deterministic even if empty.
            out_df = pd.DataFrame(columns=[col for col in raw_df.columns if col != "timestamp"] + ["timestamp"])

        ordered_columns = ["timestamp"] + [
            column for column in out_df.columns if column != "timestamp"
        ]
        out_df = out_df[ordered_columns]
        out_df.to_csv(output_path, index=False)
        outputs[tf] = output_path

    return outputs


__all__ = ["resample_to_timeframes"]
