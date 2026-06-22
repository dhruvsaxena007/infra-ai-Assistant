from fastapi import APIRouter

from app.utils.response import success_response


router = APIRouter()


@router.get("/assistant/capabilities")
async def get_assistant_capabilities():
    capabilities = [
        {
            "name": "Real Marketplace Data",
            "endpoint": "/machines",
            "status": "active",
            "description": (
                "Live construction equipment marketplace listings with normalized schema, "
                "category-appropriate images, brand/model/spec fields, and rent/sell pricing."
            ),
        },
        {
            "name": "Normalized Machine Schema",
            "endpoint": "all machine endpoints",
            "status": "active",
            "description": (
                "Central machine_normalizer ensures stable API objects with category_display, "
                "images, specifications, availability, listing_type, and source=infraforge_real_db."
            ),
        },
        {
            "name": "Brand / Model / Specification-Aware Search",
            "endpoint": "/chat, /machines/ai-search",
            "status": "active",
            "description": (
                "Search understands brand, model, condition, pincode, listing_type, and "
                "real categories like crawler drill, concrete pump, air compressor."
            ),
        },
        {
            "name": "Natural Language Machine Search",
            "endpoint": "/chat",
            "status": "active",
            "description": "Search machines using English, Hindi, or Hinglish.",
        },
        {
            "name": "Conversational Memory",
            "endpoint": "/chat",
            "status": "active",
            "description": "Maintains session-wise context for follow-up queries.",
        },
        {
            "name": "Image Context Memory",
            "endpoint": "/image-search, /chat",
            "status": "active",
            "description": (
                "Remembers last uploaded image type for follow-ups like "
                "'is this available in Jaipur?'."
            ),
        },
        {
            "name": "Voice Assistant",
            "endpoint": "/voice/chat",
            "status": "active",
            "description": "Speak in Hindi/Hinglish/English and get machine search results.",
        },
        {
            "name": "Image Search AI",
            "endpoint": "/image-search",
            "status": "active",
            "description": (
                "Upload a machine photo; classifier maps to real categories including "
                "crawler drill, crane, backhoe loader, and more."
            ),
        },
        {
            "name": "Rent / Sell Listing-Aware Insights",
            "endpoint": "/price-insight, /deal-score",
            "status": "active",
            "description": (
                "Price insight and deal score handle rent vs sell listings, null ratings, "
                "availability, condition, and security deposit safely."
            ),
        },
        {
            "name": "Machine Comparison",
            "endpoint": "/compare-machines",
            "status": "active",
            "description": "Compare two normalized listings on price, availability, and rating.",
        },
        {
            "name": "Recommendation Engine",
            "endpoint": "/machines/{machine_id}/recommendations",
            "status": "active",
            "description": "Semantic recommendations using rich search text, not description alone.",
        },
        {
            "name": "RAG PDF Q&A",
            "endpoint": "/rag/upload-pdf and /rag/ask",
            "status": "active",
            "description": "Upload PDFs and ask questions from documents.",
        },
        {
            "name": "AI Advisor",
            "endpoint": "/chat",
            "status": "active",
            "description": (
                "Practical recommendations using price, availability, condition, year, and city "
                "when ratings are unavailable."
            ),
        },
        {
            "name": "Search Analytics Logging",
            "endpoint": "/chat",
            "status": "active",
            "description": "Stores chatbot search activity in MongoDB search_logs collection.",
        },
    ]

    future_scope = [
        "Streaming AI responses",
        "Redis/Mongo persistent memory",
        "YOLO construction machine classifier",
        "Geo-distance based machine search",
        "Authentication / JWT",
        "Docker deployment",
        "Cloud deployment",
    ]

    return success_response(
        message="Assistant capabilities fetched successfully",
        data={
            "project": "Infra AI-Assistant for Marketplace",
            "version": "1.1.0",
            "data_source": "infraforge_real_db",
            "capabilities": capabilities,
            "future_scope": future_scope,
        },
    )
