"""
Add YOLO settings to .env (safe append — does not overwrite existing keys).

Usage:
    python scripts/configure_yolo_env.py
"""

from __future__ import annotations

import os

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV_PATH = os.path.join(PROJECT_ROOT, ".env")

LINES = [
    "",
    "# YOLO image search (local trained model)",
    "YOLO_MODEL_PATH=models/infraforge_yolov8n_cls/best.pt",
    "IMAGE_CLASSIFIER=auto",
]


def main() -> None:
    existing = ""
    if os.path.isfile(ENV_PATH):
        with open(ENV_PATH, "r", encoding="utf-8") as fh:
            existing = fh.read()

    to_add = []
    for line in LINES:
        key = line.split("=", 1)[0].strip() if "=" in line and not line.startswith("#") else None
        if key and key in existing:
            continue
        to_add.append(line)

    if not to_add:
        print(".env already contains YOLO settings.")
        return

    with open(ENV_PATH, "a", encoding="utf-8") as fh:
        fh.write("\n".join(to_add) + "\n")

    print(f"Updated {ENV_PATH}")
    print("Restart the backend for changes to apply.")


if __name__ == "__main__":
    main()
