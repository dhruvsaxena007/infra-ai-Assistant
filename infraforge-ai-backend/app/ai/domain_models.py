"""
Phase 12 — structured domain interpretation schema.

Compatible with existing intent/action routing; does not replace intents.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

# Domain scope
SCOPE_CONSTRUCTION = "construction"
SCOPE_HEAVY_EQUIPMENT = "heavy_equipment"
SCOPE_MARKETPLACE = "marketplace"
SCOPE_PLATFORM_SUPPORT = "platform_support"
SCOPE_COMPANY_KNOWLEDGE = "company_knowledge"
SCOPE_ADJACENT = "adjacent"
SCOPE_UNRELATED = "unrelated"
SCOPE_UNSAFE = "unsafe"

# Relevance
REL_IN_DOMAIN = "in_domain"
REL_ADJACENT = "adjacent"
REL_OUT_OF_DOMAIN = "out_of_domain"

# Request types
REQ_MARKETPLACE_ACTION = "marketplace_action"
REQ_DOMAIN_KNOWLEDGE = "domain_knowledge"
REQ_RECOMMENDATION = "recommendation"
REQ_COMPARISON = "comparison"
REQ_TROUBLESHOOTING = "troubleshooting"
REQ_SUPPORT = "support"
REQ_DOCUMENT_QUESTION = "document_question"
REQ_CONVERSATIONAL = "conversational"
REQ_UNSUPPORTED_SERVICE = "unsupported_service"
REQ_UNRELATED = "unrelated_request"
REQ_AMBIGUOUS = "ambiguous"

# Response modes
MODE_TOOL_ACTION = "tool_action"
MODE_DOMAIN_ANSWER = "domain_answer"
MODE_CLARIFICATION = "clarification"
MODE_UNSUPPORTED_SERVICE = "unsupported_service"
MODE_UNRELATED_REDIRECT = "unrelated_redirect"
MODE_CONVERSATIONAL = "conversational"
MODE_REFUSAL = "refusal"

# Context actions
CTX_CONTINUE = "continue"
CTX_REVISE = "revise"
CTX_SUSPEND = "suspend"
CTX_RESET = "reset"
CTX_NONE = "none"


@dataclass
class DomainEntities:
    category: str | None = None
    purpose: str | None = None
    city: str | None = None
    brand: str | None = None
    model: str | None = None
    budget: float | None = None
    listing_type: str | None = None
    requested_asset: str | None = None
    transaction_reference: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "category": self.category,
            "purpose": self.purpose,
            "city": self.city,
            "brand": self.brand,
            "model": self.model,
            "budget": self.budget,
            "listing_type": self.listing_type,
            "requested_asset": self.requested_asset,
            "transaction_reference": self.transaction_reference,
        }

    @classmethod
    def from_dict(cls, d: dict | None) -> "DomainEntities":
        d = d or {}
        return cls(
            category=d.get("category"),
            purpose=d.get("purpose"),
            city=d.get("city"),
            brand=d.get("brand"),
            model=d.get("model"),
            budget=d.get("budget") or d.get("max_price"),
            listing_type=d.get("listing_type"),
            requested_asset=d.get("requested_asset"),
            transaction_reference=d.get("transaction_reference"),
        )


@dataclass
class CapabilityValidation:
    registry_checked: bool = False
    catalog_checked: bool = False
    requested_asset_supported: bool | None = None
    requested_action_supported: bool | None = None
    closest_supported_capability: str | None = None
    catalog_match_type: str | None = None  # category | purpose | brand | model | none
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "registry_checked": self.registry_checked,
            "catalog_checked": self.catalog_checked,
            "requested_asset_supported": self.requested_asset_supported,
            "requested_action_supported": self.requested_action_supported,
            "closest_supported_capability": self.closest_supported_capability,
            "catalog_match_type": self.catalog_match_type,
            "notes": self.notes,
        }


@dataclass
class DomainInterpretation:
    user_goal: str = ""
    domain_scope: str = SCOPE_HEAVY_EQUIPMENT
    relevance: str = REL_IN_DOMAIN
    request_type: str = REQ_AMBIGUOUS
    entities: DomainEntities = field(default_factory=DomainEntities)
    context_action: str = CTX_NONE
    needs_marketplace_data: bool = False
    needs_rag: bool = False
    needs_support_tool: bool = False
    can_answer_from_domain_knowledge: bool = False
    needs_clarification: bool = False
    proposed_tool: str | None = None
    response_mode: str = MODE_CLARIFICATION
    confidence: float = 0.0
    reason: str = ""
    source: str = "rules"  # rules | llm | hybrid
    legacy_intent_hint: str | None = None
    capability: CapabilityValidation = field(default_factory=CapabilityValidation)

    def to_dict(self) -> dict[str, Any]:
        return {
            "user_goal": self.user_goal,
            "domain_scope": self.domain_scope,
            "relevance": self.relevance,
            "request_type": self.request_type,
            "entities": self.entities.to_dict(),
            "context_action": self.context_action,
            "needs_marketplace_data": self.needs_marketplace_data,
            "needs_rag": self.needs_rag,
            "needs_support_tool": self.needs_support_tool,
            "can_answer_from_domain_knowledge": self.can_answer_from_domain_knowledge,
            "needs_clarification": self.needs_clarification,
            "proposed_tool": self.proposed_tool,
            "response_mode": self.response_mode,
            "confidence": self.confidence,
            "reason": self.reason,
            "source": self.source,
            "legacy_intent_hint": self.legacy_intent_hint,
            "capability": self.capability.to_dict(),
        }

    @classmethod
    def from_dict(cls, d: dict | None) -> "DomainInterpretation":
        d = d or {}
        cap = d.get("capability") or {}
        return cls(
            user_goal=str(d.get("user_goal") or ""),
            domain_scope=str(d.get("domain_scope") or SCOPE_HEAVY_EQUIPMENT),
            relevance=str(d.get("relevance") or REL_IN_DOMAIN),
            request_type=str(d.get("request_type") or REQ_AMBIGUOUS),
            entities=DomainEntities.from_dict(d.get("entities")),
            context_action=str(d.get("context_action") or CTX_NONE),
            needs_marketplace_data=bool(d.get("needs_marketplace_data")),
            needs_rag=bool(d.get("needs_rag")),
            needs_support_tool=bool(d.get("needs_support_tool")),
            can_answer_from_domain_knowledge=bool(d.get("can_answer_from_domain_knowledge")),
            needs_clarification=bool(d.get("needs_clarification")),
            proposed_tool=d.get("proposed_tool"),
            response_mode=str(d.get("response_mode") or MODE_CLARIFICATION),
            confidence=float(d.get("confidence") or 0.0),
            reason=str(d.get("reason") or ""),
            source=str(d.get("source") or "rules"),
            legacy_intent_hint=d.get("legacy_intent_hint"),
            capability=CapabilityValidation(
                registry_checked=bool(cap.get("registry_checked")),
                catalog_checked=bool(cap.get("catalog_checked")),
                requested_asset_supported=cap.get("requested_asset_supported"),
                requested_action_supported=cap.get("requested_action_supported"),
                closest_supported_capability=cap.get("closest_supported_capability"),
                catalog_match_type=cap.get("catalog_match_type"),
                notes=list(cap.get("notes") or []),
            ),
        )
