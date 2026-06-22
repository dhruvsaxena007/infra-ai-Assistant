"""
Legacy voice transcription helpers — kept for VOICE_PIPELINE_V2=false rollback.

New code should use app.ai.voice_transcription.transcribe_audio_file.
"""

from app.ai.transcript_normalizer import normalize_transcribed_text
from app.ai.voice_input import build_transcription_prompt
from app.core.groq_client import client

def transcribe_audio_legacy(audio_file_path: str) -> dict:
    """Legacy: Hindi-biased Whisper + aggressive Latin normalization."""
    try:
        with open(audio_file_path, "rb") as audio_file:
            transcription = client.audio.transcriptions.create(
                file=audio_file,
                model="whisper-large-v3",
                language="hi",
                prompt=build_transcription_prompt(),
                temperature=0,
            )

        original_text = (transcription.text or "").strip()
        normalized_text = normalize_transcribed_text(original_text)

        return {
            "success": True,
            "text": normalized_text or original_text,
            "original_text": original_text,
            "normalized_text": normalized_text or original_text,
        }
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def transcribe_audio(audio_file_path: str) -> dict:
    """Backward-compatible sync wrapper — prefer async facade in routes."""
    return transcribe_audio_legacy(audio_file_path)
