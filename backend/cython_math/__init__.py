"""
Cython math kernels — imports compiled modules with Python fallback (E-16).

When Cython .so/.pyd files are not compiled, falls back to pure Python
implementations with a RuntimeWarning.
"""
from __future__ import annotations

import warnings

# VWAP kernels (E-27: two distinct formulas)
try:
    from .vwap import compute_vwap_close, compute_vwap_typical
except ImportError:
    warnings.warn(
        "Cython VWAP not available — using pure Python fallback. Performance degraded.",
        RuntimeWarning,
        stacklevel=2,
    )
    from ._fallback import compute_vwap_close, compute_vwap_typical  # type: ignore[assignment]

# RSI kernel
try:
    from .rsi import compute_rsi
except ImportError:
    warnings.warn(
        "Cython RSI not available — using pure Python fallback. Performance degraded.",
        RuntimeWarning,
        stacklevel=2,
    )
    from ._fallback import compute_rsi  # type: ignore[assignment]

# SMA kernel
try:
    from .sma import compute_sma
except ImportError:
    warnings.warn(
        "Cython SMA not available — using pure Python fallback. Performance degraded.",
        RuntimeWarning,
        stacklevel=2,
    )
    from ._fallback import compute_sma  # type: ignore[assignment]


__all__ = [
    "compute_vwap_close",
    "compute_vwap_typical",
    "compute_rsi",
    "compute_sma",
]
