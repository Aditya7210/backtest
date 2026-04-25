from __future__ import annotations

from datetime import date, datetime, time
import importlib.util
import os
from pathlib import Path
from typing import Any

import pandas as pd

from . import zerodha_auth


def resolve_env_path() -> Path:
    return Path(__file__).resolve().parents[3] / ".env"


def get_zerodha_credentials(session_access_token: str | None = None) -> tuple[str, str]:
    api_key = os.getenv("ZERODHA_API_KEY", "").strip()
    access_token = (session_access_token or "").strip()

    if not access_token:
        env_path = resolve_env_path()
        if env_path.is_file():
            try:
                env_data = zerodha_auth.load_env_variables(str(env_path))
            except Exception:
                env_data = {}
            if not api_key:
                api_key = str(env_data.get("api_key") or "").strip()
            access_token = str(env_data.get("access_token") or "").strip()

    if not access_token:
        access_token = os.getenv("ZERODHA_ACCESS_TOKEN", "").strip()

    return api_key, access_token


def normalize_interval(interval: str, *, default: str = "15minute") -> str:
    normalized = str(interval or "").strip().lower()
    return normalized or default


def create_queue_item(
    *,
    selected_instrument: dict[str, Any] | None,
    interval: str,
    from_day: date | None,
    to_day: date | None,
    requested_continuous: bool,
    oi: bool,
) -> dict[str, Any]:
    if not isinstance(selected_instrument, dict) or not selected_instrument:
        raise ValueError("Select a valid instrument before adding to queue.")
    if from_day is None or to_day is None:
        raise ValueError("Please select valid dates before adding to queue.")
    if from_day > to_day:
        raise ValueError("From Date must be earlier than To Date.")

    return {
        "instrument": dict(selected_instrument),
        "interval": normalize_interval(interval),
        "from": from_day,
        "to": to_day,
        "continuous": bool(requested_continuous),
        "oi": bool(oi),
    }


def _extract_selected_instrument_fields(
    selected_instrument: dict[str, Any] | None,
) -> tuple[int, str, str]:
    if not isinstance(selected_instrument, dict) or not selected_instrument:
        raise ValueError("Please select a valid instrument from suggestions")

    symbol = str(selected_instrument.get("tradingsymbol", "")).strip().upper()
    if not symbol:
        raise ValueError("Please select a valid instrument from suggestions")

    instrument_token_raw = selected_instrument.get("instrument_token")
    if instrument_token_raw in (None, ""):
        raise ValueError("Instrument token not found")

    try:
        instrument_token = int(instrument_token_raw)
    except (TypeError, ValueError) as exc:
        raise ValueError("Instrument token not found") from exc

    instrument_type = str(selected_instrument.get("instrument_type", "")).strip().upper()
    return instrument_token, symbol, instrument_type


def fetch_zerodha_dataframe(
    *,
    service: Any,
    selected_instrument: dict[str, Any] | None,
    from_day: date | None,
    to_day: date | None,
    interval: str,
    requested_continuous: bool,
    oi: bool,
) -> pd.DataFrame:
    if from_day is None or to_day is None:
        raise ValueError("Please select valid dates")
    if from_day > to_day:
        raise ValueError("From Date must be earlier than To Date")

    instrument_token, _, instrument_type = _extract_selected_instrument_fields(
        selected_instrument
    )
    normalized_interval = normalize_interval(interval)
    continuous = bool(requested_continuous) and instrument_type == "FUT"

    df = service.fetch_data(
        instrument_token=instrument_token,
        from_date=datetime.combine(from_day, time.min),
        to_date=datetime.combine(to_day, time.max),
        interval=normalized_interval,
        continuous=continuous,
        oi=bool(oi),
    )
    return df.copy()


def build_zerodha_queue_tasks(
    *,
    queue: list[dict[str, Any]],
    service: Any,
    selected_strategy: type[Any],
) -> list[dict[str, Any]]:
    if not queue:
        raise RuntimeError("Zerodha queue is empty.")

    tasks: list[dict[str, Any]] = []
    for item in queue:
        instrument = item.get("instrument")
        interval = normalize_interval(str(item.get("interval", "15minute")))
        from_day = item.get("from")
        to_day = item.get("to")
        requested_continuous = bool(item.get("continuous", False))
        oi = bool(item.get("oi", False))

        df = fetch_zerodha_dataframe(
            service=service,
            selected_instrument=instrument if isinstance(instrument, dict) else None,
            from_day=from_day,
            to_day=to_day,
            interval=interval,
            requested_continuous=requested_continuous,
            oi=oi,
        )

        symbol = str((instrument or {}).get("tradingsymbol", "")).strip().upper()
        tasks.append(
            {
                "mode": "api",
                "data": df,
                "symbol": symbol,
                "interval": interval,
                "strategy_class": selected_strategy,
            }
        )
    return tasks


def build_csv_tasks(
    selected_files: list[str] | tuple[str, ...],
    selected_strategy: type[Any],
) -> list[dict[str, object]]:
    return [
        {
            "mode": "csv",
            "data": file_id,
            "symbol": str(file_id).split("/")[-1].replace(".csv", ""),
            "strategy_class": selected_strategy,
        }
        for file_id in selected_files
    ]


def load_strategy_class(strategy_file_path: str, class_name: str) -> type[Any]:
    if not strategy_file_path or not class_name:
        raise ValueError("Invalid strategy selection")

    strategy_root = Path(__file__).resolve().parents[3] / "Strategies" / "Strategy_codes"
    raw_path = Path(strategy_file_path)
    resolved_path = (
        raw_path.resolve()
        if raw_path.is_absolute()
        else (strategy_root / raw_path).resolve()
    )

    if not resolved_path.is_file():
        raise ValueError(f"Strategy file not found: {strategy_file_path}")

    spec = importlib.util.spec_from_file_location("strategy_module", resolved_path)
    if spec is None or spec.loader is None:
        raise ValueError("Unable to load strategy module")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    if not hasattr(module, class_name):
        raise ValueError(f"Strategy class '{class_name}' not found")

    strategy_class = getattr(module, class_name)
    if not isinstance(strategy_class, type):
        raise ValueError(f"Strategy class '{class_name}' is invalid")

    return strategy_class


__all__ = [
    "build_csv_tasks",
    "build_zerodha_queue_tasks",
    "create_queue_item",
    "fetch_zerodha_dataframe",
    "get_zerodha_credentials",
    "load_strategy_class",
    "normalize_interval",
    "resolve_env_path",
]
