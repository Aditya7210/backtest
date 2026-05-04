"""Collector entry point — runnable as `python -m backend.collector.run_collector`."""
from __future__ import annotations

import sys
import time
from pathlib import Path

import pandas as pd

# Ensure project root is on path
PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from backend.utils.time_utils import today_ist


def refresh_instruments_if_stale(kite, path: Path, max_age_hours: int = 12) -> None:
    path = path.resolve()
    if path.is_file():
        age_hours = (time.time() - path.stat().st_mtime) / 3600.0
        if age_hours < max_age_hours:
            return
    try:
        instruments = kite.instruments()
        frame = pd.DataFrame(instruments)
        if frame.empty:
            print("[run_collector] WARNING: Zerodha instruments refresh returned empty; using existing file.")
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        frame.to_csv(path, index=False)
        print(f"[run_collector] Instruments CSV refreshed: {len(frame)} rows at {path}")
    except Exception as exc:  # noqa: BLE001
        print(f"[run_collector] WARNING: instrument refresh failed ({type(exc).__name__}: {exc}); using existing file if present.")


def main():
    from backend.collector.ws_collector import start, build_kite_client
    from backend.collector.token_loader import load_all_tokens, resolve_default_instruments_path

    csv_path = resolve_default_instruments_path()
    kite = build_kite_client()
    refresh_instruments_if_stale(kite, csv_path, max_age_hours=12)
    print("[run_collector] Loading tokens...")
    token_bundle = load_all_tokens(csv_path)

    trading_date = today_ist().isoformat()
    print(f"[run_collector] Trading date: {trading_date}")

    start(
        equity_tokens=token_bundle["equity_tokens"],
        futures_tokens=token_bundle["futures_tokens"],
        options_tokens=token_bundle["options_tokens"],
        vix_token=token_bundle["vix_token"],
        futures_meta=token_bundle["futures_meta"],
        options_meta=token_bundle["options_meta"],
        token_to_symbol=token_bundle["token_to_symbol"],
        trading_date=trading_date,
        token_counts=token_bundle["token_counts"],
    )


if __name__ == "__main__":
    main()
