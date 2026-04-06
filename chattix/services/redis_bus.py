from __future__ import annotations

import asyncio
import json
import logging
from typing import TYPE_CHECKING, Any
from uuid import UUID

import redis.asyncio as redis

if TYPE_CHECKING:
    from chattix.services.connection_manager import ConnectionManager

logger = logging.getLogger(__name__)

GLOBAL_CHANNEL = "chattix:global"
ROOM_PREFIX = "chattix:room:"


def room_channel(room_id: UUID) -> str:
    return f"{ROOM_PREFIX}{room_id}"


async def publish_room(redis_client: redis.Redis, room_id: UUID, wire: dict[str, Any]) -> None:
    body = json.dumps({"room_id": str(room_id), "wire": wire})
    await redis_client.publish(room_channel(room_id), body)


async def publish_global(redis_client: redis.Redis, wire: dict[str, Any]) -> None:
    await redis_client.publish(GLOBAL_CHANNEL, json.dumps({"wire": wire}))


async def redis_listener_loop(
    redis_url: str,
    manager: ConnectionManager,
    stop: asyncio.Event,
) -> None:
    client = redis.from_url(redis_url, decode_responses=True)
    pubsub = client.pubsub()
    await pubsub.subscribe(GLOBAL_CHANNEL)
    await pubsub.psubscribe(f"{ROOM_PREFIX}*")
    try:
        async for msg in pubsub.listen():
            if stop.is_set():
                break
            mtype = msg.get("type")
            if mtype == "message":
                raw = msg.get("data")
                if raw is None:
                    continue
                try:
                    data = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                wire = data.get("wire")
                if isinstance(wire, dict):
                    await manager.broadcast_global(wire)
            elif mtype == "pmessage":
                raw = msg.get("data")
                if raw is None:
                    continue
                try:
                    data = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                room_id = data.get("room_id")
                wire = data.get("wire")
                if isinstance(room_id, str) and isinstance(wire, dict):
                    await manager.broadcast_room(room_id, wire)
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.exception("redis listener crashed")
    finally:
        await pubsub.unsubscribe(GLOBAL_CHANNEL)
        await pubsub.punsubscribe(f"{ROOM_PREFIX}*")
        await pubsub.close()
        await client.aclose()


async def presence_set(
    redis_client: redis.Redis,
    *,
    user_id: UUID,
    username: str,
    ttl_seconds: int,
) -> None:
    key = f"chattix:presence:{user_id}"
    await redis_client.set(key, username, ex=ttl_seconds)


async def presence_clear(redis_client: redis.Redis, user_id: UUID) -> None:
    await redis_client.delete(f"chattix:presence:{user_id}")


async def presence_refresh(redis_client: redis.Redis, user_id: UUID, ttl_seconds: int) -> None:
    key = f"chattix:presence:{user_id}"
    await redis_client.expire(key, ttl_seconds)


async def list_online(redis_client: redis.Redis) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    async for key in redis_client.scan_iter("chattix:presence:*"):
        uid = key.split(":")[-1]
        username = await redis_client.get(key)
        if username:
            out.append({"user_id": uid, "username": username})
    return out
