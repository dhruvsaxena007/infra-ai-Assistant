"""Quick offline test for image classification pipeline (no server required)."""

from __future__ import annotations

import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from app.ai.image_classifier import classify_marketplace_image
from app.ai.clip_image_classifier import clip_available


def main() -> int:
    paths = sys.argv[1:]
    if not paths:
        print("Usage: python scripts/test_image_classifier.py <image1> [image2 ...]")
        print(f"CLIP available: {clip_available()}")
        return 1

    ok = 0
    total = 0
    for path in paths:
        if not os.path.isfile(path):
            print(f"SKIP missing: {path}")
            continue
        total += 1
        result = classify_marketplace_image(path)
        intent = result.get("intent") or {}
        print("---")
        print(f"file: {path}")
        print(f"success: {result.get('success')}")
        print(f"stage: {result.get('stage')}")
        print(f"type: {intent.get('machine_type')}")
        print(f"conf: {intent.get('intent_confidence')}")
        print(f"classifier: {intent.get('classifier')}")
        print(f"message: {intent.get('message') or result.get('error')}")
        if result.get("success"):
            ok += 1

    print(f"\n{ok}/{total} classified")
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
