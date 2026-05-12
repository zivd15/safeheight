import os
import re
import base64
import secrets
from pathlib import Path
from fastapi import UploadFile, HTTPException

from app.config import settings

ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}
ALLOWED_PHOTO_ID_TYPES = {"image/jpeg", "image/png", "image/webp", "application/pdf"}
MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB
MAX_PHOTO_ID_BYTES = 5 * 1024 * 1024  # 5 MB for photo ID


def _safe_filename(original: str) -> str:
    stem = Path(original).stem
    suffix = Path(original).suffix.lower()
    clean = re.sub(r"[^\w]", "_", stem)[:40]
    rand = secrets.token_hex(8)
    return f"{clean}_{rand}{suffix}"


def save_upload(file: UploadFile, subfolder: str) -> str:
    if file.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(status_code=400, detail="Only JPEG, PNG, or WebP images are accepted.")

    dest_dir = Path(settings.UPLOAD_DIR) / subfolder
    dest_dir.mkdir(parents=True, exist_ok=True)

    filename = _safe_filename(file.filename or "upload.jpg")
    dest = dest_dir / filename

    content = file.file.read()
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=400, detail="File too large (max 10 MB).")

    dest.write_bytes(content)
    return str(dest)


def save_photo_id(file: UploadFile, subfolder: str) -> str:
    """Photo ID accepts JPEG, PNG, WebP, or PDF. Max 5 MB."""
    if file.content_type not in ALLOWED_PHOTO_ID_TYPES:
        raise HTTPException(status_code=400, detail="Photo ID must be JPEG, PNG, WebP, or PDF.")

    dest_dir = Path(settings.UPLOAD_DIR) / subfolder
    dest_dir.mkdir(parents=True, exist_ok=True)

    filename = _safe_filename(file.filename or "photoid.jpg")
    dest = dest_dir / filename

    content = file.file.read()
    if len(content) > MAX_PHOTO_ID_BYTES:
        raise HTTPException(status_code=400, detail="File too large (max 5 MB).")

    dest.write_bytes(content)
    return str(dest)


def save_signature_base64(data_url: str, student_id: int) -> str:
    """Accept a base64 data URL from the canvas and write it as a PNG."""
    if not data_url.startswith("data:image/png;base64,"):
        raise HTTPException(status_code=400, detail="Signature must be a PNG data URL.")

    raw = base64.b64decode(data_url.split(",", 1)[1])
    dest_dir = Path(settings.UPLOAD_DIR) / "signatures"
    dest_dir.mkdir(parents=True, exist_ok=True)
    filename = f"sig_{student_id}_{secrets.token_hex(6)}.png"
    path = dest_dir / filename
    path.write_bytes(raw)
    return str(path)


def read_file_bytes(path: str) -> bytes:
    p = Path(path)
    if not p.exists():
        raise HTTPException(status_code=404, detail="File not found.")
    return p.read_bytes()
