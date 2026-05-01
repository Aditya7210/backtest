"""RSI indicator — uses Cython kernel with pandas-ta fallback."""
from __future__ import annotations

import numpy as np
import pandas as pd


def compute_rsi(df: pd.DataFrame, period: int = 14, column: str = "Close") -> pd.Series:
    """Compute RSI for a DataFrame."""
    try:
        from backend.cython_math import compute_rsi as _cython_rsi
        result = _cython_rsi(df[column].values.astype(np.float64), period)
        return pd.Series(result, index=df.index, name=f"RSI_{period}")
    except Exception:
        try:
            import pandas_ta as ta
            return ta.rsi(df[column], length=period)
        except Exception:
            # Manual fallback
            delta = df[column].diff()
            gain = delta.clip(lower=0)
            loss = (-delta).clip(lower=0)
            avg_gain = gain.ewm(alpha=1.0/period, min_periods=period, adjust=False).mean()
            avg_loss = loss.ewm(alpha=1.0/period, min_periods=period, adjust=False).mean()
            rs = avg_gain / avg_loss
            return 100.0 - (100.0 / (1.0 + rs))
