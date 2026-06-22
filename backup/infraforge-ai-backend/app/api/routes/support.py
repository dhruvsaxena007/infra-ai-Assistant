from datetime import datetime, timezone

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.database.mongodb import database
from app.utils.response import error_response, success_response

router = APIRouter()


class SupportRequestBody(BaseModel):
    session_id: str = ""
    name: str = Field(..., min_length=1, max_length=120)
    mobile: str = Field(..., min_length=6, max_length=20)
    order_id: str = ""
    issue_type: str = ""
    message: str = Field(..., min_length=1, max_length=2000)


@router.post("/support/request")
async def create_support_request(body: SupportRequestBody):
    """Capture a support handover request for follow-up."""
    name = body.name.strip()
    mobile = body.mobile.strip()
    if not name or not mobile:
        return error_response(
            message="Name and mobile are required",
            error={"stage": "validation"},
        )

    doc = {
        "session_id": (body.session_id or "").strip(),
        "name": name,
        "mobile": mobile,
        "order_id": (body.order_id or "").strip(),
        "issue_type": (body.issue_type or "").strip() or "general",
        "message": body.message.strip(),
        "status": "open",
        "created_at": datetime.now(timezone.utc),
    }
    result = await database.support_requests.insert_one(doc)
    return success_response(
        message="Support request received. Our team will contact you soon.",
        data={"request_id": str(result.inserted_id)},
    )
