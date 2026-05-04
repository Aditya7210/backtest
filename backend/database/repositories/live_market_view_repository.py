"""Live market view feature repository.

Builds a spot + futures basis view for NIFTY/BANKNIFTY using live tick data.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from backend.database.connection import get_db
from backend.utils.time_utils import now_ist_iso


def _as_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except Exception:
        return None


def _iso_or_none(value: Any) -> str | None:
    if isinstance(value, datetime):
        return value.isoformat()
    return None


def _resolve_index_underlying(symbol: str) -> str:
    up = str(symbol or "").strip().upper()
    if up in {"NIFTY 50", "NIFTY"}:
        return "NIFTY"
    if up in {"NIFTY BANK", "BANKNIFTY"}:
        return "BANKNIFTY"
    return ""


async def get_live_market_view() -> dict[str, Any]:
    db = get_db()
    docs = await db.live_ticks.find(
        {"instrument_type": {"$in": ["index", "future"]}},
        {"_id": 0},
    ).to_list(length=None)

    view: dict[str, dict[str, Any]] = {
        "NIFTY": {"spot": None, "futures": []},
        "BANKNIFTY": {"spot": None, "futures": []},
    }

    for doc in docs:
        instrument_type = str(doc.get("instrument_type") or "").strip().lower()
        symbol = str(doc.get("tradingsymbol") or "").strip().upper()
        underlying = str(doc.get("underlying") or "").strip().upper()
        price = _as_float(doc.get("last_price"))
        updated_at = _iso_or_none(doc.get("timestamp"))

        if instrument_type == "index":
            resolved = _resolve_index_underlying(symbol)
            if not resolved:
                continue
            view[resolved]["spot"] = {
                "price": price,
                "tradingsymbol": symbol,
                "updated_at": updated_at,
            }
            continue

        if instrument_type == "future" and underlying in view:
            view[underlying]["futures"].append(
                {
                    "price": price,
                    "tradingsymbol": symbol,
                    "expiry": doc.get("expiry"),
                    "oi": _as_float(doc.get("oi")) or 0.0,
                    "updated_at": updated_at,
                }
            )

    for underlying in view:
        view[underlying]["futures"].sort(key=lambda row: str(row.get("expiry") or ""))

    return {"generated_at": now_ist_iso(), "market_view": view}

