from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import HTTPException, UploadFile

from app.config import BACKEND_DIR, get_settings
from app.report_constants import ALLOWED_IMAGE_TYPES, MAX_FILES, MAX_UPLOAD_BYTES

MAGIC = (
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"RIFF", "image/webp"),
)


def upload_dir() -> Path:
    settings = get_settings()
    path = Path(settings.upload_dir)
    if not path.is_absolute():
        path = BACKEND_DIR / path
    path.mkdir(parents=True, exist_ok=True)
    return path


def sniff_image(data: bytes) -> str:
    for prefix, content_type in MAGIC:
        if data.startswith(prefix):
            if content_type == "image/webp" and b"WEBP" not in data[:16]:
                break
            return content_type
    raise HTTPException(status_code=400, detail="Only JPEG, PNG, or WebP images are allowed.")


async def save_images(files: list[UploadFile]) -> list[dict]:
    if len(files) > MAX_FILES:
        raise HTTPException(status_code=400, detail=f"At most {MAX_FILES} images are allowed.")
    saved: list[dict] = []
    directory = upload_dir()
    for upload in files:
        if not upload.filename:
            continue
        data = await upload.read()
        if not data:
            continue
        if len(data) > MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=400, detail="Each image must be 5 MB or smaller.")
        content_type = sniff_image(data)
        suffix = ALLOWED_IMAGE_TYPES[content_type]
        stored_name = f"{uuid.uuid4().hex}{suffix}"
        (directory / stored_name).write_bytes(data)
        saved.append(
            {
                "stored_name": stored_name,
                "original_name": Path(upload.filename).name[:256],
                "content_type": content_type,
                "size_bytes": len(data),
            }
        )
    return saved
