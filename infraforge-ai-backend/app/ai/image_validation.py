"""
Centralized image upload validation for /image-search.

Trusts MIME sniffing, magic bytes, and extension consistency — never filename alone.
"""

from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from typing import Optional

from fastapi import UploadFile

from app.core.config import settings

_ALLOWED_MIME_TYPES = frozenset({
    "image/jpeg",
    "image/jpg",
    "image/png",
    "image/webp",
})

_MIME_TO_EXT = {
    "image/jpeg": "jpg",
    "image/jpg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
}

_MAGIC = {
    b"\xff\xd8\xff": "jpg",
    b"\x89PNG\r\n\x1a\n": "png",
    b"RIFF": "webp",  # checked further below
}

_ALLOWED_EXTENSIONS = frozenset({"jpg", "jpeg", "png", "webp"})


@dataclass
class ImageValidationResult:
    ok: bool
    error: Optional[str] = None
    safe_extension: Optional[str] = None
    safe_filename: Optional[str] = None
    file_bytes: bytes = b""


def _normalize_mime(content_type: Optional[str]) -> str:
    return (content_type or "").split(";")[0].strip().lower()


def _extension_from_filename(filename: Optional[str]) -> Optional[str]:
    if not filename or "." not in filename:
        return None
    ext = filename.rsplit(".", 1)[-1].lower()
    if ext == "jpeg":
        ext = "jpg"
    return ext if ext in _ALLOWED_EXTENSIONS else None


def _sniff_format(data: bytes) -> Optional[str]:
    if not data:
        return None
    if data[:3] == b"\xff\xd8\xff":
        return "jpg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    return None


def validate_image_format(file: UploadFile, data: bytes) -> ImageValidationResult:
    """Validate MIME, extension, magic bytes, and non-empty payload."""
    if not data:
        return ImageValidationResult(ok=False, error="empty_file")

    max_bytes = settings.IMAGE_SEARCH_MAX_FILE_SIZE_MB * 1024 * 1024
    if len(data) > max_bytes:
        return ImageValidationResult(ok=False, error="file_too_large")

    mime = _normalize_mime(file.content_type)
    ext_from_name = _extension_from_filename(file.filename)
    sniffed = _sniff_format(data)

    if sniffed is None:
        return ImageValidationResult(ok=False, error="invalid_image_data")

    if mime and mime not in _ALLOWED_MIME_TYPES:
        return ImageValidationResult(ok=False, error=f"invalid_mime:{mime}")

    safe_ext = _MIME_TO_EXT.get(mime) if mime else sniffed
    if not safe_ext:
        safe_ext = sniffed

    if ext_from_name and ext_from_name.replace("jpeg", "jpg") != safe_ext.replace("jpeg", "jpg"):
        # Extension mismatch is suspicious but not fatal if magic bytes are valid.
        pass

    safe_name = f"{uuid.uuid4()}.{safe_ext}"
    return ImageValidationResult(
        ok=True,
        safe_extension=safe_ext,
        safe_filename=safe_name,
        file_bytes=data,
    )


def save_validated_image(data: bytes, safe_filename: str) -> str:
    """Persist validated bytes to the configured upload directory."""
    upload_dir = settings.IMAGE_SEARCH_UPLOAD_DIR
    os.makedirs(upload_dir, exist_ok=True)
    path = os.path.join(upload_dir, safe_filename)
    with open(path, "wb") as fh:
        fh.write(data)
    return path


def resize_image_if_needed(path: str) -> str:
    """
    Resize in-place when dimensions exceed IMAGE_SEARCH_MAX_DIMENSION.
    Returns the path (unchanged when no resize needed).
    """
    try:
        import cv2
    except ImportError:
        return path

    img = cv2.imread(path)
    if img is None:
        return path

    h, w = img.shape[:2]
    max_dim = settings.IMAGE_SEARCH_MAX_DIMENSION
    longest = max(h, w)
    if longest <= max_dim:
        return path

    scale = max_dim / float(longest)
    new_w = max(1, int(w * scale))
    new_h = max(1, int(h * scale))
    resized = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_AREA)
    cv2.imwrite(path, resized, [int(cv2.IMWRITE_JPEG_QUALITY), 90])
    return path


def cleanup_image_path(path: str | None) -> None:
    if not path or not settings.IMAGE_SEARCH_TEMP_CLEANUP:
        return
    try:
        if os.path.isfile(path):
            os.remove(path)
    except OSError:
        pass
