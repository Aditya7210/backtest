"""VWAP indicator — uses Cython kernel with pandas-ta fallback."""
from __future__ import annotations

import numpy as np
import pandas as pd


def compute_vwap(df: pd.DataFrame, use_typical: bool = True) -> pd.Series:
    """Compute VWAP for a DataFrame with OHLCV columns.

    Uses Cython kernel for speed, falls back to pandas-ta.
    """
    try:
        from backend.cython_math import compute_vwap_close, compute_vwap_typical

        if use_typical:
            result = compute_vwap_typical(
                df["High"].values.astype(np.float64),
                df["Low"].values.astype(np.float64),
                df["Close"].values.astype(np.float64),
                df["Volume"].values.astype(np.float64),
            )
        else:
            result = compute_vwap_close(
                df["Close"].values.astype(np.float64),
                df["Volume"].values.astype(np.float64),
            )
        return pd.Series(result, index=df.index, name="VWAP")

    except Exception:
        # Fallback to pandas-ta
        try:
            import pandas_ta as ta
            return ta.vwap(df["High"], df["Low"], df["Close"], df["Volume"])
        except Exception:
            # Manual fallback
            tp = (df["High"] + df["Low"] + df["Close"]) / 3.0
            cum_tp_vol = (tp * df["Volume"]).cumsum()
            cum_vol = df["Volume"].cumsum()
            return cum_tp_vol / cum_vol
