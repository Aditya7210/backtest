from __future__ import annotations

from datetime import date
import json
import os

from LiveMarket import COLLECTOR_STATUS_PATH, ensure_live_market_dirs
from LiveMarket.collector import prev_close_loader, token_loader, trading_calendar, ws_collector
from LiveMarket.time_utils import now_ist_iso, today_ist


def _write_not_trading_day_status(today: date) -> None:
    payload = {
        "status": "not_trading_day",
        "pid": os.getpid(),
        "date": today.isoformat(),
        "updated_at": now_ist_iso(),
    }
    COLLECTOR_STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
    COLLECTOR_STATUS_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def main() -> int:
    today = today_ist()
    if not trading_calendar.is_trading_day(today):
        print("[run_collector] Today is not a trading day. Collector will not start.")
        _write_not_trading_day_status(today)
        return 0

    day_dir = ensure_live_market_dirs(trading_date=today)

    token_bundle = token_loader.load_all_tokens()
    equity_tokens = set(token_bundle.get("equity_tokens", set()))
    options_tokens = set(token_bundle.get("options_tokens", set()))
    vix_token = token_bundle.get("vix_token")
    options_meta = dict(token_bundle.get("options_meta", {}))
    token_to_symbol = dict(token_bundle.get("token_to_symbol", {}))
    equity_symbol_by_token = dict(token_bundle.get("equity_symbol_by_token", {}))
    token_counts = dict(token_bundle.get("token_counts", {}))
    equity_universe = dict(token_bundle.get("equity_universe", {}))

    kite = ws_collector.build_kite_client()
    prev_close_loader.fetch_and_save(
        equity_symbol_by_token,
        kite,
        day_dir / "prev_close.json",
    )

    ws_collector.start(
        equity_tokens=equity_tokens,
        options_tokens=options_tokens,
        vix_token=vix_token,
        options_meta=options_meta,
        token_to_symbol=token_to_symbol,
        day_dir=day_dir,
        token_counts=token_counts,
        equity_universe=equity_universe,
        status_path=COLLECTOR_STATUS_PATH,
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(0)
    except Exception as exc:
        print(f"[run_collector] fatal error: {type(exc).__name__}: {exc}")
        raise SystemExit(1)
