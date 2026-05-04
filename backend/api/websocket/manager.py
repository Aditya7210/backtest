"""WebSocket manager for live data and backtest streaming."""
from __future__ import annotations

import asyncio
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect

from backend.api.websocket.live_stream_payload import build_live_stream_payload
from backend.database.connection import get_db
from backend.database.repositories.live_tick_repository import get_latest_tick


class ConnectionManager:
    """Track active WebSocket connections by channel (e.g. 'live', task_id)."""

    def __init__(self) -> None:
        self._connections: dict[str, list[WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, channel: str, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            self._connections.setdefault(channel, []).append(ws)

    async def disconnect(self, channel: str, ws: WebSocket) -> None:
        async with self._lock:
            conns = self._connections.get(channel, [])
            if ws in conns:
                conns.remove(ws)
            if not conns and channel in self._connections:
                del self._connections[channel]

    async def broadcast(self, channel: str, data: dict[str, Any]) -> None:
        """Broadcast JSON to all connections on a channel."""
        async with self._lock:
            conns = list(self._connections.get(channel, []))

        dead: list[WebSocket] = []
        for ws in conns:
            try:
                await ws.send_json(data)
            except Exception:
                dead.append(ws)

        for ws in dead:
            await self.disconnect(channel, ws)


manager = ConnectionManager()


async def ws_live_endpoint(ws: WebSocket) -> None:
    """Live market socket: status + market view + snapshot updates."""
    await manager.connect("live", ws)
    try:
        while True:
            try:
                db = get_db()
                payload = await build_live_stream_payload(db)
                await ws.send_json(payload)
            except WebSocketDisconnect:
                break
            except Exception:
                pass
            await asyncio.sleep(1.0)
    except WebSocketDisconnect:
        pass
    finally:
        await manager.disconnect("live", ws)


async def ws_backtest_endpoint(ws: WebSocket, task_id: str) -> None:
    """Backtest progress streaming WebSocket."""
    channel = f"backtest_{task_id}"
    await manager.connect(channel, ws)
    try:
        while True:
            try:
                db = get_db()
                doc = await db.backtest_results.find_one({"task_id": task_id})
                if doc:
                    doc.pop("_id", None)
                    await ws.send_json({"type": "progress", "data": doc})
                    if doc.get("status") in ("COMPLETED", "FAILED"):
                        await ws.send_json({"type": "complete", "data": doc})
                        break
            except WebSocketDisconnect:
                break
            except Exception:
                pass
            await asyncio.sleep(0.5)
    except WebSocketDisconnect:
        pass
    finally:
        await manager.disconnect(channel, ws)


async def ws_market_tick_endpoint(ws: WebSocket, instrument_token: int) -> None:
    """Token-scoped tick streaming endpoint for live chart updates."""
    channel = f"tick_{int(instrument_token)}"
    await manager.connect(channel, ws)
    try:
        while True:
            try:
                tick = await get_latest_tick(int(instrument_token))
                if tick:
                    ts = tick.get("timestamp")
                    if ts:
                        tick["time"] = int(ts.timestamp())
                    await ws.send_json(
                        {
                            "type": "tick_update",
                            "instrument_token": int(instrument_token),
                            "tick": tick,
                        }
                    )
            except WebSocketDisconnect:
                break
            except Exception:
                pass
            await asyncio.sleep(1.0)
    except WebSocketDisconnect:
        pass
    finally:
        await manager.disconnect(channel, ws)
