import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class MessageCreate(BaseModel):
    content: str = Field(min_length=1, max_length=10000)
    attachment_url: str | None = Field(default=None, max_length=512)


class MessagePatch(BaseModel):
    content: str = Field(min_length=1, max_length=10000)


class ReactionOut(BaseModel):
    emoji: str
    user_id: uuid.UUID
    username: str


class MessageOut(BaseModel):
    id: uuid.UUID
    room_id: uuid.UUID
    user_id: uuid.UUID
    username: str
    content: str
    attachment_url: str | None
    edited_at: datetime | None
    deleted: bool
    created_at: datetime
    reactions: list[ReactionOut] = Field(default_factory=list)


class ReactionBody(BaseModel):
    emoji: str = Field(min_length=1, max_length=32)
