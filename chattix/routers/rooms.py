from uuid import UUID

from litestar import Request, Router, get, post
from litestar.exceptions import ClientException
from sqlalchemy import select

from chattix.db import SessionLocal
from chattix.dependencies import current_user_id_from_request
from chattix.models import Room, RoomMember
from chattix.schemas import RoomCreate, RoomOut


@get("/")
async def list_rooms(request: Request) -> list[RoomOut]:
    user_id = await current_user_id_from_request(request)
    async with SessionLocal() as session:
        result = await session.execute(
            select(Room).join(RoomMember).where(RoomMember.user_id == user_id)
        )
        rooms = result.scalars().unique().all()
        return [RoomOut.model_validate(r) for r in rooms]


@post("/")
async def create_room(request: Request, data: RoomCreate) -> RoomOut:
    user_id = await current_user_id_from_request(request)
    async with SessionLocal() as session:
        room = Room(name=data.name, description=data.description, created_by=user_id)
        session.add(room)
        await session.flush()
        session.add(RoomMember(room_id=room.id, user_id=user_id))
        await session.commit()
        await session.refresh(room)
        return RoomOut.model_validate(room)


@post("/{room_id:uuid}/join")
async def join_room(request: Request, room_id: UUID) -> RoomOut:
    user_id = await current_user_id_from_request(request)
    async with SessionLocal() as session:
        room = await session.get(Room, room_id)
        if room is None:
            raise ClientException(detail="Room not found", status_code=404)
        existing = await session.execute(
            select(RoomMember).where(
                RoomMember.room_id == room_id,
                RoomMember.user_id == user_id,
            )
        )
        if existing.scalar_one_or_none() is None:
            session.add(RoomMember(room_id=room_id, user_id=user_id))
            await session.commit()
        await session.refresh(room)
        return RoomOut.model_validate(room)


rooms_router = Router(path="/rooms", route_handlers=[list_rooms, create_room, join_room])
