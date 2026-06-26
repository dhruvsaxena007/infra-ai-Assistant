"""
Legacy voice transcription helpers — kept for VOICE_PIPELINE_V2=false rollback.

New code should use app.ai.voice_transcription.transcribe_audio_file.
"""

from app.ai.transcript_normalizer import normalize_transcribed_text
from app.ai.voice_input import build_transcription_prompt


def transcribe_audio_legacy(audio_file_path: str) -> dict:
    """Legacy: Hindi-biased Whisper + aggressive Latin normalization."""
    from app.core.ai_client import ai_transcribe_audio

    try:
        result = ai_transcribe_audio(
            audio_file_path,
            language_hint="hi",
            prompt=build_transcription_prompt(),
        )
        if not result.get("success"):
            return result

        original_text = (result.get("original_text") or result.get("text") or "").strip()
        normalized_text = normalize_transcribed_text(original_text)

        return {
            "success": True,
            "text": normalized_text or original_text,
            "original_text": original_text,
            "normalized_text": normalized_text or original_text,
            "provider": result.get("provider"),
        }
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def transcribe_audio(audio_file_path: str) -> dict:
    """Backward-compatible sync wrapper — prefer async facade in routes."""
    return transcribe_audio_legacy(audio_file_path)
