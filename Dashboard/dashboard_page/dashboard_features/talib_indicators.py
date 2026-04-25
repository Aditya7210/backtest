from __future__ import annotations

from typing import Any

import pandas as pd
import talib

_OVERLAY_GROUPS = {"Overlap Studies", "Price Transform", "Pattern Recognition"}


def get_loadable_indicators(df_price: pd.DataFrame | None) -> list[str]:
    """
    Return TA-Lib indicator names that can run with the currently loaded price columns.
    """

    if df_price is None or df_price.empty:
        return []

    input_columns = {str(col).lower() for col in df_price.columns}
    can_load: list[str] = []

    for ind_name in [func for func in talib.get_functions() if not func.startswith("CDL")]:
        try:
            func = getattr(talib.abstract, ind_name)
            reqs = func.info.get("input_names", {})
            if _inputs_satisfied(reqs, input_columns):
                can_load.append(ind_name)
        except Exception:
            continue

    return can_load


def split_indicators(
    selected_indicators: list[str],
) -> tuple[list[tuple[str, Any]], list[tuple[str, Any]]]:
    """
    Split selected indicators into overlays and oscillators based on TA-Lib group metadata.
    """

    overlays: list[tuple[str, Any]] = []
    oscillators: list[tuple[str, Any]] = []

    for ind_name in selected_indicators:
        try:
            func = getattr(talib.abstract, ind_name)
            if func.info.get("group") in _OVERLAY_GROUPS:
                overlays.append((ind_name, func))
            else:
                oscillators.append((ind_name, func))
        except Exception:
            continue

    return overlays, oscillators


def build_talib_inputs(df_price: pd.DataFrame) -> dict[str, Any]:
    """
    Build TA-Lib input mapping from OHLCV dataframe.
    """

    return {
        "open": df_price["Open"].values,
        "high": df_price["High"].values,
        "low": df_price["Low"].values,
        "close": df_price["Close"].values,
        "volume": df_price.get("Volume", pd.Series(dtype=float)).values,
    }


def run_indicator(func: Any, inputs: dict[str, Any]) -> Any | None:
    """
    Execute a TA-Lib abstract function safely.
    """

    try:
        return func(inputs)
    except Exception:
        return None


def _inputs_satisfied(reqs: dict[str, Any], input_columns: set[str]) -> bool:
    for requirement in reqs.values():
        if isinstance(requirement, str):
            req_lower = requirement.lower()
            if req_lower == "price":
                if "close" not in input_columns:
                    return False
            elif req_lower not in input_columns:
                return False
        elif isinstance(requirement, (tuple, list)):
            for req in requirement:
                if str(req).lower() not in input_columns:
                    return False
    return True


__all__ = [
    "build_talib_inputs",
    "get_loadable_indicators",
    "run_indicator",
    "split_indicators",
]
