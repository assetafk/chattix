from __future__ import annotations

import asyncio
import json
import logging
from collections import defaultdict
from typing import Any

from litestar.connection import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    """In-memory room subscriptions per worker. Redis pub/sub fans out across workers."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._rooms: dict[str, set[WebSocket]] = defaultdict(set)
        self._global_clients: set[WebSocket] = set()

    async def add_global(self, ws: WebSocket) -> None:
        async with self._lock:
            self._global_clients.add(ws)

    async def remove_global(self, ws: WebSocket) -> None:
        async with self._lock:
            self._global_clients.discard(ws)

    async def join_room(self, room_id: str, ws: WebSocket) -> None:
        async with self._lock:
            self._rooms[room_id].add(ws)

    async def leave_room(self, room_id: str, ws: WebSocket) -> None:
        async with self._lock:
            bucket = self._rooms.get(room_id)
            if not bucket:
                return
            bucket.discard(ws)
            if not bucket:
                del self._rooms[room_id]

    async def leave_all_rooms(self, ws: WebSocket) -> None:
        async with self._lock:
            empty: list[str] = []
            for rid, clients in self._rooms.items():
                clients.discard(ws)
                if not clients:
                    empty.append(rid)
            for rid in empty:
                del self._rooms[rid]

    async def broadcast_room(self, room_id: str, message: dict[str, Any]) -> None:
        payload = json.dumps(message)
        async with self._lock:
            targets = list(self._rooms.get(room_id, ()))
        await self._send_many(targets, payload)

    async def broadcast_global(self, message: dict[str, Any]) -> None:
        payload = json.dumps(message)
        async with self._lock:
            targets = list(self._global_clients)
        await self._send_many(targets, payload)

    async def _send_many(self, sockets: list[WebSocket], payload: str) -> None:
        for ws in sockets:
            try:
                await ws.send_text(payload)
            except Exception as e:  # noqa: BLE001
                logger.debug("ws send failed: %s", e)
