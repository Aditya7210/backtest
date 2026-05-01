"""Data loader — reads from MongoDB, returns Title-Case OHLCV with IST DatetimeIndex (E-01/E-22)."""
from __future__ import annotations

from typing import Any

import pandas as pd
from pymongo import MongoClient

from backend.config import settings


def load_backtest_data(
    instrument_token: int,
    timeframe: str,
    date_from: str,
    date_to: str,
) -> pd.DataFrame:
    """Load bars from MongoDB and return Backtrader-compatible DataFrame.

    Returns DataFrame with:
    - Title-Case columns: Date, Open, High, Low, Close, Volume (E-01)
    - IST-aware DatetimeIndex (E-22)
    """
    client = MongoClient(settings.MONGO_URI)
    db = client.get_default_database()

    cursor = db.bars.find({
        "instrument_token": instrument_token,
        "timeframe": timeframe,
        "trading_date": {"$gte": date_from, "$lte": date_to},
    }).sort("timestamp", 1)

    rows = list(cursor)
    client.close()

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    df = df.drop(columns=["_id"], errors="ignore")

    # Rename to Title-Case for Backtrader (E-01)
    df = df.rename(columns={
        "timestamp": "Date",
        "open": "Open",
        "high": "High",
        "low": "Low",
        "close": "Close",
        "volume": "Volume",
    })

    df["Date"] = pd.to_datetime(df["Date"])
    df = df.set_index("Date").sort_index()

    # Ensure IST-aware DatetimeIndex (E-22)
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC").tz_convert("Asia/Kolkata")
    else:
        df.index = df.index.tz_convert("Asia/Kolkata")

    df.index.name = "Date"

    return df[["Open", "High", "Low", "Close", "Volume"]]
