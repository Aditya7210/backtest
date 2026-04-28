from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


def _load_prev_close(path: Path) -> dict[str, float]:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    data = payload.get("data", {})
    if not isinstance(data, dict):
        return {}
    result: dict[str, float] = {}
    for key, value in data.items():
        try:
            result[str(key)] = float(value)
        except (TypeError, ValueError):
            continue
    return result


def compute(
    equities_1min_csv: Path,
    prev_close_json: Path,
) -> dict[str, float | int | str]:
    prev_close = _load_prev_close(prev_close_json)
    if not equities_1min_csv.is_file():
        return {
            "generated_at": pd.Timestamp.now().isoformat(),
            "advances": 0,
            "declines": 0,
            "unchanged": 0,
            "ad_ratio": 0.0,
        }
    df = pd.read_csv(equities_1min_csv)
    if df.empty:
        return {
            "generated_at": pd.Timestamp.now().isoformat(),
            "advances": 0,
            "declines": 0,
            "unchanged": 0,
            "ad_ratio": 0.0,
        }
    required = {"timestamp", "instrument_token", "close"}
    if not required.issubset(set(df.columns)):
        return {
            "generated_at": pd.Timestamp.now().isoformat(),
            "advances": 0,
            "declines": 0,
            "unchanged": 0,
            "ad_ratio": 0.0,
        }

    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    df = df.dropna(subset=["timestamp"])
    if df.empty:
        return {
            "generated_at": pd.Timestamp.now().isoformat(),
            "advances": 0,
            "declines": 0,
            "unchanged": 0,
            "ad_ratio": 0.0,
        }
    df = df[df["timestamp"].dt.date == pd.Timestamp.now().date()]
    if df.empty:
        return {
            "generated_at": pd.Timestamp.now().isoformat(),
            "advances": 0,
            "declines": 0,
            "unchanged": 0,
            "ad_ratio": 0.0,
        }
    df["close"] = pd.to_numeric(df["close"], errors="coerce")
    df["instrument_token"] = pd.to_numeric(df["instrument_token"], errors="coerce")
    df = df.dropna(subset=["close", "instrument_token"]).sort_values("timestamp")
    if df.empty:
        return {
            "generated_at": pd.Timestamp.now().isoformat(),
            "advances": 0,
            "declines": 0,
            "unchanged": 0,
            "ad_ratio": 0.0,
        }
    latest_close = df.groupby("instrument_token", sort=False)["close"].last()

    advances = 0
    declines = 0
    unchanged = 0
    for token, close in latest_close.items():
        prev = prev_close.get(str(int(token)))
        if prev is None:
            continue
        if close > prev:
            advances += 1
        elif close < prev:
            declines += 1
        else:
            unchanged += 1

    ad_ratio = round((advances / declines), 4) if declines > 0 else float(advances)
    return {
        "generated_at": pd.Timestamp.now().isoformat(),
        "advances": advances,
        "declines": declines,
        "unchanged": unchanged,
        "ad_ratio": ad_ratio,
    }


__all__ = ["compute"]

