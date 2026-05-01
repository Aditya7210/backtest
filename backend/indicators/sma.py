"""SMA indicator — uses Cython kernel with pandas-ta fallback."""
from __future__ import annotations

import numpy as np
import pandas as pd


def compute_sma(df: pd.DataFrame, period: int, column: str = "Close") -> pd.Series:
    """Compute SMA for a DataFrame."""
    try:
        from backend.cython_math import compute_sma as _cython_sma
        result = _cython_sma(df[column].values.astype(np.float64), period)
        return pd.Series(result, index=df.index, name=f"SMA_{period}")
    except Exception:
        try:
            import pandas_ta as ta
            return ta.sma(df[column], length=period)
        except Exception:
            return df[column].rolling(window=period, min_periods=period).mean()
