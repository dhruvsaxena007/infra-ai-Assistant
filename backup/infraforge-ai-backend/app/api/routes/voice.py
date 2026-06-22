import os
import uuid

from fastapi import APIRouter, UploadFile, File, Form

from app.ai.voice_service import transcribe_audio
from app.ai.rules_understanding import understand_user_text_rules
from app.chatbot.chatbot_service import chatbot_response
from app.database.mongodb import database
from app.utils.response import success_response, error_response


router = APIRouter()

from app.core.config import settings

UPLOAD_DIR = settings.AUDIO_UPLOAD_DIR

os.makedirs(
    UPLOAD_DIR,
    exist_ok=True
)


def build_enhanced_query(message: str):
    """
    Convert normal / Hindi / Hinglish text into better search query.
    """

    understanding_result = understand_user_text_rules(
        message
    )

    print("VOICE TEXT UNDERSTANDING:", understanding_result)

    if understanding_result.get("success"):

        extracted_data = understanding_result.get(
            "data",
            {}
        )

        machine_type = extracted_data.get("machine_type")
        city = extracted_data.get("city")
        max_price = extracted_data.get("max_price")
        intent = extracted_data.get("intent")

    else:

        extracted_data = {}
        machine_type = None
        city = None
        max_price = None
        intent = "unknown"

    enhanced_query_parts = []

    if machine_type:
        enhanced_query_parts.append(
            machine_type
        )

    if city:
        enhanced_query_parts.append(
            city
        )

    if max_price:
        enhanced_query_parts.append(
            f"under {max_price}"
        )

    if intent == "cheaper_options":
        enhanced_query_parts.append(
            "cheap budget low price"
        )

    enhanced_query = " ".join(
        enhanced_query_parts
    )

    if not enhanced_query:
        enhanced_query = message

    return enhanced_query, extracted_data


@router.post("/voice/transcribe")
async def voice_transcribe(
    file: UploadFile = File(...)
):
    """
    Upload audio file and convert speech to text only.
    """

    file_extension = file.filename.split(".")[-1]

    unique_filename = f"{uuid.uuid4()}.{file_extension}"

    file_path = os.path.join(
        UPLOAD_DIR,
        unique_filename
    )

    with open(file_path, "wb") as buffer:

        buffer.write(
            await file.read()
        )

    result = transcribe_audio(
        file_path
    )

    if not result.get("success"):

        return error_response(
            message="Audio transcription failed",
            error={
                "stage": "transcription",
                "details": result.get("error")
            }
        )

    return success_response(
        message="Audio transcribed successfully",
        data={
            "text": result.get("text"),
            "original_transcription": result.get("original_text"),
            "normalized_text": result.get("normalized_text"),
        }
    )


@router.post("/voice/chat")
async def voice_chat(
    session_id: str = Form(...),
    file: UploadFile = File(...)
):
    """
    Upload voice file.
    Convert speech to text.
    Understand Hindi/Hinglish/English.
    Send enhanced query to chatbot.
    Return machine results.
    """

    session_id = (session_id or "").strip()

    if not session_id:

        return error_response(
            message="session_id is required",
            error={
                "stage": "validation",
                "field": "session_id"
            }
        )

    file_extension = file.filename.split(".")[-1]

    unique_filename = f"{uuid.uuid4()}.{file_extension}"

    file_path = os.path.join(
        UPLOAD_DIR,
        unique_filename
    )

    with open(file_path, "wb") as buffer:

        buffer.write(
            await file.read()
        )

    transcription_result = transcribe_audio(
        file_path
    )

    if not transcription_result.get("success"):

        return error_response(
            message="Audio transcription failed",
            error={
                "stage": "transcription",
                "details": transcription_result.get("error")
            }
        )

    # original_transcription = exactly what Whisper returned (may be Devanagari).
    # normalized_text        = cleaned Latin/Hinglish text for the search parser.
    original_transcription = (
        transcription_result.get("original_text")
        or transcription_result.get("text")
    )
    normalized_text = (
        transcription_result.get("normalized_text")
        or transcription_result.get("text")
    )

    enhanced_query, extracted_data = build_enhanced_query(
        normalized_text
    )

    print("VOICE ORIGINAL TEXT:", original_transcription)
    print("VOICE NORMALIZED TEXT:", normalized_text)
    print("VOICE ENHANCED QUERY:", enhanced_query)

    # Search on the NORMALIZED text so the chatbot's strong parser sees clean
    # tokens (excavator/jcb/jaipur...) and can detect category, override,
    # free-budget and list-all intents reliably.
    chatbot_result = await chatbot_response(
        session_id,
        normalized_text,
        database
    )

    chat_data = chatbot_result.get(
        "data",
        {}
    )

    chat_data["voice_input"] = {
        "original_transcription": original_transcription,
        "normalized_text": normalized_text,
        # Kept for frontend backward-compatibility.
        "original_voice_text": original_transcription,
        "enhanced_query": enhanced_query,
        "text_understanding": extracted_data,
    }

    return success_response(
        message=chatbot_result.get("message"),
        data=chat_data
    )