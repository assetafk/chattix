"""Схемы сообщений по проводу (WebSocket и поле wire в Redis)."""

from __future__ import annotations

import msgspec


# --- Вложенное тело сообщения чата (совместимо с REST MessageOut) ---


class ReactionWire(msgspec.Struct):
    emoji: str
    user_id: str
    username: str


class MessagePayload(msgspec.Struct):
    id: str
    room_id: str
    user_id: str
    username: str
    content: str
    attachment_url: str | None
    edited_at: str | None
    deleted: bool
    created_at: str
    reactions: list[ReactionWire]


# --- Клиент → сервер (один JSON на входе WebSocket) ---


class WsPing(msgspec.Struct, tag_field="type", tag="ping"):
    pass


class WsJoinRoom(msgspec.Struct, tag_field="type", tag="join_room"):
    room_id: str


class WsLeaveRoom(msgspec.Struct, tag_field="type", tag="leave_room"):
    room_id: str | None = None


class WsClientTyping(msgspec.Struct, tag_field="type", tag="typing"):
    room_id: str
    typing: bool = False


class WsSendMessage(msgspec.Struct, tag_field="type", tag="send_message"):
    room_id: str
    content: str
    attachment_url: str | None = None


WsClientIncoming = (
    WsPing | WsJoinRoom | WsLeaveRoom | WsClientTyping | WsSendMessage
)


# --- Сервер → клиент (broadcast / ответы по WebSocket) ---


class WsError(msgspec.Struct, tag_field="type", tag="error"):
    message: str


class WsPong(msgspec.Struct, tag_field="type", tag="pong"):
    pass


class WsJoined(msgspec.Struct, tag_field="type", tag="joined"):
    room_id: str


class WsLeft(msgspec.Struct, tag_field="type", tag="left"):
    room_id: str | None = None


class WsPresence(msgspec.Struct, tag_field="type", tag="presence"):
    user_id: str
    username: str
    status: str


class WsServerTyping(msgspec.Struct, tag_field="type", tag="typing"):
    room_id: str
    user_id: str
    username: str
    typing: bool


class WsChatMessage(msgspec.Struct, tag_field="type", tag="message"):
    message: MessagePayload


class WsMessageEdited(msgspec.Struct, tag_field="type", tag="message_edited"):
    message: MessagePayload


class WsMessageDeleted(msgspec.Struct, tag_field="type", tag="message_deleted"):
    room_id: str
    message_id: str


class WsReactionAdded(msgspec.Struct, tag_field="type", tag="reaction_added"):
    room_id: str
    message_id: str
    emoji: str
    user_id: str
    username: str
    message: MessagePayload


class WsReactionRemoved(msgspec.Struct, tag_field="type", tag="reaction_removed"):
    room_id: str
    message_id: str
    emoji: str
    user_id: str
    username: str
    message: MessagePayload


WsServerOutgoing = (
    WsError
    | WsPong
    | WsJoined
    | WsLeft
    | WsPresence
    | WsServerTyping
    | WsChatMessage
    | WsMessageEdited
    | WsMessageDeleted
    | WsReactionAdded
    | WsReactionRemoved
)


# --- Обёртки Redis pub/sub ---


class RoomPublishEnvelope(msgspec.Struct):
    room_id: str
    wire: WsServerOutgoing


class GlobalPublishEnvelope(msgspec.Struct):
    wire: WsServerOutgoing
