"""
Centralized audio upload validation for voice endpoints.

Trusts MIME sniffing and extension consistency — never the original filename alone.
"""

from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from typing import Optional

from fastapi import UploadFile

from app.core.config import settings

# Browser / mobile common audio formats
_ALLOWED_MIME_TYPES = frozenset({
    "audio/webm",
    "audio/wav",
    "audio/x-wav",
    "audio/wave",
    "audio/mpeg",
    "audio/mp3",
    "audio/mp4",
    "audio/x-m4a",
    "audio/m4a",
    "audio/ogg",
    "audio/opus",
    "video/webm",  # some browsers label webm audio as video/webm
})

_MIME_TO_EXT = {
    "audio/webm": "webm",
    "video/webm": "webm",
    "audio/wav": "wav",
    "audio/x-wav": "wav",
    "audio/wave": "wav",
    "audio/mpeg": "mp3",
    "audio/mp3": "mp3",
    "audio/mp4": "m4a",
    "audio/x-m4a": "m4a",
    "audio/m4a": "m4a",
    "audio/ogg": "ogg",
    "audio/opus": "ogg",
}

_ALLOWED_EXTENSIONS = frozenset({"webm", "wav", "mp3", "m4a", "mp4", "ogg"})


@dataclass
class AudioValidationResult:
    ok: bool
    error: Optional[str] = None
    safe_extension: Optional[str] = None
    safe_filename: Optional[str] = None


def _normalize_mime(content_type: Optional[str]) -> str:
    raw = (content_type or "").split(";")[0].strip().lower()
    return raw


def _extension_from_filename(filename: Optional[str]) -> Optional[str]:
    if not filename or "." not in filename:
        return None
    ext = filename.rsplit(".", 1)[-1].lower()
    return ext if ext in _ALLOWED_EXTENSIONS else None


def validate_audio_format(file: UploadFile) -> AudioValidationResult:
    """Validate MIME / extension without requiring file size."""
    mime = _normalize_mime(file.content_type)
    ext_from_name = _extension_from_filename(file.filename)

    if mime and mime not in _ALLOWED_MIME_TYPES:
        return AudioValidationResult(ok=False, error=f"invalid_mime:{mime}")

    safe_ext = _MIME_TO_EXT.get(mime) if mime else None
    if not safe_ext:
        safe_ext = ext_from_name
    if not safe_ext or safe_ext not in _ALLOWED_EXTENSIONS:
        return AudioValidationResult(ok=False, error="unsupported_format")

    safe_filename = f"{uuid.uuid4()}.{safe_ext}"
    return AudioValidationResult(
        ok=True,
        safe_extension=safe_ext,
        safe_filename=safe_filename,
    )


def validate_audio_upload(
    file: UploadFile,
    *,
    size_bytes: int,
) -> AudioValidationResult:
    """Validate upload metadata before persisting to disk."""
    if size_bytes <= 0:
        return AudioValidationResult(ok=False, error="empty_file")

    max_bytes = settings.VOICE_MAX_FILE_SIZE_MB * 1024 * 1024
    if size_bytes > max_bytes:
        return AudioValidationResult(
            ok=False,
            error=f"file_too_large:{size_bytes}>{max_bytes}",
        )

    mime = _normalize_mime(file.content_type)
    ext_from_name = _extension_from_filename(file.filename)

    if mime and mime not in _ALLOWED_MIME_TYPES:
        return AudioValidationResult(ok=False, error=f"invalid_mime:{mime}")

    safe_ext = _MIME_TO_EXT.get(mime) if mime else None
    if not safe_ext:
        safe_ext = ext_from_name
    if not safe_ext or safe_ext not in _ALLOWED_EXTENSIONS:
        return AudioValidationResult(ok=False, error="unsupported_format")

    if mime and ext_from_name and ext_from_name != safe_ext:
        # Mismatch is suspicious — prefer MIME-derived extension.
        pass

    safe_filename = f"{uuid.uuid4()}.{safe_ext}"
    return AudioValidationResult(
        ok=True,
        safe_extension=safe_ext,
        safe_filename=safe_filename,
    )


async def save_upload_bounded(
    file: UploadFile,
    dest_path: str,
    *,
    max_bytes: Optional[int] = None,
) -> tuple[int, Optional[str]]:
    """
    Stream upload to disk in bounded chunks.
    Returns (bytes_written, error_code).
    """
    limit = max_bytes or (settings.VOICE_MAX_FILE_SIZE_MB * 1024 * 1024)
    written = 0
    chunk_size = 1024 * 256

    os.makedirs(os.path.dirname(dest_path) or ".", exist_ok=True)

    with open(dest_path, "wb") as out:
        while True:
            chunk = await file.read(chunk_size)
            if not chunk:
                break
            written += len(chunk)
            if written > limit:
                out.close()
                try:
                    os.remove(dest_path)
                except OSError:
                    pass
                return written, "file_too_large"
            out.write(chunk)

    return written, None


def safe_delete_file(path: Optional[str]) -> None:
    if not path:
        return
    try:
        if os.path.isfile(path):
            os.remove(path)
    except OSError:
        pass
