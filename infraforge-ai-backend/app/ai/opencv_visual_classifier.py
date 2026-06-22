"""
OpenCV-only visual heuristics for construction equipment classification.

Works without TensorFlow/YOLO — primary fallback on Python 3.14+.
"""

from __future__ import annotations

import math
from functools import lru_cache
from typing import Any

# Categories we can score from shape / colour / structure cues.
_VISUAL_CATEGORIES = (
    "wheel loader",
    "backhoe loader",
    "excavator",
    "bulldozer",
    "dump truck",
    "road roller",
    "motor grader",
    "crane",
    "hydra crane",
    "concrete mixer",
    "concrete pump",
    "crawler drill",
    "forklift",
    "mobile crusher",
    "air compressor",
    "telehandler",
    "compactor",
)


def _safe_import_cv2():
    try:
        import cv2
        import numpy as np

        return cv2, np
    except ImportError:
        return None, None


def _line_stats(lines: Any, w: int, h: int) -> dict[str, float]:
    """Summarise Hough line orientations (booms, masts, tracks)."""
    if lines is None or len(lines) == 0:
        return {"diag": 0.0, "vertical": 0.0, "horizontal": 0.0, "count": 0.0}

    diag = vertical = horizontal = 0
    for seg in lines[:80]:
        x1, y1, x2, y2 = seg[0]
        dx = abs(x2 - x1)
        dy = abs(y2 - y1)
        length = math.hypot(dx, dy)
        if length < max(18, w * 0.06):
            continue
        if dx < 8:
            vertical += 1
        elif dy < 8:
            horizontal += 1
        else:
            diag += 1

    total = max(diag + vertical + horizontal, 1)
    return {
        "diag": diag / total,
        "vertical": vertical / total,
        "horizontal": horizontal / total,
        "count": float(diag + vertical + horizontal),
    }


@lru_cache(maxsize=48)
def analyze_construction_equipment(image_path: str) -> dict[str, float]:
    """
    Score marketplace categories from local image features only.
    Returns category -> score (typically 0.05–0.55).
    """
    cv2, np = _safe_import_cv2()
    if cv2 is None:
        return {}

    img = cv2.imread(image_path)
    if img is None:
        return {}

    h, w = img.shape[:2]
    if w < 24 or h < 24:
        return {}

    # Large listing photos (5MB+) slow Hough transforms — analyse a bounded size.
    max_side = max(h, w)
    if max_side > 960:
        scale = 960.0 / max_side
        img = cv2.resize(
            img,
            (max(24, int(w * scale)), max(24, int(h * scale))),
            interpolation=cv2.INTER_AREA,
        )
        h, w = img.shape[:2]

    scores: dict[str, float] = {c: 0.0 for c in _VISUAL_CATEGORIES}
    aspect = h / float(w)

    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    yellow_mask = cv2.inRange(hsv, np.array([10, 70, 70]), np.array([40, 255, 255]))
    orange_mask = cv2.inRange(hsv, np.array([5, 100, 100]), np.array([18, 255, 255]))
    construction_mask = cv2.bitwise_or(yellow_mask, orange_mask)
    yellow_ratio = float(cv2.countNonZero(construction_mask)) / float(h * w)

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 60, 160)
    lines = cv2.HoughLinesP(
        edges,
        rho=1,
        theta=np.pi / 180,
        threshold=max(30, w // 12),
        minLineLength=max(24, w // 7),
        maxLineGap=max(8, w // 30),
    )
    line_stats = _line_stats(lines, w, h)

    circles = cv2.HoughCircles(
        gray,
        cv2.HOUGH_GRADIENT,
        dp=1.2,
        minDist=max(18, w // 7),
        param1=75,
        param2=32,
        minRadius=max(6, w // 30),
        maxRadius=max(40, w // 4),
    )
    circle_count = len(circles[0]) if circles is not None else 0

    # Bottom band — tracks, chassis, wheels
    bottom = gray[int(h * 0.62) :, :]
    bottom_edges = cv2.Canny(bottom, 50, 140)
    bottom_edge_ratio = float(cv2.countNonZero(bottom_edges)) / float(bottom.size or 1)

    # Front-centre bucket region (wheel loaders)
    cx0, cx1 = int(w * 0.2), int(w * 0.8)
    cy0, cy1 = int(h * 0.45), int(h * 0.92)
    front_roi = img[cy0:cy1, cx0:cx1]
    if front_roi.size:
        front_hsv = cv2.cvtColor(front_roi, cv2.COLOR_BGR2HSV)
        front_yellow = cv2.inRange(
            front_hsv, np.array([10, 60, 60]), np.array([42, 255, 255])
        )
        front_yellow_ratio = float(cv2.countNonZero(front_yellow)) / float(
            front_roi.shape[0] * front_roi.shape[1]
        )
    else:
        front_yellow_ratio = 0.0

    # --- Category rules -------------------------------------------------------

    # Wheel loader: boxy, yellow front bucket, moderate aspect
    if 0.72 <= aspect <= 1.35:
        wl = 0.16
        if yellow_ratio > 0.04:
            wl += 0.16
        if front_yellow_ratio > 0.10:
            wl += 0.30
        if front_yellow_ratio > 0.20:
            wl += 0.18
        if 0.85 <= aspect <= 1.15:
            wl += 0.10
        scores["wheel loader"] += wl

    # Backhoe / JCB: yellow, medium aspect, diagonal arm
    if 0.78 <= aspect <= 1.25 and yellow_ratio > 0.05:
        scores["backhoe loader"] += 0.16 + line_stats["diag"] * 0.18

    # Excavator: tracks at bottom, arm lines, often yellow
    if bottom_edge_ratio > 0.045 and line_stats["diag"] > 0.22:
        scores["excavator"] += 0.18
    if bottom_edge_ratio > 0.06 and 0.75 <= aspect <= 1.2:
        scores["excavator"] += 0.14
    if yellow_ratio > 0.06 and line_stats["horizontal"] > 0.25:
        scores["excavator"] += 0.10

    # Bulldozer: wide, low blade, yellow
    if aspect <= 0.92 and yellow_ratio > 0.05:
        scores["bulldozer"] += 0.16 + line_stats["horizontal"] * 0.12

    # Dump truck: wide profile, cab + bed, yellow common
    if 0.62 <= aspect <= 1.05:
        scores["dump truck"] += 0.14
        if yellow_ratio > 0.08:
            scores["dump truck"] += 0.18
        if aspect <= 0.88:
            scores["dump truck"] += 0.10

    # Road roller / compactor: multiple drums (circles) — not front-loader buckets
    roller_boost = 0.0
    if circle_count >= 2 and front_yellow_ratio < 0.18:
        roller_boost = 0.20 + min(circle_count, 4) * 0.04
    elif circle_count >= 2 and line_stats["horizontal"] > 0.25:
        roller_boost = 0.14
    if 0.55 <= aspect <= 0.95 and circle_count >= 2 and front_yellow_ratio < 0.15:
        roller_boost += 0.10
    if roller_boost:
        scores["road roller"] += roller_boost
        scores["compactor"] += roller_boost * 0.7

    # Motor grader: long blade, low wide body
    if aspect <= 0.82 and line_stats["horizontal"] > 0.30:
        scores["motor grader"] += 0.20

    # Cranes: tall OR long boom diagonals
    if aspect >= 1.05:
        scores["crane"] += 0.14
        scores["hydra crane"] += 0.10
        scores["crawler drill"] += 0.08
    if line_stats["diag"] > 0.35 and line_stats["count"] >= 4:
        scores["crane"] += 0.22
        scores["hydra crane"] += 0.16
    if line_stats["vertical"] > 0.28 and aspect >= 0.95:
        scores["crane"] += 0.14

    # Hydra / truck-mounted crane: boom + chassis at bottom
    if line_stats["diag"] > 0.28 and bottom_edge_ratio > 0.04 and aspect >= 0.9:
        scores["hydra crane"] += 0.24
        scores["truck mounted crane"] = scores.get("truck mounted crane", 0) + 0.18

    # Concrete mixer: large single drum
    if circle_count == 1 and 0.85 <= aspect <= 1.35:
        scores["concrete mixer"] += 0.26
    if circle_count >= 1 and yellow_ratio < 0.04 and 0.9 <= aspect <= 1.4:
        scores["concrete mixer"] += 0.10

    # Concrete pump: boom lines + truck base
    if line_stats["diag"] > 0.32 and bottom_edge_ratio > 0.035:
        scores["concrete pump"] += 0.16

    # Crawler drill: very tall, lattice / vertical structure
    if aspect >= 1.25 and line_stats["vertical"] > 0.22:
        scores["crawler drill"] += 0.28

    # Forklift / telehandler: vertical mast
    if line_stats["vertical"] > 0.32 and 0.9 <= aspect <= 1.5:
        scores["forklift"] += 0.18
        scores["telehandler"] += 0.12

    # Mobile crusher: industrial, dark metal, wide
    if aspect <= 1.0 and yellow_ratio < 0.04 and bottom_edge_ratio > 0.05:
        scores["mobile crusher"] += 0.14

    # Air compressor: small trailer unit on site
    if aspect <= 1.1 and yellow_ratio < 0.03 and circle_count == 0:
        scores["air compressor"] += 0.08

    # Drop negligible scores
    return {k: round(v, 4) for k, v in scores.items() if v >= 0.06}


def opencv_machine_hints(image_path: str) -> dict[str, float]:
    """Backward-compatible alias used by image_intent_service."""
    return analyze_construction_equipment(image_path)
