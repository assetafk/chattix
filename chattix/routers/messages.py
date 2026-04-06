from uuid import UUID

import redis.asyncio as redis
from litestar import Request, Router, delete, get, patch, post
from litestar.exceptions import ClientException
from litestar.params import Parameter
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from chattix.config import get_settings
from chattix.db import SessionLocal
from chattix.dependencies import current_user_id_from_request
from chattix.models import Message, MessageReaction, RoomMember, User
from chattix.schemas import MessageOut, MessagePatch, ReactionBody
from chattix.services.messages import load_message_with_relations, message_to_out
from chattix.services.redis_bus import publish_room


def _redis() -> redis.Redis:
    return redis.from_url(get_settings().redis_url, decode_responses=True)


async def _ensure_member(session, room_id: UUID, user_id: UUID) -> None:
    q = await session.execute(
        select(RoomMember).where(RoomMember.room_id == room_id, RoomMember.user_id == user_id)
    )
    if q.scalar_one_or_none() is None:
        raise ClientException(detail="Not a member of this room", status_code=403)


@get("/rooms/{room_id:uuid}/messages")
async def list_messages(
    request: Request,
    room_id: UUID,
    limit: int = Parameter(default=50, ge=1, le=200),
    before_id: UUID | None = None,
) -> list[MessageOut]:
    user_id = await current_user_id_from_request(request)
    async with SessionLocal() as session:
        await _ensure_member(session, room_id, user_id)
        stmt = (
            select(Message)
            .options(
                selectinload(Message.author),
                selectinload(Message.reactions).selectinload(MessageReaction.user),
            )
            .where(Message.room_id == room_id)
            .order_by(Message.created_at.desc())
            .limit(limit)
        )
        if before_id:
            anchor = await session.get(Message, before_id)
            if anchor and anchor.room_id == room_id:
                stmt = stmt.where(Message.created_at < anchor.created_at)
        result = await session.execute(stmt)
        rows = list(result.scalars().all())
        rows.reverse()
        out: list[MessageOut] = []
        for m in rows:
            d = await message_to_out(session, m)
            out.append(MessageOut.model_validate(d))
        return out


@patch("/messages/{message_id:uuid}")
async def edit_message(request: Request, message_id: UUID, data: MessagePatch) -> MessageOut:
    user_id = await current_user_id_from_request(request)
    r = _redis()
    async with SessionLocal() as session:
        msg = await load_message_with_relations(session, message_id)
        if msg is None:
            raise ClientException(detail="Message not found", status_code=404)
        if msg.user_id != user_id:
            raise ClientException(detail="Forbidden", status_code=403)
        if msg.deleted:
            raise ClientException(detail="Message deleted", status_code=400)
        from datetime import datetime, timezone

        msg.content = data.content
        msg.edited_at = datetime.now(timezone.utc)
        await session.commit()
        await session.refresh(msg)
        payload = await message_to_out(session, msg)
        wire = {"type": "message_edited", "message": payload}
        await publish_room(r, msg.room_id, wire)
    await r.aclose()
    return MessageOut.model_validate(payload)


@delete("/messages/{message_id:uuid}")
async def delete_message(request: Request, message_id: UUID) -> None:
    user_id = await current_user_id_from_request(request)
    r = _redis()
    async with SessionLocal() as session:
        msg = await load_message_with_relations(session, message_id)
        if msg is None:
            raise ClientException(detail="Message not found", status_code=404)
        if msg.user_id != user_id:
            raise ClientException(detail="Forbidden", status_code=403)
        msg.deleted = True
        msg.content = ""
        await session.commit()
        wire = {"type": "message_deleted", "room_id": str(msg.room_id), "message_id": str(msg.id)}
        await publish_room(r, msg.room_id, wire)
    await r.aclose()


@post("/messages/{message_id:uuid}/reactions")
async def add_reaction(request: Request, message_id: UUID, data: ReactionBody) -> MessageOut:
    user_id = await current_user_id_from_request(request)
    r = _redis()
    async with SessionLocal() as session:
        msg = await load_message_with_relations(session, message_id)
        if msg is None:
            raise ClientException(detail="Message not found", status_code=404)
        await _ensure_member(session, msg.room_id, user_id)
        exists = await session.execute(
            select(MessageReaction).where(
                MessageReaction.message_id == message_id,
                MessageReaction.user_id == user_id,
                MessageReaction.emoji == data.emoji,
            )
        )
        if exists.scalar_one_or_none() is None:
            session.add(
                MessageReaction(message_id=message_id, user_id=user_id, emoji=data.emoji)
            )
            await session.commit()
        await session.refresh(msg)
        payload = await message_to_out(session, msg)
        user = await session.get(User, user_id)
        wire = {
            "type": "reaction_added",
            "room_id": str(msg.room_id),
            "message_id": str(message_id),
            "emoji": data.emoji,
            "user_id": str(user_id),
            "username": user.username if user else "",
            "message": payload,
        }
        await publish_room(r, msg.room_id, wire)
    await r.aclose()
    return MessageOut.model_validate(payload)


@delete("/messages/{message_id:uuid}/reactions", status_code=200)
async def remove_reaction(
    request: Request,
    message_id: UUID,
    emoji: str = Parameter(query="emoji", min_length=1, max_length=32),
) -> MessageOut:
    user_id = await current_user_id_from_request(request)
    r = _redis()
    async with SessionLocal() as session:
        msg = await load_message_with_relations(session, message_id)
        if msg is None:
            raise ClientException(detail="Message not found", status_code=404)
        await _ensure_member(session, msg.room_id, user_id)
        result = await session.execute(
            select(MessageReaction).where(
                MessageReaction.message_id == message_id,
                MessageReaction.user_id == user_id,
                MessageReaction.emoji == emoji,
            )
        )
        row = result.scalar_one_or_none()
        if row:
            await session.delete(row)
            await session.commit()
        await session.refresh(msg)
        payload = await message_to_out(session, msg)
        wire = {
            "type": "reaction_removed",
            "room_id": str(msg.room_id),
            "message_id": str(message_id),
            "emoji": emoji,
            "user_id": str(user_id),
            "message": payload,
        }
        await publish_room(r, msg.room_id, wire)
    await r.aclose()
    return MessageOut.model_validate(payload)


messages_router = Router(path="", route_handlers=[list_messages, edit_message, delete_message, add_reaction, remove_reaction])
