from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
import time
from typing import Any

from LiveMarket import COLLECTOR_STATUS_PATH, DAILY_ROOT, SNAPSHOTS_ROOT
from LiveMarket.calculations import ad_calculator, atm_oi_calculator, pcr_calculator, snapshot_writer, vix_reader, vwap_calculator
from LiveMarket.calculations.bar_resampler import resample_to_timeframes


_RESAMPLE_TIMEFRAMES = [3, 5, 10, 15, 30, 60]


def _read_collector_status(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _resolve_day_dir(status_path: Path = COLLECTOR_STATUS_PATH) -> Path | None:
    status_payload = _read_collector_status(status_path)
    day_name = str(status_payload.get("trading_date") or "").strip()
    if day_name:
        candidate = DAILY_ROOT / day_name
        if candidate.is_dir():
            return candidate

    available_days = sorted([p for p in DAILY_ROOT.glob("*") if p.is_dir()])
    if not available_days:
        return None
    return available_days[-1]


def _build_vwap_snapshot(day_dir: Path) -> dict[str, Any]:
    timeframe_payload = vwap_calculator.compute_all_timeframes(day_dir, base_name="equities")
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "data": timeframe_payload,
    }


def run_once() -> dict[str, Any]:
    day_dir = _resolve_day_dir()
    if day_dir is None:
        return {
            "status": "no_data",
            "message": "No daily live-market directory found.",
        }

    equities_1min = day_dir / "equities_1min.csv"
    options_1min = day_dir / "options_1min.csv"
    vix_1min = day_dir / "vix_1min.csv"
    prev_close = day_dir / "prev_close.json"

    if equities_1min.is_file():
        resample_to_timeframes(equities_1min, _RESAMPLE_TIMEFRAMES, day_dir, group_by_token=True)
    if options_1min.is_file():
        resample_to_timeframes(options_1min, _RESAMPLE_TIMEFRAMES, day_dir, group_by_token=True)
    if vix_1min.is_file():
        resample_to_timeframes(vix_1min, _RESAMPLE_TIMEFRAMES, day_dir, group_by_token=False)

    vwap_snapshot = _build_vwap_snapshot(day_dir)
    ad_snapshot = ad_calculator.compute(equities_1min, prev_close)
    pcr_snapshot = pcr_calculator.compute(options_1min)
    atm_oi_snapshot = atm_oi_calculator.compute(options_1min, equities_1min)
    vix_snapshot = vix_reader.read(vix_1min)

    snapshot_writer.write_all(
        SNAPSHOTS_ROOT,
        vwap_snapshot=vwap_snapshot,
        ad_snapshot=ad_snapshot,
        pcr_snapshot=pcr_snapshot,
        atm_oi_snapshot=atm_oi_snapshot,
        vix_snapshot=vix_snapshot,
    )

    return {
        "status": "ok",
        "trading_date": day_dir.name,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
    }


def start_loop(interval_seconds: float = 60.0) -> None:
    wait_seconds = max(5.0, float(interval_seconds))
    print(f"[calculation_runner] started interval={wait_seconds:.1f}s")
    while True:
        started_at = time.time()
        try:
            result = run_once()
            print(f"[calculation_runner] cycle result: {result}")
        except KeyboardInterrupt:
            print("[calculation_runner] interrupted by user")
            raise
        except Exception as exc:
            print(f"[calculation_runner] cycle failed: {type(exc).__name__}: {exc}")

        elapsed = time.time() - started_at
        sleep_time = max(0.0, wait_seconds - elapsed)
        if sleep_time > 0:
            time.sleep(sleep_time)


__all__ = ["run_once", "start_loop"]
