"""
Synchronous MongoDB connection via PyMongo — used by collector and calculator subprocesses.

These subprocesses run in threads (KiteTicker) or plain loops (calculator),
NOT inside an asyncio event loop. Using Motor here would crash (E-03).
"""
from __future__ import annotations

from pymongo import MongoClient
from pymongo.database import Database

from backend.config import settings

_sync_client: MongoClient | None = None
_sync_db: Database | None = None


def get_sync_db() -> Database:
    """Return a synchronous pymongo Database instance (lazy init)."""
    global _sync_client, _sync_db
    if _sync_db is None:
        _sync_client = MongoClient(settings.MONGO_URI)
        _sync_db = _sync_client.get_default_database()
    return _sync_db


def close_sync_db() -> None:
    """Close the synchronous client."""
    global _sync_client, _sync_db
    if _sync_client is not None:
        _sync_client.close()
        _sync_client = None
        _sync_db = None
