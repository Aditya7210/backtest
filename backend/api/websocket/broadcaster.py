"""Broadcaster helper — pushes data to WebSocket channels from background tasks."""
from __future__ import annotations

from typing import Any

from backend.api.websocket.manager import manager


async def broadcast_live_update(data: dict[str, Any]) -> None:
    """Push a live market update to all connected live clients."""
    await manager.broadcast("live", {"type": "live_update", **data})


async def broadcast_backtest_progress(task_id: str, data: dict[str, Any]) -> None:
    """Push backtest progress to the task-specific channel."""
    channel = f"backtest_{task_id}"
    await manager.broadcast(channel, {"type": "progress", **data})
