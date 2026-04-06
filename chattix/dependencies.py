from uuid import UUID

from litestar import Request
from litestar.connection import ASGIConnection
from litestar.exceptions import NotAuthorizedException

from chattix.auth import decode_token


async def current_user_id_from_connection(connection: ASGIConnection) -> UUID:
    auth = connection.headers.get("authorization")
    if not auth:
        raise NotAuthorizedException("Missing Authorization header")
    parts = auth.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise NotAuthorizedException("Invalid Authorization header")
    uid = decode_token(parts[1])
    if uid is None:
        raise NotAuthorizedException("Invalid or expired token")
    return uid


async def current_user_id_from_request(request: Request) -> UUID:
    return await current_user_id_from_connection(request)
