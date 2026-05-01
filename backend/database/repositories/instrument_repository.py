"""Repository for instrument master data."""
from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from backend.database.connection import get_db


def _project_root() -> Path:
    here = Path(__file__).resolve()
    return here.parents[3]


def _instrument_csv_path() -> Path:
    return _project_root() / "Data" / "instrument_mapper_data" / "zerodha_instruments_latest.csv"


async def find_by_token(token: int) -> dict[str, Any] | None:
    db = get_db()
    return await db.instruments.find_one({"instrument_token": token})


async def find_by_symbol(symbol: str) -> dict[str, Any] | None:
    db = get_db()
    return await db.instruments.find_one(
        {"tradingsymbol": {"$regex": f"^{symbol}$", "$options": "i"}}
    )


async def search(query: str, limit: int = 50) -> list[dict[str, Any]]:
    """Search instruments by tradingsymbol (case-insensitive partial match)."""
    db = get_db()
    cursor = db.instruments.find(
        {"tradingsymbol": {"$regex": query, "$options": "i"}},
    ).limit(limit)
    return await cursor.to_list(length=limit)


async def get_all_equity() -> list[dict[str, Any]]:
    db = get_db()
    cursor = db.instruments.find(
        {"segment": "NSE", "instrument_type": "EQ"}
    )
    return await cursor.to_list(length=None)


async def search_with_fallback(query: str, limit: int = 50) -> dict[str, Any]:
    """Search MongoDB instruments first, fallback to cached CSV if Mongo is empty."""
    db = get_db()
    mongo_count = await db.instruments.count_documents({})
    q = query.strip()
    if not q:
        return {"items": [], "source": "none", "warning": "Empty search query."}

    if mongo_count > 0:
        items = await search(q, limit)
        return {"items": items, "source": "mongo", "warning": None}

    csv_path = _instrument_csv_path()
    if not csv_path.exists():
        return {
            "items": [],
            "source": "none",
            "warning": "Instrument master is empty in MongoDB and cached instrument CSV was not found.",
        }

    needle = q.upper()
    rows: list[dict[str, Any]] = []
    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            symbol = str(row.get("tradingsymbol", "")).upper()
            name = str(row.get("name", "")).upper()
            if needle not in symbol and needle not in name:
                continue
            try:
                token = int(float(str(row.get("instrument_token", "0"))))
            except Exception:
                continue
            rows.append({
                "instrument_token": token,
                "tradingsymbol": row.get("tradingsymbol", ""),
                "name": row.get("name", ""),
                "segment": row.get("segment", ""),
                "exchange": row.get("exchange", ""),
                "instrument_type": row.get("instrument_type", ""),
                "expiry": row.get("expiry", ""),
                "strike": row.get("strike", ""),
            })
            if len(rows) >= limit:
                break

    return {
        "items": rows,
        "source": "csv_cache",
        "warning": "MongoDB instruments collection is empty. Results are from cached CSV.",
    }
