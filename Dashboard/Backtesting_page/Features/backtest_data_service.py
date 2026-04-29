from __future__ import annotations

import ast
from datetime import date, datetime, time
import hashlib
import importlib.util
import os
from pathlib import Path
import sys
from typing import Any

import pandas as pd

from . import zerodha_auth


def resolve_project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def resolve_env_path() -> Path:
    return resolve_project_root() / ".env"


def resolve_zerodha_cache_dir() -> Path:
    return (
        resolve_project_root()
        / "Data"
        / "testing_data"
        / "Data_files"
        / "Zerodha_data"
    )


def resolve_strategy_root() -> Path:
    return (resolve_project_root() / "Strategies" / "Strategy_codes").resolve()


def resolve_live_data_root() -> Path:
    return resolve_project_root() / "Data" / "live_market"


def resolve_strategy_file_path(strategy_file_path: str) -> Path:
    raw_value = str(strategy_file_path or "").strip()
    if not raw_value:
        raise ValueError("Invalid strategy path")

    strategy_root = resolve_strategy_root()
    raw_path = Path(raw_value)
    candidate = raw_path if raw_path.is_absolute() else (strategy_root / raw_path)

    try:
        resolved_path = candidate.resolve(strict=True)
    except FileNotFoundError as exc:
        raise ValueError(f"Strategy file not found: {strategy_file_path}") from exc
    except OSError as exc:
        raise ValueError("Invalid strategy path") from exc

    try:
        resolved_path.relative_to(strategy_root)
    except ValueError as exc:
        raise ValueError("Invalid strategy path") from exc

    if not resolved_path.is_file():
        raise ValueError(f"Strategy file not found: {strategy_file_path}")
    if resolved_path.suffix.lower() != ".py":
        raise ValueError("Invalid strategy path")

    return resolved_path


def _callable_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return ""


def _iter_assignment_targets(node: ast.AST) -> list[ast.AST]:
    if isinstance(node, ast.Assign):
        return list(node.targets)
    if isinstance(node, ast.AnnAssign):
        return [node.target]
    if isinstance(node, ast.AugAssign):
        return [node.target]
    return []


def _validate_strategy_source_safety(resolved_path: Path) -> None:
    try:
        source = resolved_path.read_text(encoding="utf-8")
    except Exception as exc:
        raise ValueError("Unable to read strategy source") from exc

    try:
        tree = ast.parse(source, filename=str(resolved_path))
    except SyntaxError as exc:
        raise ValueError(f"Strategy file has syntax errors: {exc}") from exc

    blocked_calls = {"eval", "exec", "compile", "__import__"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            called_name = _callable_name(node.func)
            if called_name in blocked_calls:
                raise ValueError(
                    "Strategy contains disallowed dynamic execution primitives"
                )

        if isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
            for target in _iter_assignment_targets(node):
                if isinstance(target, ast.Name) and target.id == "__import__":
                    raise ValueError("Invalid strategy code: import override is not allowed")
                if isinstance(target, ast.Attribute) and target.attr == "__import__":
                    raise ValueError("Invalid strategy code: import override is not allowed")


def get_zerodha_credentials(session_access_token: str | None = None) -> tuple[str, str]:
    api_key = ""
    access_token = (session_access_token or "").strip()

    env_path = resolve_env_path()
    env_data: dict[str, str | None] = {}
    if env_path.is_file():
        try:
            env_data = zerodha_auth.load_env_variables(str(env_path))
        except Exception:
            env_data = {}

    api_key = str(env_data.get("api_key") or "").strip()
    if not access_token:
        access_token = str(env_data.get("access_token") or "").strip()

    if not api_key:
        api_key = os.getenv("ZERODHA_API_KEY", "").strip()
    if not access_token:
        access_token = os.getenv("ZERODHA_ACCESS_TOKEN", "").strip()

    return api_key, access_token


def get_zerodha_session_metadata() -> dict[str, str]:
    env_path = resolve_env_path()
    env_data: dict[str, str | None] = {}
    if env_path.is_file():
        try:
            env_data = zerodha_auth.load_env_variables(str(env_path))
        except Exception:
            env_data = {}

    # Source of truth is .env; process env is fallback only.
    api_key = str(env_data.get("api_key") or "").strip()
    access_token = str(env_data.get("access_token") or "").strip()
    token_date = str(env_data.get("token_date") or "").strip()

    if not api_key:
        api_key = os.getenv("ZERODHA_API_KEY", "").strip()
    if not access_token:
        access_token = os.getenv("ZERODHA_ACCESS_TOKEN", "").strip()
    if not token_date:
        token_date = (os.getenv("ZERODHA_TOKEN_DATE") or "").strip()

    return {
        "api_key": api_key,
        "access_token": access_token,
        "token_date": token_date,
    }


def validate_zerodha_session() -> tuple[str, str]:
    metadata = get_zerodha_session_metadata()
    api_key = str(metadata.get("api_key") or "").strip()
    access_token = str(metadata.get("access_token") or "").strip()
    token_date = str(metadata.get("token_date") or "").strip()

    if not api_key or not access_token:
        raise RuntimeError("Zerodha session expired. Please login again.")

    if not token_date:
        raise RuntimeError("Zerodha session expired. Please login again.")

    if zerodha_auth.is_token_expired(token_date):
        raise RuntimeError("Zerodha session expired. Please login again.")

    if token_date != date.today().isoformat():
        raise RuntimeError("Zerodha session expired. Please login again.")

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
    selected_strategy: type[Any],
) -> list[dict[str, Any]]:
    if not queue:
        raise RuntimeError("Zerodha queue is empty.")

    tasks: list[dict[str, Any]] = []
    for item in queue:
        instrument = item.get("instrument")
        instrument_dict = instrument if isinstance(instrument, dict) else None
        interval = normalize_interval(str(item.get("interval", "15minute")))
        from_day = item.get("from")
        to_day = item.get("to")
        requested_continuous = bool(item.get("continuous", False))
        oi = bool(item.get("oi", False))

        instrument_token, symbol, instrument_type = _extract_selected_instrument_fields(
            instrument_dict
        )
        if from_day is None or to_day is None:
            raise ValueError("Please select valid dates for queued API task.")
        if from_day > to_day:
            raise ValueError("From Date must be earlier than To Date for queued API task.")

        start_date = datetime.combine(from_day, time.min)
        end_date = datetime.combine(to_day, time.max)
        continuous = bool(requested_continuous) and instrument_type == "FUT"

        tasks.append(
            {
                "mode": "api",
                "symbol": symbol,
                "instrument_token": instrument_token,
                "instrument_type": instrument_type,
                "interval": interval,
                "start_date": start_date,
                "end_date": end_date,
                "continuous": continuous,
                "oi": oi,
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
            "symbol": Path(str(file_id)).stem,
            "strategy_class": selected_strategy,
        }
        for file_id in selected_files
    ]


def ensure_instrument_mapper_ready() -> tuple[bool, str]:
    data_dir = (
        resolve_project_root()
        / "Data"
        / "instrument_mapper_data"
    )
    latest_path = data_dir / "zerodha_instruments_latest.csv"
    metadata_path = data_dir / "metadata.json"

    if latest_path.is_file() and latest_path.stat().st_size > 0:
        return True, "Instrument mapper data ready."

    try:
        api_key, access_token = validate_zerodha_session()
    except Exception as exc:
        return (
            False,
            (
                "Instrument mapper data missing. "
                f"Auto-update skipped: {exc}"
            ),
        )

    try:
        from . import instrument_mapper as instrument_mapper_feature

        mapper = instrument_mapper_feature.InstrumentMapper(
            api_key=api_key,
            access_token=access_token,
            auto_update=False,
        )
        mapper.update_instruments()
    except Exception as exc:
        return False, f"Instrument mapper auto-update failed: {exc}"

    if latest_path.is_file() and latest_path.stat().st_size > 0:
        return True, "Instrument mapper updated successfully."

    if not metadata_path.is_file():
        return False, "Instrument mapper update did not create metadata."

    return False, "Instrument mapper data is still unavailable after update."


def load_strategy_class(strategy_file_path: str, class_name: str) -> type[Any]:
    if not strategy_file_path or not class_name:
        raise ValueError("Invalid strategy selection")
    if not str(class_name).strip().isidentifier():
        raise ValueError("Invalid strategy class name")

    resolved_path = resolve_strategy_file_path(strategy_file_path)
    _validate_strategy_source_safety(resolved_path)

    module_name = (
        "strategy_module_"
        + hashlib.sha1(str(resolved_path).encode("utf-8")).hexdigest()
    )
    spec = importlib.util.spec_from_file_location(module_name, resolved_path)
    if spec is None or spec.loader is None:
        raise ValueError("Unable to load strategy module")

    module = importlib.util.module_from_spec(spec)
    previous_module = sys.modules.get(module_name)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        if previous_module is None:
            sys.modules.pop(module_name, None)
        else:
            sys.modules[module_name] = previous_module

    if not hasattr(module, class_name):
        raise ValueError(f"Strategy class '{class_name}' not found")

    strategy_class = getattr(module, class_name)
    if not isinstance(strategy_class, type):
        raise ValueError(f"Strategy class '{class_name}' is invalid")

    return strategy_class


def validate_live_data_selection(
    date_str: str,
    instrument_token: int,
    tradingsymbol: str,
    timeframe: str,
    data_type: str,
    live_data_root: Path | None = None,
) -> tuple[bool, str]:
    normalized_date = str(date_str or "").strip()
    normalized_timeframe = str(timeframe or "").strip().lower()
    normalized_data_type = str(data_type or "").strip().lower()
    normalized_symbol = str(tradingsymbol or "").strip().upper()
    if not normalized_date:
        return False, "No live market date selected."
    if normalized_data_type not in {"equities", "options", "vix"}:
        return False, "Invalid live market data type."
    if not normalized_timeframe:
        return False, "No live market timeframe selected."

    root = resolve_live_data_root() if live_data_root is None else Path(live_data_root)
    daily_dir = root / "daily" / normalized_date
    if not daily_dir.is_dir():
        return False, f"No data collected for {normalized_date}."

    source_csv = daily_dir / f"{normalized_data_type}_{normalized_timeframe}.csv"
    if not source_csv.is_file():
        return False, f"{normalized_timeframe} data not available for {normalized_date}. Try 1min."

    try:
        frame = pd.read_csv(source_csv)
    except Exception as exc:
        return False, f"Unable to read selected live data file: {exc}"
    if frame.empty:
        return False, "Selected live data file is empty."

    if normalized_data_type == "vix":
        required = {"timestamp", "open", "high", "low", "close"}
        missing = required - set(frame.columns)
        if missing:
            return False, f"Selected VIX data missing columns: {sorted(missing)}"
        return True, ""

    required = {"instrument_token", "tradingsymbol"}
    missing = required - set(frame.columns)
    if missing:
        return False, f"Selected live data missing columns: {sorted(missing)}"

    token_series = pd.to_numeric(frame["instrument_token"], errors="coerce")
    token_matches = token_series == int(instrument_token)
    if bool(token_matches.any()):
        return True, ""

    symbol_series = frame["tradingsymbol"].astype(str).str.strip().str.upper()
    if normalized_symbol and bool((symbol_series == normalized_symbol).any()):
        return True, ""

    return (
        False,
        f"No rows found for selected instrument in {normalized_data_type}_{normalized_timeframe}.csv.",
    )


__all__ = [
    "build_csv_tasks",
    "build_zerodha_queue_tasks",
    "create_queue_item",
    "ensure_instrument_mapper_ready",
    "fetch_zerodha_dataframe",
    "get_zerodha_credentials",
    "get_zerodha_session_metadata",
    "load_strategy_class",
    "normalize_interval",
    "resolve_project_root",
    "resolve_live_data_root",
    "resolve_zerodha_cache_dir",
    "resolve_env_path",
    "resolve_strategy_file_path",
    "resolve_strategy_root",
    "validate_zerodha_session",
    "validate_live_data_selection",
]
