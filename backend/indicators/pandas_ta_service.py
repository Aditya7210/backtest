"""Pandas-TA indicator discovery and computation service."""
from __future__ import annotations

from dataclasses import dataclass
import inspect
import math
from typing import Any

import pandas as pd


@dataclass(slots=True)
class IndicatorMetadata:
    name: str
    label: str
    category: str
    pane: str
    params: list[dict[str, Any]]
    presets: list[dict[str, Any]]


OVERLAY_NAMES = {
    "alma", "dema", "ema", "fwma", "hma", "hwma", "linreg", "midpoint", "midprice",
    "ohlc4", "pwma", "rma", "sinwma", "sma", "ssf", "swma", "tema", "trima", "vidya",
    "vwap", "vwma", "wcp", "wma", "zlma", "bbands", "donchian", "kc", "mcgd", "supertrend",
    "atr", "natr", "aberration", "accbands", "alligator", "chandelier_exit",
}

OSCILLATOR_NAMES = {
    "ao", "apo", "bias", "bop", "brar", "cci", "cfo", "cg", "cmo", "coppock", "cti", "er",
    "fisher", "inertia", "kdj", "kst", "macd", "mom", "ppo", "psl", "pgo", "qqe", "roc",
    "rsi", "rsx", "rvgi", "slope", "smi", "squeeze", "squeeze_pro", "stc", "stoch", "stochf",
    "stochrsi", "tsi", "uo", "willr", "adx", "dm", "vortex", "vhf",
}

DEFAULT_COLORS = [
    "#2962FF",
    "#FF9800",
    "#9C27B0",
    "#00BCD4",
    "#7C3AED",
    "#16A34A",
    "#EF4444",
    "#0EA5E9",
]

PARAM_OVERRIDES: dict[str, dict[str, Any]] = {
    "ema": {
        "params": [
            {"name": "length", "type": "number", "default": 20, "min": 1},
            {"name": "offset", "type": "number", "default": 0},
        ],
        "presets": [
            {"label": "EMA 5", "params": {"length": 5}},
            {"label": "EMA 20", "params": {"length": 20}},
            {"label": "EMA 50", "params": {"length": 50}},
            {"label": "EMA 200", "params": {"length": 200}},
        ],
    },
    "sma": {
        "params": [
            {"name": "length", "type": "number", "default": 20, "min": 1},
            {"name": "offset", "type": "number", "default": 0},
        ],
    },
    "rsi": {
        "params": [{"name": "length", "type": "number", "default": 14, "min": 1}],
    },
    "macd": {
        "params": [
            {"name": "fast", "type": "number", "default": 12, "min": 1},
            {"name": "slow", "type": "number", "default": 26, "min": 1},
            {"name": "signal", "type": "number", "default": 9, "min": 1},
        ],
    },
    "bbands": {
        "params": [
            {"name": "length", "type": "number", "default": 20, "min": 1},
            {"name": "std", "type": "number", "default": 2},
        ],
    },
    "vwap": {
        "params": [{"name": "offset", "type": "number", "default": 0}],
    },
}


def _import_pandas_ta():
    try:
        import pandas_ta as ta  # type: ignore[import-not-found]
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError("pandas-ta is not available in backend environment.") from exc
    return ta


def _safe_default(value: Any) -> Any:
    if value is inspect.Signature.empty:
        return None
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return None


def _param_type_from_default(default: Any) -> str:
    if isinstance(default, bool):
        return "boolean"
    if isinstance(default, int):
        return "number"
    if isinstance(default, float):
        return "number"
    return "string"


def _signature_params(func: Any) -> list[dict[str, Any]]:
    params: list[dict[str, Any]] = []
    try:
        sig = inspect.signature(func)
    except (TypeError, ValueError):
        return params

    skip = {"open_", "high", "low", "close", "volume", "adj_close", "open", "ohlc", "kwargs"}
    for name, p in sig.parameters.items():
        if name in skip:
            continue
        if p.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
            continue
        default = _safe_default(p.default)
        entry: dict[str, Any] = {
            "name": name,
            "type": _param_type_from_default(default),
            "default": default,
        }
        if name in {"length", "fast", "slow", "signal"}:
            entry["min"] = 1
        params.append(entry)
    return params


def _to_label(name: str) -> str:
    return name.replace("_", " ").upper()


def _pane_for_indicator(name: str) -> str:
    lname = name.lower()
    if lname in OSCILLATOR_NAMES:
        return "oscillator"
    return "price"


def _category_for_indicator(name: str, inverse_map: dict[str, str]) -> str:
    return inverse_map.get(name.lower(), "Other")


def discover_indicator_metadata() -> list[IndicatorMetadata]:
    ta = _import_pandas_ta()
    names: set[str] = set()
    category_inverse: dict[str, str] = {}

    category_obj = getattr(ta, "Category", None)
    if isinstance(category_obj, dict):
        for category, members in category_obj.items():
            if not isinstance(members, (list, tuple, set)):
                continue
            for member in members:
                indicator_name = str(member).strip().lower()
                if not indicator_name:
                    continue
                names.add(indicator_name)
                category_inverse[indicator_name] = str(category)

    module_level_indicators = getattr(ta, "indicators", None)
    if callable(module_level_indicators):
        try:
            discovered = module_level_indicators(as_list=True)
            if isinstance(discovered, (list, tuple)):
                for item in discovered:
                    names.add(str(item).strip().lower())
        except TypeError:
            try:
                discovered = module_level_indicators()
                if isinstance(discovered, (list, tuple)):
                    for item in discovered:
                        names.add(str(item).strip().lower())
            except Exception:
                pass
        except Exception:
            pass

    if not names:
        for attr_name in dir(ta):
            if attr_name.startswith("_"):
                continue
            lowered = attr_name.lower()
            if lowered in {"analysisindicators", "imports", "maps", "ma", "version"}:
                continue
            attr = getattr(ta, attr_name, None)
            if callable(attr):
                names.add(lowered)

    out: list[IndicatorMetadata] = []
    for name in sorted(names):
        func = getattr(ta, name, None)
        if not callable(func):
            continue
        if name in PARAM_OVERRIDES:
            params = PARAM_OVERRIDES[name]["params"]
            presets = PARAM_OVERRIDES[name].get("presets", [])
        else:
            params = _signature_params(func)
            presets = []
        out.append(
            IndicatorMetadata(
                name=name,
                label=_to_label(name),
                category=_category_for_indicator(name, category_inverse),
                pane=_pane_for_indicator(name),
                params=params,
                presets=presets,
            )
        )

    # Keep common overlays/oscillators grouped first for practical UX ordering.
    out.sort(key=lambda item: (item.category, item.label))
    return out


def _normalize_bars_dataframe(bars: list[dict[str, Any]]) -> pd.DataFrame:
    df = pd.DataFrame(bars)
    if df.empty:
        return df

    rename_map = {
        "timestamp": "timestamp",
        "open": "open",
        "high": "high",
        "low": "low",
        "close": "close",
        "volume": "volume",
    }
    df = df.rename(columns=rename_map)
    required_cols = ["timestamp", "open", "high", "low", "close", "volume"]
    for col in required_cols:
        if col not in df.columns:
            raise ValueError(f"Missing required column for indicator computation: {col}")

    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce", utc=True)
    df = df.dropna(subset=["timestamp"])
    df = df.sort_values("timestamp")
    df = df.drop_duplicates(subset=["timestamp"], keep="last")
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["open", "high", "low", "close"])
    df = df.set_index("timestamp")
    if df.index.tz is not None:
        df.index = df.index.tz_convert("Asia/Kolkata")
    else:
        df.index = df.index.tz_localize("Asia/Kolkata")
    return df


def _sanitize_params(params: dict[str, Any]) -> dict[str, Any]:
    clean: dict[str, Any] = {}
    for key, value in params.items():
        if isinstance(value, str):
            stripped = value.strip()
            if stripped == "":
                continue
            # coerce numeric strings when appropriate
            if stripped.replace(".", "", 1).replace("-", "", 1).isdigit():
                if "." in stripped:
                    clean[key] = float(stripped)
                else:
                    clean[key] = int(stripped)
                continue
            if stripped.lower() in {"true", "false"}:
                clean[key] = stripped.lower() == "true"
                continue
            clean[key] = stripped
        else:
            clean[key] = value
    return clean


def _series_to_points(series: pd.Series) -> list[dict[str, Any]]:
    if series.empty:
        return []
    clean = pd.to_numeric(series, errors="coerce")
    mask = clean.notna() & clean.map(lambda x: math.isfinite(float(x)))
    filtered = clean[mask]
    out: list[dict[str, Any]] = []
    for ts, value in filtered.items():
        ts_value = pd.Timestamp(ts)
        out.append({"time": int(ts_value.timestamp()), "value": float(value)})
    return out


def compute_indicators(
    *,
    bars: list[dict[str, Any]],
    indicators: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[str]]:
    ta = _import_pandas_ta()
    df = _normalize_bars_dataframe(bars)
    if df.empty:
        return [], ["No bars available for indicator computation."]

    series_output: list[dict[str, Any]] = []
    warnings: list[str] = []

    for idx, spec in enumerate(indicators):
        name = str(spec.get("name", "")).strip().lower()
        if not name:
            continue
        func = getattr(ta, name, None)
        if not callable(func):
            warnings.append(f"Indicator not found: {name}")
            continue

        params = _sanitize_params(dict(spec.get("params") or {}))
        kwargs = dict(params)
        try:
            sig = inspect.signature(func)
            sig_params = sig.parameters
        except (TypeError, ValueError):
            sig_params = {}

        if "open_" in sig_params:
            kwargs["open_"] = df["open"]
        if "open" in sig_params:
            kwargs["open"] = df["open"]
        if "high" in sig_params:
            kwargs["high"] = df["high"]
        if "low" in sig_params:
            kwargs["low"] = df["low"]
        if "close" in sig_params:
            kwargs["close"] = df["close"]
        if "volume" in sig_params:
            kwargs["volume"] = df["volume"]

        try:
            result = func(**kwargs)
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"{name}: {type(exc).__name__}: {exc}")
            continue

        pane = _pane_for_indicator(name)
        color = DEFAULT_COLORS[idx % len(DEFAULT_COLORS)]
        if isinstance(result, pd.Series):
            points = _series_to_points(result)
            if not points:
                warnings.append(f"{name}: indicator produced no plottable values.")
                continue
            series_output.append({
                "id": f"{name}-{idx}",
                "name": name,
                "label": result.name or _to_label(name),
                "pane": pane,
                "params": params,
                "color": color,
                "points": points,
            })
            continue

        if isinstance(result, pd.DataFrame):
            if result.empty:
                warnings.append(f"{name}: indicator produced no plottable values.")
                continue
            for col_idx, col_name in enumerate(result.columns):
                points = _series_to_points(result[col_name])
                if not points:
                    continue
                series_output.append({
                    "id": f"{name}-{idx}-{col_idx}",
                    "name": name,
                    "label": str(col_name),
                    "pane": pane,
                    "params": params,
                    "color": DEFAULT_COLORS[(idx + col_idx) % len(DEFAULT_COLORS)],
                    "points": points,
                })
            if not any(s["name"] == name and s["id"].startswith(f"{name}-{idx}-") for s in series_output):
                warnings.append(f"{name}: indicator produced no plottable values.")
            continue

        warnings.append(f"{name}: unsupported indicator output type.")

    return series_output, warnings
