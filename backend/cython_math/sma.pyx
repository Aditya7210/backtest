# cython: language_level=3
"""SMA Cython kernel — typed rolling simple moving average."""
import numpy as np
cimport numpy as np


def compute_sma(np.ndarray[double, ndim=1] prices, int period) -> np.ndarray:
    """Compute SMA. Returns array of same length; first `period-1` values are NaN."""
    cdef int n = prices.shape[0]
    cdef np.ndarray[double, ndim=1] result = np.full(n, np.nan)
    cdef double window_sum = 0.0
    cdef int i

    if n < period or period <= 0:
        return result

    # Initial window sum
    for i in range(period):
        window_sum += prices[i]
    result[period - 1] = window_sum / period

    # Slide the window
    for i in range(period, n):
        window_sum += prices[i] - prices[i - period]
        result[i] = window_sum / period

    return result
