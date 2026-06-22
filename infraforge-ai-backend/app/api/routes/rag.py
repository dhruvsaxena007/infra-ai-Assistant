import os
import uuid

from fastapi import APIRouter, UploadFile, File, Form
from pydantic import BaseModel

from typing import Optional

from app.ai.rag_service import (
    add_document_to_rag,
    ask_rag_question,
)

from app.ai.pdf_service import extract_text_from_pdf
from app.utils.response import success_response, error_response


router = APIRouter()

from app.core.config import settings

UPLOAD_DIR = settings.RAG_PDF_UPLOAD_DIR
os.makedirs(
    UPLOAD_DIR,
    exist_ok=True
)


class DocumentRequest(BaseModel):
    text: str
    session_id: Optional[str] = None


class QuestionRequest(BaseModel):
    question: str
    session_id: Optional[str] = None


@router.post("/rag/upload-text")
async def upload_text_document(
    request: DocumentRequest
):
    """
    Upload plain text and store it in RAG memory.
    Optional session_id scopes chunks to that chat session.
    """

    if not request.text.strip():

        return error_response(
            message="Text is required",
            error={
                "stage": "validation"
            }
        )

    result = add_document_to_rag(
        request.text,
        session_id=request.session_id,
    )

    if not result.get("success"):

        return error_response(
            message=result.get("message", "Failed to add text document"),
            error=result
        )

    return success_response(
        message="Text document added to RAG successfully",
        data={
            "chunks_added": result.get("chunks_added"),
            "total_chunks": result.get("total_chunks"),
            "rag_scope": result.get("rag_scope"),
            "session_id": result.get("session_id"),
        }
    )


@router.post("/rag/upload-pdf")
async def upload_pdf_document(
    file: UploadFile = File(...),
    session_id: str = Form(default=""),
):
    """
    Upload PDF.
    Extract text.
    Store in RAG memory.
    Optional session_id (form field) scopes to chat session.
    """

    if not file.filename:

        return error_response(
            message="PDF file is required",
            error={
                "stage": "validation"
            }
        )

    file_extension = file.filename.split(".")[-1].lower()

    if file_extension != "pdf":

        return error_response(
            message="Only PDF files are allowed",
            error={
                "stage": "validation",
                "allowed_format": "pdf"
            }
        )

    unique_filename = f"{uuid.uuid4()}.pdf"

    file_path = os.path.join(
        UPLOAD_DIR,
        unique_filename
    )

    try:

        with open(file_path, "wb") as buffer:

            buffer.write(
                await file.read()
            )

    except Exception as e:

        return error_response(
            message="Failed to save uploaded PDF",
            error={
                "stage": "file_save",
                "details": str(e)
            }
        )

    extracted = extract_text_from_pdf(
        file_path
    )

    if not extracted.get("success"):

        return error_response(
            message=extracted.get("message", "Failed to extract text from PDF"),
            error={
                "stage": "pdf_text_extraction",
                "details": extracted.get("error")
            }
        )

    sid = (session_id or "").strip() or None
    result = add_document_to_rag(
        extracted.get("text"),
        session_id=sid,
    )

    if not result.get("success"):

        return error_response(
            message=result.get("message", "Failed to add PDF text to RAG"),
            error=result
        )

    return success_response(
        message="PDF uploaded and added to RAG successfully",
        data={
            "file_name": file.filename,
            "chunks_added": result.get("chunks_added"),
            "total_chunks": result.get("total_chunks"),
            "rag_scope": result.get("rag_scope"),
            "session_id": result.get("session_id"),
        }
    )


@router.post("/rag/ask")
async def ask_document_question(
    request: QuestionRequest
):
    """
    Ask a question from uploaded RAG documents.
    When session_id is set, only that session's documents are searched.
    """

    if not request.question.strip():

        return error_response(
            message="Question is required",
            error={
                "stage": "validation"
            }
        )

    result = ask_rag_question(
        request.question,
        session_id=request.session_id,
    )

    if not result.get("success"):

        return error_response(
            message=result.get("message", "Could not answer question"),
            error={
                "stage": "rag_retrieval",
                "details": result
            }
        )

    return success_response(
        message=result.get("message", "Answer generated successfully"),
        data={
            "question": result.get("question"),
            "answer": result.get("answer"),
            "answer_source": result.get("answer_source"),
            "similarity_score": result.get("similarity_score"),
            "sources": result.get("sources") or [],
            "rag_scope": result.get("rag_scope"),
        }
    )
