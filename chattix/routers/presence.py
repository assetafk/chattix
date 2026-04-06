import redis.asyncio as redis
from litestar import Request, Router, get

from chattix.config import get_settings
from chattix.dependencies import current_user_id_from_request
from chattix.services.redis_bus import list_online


@get("/presence")
async def get_presence(request: Request) -> list[dict[str, str]]:
    await current_user_id_from_request(request)
    settings = get_settings()
    client = redis.from_url(settings.redis_url, decode_responses=True)
    try:
        return await list_online(client)
    finally:
        await client.aclose()


presence_router = Router(path="", route_handlers=[get_presence])
