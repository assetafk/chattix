from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from litestar import Litestar, get
from litestar.config.cors import CORSConfig
from litestar.static_files import create_static_files_router

from chattix.config import get_settings
from chattix.db import engine
from chattix.models import Base
from chattix.routers.auth import auth_router
from chattix.routers.messages import messages_router
from chattix.routers.presence import presence_router
from chattix.routers.rooms import rooms_router
from chattix.routers.uploads import uploads_router
from chattix.services.connection_manager import ConnectionManager
from chattix.services.redis_bus import redis_listener_loop
from chattix.websocket.chat import chat_socket

logger = logging.getLogger(__name__)


@get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@asynccontextmanager
async def lifespan(app: Litestar):
    settings = get_settings()
    upload_path = Path(settings.upload_dir)
    upload_path.mkdir(parents=True, exist_ok=True)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    app.state.connection_manager = ConnectionManager()
    stop = asyncio.Event()
    app.state.redis_stop = stop
    app.state.redis_listener_task = asyncio.create_task(
        redis_listener_loop(settings.redis_url, app.state.connection_manager, stop)
    )

    yield

    stop.set()
    app.state.redis_listener_task.cancel()
    try:
        await app.state.redis_listener_task
    except asyncio.CancelledError:
        pass
    await engine.dispose()


def create_app() -> Litestar:
    settings = get_settings()
    upload_dir = str(Path(settings.upload_dir).resolve())
    static_router = create_static_files_router(path="/uploads", directories=[upload_dir])

    return Litestar(
        route_handlers=[
            health,
            auth_router,
            rooms_router,
            messages_router,
            uploads_router,
            presence_router,
            chat_socket,
            static_router,
        ],
        lifespan=[lifespan],
        cors_config=CORSConfig(allow_origins=["*"]),
        debug=True,
    )


app = create_app()


def run() -> None:
    import uvicorn

    uvicorn.run(
        "chattix.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )
