"""
Validate image files for YOLO classification training.

Detects empty downloads, HTML error pages, and unreadable images.
"""

from __future__ import annotations

import os
from pathlib import Path

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
MIN_BYTES = 512


def _looks_like_html(data: bytes) -> bool:
    head = data[:256].lower()
    return head.startswith(b"<!doctype") or head.startswith(b"<html") or b"<body" in head[:120]


def is_valid_image_file(path: str | os.PathLike, *, min_bytes: int = MIN_BYTES) -> tuple[bool, str]:
    """Return (ok, reason)."""
    p = Path(path)
    if not p.is_file():
        return False, "missing"

    size = p.stat().st_size
    if size < min_bytes:
        return False, f"too_small_{size}b"

    try:
        head = p.read_bytes()[:256]
    except OSError as exc:
        return False, f"read_error:{exc}"

    if _looks_like_html(head):
        return False, "html_error_page"

    try:
        import cv2

        img = cv2.imread(str(p))
        if img is None or img.size == 0:
            return False, "cv2_unreadable"
        if img.shape[0] < 8 or img.shape[1] < 8:
            return False, "dimensions_too_small"
    except Exception as exc:
        return False, f"cv2_error:{exc}"

    return True, "ok"


def scan_dataset(
    dataset_root: str | os.PathLike,
    *,
    delete_invalid: bool = False,
) -> dict:
    """
    Scan cls_dataset/train and val. Optionally delete bad files.
    Returns summary dict.
    """
    root = Path(dataset_root)
    bad: list[dict] = []
    ok = 0
    by_class: dict[str, int] = {}

    for split in ("train", "val"):
        split_dir = root / split
        if not split_dir.is_dir():
            continue
        for class_dir in sorted(split_dir.iterdir()):
            if not class_dir.is_dir():
                continue
            for f in class_dir.iterdir():
                if f.suffix.lower() not in IMAGE_EXTS:
                    continue
                valid, reason = is_valid_image_file(f)
                if valid:
                    ok += 1
                else:
                    bad.append({
                        "path": str(f),
                        "class": class_dir.name,
                        "split": split,
                        "reason": reason,
                        "size": f.stat().st_size if f.exists() else 0,
                    })
                    by_class[class_dir.name] = by_class.get(class_dir.name, 0) + 1
                    if delete_invalid:
                        try:
                            f.unlink()
                        except OSError:
                            pass

    return {
        "ok": ok,
        "bad_count": len(bad),
        "bad_by_class": by_class,
        "bad_samples": bad[:50],
        "deleted": delete_invalid,
    }


def purge_invalid_in_dataset(dataset_root: str | os.PathLike) -> dict:
    return scan_dataset(dataset_root, delete_invalid=True)
