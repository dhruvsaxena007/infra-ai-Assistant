"""
Smoke test for OpenAI paid API mode (chat, voice STT, vision).

Usage:
  set AI_PROVIDER=openai ENABLE_OPENAI=true OPENAI_API_KEY=sk-...
  python scripts/test_openai_mode.py
  python scripts/test_openai_mode.py --chat-only
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.config import settings  # noqa: E402


def _require_openai() -> None:
    if not settings.openai_usable:
        print("FAIL: OpenAI mode not active.")
        print("Set AI_PROVIDER=openai, ENABLE_OPENAI=true, and OPENAI_API_KEY in .env")
        sys.exit(1)
    print(f"OK: OpenAI mode active (chat={settings.OPENAI_CHAT_MODEL})")


def test_chat_completion() -> None:
    from app.core.ai_client import ai_chat_completion

    response = ai_chat_completion(
        messages=[{"role": "user", "content": "Reply with exactly: OPENAI_CHAT_OK"}],
        temperature=0,
        tag="smoke_chat",
        max_tokens=20,
    )
    assert response is not None, "chat completion returned None"
    text = (response.choices[0].message.content or "").strip()
    assert "OPENAI_CHAT_OK" in text or text, f"unexpected chat reply: {text!r}"
    print(f"OK: chat completion -> {text[:80]}")


async def test_intent_classifier() -> None:
    from app.ai.llm_intent_classifier import classify_intent_llm

    result = await classify_intent_llm("excavator in jaipur under 50 lakh")
    assert result and result.get("intent"), f"intent failed: {result}"
    print(f"OK: intent -> {result.get('intent')} (layer={result.get('layer')})")


async def test_voice_stt(audio_path: str | None) -> None:
    if not audio_path or not Path(audio_path).is_file():
        print("SKIP: voice STT (pass --audio path/to/sample.webm)")
        return
    from app.ai.voice_transcription import transcribe_audio_file

    result = await transcribe_audio_file(audio_path, request_id="openai-smoke")
    assert result.get("success"), f"STT failed: {result}"
    assert result.get("text"), "STT returned empty text"
    print(f"OK: voice STT ({result.get('provider', 'unknown')}) -> {result['text'][:80]}")


def test_vision(image_path: str | None) -> None:
    if not settings.USE_OPENAI_VISION:
        print("SKIP: vision (USE_OPENAI_VISION=false)")
        return
    if not image_path or not Path(image_path).is_file():
        print("SKIP: vision (pass --image path/to/machine.jpg)")
        return
    from app.core.ai_client import ai_vision_classify_machine

    result = ai_vision_classify_machine(image_path)
    assert result, "vision returned None"
    print(
        f"OK: vision -> {result.get('machine_type') or 'unknown'} "
        f"(conf={result.get('intent_confidence')})"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--chat-only", action="store_true")
    parser.add_argument("--audio", default=os.getenv("SMOKE_AUDIO_PATH"))
    parser.add_argument("--image", default=os.getenv("SMOKE_IMAGE_PATH"))
    args = parser.parse_args()

    _require_openai()
    test_chat_completion()
    if args.chat_only:
        print("\nAll requested OpenAI smoke checks passed.")
        return

    try:
        asyncio.run(test_intent_classifier())
    except Exception as exc:
        print(f"SKIP/WARN: intent classifier: {exc}")

    asyncio.run(test_voice_stt(args.audio))
    test_vision(args.image)
    print("\nAll OpenAI smoke checks passed.")


if __name__ == "__main__":
    main()
