from __future__ import annotations

import pandas as pd


def add_indicators(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame
    result = frame.copy().sort_values("timestamp")
    result["close"] = pd.to_numeric(result["close"], errors="coerce")
    for window in (5, 20, 50):
        result[f"sma_{window}"] = result["close"].rolling(window=window, min_periods=1).mean()

    delta = result["close"].diff()
    gain = delta.clip(lower=0).rolling(window=14, min_periods=1).mean()
    loss = (-delta.clip(upper=0)).rolling(window=14, min_periods=1).mean()
    rs = gain / loss.replace(0, pd.NA)
    result["rsi_14"] = (100 - (100 / (1 + rs))).fillna(50)

    if "volume" in result.columns:
        volume = pd.to_numeric(result["volume"], errors="coerce").fillna(0)
        typical = (
            pd.to_numeric(result["high"], errors="coerce")
            + pd.to_numeric(result["low"], errors="coerce")
            + result["close"]
        ) / 3
        cumulative_volume = volume.cumsum()
        result["vwap"] = ((typical * volume).cumsum() / cumulative_volume.replace(0, pd.NA)).fillna(result["close"])
    else:
        result["vwap"] = result["close"]
    return result


def indicator_summary(frame: pd.DataFrame) -> dict[str, str | float]:
    if frame.empty:
        return {
            "short_term": "NA",
            "long_term": "NA",
            "rsi_label": "NA",
            "rsi": 0.0,
        }
    latest = frame.iloc[-1]
    sma5 = float(latest.get("sma_5") or 0)
    sma20 = float(latest.get("sma_20") or 0)
    sma50 = float(latest.get("sma_50") or 0)
    rsi = float(latest.get("rsi_14") or 0)
    if rsi >= 60:
        rsi_label = "Bullish"
    elif rsi <= 40:
        rsi_label = "Bearish"
    else:
        rsi_label = "Neutral"
    return {
        "short_term": "Bullish" if sma5 >= sma20 else "Bearish",
        "long_term": "Bullish" if sma20 >= sma50 else "Bearish",
        "rsi_label": rsi_label,
        "rsi": round(rsi, 2),
    }


__all__ = ["add_indicators", "indicator_summary"]
