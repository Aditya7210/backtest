"""Live tick repository feature."""
from __future__ import annotations

from typing import Any

from backend.database.connection import get_db


async def get_latest_tick(instrument_token: int) -> dict[str, Any] | None:
    db = get_db()
    doc = await db.live_ticks.find_one({"instrument_token": int(instrument_token)})
    if not doc:
        return None
    doc.pop("_id", None)
    return doc
