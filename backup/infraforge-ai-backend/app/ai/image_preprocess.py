"""
Crop helpers when users upload chat screenshots or photos with large borders.
"""

from __future__ import annotations

import os
import tempfile
import uuid

import cv2
import numpy as np


def center_crop_path(image_path: str, *, margin_ratio: float = 0.18) -> str:
    """
    Return path to a center-cropped temp JPEG (smaller margin = tighter crop).
    Caller may delete the file after use.
    """
    img = cv2.imread(image_path)
    if img is None:
        raise ValueError(f"Cannot read image: {image_path}")

    h, w = img.shape[:2]
    mx = int(w * margin_ratio)
    my = int(h * margin_ratio)
    cropped = img[my : h - my, mx : w - mx]
    if cropped.size == 0:
        cropped = img

    fd, out = tempfile.mkstemp(suffix=".jpg", prefix="infraforge_crop_")
    os.close(fd)
    cv2.imwrite(out, cropped, [int(cv2.IMWRITE_JPEG_QUALITY), 92])
    return out


def classification_variants(image_path: str) -> list[tuple[str, bool]]:
    """
    (path, is_temp) pairs to try — full frame then center crop.
    """
    variants: list[tuple[str, bool]] = [(image_path, False)]
    try:
        cropped = center_crop_path(image_path)
        if os.path.isfile(cropped):
            variants.append((cropped, True))
    except Exception:
        pass
    return variants


def cleanup_temp(path: str, is_temp: bool) -> None:
    if is_temp and path and os.path.isfile(path):
        try:
            os.remove(path)
        except OSError:
            pass
