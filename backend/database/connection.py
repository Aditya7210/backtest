"""
Async MongoDB connection via Motor — used by FastAPI routes only.

The client is created once at startup and closed at shutdown via FastAPI lifespan.
Never create per-request clients (E-03: Motor must use event loop).
"""
from __future__ import annotations

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from backend.config import settings

_client: AsyncIOMotorClient | None = None
_db: AsyncIOMotorDatabase | None = None


async def connect_db() -> None:
    """Create the Motor client. Call once at FastAPI startup."""
    global _client, _db
    _client = AsyncIOMotorClient(settings.MONGO_URI)
    _db = _client.get_default_database()
    # Verify connectivity
    await _client.admin.command("ping")
    print("[database] MongoDB connected via Motor (async)")


async def close_db() -> None:
    """Close the Motor client. Call once at FastAPI shutdown."""
    global _client, _db
    if _client is not None:
        _client.close()
        _client = None
        _db = None
    print("[database] MongoDB connection closed")


def get_db() -> AsyncIOMotorDatabase:
    """Return the database instance. Raises if not connected."""
    if _db is None:
        raise RuntimeError("MongoDB not connected — call connect_db() first")
    return _db
