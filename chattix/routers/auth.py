from litestar import Router, post
from litestar.exceptions import ClientException
from sqlalchemy import select

from chattix.auth import create_access_token, hash_password, verify_password
from chattix.db import SessionLocal
from chattix.models import User
from chattix.schemas import LoginBody, RegisterBody, TokenResponse, UserPublic


@post("/register")
async def register(data: RegisterBody) -> UserPublic:
    async with SessionLocal() as session:
        exists = await session.execute(select(User).where(User.username == data.username))
        if exists.scalar_one_or_none():
            raise ClientException(detail="Username already taken", status_code=400)
        exists_e = await session.execute(select(User).where(User.email == str(data.email)))
        if exists_e.scalar_one_or_none():
            raise ClientException(detail="Email already registered", status_code=400)
        user = User(
            username=data.username,
            email=str(data.email),
            password_hash=hash_password(data.password),
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return UserPublic.model_validate(user)


@post("/login")
async def login(data: LoginBody) -> TokenResponse:
    async with SessionLocal() as session:
        result = await session.execute(select(User).where(User.username == data.username))
        user = result.scalar_one_or_none()
        if user is None or not verify_password(data.password, user.password_hash):
            raise ClientException(detail="Invalid credentials", status_code=401)
        token = create_access_token(user.id)
        return TokenResponse(access_token=token)


auth_router = Router(path="/auth", route_handlers=[register, login])
