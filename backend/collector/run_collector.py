"""Collector entry point — runnable as `python -m backend.collector.run_collector`."""
from __future__ import annotations

import sys
from pathlib import Path

# Ensure project root is on path
PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from backend.utils.time_utils import today_ist


def main():
    from backend.collector.ws_collector import start, build_kite_client
    from backend.collector.token_loader import load_all_tokens

    print("[run_collector] Loading tokens...")
    token_bundle = load_all_tokens()

    trading_date = today_ist().isoformat()
    print(f"[run_collector] Trading date: {trading_date}")

    start(
        equity_tokens=token_bundle["equity_tokens"],
        options_tokens=token_bundle["options_tokens"],
        vix_token=token_bundle["vix_token"],
        options_meta=token_bundle["options_meta"],
        token_to_symbol=token_bundle["token_to_symbol"],
        trading_date=trading_date,
        token_counts=token_bundle["token_counts"],
    )


if __name__ == "__main__":
    main()
