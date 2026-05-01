"""WebSocket manager for live data and backtest streaming (E-05 compliant)."""
from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect

from backend.database.connection import get_db


class ConnectionManager:
    """Track active WebSocket connections by channel (e.g. 'live', task_id)."""

    def __init__(self):
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
    """Live market data WebSocket — polls snapshots every second and sends updates."""
    await manager.connect("live", ws)
    try:
        while True:
            try:
                db = get_db()
                # Fetch latest snapshots and broadcast
                snapshot_types = ["vwap", "ad", "pcr", "atm_oi", "vix"]
                payload: dict[str, Any] = {"type": "snapshot_update"}
                for st in snapshot_types:
                    doc = await db.snapshots.find_one(
                        {"snapshot_type": st},
                        sort=[("trading_date", -1)],
                    )
                    if doc:
                        doc.pop("_id", None)
                        payload[st] = doc.get("data", {})
                    else:
                        payload[st] = {}

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
    """Backtest progress streaming WebSocket (E-05: long-running)."""
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
