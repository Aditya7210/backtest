from __future__ import annotations

from datetime import datetime
import json
import os
from pathlib import Path
import threading
import time
from typing import Any

from dotenv import load_dotenv
from kiteconnect import KiteConnect, KiteTicker

from LiveMarket import COLLECTOR_STATUS_PATH
from LiveMarket.collector.bar_aggregator import IST, MinuteBarAggregator


_EQUITIES_HEADER = [
    "timestamp",
    "instrument_token",
    "tradingsymbol",
    "open",
    "high",
    "low",
    "close",
    "volume",
]
_OPTIONS_HEADER = [
    "timestamp",
    "instrument_token",
    "tradingsymbol",
    "strike",
    "expiry",
    "option_type",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "oi",
]
_VIX_HEADER = ["timestamp", "open", "high", "low", "close"]
_MAX_WS_TOKENS = 3000


def _now_iso() -> str:
    return datetime.now(tz=IST).isoformat(timespec="seconds")


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")
    temp_path.replace(path)


def _read_status(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _write_status(path: Path, **updates: Any) -> None:
    payload = _read_status(path)
    payload.update(updates)
    _atomic_write_json(path, payload)


def _is_process_alive(pid: int | None) -> bool:
    if pid is None or pid <= 0:
        return False

    # Linux: treat zombie processes as not alive so stale status does not block startup.
    if os.name != "nt":
        stat_path = Path("/proc") / str(pid) / "stat"
        if stat_path.is_file():
            try:
                fields = stat_path.read_text(encoding="utf-8", errors="replace").split()
                if len(fields) >= 3 and fields[2] == "Z":
                    return False
            except Exception:
                pass

    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _assert_not_duplicate_instance(status_path: Path) -> None:
    payload = _read_status(status_path)
    status = str(payload.get("status") or "").strip().lower()
    pid_raw = payload.get("pid")
    try:
        running_pid = int(pid_raw)
    except (TypeError, ValueError):
        running_pid = None

    if status == "running" and _is_process_alive(running_pid):
        raise RuntimeError(f"Collector is already running with PID {running_pid}")


def _append_csv_row(path: Path, header: list[str], row: list[Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    write_header = not path.exists() or path.stat().st_size == 0
    with path.open("a", encoding="utf-8", newline="") as handle:
        if write_header:
            handle.write(",".join(header) + "\n")
        handle.write(",".join(str(value) for value in row) + "\n")


def _load_kite_credentials() -> tuple[str, str]:
    env_path = Path(__file__).resolve().parents[2] / ".env"
    load_dotenv(dotenv_path=env_path, override=True)

    api_key = (
        (os.getenv("ZERODHA_API_KEY") or "").strip()
        or (os.getenv("api_key") or "").strip()
    )
    access_token = (
        (os.getenv("ZERODHA_ACCESS_TOKEN") or "").strip()
        or (os.getenv("access_token") or "").strip()
    )
    if not api_key:
        raise RuntimeError("Missing ZERODHA_API_KEY/api_key in .env")
    if not access_token:
        raise RuntimeError("Missing ZERODHA_ACCESS_TOKEN/access_token in .env")
    return api_key, access_token


def build_kite_client() -> KiteConnect:
    api_key, access_token = _load_kite_credentials()
    kite = KiteConnect(api_key=api_key)
    kite.set_access_token(access_token)
    return kite


def _flush_completed_bars(
    *,
    aggregator: MinuteBarAggregator,
    current_minute: datetime,
    day_dir: Path,
    equity_tokens: set[int],
    options_tokens: set[int],
    vix_token: int | None,
    token_to_symbol: dict[int, str],
    options_meta: dict[int, dict[str, Any]],
    state: dict[str, Any],
) -> int:
    completed = aggregator.get_completed_bars(current_minute)
    if not completed:
        return 0

    rows_written = 0
    equities_path = day_dir / "equities_1min.csv"
    options_path = day_dir / "options_1min.csv"
    vix_path = day_dir / "vix_1min.csv"

    for bar in completed:
        ts = bar.bar_start.isoformat()
        token = int(bar.instrument_token)
        if token in equity_tokens:
            symbol = str(token_to_symbol.get(token) or f"TOKEN_{token}")
            _append_csv_row(
                equities_path,
                _EQUITIES_HEADER,
                [
                    ts,
                    token,
                    symbol,
                    round(float(bar.open), 6),
                    round(float(bar.high), 6),
                    round(float(bar.low), 6),
                    round(float(bar.close), 6),
                    round(float(bar.volume), 6),
                ],
            )
            rows_written += 1
            continue

        if token in options_tokens:
            meta = options_meta.get(token, {})
            symbol = str(meta.get("tradingsymbol") or token_to_symbol.get(token) or f"TOKEN_{token}")
            _append_csv_row(
                options_path,
                _OPTIONS_HEADER,
                [
                    ts,
                    token,
                    symbol,
                    meta.get("strike", 0),
                    meta.get("expiry", ""),
                    meta.get("option_type", ""),
                    round(float(bar.open), 6),
                    round(float(bar.high), 6),
                    round(float(bar.low), 6),
                    round(float(bar.close), 6),
                    round(float(bar.volume), 6),
                    round(float(bar.oi), 6),
                ],
            )
            rows_written += 1
            continue

        if vix_token is not None and token == int(vix_token):
            _append_csv_row(
                vix_path,
                _VIX_HEADER,
                [
                    ts,
                    round(float(bar.open), 6),
                    round(float(bar.high), 6),
                    round(float(bar.low), 6),
                    round(float(bar.close), 6),
                ],
            )
            rows_written += 1

    if rows_written > 0:
        state["bars_written"] = int(state.get("bars_written", 0)) + rows_written
    return rows_written


def start(
    *,
    equity_tokens: set[int],
    options_tokens: set[int],
    vix_token: int | None,
    options_meta: dict[int, dict[str, Any]],
    token_to_symbol: dict[int, str],
    day_dir: Path,
    token_counts: dict[str, Any] | None = None,
    equity_universe: dict[str, Any] | None = None,
    status_path: Path = COLLECTOR_STATUS_PATH,
) -> None:
    _assert_not_duplicate_instance(status_path)

    api_key, access_token = _load_kite_credentials()
    aggregator = MinuteBarAggregator()
    status_lock = threading.Lock()
    state: dict[str, Any] = {
        "bars_written": 0,
        "last_tick_at": None,
        "last_error": None,
    }

    all_tokens: list[int] = sorted(
        {int(token) for token in equity_tokens}
        | {int(token) for token in options_tokens}
        | ({int(vix_token)} if vix_token is not None else set())
    )
    if not all_tokens:
        raise RuntimeError("No instruments available for WebSocket subscription")
    if len(all_tokens) > _MAX_WS_TOKENS:
        raise RuntimeError(
            "Too many tokens selected for one WebSocket connection: "
            f"{len(all_tokens)} > {_MAX_WS_TOKENS}"
        )

    ticker = KiteTicker(
        api_key,
        access_token,
        reconnect=True,
        reconnect_max_tries=100,
        reconnect_max_delay=10,
    )

    _write_status(
        status_path,
        status="running",
        pid=os.getpid(),
        started_at=_now_iso(),
        trading_date=day_dir.name,
        tokens_subscribed=len(all_tokens),
        token_counts=token_counts or {},
        equity_universe=equity_universe or {},
        bars_written=0,
        last_tick_at=None,
        last_error=None,
    )

    def _touch_status() -> None:
        with status_lock:
            _write_status(
                status_path,
                status="running",
                pid=os.getpid(),
                trading_date=day_dir.name,
                tokens_subscribed=len(all_tokens),
                token_counts=token_counts or {},
                equity_universe=equity_universe or {},
                bars_written=int(state.get("bars_written", 0)),
                last_tick_at=state.get("last_tick_at"),
                last_error=state.get("last_error"),
                updated_at=_now_iso(),
            )

    def on_connect(ws: KiteTicker, _response: dict[str, Any]) -> None:
        print(f"[ws_collector] connected. subscribing tokens={len(all_tokens)}")
        ws.subscribe(all_tokens)
        equities = sorted({int(token) for token in equity_tokens})
        derivatives: list[int] = sorted(
            {int(token) for token in options_tokens}
            | ({int(vix_token)} if vix_token is not None else set())
        )
        if equities:
            ws.set_mode(ws.MODE_QUOTE, equities)
        if derivatives:
            ws.set_mode(ws.MODE_FULL, derivatives)

    def on_ticks(_ws: KiteTicker, ticks: list[dict[str, Any]]) -> None:
        if not ticks:
            return
        with status_lock:
            state["last_tick_at"] = _now_iso()
        for tick in ticks:
            try:
                token = int(tick.get("instrument_token"))
            except Exception:
                continue

            ltp = float(tick.get("last_price") or 0.0)
            volume = tick.get("volume_traded")
            if volume is None:
                volume = tick.get("volume")
            oi = tick.get("oi") or 0.0

            tick_ts = tick.get("timestamp")
            if tick_ts is None:
                tick_ts = datetime.now(tz=IST)
            elif isinstance(tick_ts, datetime):
                if tick_ts.tzinfo is None:
                    tick_ts = tick_ts.replace(tzinfo=IST)
            else:
                try:
                    parsed = datetime.fromisoformat(str(tick_ts))
                except Exception:
                    parsed = datetime.now(tz=IST)
                tick_ts = parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=IST)

            aggregator.update(
                token=token,
                ltp=ltp,
                session_volume=volume,
                oi=oi,
                tick_time=tick_ts,
            )

    def on_error(_ws: KiteTicker, code: int, reason: str) -> None:
        message = f"[{code}] {reason}"
        print(f"[ws_collector] error: {message}")
        with status_lock:
            state["last_error"] = message
        _touch_status()

    def on_reconnect(_ws: KiteTicker, attempts_count: int) -> None:
        print(f"[ws_collector] reconnect attempt={attempts_count}")

    def on_close(_ws: KiteTicker, code: int, reason: str) -> None:
        print(f"[ws_collector] closed code={code} reason={reason}")

    ticker.on_connect = on_connect
    ticker.on_ticks = on_ticks
    ticker.on_error = on_error
    ticker.on_reconnect = on_reconnect
    ticker.on_close = on_close

    ticker.connect(threaded=True)
    print("[ws_collector] ticker thread started")

    last_status_update_epoch = 0.0
    try:
        while True:
            current_minute = datetime.now(tz=IST)
            rows = _flush_completed_bars(
                aggregator=aggregator,
                current_minute=current_minute,
                day_dir=day_dir,
                equity_tokens=equity_tokens,
                options_tokens=options_tokens,
                vix_token=vix_token,
                token_to_symbol=token_to_symbol,
                options_meta=options_meta,
                state=state,
            )
            now_epoch = time.time()
            if rows > 0 or (now_epoch - last_status_update_epoch) >= 5.0:
                _touch_status()
                last_status_update_epoch = now_epoch
            time.sleep(1.0)
    except KeyboardInterrupt:
        print("[ws_collector] interrupted by user")
    except Exception as exc:
        with status_lock:
            state["last_error"] = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        try:
            ticker.close()
        except Exception:
            pass
        _write_status(
            status_path,
            status="stopped",
            pid=os.getpid(),
            stopped_at=_now_iso(),
            trading_date=day_dir.name,
            tokens_subscribed=len(all_tokens),
            token_counts=token_counts or {},
            equity_universe=equity_universe or {},
            bars_written=int(state.get("bars_written", 0)),
            last_tick_at=state.get("last_tick_at"),
            last_error=state.get("last_error"),
            updated_at=_now_iso(),
        )


__all__ = ["build_kite_client", "start"]
