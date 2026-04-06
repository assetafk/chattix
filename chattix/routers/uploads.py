import uuid
from pathlib import Path

from litestar import Request, Router, post
from litestar.datastructures import UploadFile
from litestar.exceptions import ClientException

from chattix.config import get_settings
from chattix.dependencies import current_user_id_from_request


@post("/uploads")
async def upload_file(request: Request, file: UploadFile) -> dict[str, str]:
    await current_user_id_from_request(request)
    settings = get_settings()
    if not file.filename:
        raise ClientException(detail="No filename", status_code=400)
    max_bytes = settings.max_upload_mb * 1024 * 1024
    dest_dir = Path(settings.upload_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    safe_name = f"{uuid.uuid4().hex}_{file.filename}"
    path = dest_dir / safe_name
    size = 0
    chunk = await file.read(1024 * 1024)
    with path.open("wb") as f:
        while chunk:
            size += len(chunk)
            if size > max_bytes:
                path.unlink(missing_ok=True)
                raise ClientException(detail="File too large", status_code=413)
            f.write(chunk)
            chunk = await file.read(1024 * 1024)
    url = f"/uploads/{safe_name}"
    return {"url": url, "filename": file.filename}


uploads_router = Router(path="", route_handlers=[upload_file])
