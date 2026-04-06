from __future__ import annotations

import json
import logging
from typing import Any
from uuid import UUID

import redis.asyncio as redis
from litestar import WebSocket, websocket
from litestar.exceptions import WebSocketException
from sqlalchemy import select

from chattix.auth import decode_token
from chattix.config import get_settings
from chattix.db import SessionLocal
from chattix.models import Message, RoomMember, User
from chattix.services.messages import message_to_out
from chattix.services.redis_bus import (
    presence_clear,
    presence_refresh,
    presence_set,
    publish_global,
    publish_room,
)

logger = logging.getLogger(__name__)


@websocket("/ws")
async def chat_socket(socket: WebSocket) -> None:
    token = socket.query_params.get("token")
    if not token:
        raise WebSocketException(detail="token query parameter required", code=4401)
    user_id = decode_token(token)
    if user_id is None:
        raise WebSocketException(detail="invalid token", code=4401)

    settings = get_settings()
    manager = socket.app.state.connection_manager
    redis_client: redis.Redis = redis.from_url(settings.redis_url, decode_responses=True)

    async with SessionLocal() as session:
        user = await session.get(User, user_id)
        if user is None:
            raise WebSocketException(detail="user not found", code=4401)
        username = user.username

    await socket.accept()
    await manager.add_global(socket)
    await presence_set(
        redis_client,
        user_id=user_id,
        username=username,
        ttl_seconds=settings.presence_ttl_seconds,
    )
    await publish_global(
        redis_client,
        {
            "type": "presence",
            "user_id": str(user_id),
            "username": username,
            "status": "online",
        },
    )

    joined_rooms: set[str] = set()

    async def ensure_member(room_id: UUID) -> bool:
        async with SessionLocal() as session:
            q = await session.execute(
                select(RoomMember).where(
                    RoomMember.room_id == room_id,
                    RoomMember.user_id == user_id,
                )
            )
            return q.scalar_one_or_none() is not None

    try:
        while True:
            raw = await socket.receive_text()
            try:
                data: dict[str, Any] = json.loads(raw)
            except json.JSONDecodeError:
                await socket.send_text(json.dumps({"type": "error", "message": "invalid json"}))
                continue

            msg_type = data.get("type")
            if msg_type == "ping":
                await presence_refresh(redis_client, user_id, settings.presence_ttl_seconds)
                await socket.send_text(json.dumps({"type": "pong"}))
                continue

            if msg_type == "join_room":
                rid = data.get("room_id")
                if not rid:
                    await socket.send_text(
                        json.dumps({"type": "error", "message": "room_id required"})
                    )
                    continue
                try:
                    room_uuid = UUID(str(rid))
                except ValueError:
                    await socket.send_text(
                        json.dumps({"type": "error", "message": "invalid room_id"})
                    )
                    continue
                if not await ensure_member(room_uuid):
                    await socket.send_text(
                        json.dumps({"type": "error", "message": "not a member"})
                    )
                    continue
                rs = str(room_uuid)
                await manager.join_room(rs, socket)
                joined_rooms.add(rs)
                await socket.send_text(json.dumps({"type": "joined", "room_id": rs}))
                continue

            if msg_type == "leave_room":
                rid = data.get("room_id")
                left_id: str | None = None
                if rid:
                    try:
                        left_id = str(UUID(str(rid)))
                        await manager.leave_room(left_id, socket)
                        joined_rooms.discard(left_id)
                    except ValueError:
                        left_id = None
                await socket.send_text(json.dumps({"type": "left", "room_id": left_id}))
                continue

            if msg_type == "typing":
                rid = data.get("room_id")
                typing = bool(data.get("typing", False))
                if not rid:
                    continue
                try:
                    room_uuid = UUID(str(rid))
                except ValueError:
                    continue
                rs = str(room_uuid)
                if rs not in joined_rooms:
                    continue
                wire = {
                    "type": "typing",
                    "room_id": rs,
                    "user_id": str(user_id),
                    "username": username,
                    "typing": typing,
                }
                await publish_room(redis_client, room_uuid, wire)
                continue

            if msg_type == "send_message":
                rid = data.get("room_id")
                content = (data.get("content") or "").strip()
                attachment_url = data.get("attachment_url")
                if not rid or not content:
                    await socket.send_text(
                        json.dumps({"type": "error", "message": "room_id and content required"})
                    )
                    continue
                try:
                    room_uuid = UUID(str(rid))
                except ValueError:
                    await socket.send_text(
                        json.dumps({"type": "error", "message": "invalid room_id"})
                    )
                    continue
                rs = str(room_uuid)
                if rs not in joined_rooms:
                    await socket.send_text(
                        json.dumps({"type": "error", "message": "join room first"})
                    )
                    continue
                if not await ensure_member(room_uuid):
                    await socket.send_text(
                        json.dumps({"type": "error", "message": "not a member"})
                    )
                    continue
                if attachment_url is not None and not isinstance(attachment_url, str):
                    attachment_url = None
                if attachment_url and len(attachment_url) > 512:
                    await socket.send_text(
                        json.dumps({"type": "error", "message": "attachment_url too long"})
                    )
                    continue

                async with SessionLocal() as session:
                    msg = Message(
                        room_id=room_uuid,
                        user_id=user_id,
                        content=content[:10000],
                        attachment_url=attachment_url,
                    )
                    session.add(msg)
                    await session.commit()
                    await session.refresh(msg, ["author", "reactions"])
                    payload = await message_to_out(session, msg)

                wire = {"type": "message", "message": payload}
                await publish_room(redis_client, room_uuid, wire)
                continue

            await socket.send_text(json.dumps({"type": "error", "message": "unknown type"}))
    except WebSocketException:
        raise
    except Exception as e:  # noqa: BLE001
        logger.debug("ws closed: %s", e)
    finally:
        for rs in list(joined_rooms):
            await manager.leave_room(rs, socket)
        joined_rooms.clear()
        await manager.remove_global(socket)
        await presence_clear(redis_client, user_id)
        await publish_global(
            redis_client,
            {
                "type": "presence",
                "user_id": str(user_id),
                "username": username,
                "status": "offline",
            },
        )
        await redis_client.aclose()
