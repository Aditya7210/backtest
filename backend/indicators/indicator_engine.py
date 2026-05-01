"""Unified indicator engine — replaces TA-Lib with Cython + pandas-ta (E-28)."""
from __future__ import annotations

import pandas as pd

from backend.indicators.sma import compute_sma
from backend.indicators.rsi import compute_rsi
from backend.indicators.vwap import compute_vwap


def add_indicators(
    df: pd.DataFrame,
    *,
    sma_periods: list[int] | None = None,
    rsi_period: int = 14,
    include_vwap: bool = True,
) -> pd.DataFrame:
    """Add technical indicators to a DataFrame with OHLCV columns.

    Returns the DataFrame with new indicator columns appended.
    """
    result = df.copy()

    if sma_periods is None:
        sma_periods = [5, 20, 50]

    for period in sma_periods:
        result[f"SMA_{period}"] = compute_sma(result, period)

    result[f"RSI_{rsi_period}"] = compute_rsi(result, rsi_period)

    if include_vwap and "Volume" in result.columns:
        result["VWAP"] = compute_vwap(result)

    return result
