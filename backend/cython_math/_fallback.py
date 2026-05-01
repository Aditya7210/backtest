"""Pure Python fallbacks for Cython math kernels. Identical math, no Cython."""
from __future__ import annotations

import numpy as np


def compute_vwap_close(close_prices: np.ndarray, volumes: np.ndarray) -> np.ndarray:
    """VWAP using close × volume."""
    n = len(close_prices)
    result = np.empty(n)
    cum_pv = 0.0
    cum_v = 0.0
    for i in range(n):
        cum_pv += close_prices[i] * volumes[i]
        cum_v += volumes[i]
        result[i] = cum_pv / cum_v if cum_v > 0 else close_prices[i]
    return result


def compute_vwap_typical(
    highs: np.ndarray,
    lows: np.ndarray,
    closes: np.ndarray,
    volumes: np.ndarray,
) -> np.ndarray:
    """VWAP using typical price (H+L+C)/3 × volume."""
    n = len(highs)
    result = np.empty(n)
    cum_pv = 0.0
    cum_v = 0.0
    for i in range(n):
        typical = (highs[i] + lows[i] + closes[i]) / 3.0
        cum_pv += typical * volumes[i]
        cum_v += volumes[i]
        result[i] = cum_pv / cum_v if cum_v > 0 else typical
    return result


def compute_rsi(prices: np.ndarray, period: int = 14) -> np.ndarray:
    """RSI with Wilder smoothing."""
    n = len(prices)
    result = np.full(n, np.nan)
    if n <= period:
        return result

    avg_gain = 0.0
    avg_loss = 0.0
    for i in range(1, period + 1):
        delta = prices[i] - prices[i - 1]
        if delta > 0:
            avg_gain += delta
        else:
            avg_loss -= delta
    avg_gain /= period
    avg_loss /= period

    if avg_loss == 0:
        result[period] = 100.0
    else:
        rs = avg_gain / avg_loss
        result[period] = 100.0 - (100.0 / (1.0 + rs))

    for i in range(period + 1, n):
        delta = prices[i] - prices[i - 1]
        gain = max(delta, 0.0)
        loss = max(-delta, 0.0)
        avg_gain = (avg_gain * (period - 1) + gain) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period
        if avg_loss == 0:
            result[i] = 100.0
        else:
            rs = avg_gain / avg_loss
            result[i] = 100.0 - (100.0 / (1.0 + rs))

    return result


def compute_sma(prices: np.ndarray, period: int) -> np.ndarray:
    """Simple moving average."""
    n = len(prices)
    result = np.full(n, np.nan)
    if n < period or period <= 0:
        return result
    window_sum = sum(prices[:period])
    result[period - 1] = window_sum / period
    for i in range(period, n):
        window_sum += prices[i] - prices[i - period]
        result[i] = window_sum / period
    return result
