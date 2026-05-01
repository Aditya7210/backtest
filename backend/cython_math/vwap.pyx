# cython: language_level=3
"""VWAP Cython kernels — two variants per E-27."""
import numpy as np
cimport numpy as np


def compute_vwap_close(np.ndarray[double, ndim=1] close_prices,
                       np.ndarray[double, ndim=1] volumes) -> np.ndarray:
    """VWAP using close × volume (for snapshot — matches vwap_calculator.py)."""
    cdef int n = close_prices.shape[0]
    cdef np.ndarray[double, ndim=1] result = np.empty(n)
    cdef double cum_pv = 0.0, cum_v = 0.0
    cdef int i
    for i in range(n):
        cum_pv += close_prices[i] * volumes[i]
        cum_v += volumes[i]
        result[i] = cum_pv / cum_v if cum_v > 0 else close_prices[i]
    return result


def compute_vwap_typical(np.ndarray[double, ndim=1] highs,
                         np.ndarray[double, ndim=1] lows,
                         np.ndarray[double, ndim=1] closes,
                         np.ndarray[double, ndim=1] volumes) -> np.ndarray:
    """VWAP using typical price (H+L+C)/3 × volume (for chart overlay)."""
    cdef int n = highs.shape[0]
    cdef np.ndarray[double, ndim=1] result = np.empty(n)
    cdef double cum_pv = 0.0, cum_v = 0.0
    cdef double typical_price
    cdef int i
    for i in range(n):
        typical_price = (highs[i] + lows[i] + closes[i]) / 3.0
        cum_pv += typical_price * volumes[i]
        cum_v += volumes[i]
        result[i] = cum_pv / cum_v if cum_v > 0 else typical_price
    return result
