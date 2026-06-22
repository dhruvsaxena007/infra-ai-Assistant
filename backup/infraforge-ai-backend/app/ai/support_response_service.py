"""
Structured responses for non-search marketplace intents.
"""

from __future__ import annotations

from typing import Any, Optional

from app.core.config import settings

UNKNOWN_CHIPS = [
    "Search machine",
    "Booking issue",
    "Refund/Return",
    "Payment issue",
    "Contact support",
]

NON_SEARCH_INTENTS = frozenset({
    "greeting",
    "order_issue",
    "refund_return",
    "payment_issue",
    "delivery_logistics",
    "security_deposit",
    "complaint",
    "support_request",
    "contact_owner",
    "booking_help",
    "platform_how_to",
    "general_marketplace_help",
    "document_question",
    "out_of_scope",
    "unknown",
    "compare_machine",
})


def build_handover(
    reason: str,
    *,
    message: Optional[str] = None,
) -> dict[str, Any]:
    phone = (settings.SUPPORT_PHONE or "").strip()
    whatsapp = (settings.SUPPORT_WHATSAPP or phone).strip()
    actions: list[dict[str, Any]] = []
    if phone:
        actions.append({"label": "Call", "type": "call", "value": phone})
    if whatsapp:
        actions.append({"label": "WhatsApp", "type": "whatsapp", "value": whatsapp})
    actions.append({"label": "Raise Request", "type": "request", "value": None})
    return {
        "enabled": True,
        "reason": reason,
        "message": message or "Do you want to talk to support?",
        "actions": actions,
    }


def _order_prompt(entities: dict, lang: str) -> str:
    if entities.get("order_id"):
        return ""
    if lang == "hinglish":
        return " Please booking/order ID ya registered mobile number share karein."
    return " Please share your booking ID/order ID or registered mobile number."


def build_response(
    intent: str,
    *,
    entities: Optional[dict] = None,
    lang: str = "english",
    has_machine_context: bool = False,
) -> dict[str, Any]:
    """Return message, assistant_mode, suggestions, handover for non-search intents."""
    ents = entities or {}
    oid_note = _order_prompt(ents, lang)
    handover_msg = "Do you want to talk to support?"

    if intent == "refund_return":
        msg = (
            "I can help with refund or return."
            + oid_note
            + " Refund/return depends on booking status and InfraForge policy."
        )
        if lang == "hinglish":
            msg = (
                "Refund ke liye booking/order ID required hoga."
                + oid_note
                + " Refund eligibility booking status aur policy par depend karti hai."
            )
        return {
            "message": msg,
            "assistant_mode": "refund_return",
            "suggestions": ["Share order ID", "Contact support", "Raise Request"],
            "handover": build_handover("refund_return", message=handover_msg),
        }

    if intent == "order_issue":
        msg = (
            "I can help with your booking/order issue."
            + oid_note
            + " Our support team can check booking status and resolve the problem."
        )
        if lang == "hinglish":
            msg = (
                "Main aapki booking/order issue me help kar sakta hoon."
                + oid_note
            )
        return {
            "message": msg,
            "assistant_mode": "order_issue",
            "suggestions": ["Share order ID", "Contact support", "Raise Request"],
            "handover": build_handover("order_issue", message=handover_msg),
        }

    if intent == "payment_issue":
        msg = (
            "If amount was deducted but booking is not confirmed, please share "
            "transaction ID or order ID. Our team can verify payment status."
        )
        if lang == "hinglish":
            msg = (
                "Samajh gaya. Payment deducted but booking confirm nahi hui."
                + oid_note
                + " Transaction ID share karein, main support request raise karne me help kar sakta hoon."
            )
        return {
            "message": msg,
            "assistant_mode": "payment_issue",
            "suggestions": ["Share transaction ID", "Contact support", "Raise Request"],
            "handover": build_handover("payment_issue", message=handover_msg),
        }

    if intent == "security_deposit":
        msg = (
            "Security deposit terms depend on machine type, rental duration, and owner policy. "
            "Share your booking ID for exact deposit/refund details."
            + oid_note
        )
        return {
            "message": msg,
            "assistant_mode": "payment_issue",
            "suggestions": ["Contact support", "Booking issue"],
            "handover": build_handover("security_deposit", message=handover_msg),
        }

    if intent == "delivery_logistics":
        msg = (
            "Delivery/transport depends on machine location, your site city, and owner terms. "
            "Please share machine name and site city so we can guide you."
            + oid_note
        )
        if lang == "hinglish":
            msg = (
                "Delivery/transport machine location, site city aur owner terms par depend karta hai. "
                "Machine name aur site city share karein."
            )
        return {
            "message": msg,
            "assistant_mode": "support",
            "suggestions": ["Contact support", "Search machine"],
            "handover": build_handover("delivery_logistics", message=handover_msg),
        }

    if intent == "complaint":
        msg = (
            "Sorry to hear that. Please share order/booking ID and describe the issue. "
            "You can raise a support request or contact us directly."
        )
        return {
            "message": msg,
            "assistant_mode": "support",
            "suggestions": ["Raise Request", "Contact support"],
            "handover": build_handover("complaint", message=handover_msg),
        }

    if intent == "support_request":
        msg = "Sure — I can connect you with support. Call, WhatsApp, or raise a request below."
        return {
            "message": msg,
            "assistant_mode": "handover",
            "suggestions": [],
            "handover": build_handover("support_request", message=handover_msg),
        }

    if intent == "contact_owner":
        if not has_machine_context:
            msg = (
                "I can help you contact the machine owner. Which machine or listing "
                "are you interested in? Search a machine first, then use Contact Owner on the card."
            )
            return {
                "message": msg,
                "assistant_mode": "support",
                "suggestions": ["Search machine", "Contact support"],
                "handover": None,
            }
        msg = (
            "Use the Contact Owner button on the machine card to reach the seller. "
            "Support can assist if you need help connecting."
        )
        return {
            "message": msg,
            "assistant_mode": "handover",
            "suggestions": ["Contact support"],
            "handover": build_handover("contact_owner", message=handover_msg),
        }

    if intent == "platform_how_to":
        msg = (
            "On InfraForge you can book/rent a machine like this:\n"
            "1. Search the machine type and city\n"
            "2. Open machine details and check price\n"
            "3. Tap Contact Owner or Raise Request\n"
            "4. Confirm rent/buy terms with owner/team\n"
            "5. Support assists if booking or payment needs help\n\n"
            "Which type of machine are you looking for?"
        )
        if lang == "hinglish":
            msg = (
                "InfraForge par machine book/rent karne ke liye:\n"
                "1. Machine search karein (type + city)\n"
                "2. Details aur price check karein\n"
                "3. Contact Owner ya Raise Request par click karein\n"
                "4. Team/owner availability confirm karega\n\n"
                "Aap kis type ki machine dhoond rahe hain?"
            )
        return {
            "message": msg,
            "assistant_mode": "platform_how_to",
            "suggestions": ["Search machine", "Contact support", "Excavator in Jaipur"],
            "handover": None,
        }

    if intent == "booking_help":
        msg = (
            "To rent or book: search machine → check details → Contact Owner → "
            "confirm dates, site location, and payment. Support can help with booking issues."
        )
        return {
            "message": msg,
            "assistant_mode": "platform_how_to",
            "suggestions": ["Search machine", "Booking issue", "Contact support"],
            "handover": None,
        }

    if intent == "general_marketplace_help":
        msg = (
            "I help with InfraForge machine search, rent/buy, recommendations, "
            "image search, document Q&A, booking issues, refund/return, payment, "
            "delivery questions, and support handover. What would you like to do?"
        )
        if lang == "hinglish":
            msg = (
                "Main machine search, rent/buy, booking issue, refund, payment, "
                "delivery aur support me help karta hoon. Aapko kya chahiye?"
            )
        return {
            "message": msg,
            "assistant_mode": "support",
            "suggestions": UNKNOWN_CHIPS,
            "handover": None,
        }

    if intent == "document_question":
        msg = (
            "Attach a PDF using the document icon, type your question, and send. "
            "I'll answer from the document inside this chat."
        )
        return {
            "message": msg,
            "assistant_mode": "document_qa",
            "suggestions": ["Upload document", "Search machine"],
            "handover": None,
        }

    if intent == "out_of_scope":
        msg = (
            "I'm not a general knowledge assistant. I help with InfraForge machine search, "
            "rental, booking, refund, payment, delivery, and support."
        )
        if lang == "hinglish":
            msg = (
                "Main weather/general knowledge assistant nahi hoon. Main InfraForge "
                "machine search, rental, booking, refund, payment aur support me help karta hoon."
            )
        return {
            "message": msg,
            "assistant_mode": "out_of_scope",
            "suggestions": ["Search machine", "Booking issue", "Contact support"],
            "handover": None,
        }

    if intent == "unknown":
        msg = (
            "I'm not fully sure what you need. I can help with machine search, rent/buy, "
            "booking issues, refund/return, payment, delivery, document questions, or support."
        )
        if lang == "hinglish":
            msg = (
                "Mujhe poora clear nahi hai. Main machine search, booking issue, refund, "
                "payment, delivery, document ya support me help kar sakta hoon."
            )
        return {
            "message": msg,
            "assistant_mode": "unknown",
            "suggestions": UNKNOWN_CHIPS,
            "handover": None,
        }

    if intent == "compare_machine":
        msg = (
            "Select two machines using Compare on the cards, then tap Compare in the bar below. "
            "I can also search machines if you tell me type and city."
        )
        return {
            "message": msg,
            "assistant_mode": "clarification",
            "suggestions": ["Search machine", "Excavator in Delhi"],
            "handover": None,
        }

    return {
        "message": "How can I help you with InfraForge marketplace today?",
        "assistant_mode": "support",
        "suggestions": UNKNOWN_CHIPS,
        "handover": build_handover(intent, message=handover_msg),
    }


def is_non_search_intent(intent: str) -> bool:
    return intent in NON_SEARCH_INTENTS
