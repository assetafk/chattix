from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from chattix.models.message import Message, MessageReaction
from chattix.models.user import User


async def message_to_out(session: AsyncSession, msg: Message) -> dict:
    await session.refresh(msg, ["author", "reactions"])
    reactions_out: list[dict] = []
    for r in msg.reactions:
        uname = r.user.username if getattr(r, "user", None) is not None else None
        if uname is None:
            u = await session.get(User, r.user_id)
            uname = u.username if u else "?"
        reactions_out.append({"emoji": r.emoji, "user_id": str(r.user_id), "username": uname})
    return {
        "id": str(msg.id),
        "room_id": str(msg.room_id),
        "user_id": str(msg.user_id),
        "username": msg.author.username,
        "content": msg.content if not msg.deleted else "",
        "attachment_url": msg.attachment_url,
        "edited_at": msg.edited_at.isoformat() if msg.edited_at else None,
        "deleted": msg.deleted,
        "created_at": msg.created_at.isoformat(),
        "reactions": reactions_out,
    }


async def load_message_with_relations(session: AsyncSession, message_id: UUID) -> Message | None:
    result = await session.execute(
        select(Message)
        .options(
            selectinload(Message.author),
            selectinload(Message.reactions).selectinload(MessageReaction.user),
        )
        .where(Message.id == message_id)
    )
    return result.scalar_one_or_none()
