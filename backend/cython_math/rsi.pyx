# cython: language_level=3
"""RSI Cython kernel with Wilder smoothing."""
import numpy as np
cimport numpy as np


def compute_rsi(np.ndarray[double, ndim=1] prices, int period=14) -> np.ndarray:
    """Compute RSI with Wilder smoothing. Returns array of same length; first `period` values are NaN."""
    cdef int n = prices.shape[0]
    cdef np.ndarray[double, ndim=1] result = np.full(n, np.nan)
    cdef double gain, loss, avg_gain, avg_loss, delta, rs
    cdef int i

    if n <= period:
        return result

    # Seed: average gain/loss over first `period` changes
    avg_gain = 0.0
    avg_loss = 0.0
    for i in range(1, period + 1):
        delta = prices[i] - prices[i - 1]
        if delta > 0:
            avg_gain += delta
        else:
            avg_loss -= delta  # make positive
    avg_gain /= period
    avg_loss /= period

    if avg_loss == 0:
        result[period] = 100.0
    else:
        rs = avg_gain / avg_loss
        result[period] = 100.0 - (100.0 / (1.0 + rs))

    # Wilder smoothing for remaining values
    for i in range(period + 1, n):
        delta = prices[i] - prices[i - 1]
        if delta > 0:
            gain = delta
            loss = 0.0
        else:
            gain = 0.0
            loss = -delta

        avg_gain = (avg_gain * (period - 1) + gain) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period

        if avg_loss == 0:
            result[i] = 100.0
        else:
            rs = avg_gain / avg_loss
            result[i] = 100.0 - (100.0 / (1.0 + rs))

    return result
