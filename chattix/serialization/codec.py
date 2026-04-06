"""JSON encode/decode для проводных типов (msgspec)."""

from __future__ import annotations

import msgspec

from chattix.serialization.wire import (
    GlobalPublishEnvelope,
    RoomPublishEnvelope,
    WsClientIncoming,
    WsServerOutgoing,
)


def decode_ws_client(raw: str | bytes) -> WsClientIncoming:
    return msgspec.json.decode(raw, type=WsClientIncoming)


def encode_ws_server(msg: WsServerOutgoing) -> bytes:
    return msgspec.json.encode(msg)


def encode_server_to_text(msg: WsServerOutgoing) -> str:
    return encode_ws_server(msg).decode("utf-8")


def encode_room_envelope(room_id: str, wire: WsServerOutgoing) -> bytes:
    return msgspec.json.encode(RoomPublishEnvelope(room_id=room_id, wire=wire))


def encode_global_envelope(wire: WsServerOutgoing) -> bytes:
    return msgspec.json.encode(GlobalPublishEnvelope(wire=wire))


def decode_room_envelope(raw: str | bytes) -> tuple[str, WsServerOutgoing]:
    env = msgspec.json.decode(raw, type=RoomPublishEnvelope)
    return env.room_id, env.wire


def decode_global_envelope(raw: str | bytes) -> WsServerOutgoing:
    env = msgspec.json.decode(raw, type=GlobalPublishEnvelope)
    return env.wire
