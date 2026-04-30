from __future__ import annotations

import json
from pathlib import Path
import time
from typing import Any

from LiveMarket.time_utils import now_ist_iso, today_ist


QUOTE_BATCH_SIZE = 500


def _is_today_snapshot(path: Path) -> bool:
    if not path.is_file():
        return False
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return False
    snapshot_date = str(payload.get("date") or "").strip()
    return snapshot_date == today_ist().isoformat()


def _cache_covers_tokens(payload: dict[str, Any], expected_tokens: set[int]) -> tuple[bool, int]:
    data = payload.get("data", {})
    if not isinstance(data, dict):
        return False, len(expected_tokens)

    cached_tokens: set[int] = set()
    for token in data.keys():
        try:
            cached_tokens.add(int(token))
        except (TypeError, ValueError):
            continue

    missing_count = len(expected_tokens - cached_tokens)
    return missing_count == 0, missing_count


def load_cached_prev_close(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _chunk_symbols(symbols: list[str], chunk_size: int = QUOTE_BATCH_SIZE) -> list[list[str]]:
    return [symbols[i : i + chunk_size] for i in range(0, len(symbols), chunk_size)]


def _quote_with_retry_once(kite_client: Any, symbols: list[str]) -> dict[str, Any]:
    keys = [f"NSE:{symbol}" for symbol in symbols]
    try:
        response = kite_client.quote(keys)
        return response if isinstance(response, dict) else {}
    except Exception as exc:
        message = str(exc).lower()
        if "429" in message or "rate" in message:
            time.sleep(1.0)
            response = kite_client.quote(keys)
            return response if isinstance(response, dict) else {}
        raise


def fetch_and_save_prev_close(
    *,
    equity_symbol_by_token: dict[int, str],
    kite_client: Any,
    output_path: Path,
    force: bool = False,
) -> dict[str, Any]:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    expected_tokens = {int(token) for token in equity_symbol_by_token.keys()}

    if (not force) and _is_today_snapshot(output_path):
        cached = load_cached_prev_close(output_path)
        if cached is not None:
            cache_ok, missing_count = _cache_covers_tokens(cached, expected_tokens)
            if cache_ok:
                print("[prev_close_loader] Using cached prev_close.json for today.")
                return cached
            print(
                "[prev_close_loader] Cached prev_close.json is incomplete for the "
                f"current universe. missing_tokens={missing_count}; refreshing."
            )

    token_by_symbol = {
        symbol: token
        for token, symbol in equity_symbol_by_token.items()
        if symbol
    }
    symbols = sorted(token_by_symbol.keys())
    batches = _chunk_symbols(symbols, QUOTE_BATCH_SIZE)
    print(f"[prev_close_loader] Fetching prev close in {len(batches)} batches of {QUOTE_BATCH_SIZE}.")

    values_by_token: dict[str, float] = {}
    failed_symbols: list[str] = []
    for batch in batches:
        try:
            quoted = _quote_with_retry_once(kite_client, batch)
        except Exception as exc:
            print(f"[prev_close_loader] Batch fetch failed ({len(batch)} symbols): {exc}")
            failed_symbols.extend(batch)
            continue

        for symbol in batch:
            key = f"NSE:{symbol}"
            payload = quoted.get(key, {})
            ohlc = payload.get("ohlc", {}) if isinstance(payload, dict) else {}
            close_raw = ohlc.get("close")
            try:
                close_val = float(close_raw)
            except (TypeError, ValueError):
                close_val = 0.0
            if close_val <= 0:
                continue
            token = token_by_symbol.get(symbol)
            if token is None:
                continue
            values_by_token[str(int(token))] = close_val

    payload = {
        "generated_at": now_ist_iso(),
        "date": today_ist().isoformat(),
        "expected_tokens": len(expected_tokens),
        "loaded_tokens": len(values_by_token),
        "missing_tokens": max(0, len(expected_tokens) - len(values_by_token)),
        "data": values_by_token,
    }
    temp_path = output_path.with_suffix(".tmp")
    temp_path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")
    temp_path.replace(output_path)

    print(
        "[prev_close_loader] Prev close loaded: "
        f"{len(values_by_token)} tokens, failed batches symbols={len(failed_symbols)}"
    )
    return payload


def fetch_and_save(
    equity_symbol_by_token: dict[int, str],
    kite_client: Any,
    output_path: Path,
) -> dict[str, Any]:
    return fetch_and_save_prev_close(
        equity_symbol_by_token=equity_symbol_by_token,
        kite_client=kite_client,
        output_path=output_path,
    )


__all__ = [
    "QUOTE_BATCH_SIZE",
    "fetch_and_save",
    "fetch_and_save_prev_close",
    "load_cached_prev_close",
]
