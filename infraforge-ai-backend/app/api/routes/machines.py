from fastapi import APIRouter
from bson import ObjectId

from app.ai.embedding_service import generate_embedding
from app.ai.intelligent_search import intelligent_machine_search
from app.ai.search_service import semantic_search
from app.database.mongodb import database
from app.models.machine_model import MachineModel
from app.utils.sanitize import (
    without_embedding,
    without_embeddings,
    deduplicate_machines,
)
from app.utils.response import success_response, error_response
from app.utils.machine_repository import (
    fetch_machine_by_id,
    fetch_machines,
    find_similar_raw_for_insights,
    search_by_filters as repo_search_by_filters,
)

from app.ai.recommendation_service import recommend_similar_machines
from app.ai.image_quality_service import detect_blur
from app.ai.image_hash_service import generate_image_hash
from app.ai.comparison_service import compare_machines
from app.ai.price_insight_service import calculate_price_insight
from app.ai.deal_score_service import calculate_deal_score
from app.utils.machine_normalizer import effective_price
from app.ai.image_classification_service import classify_machine_image
from app.ai.text_understanding_service import understand_user_text


router = APIRouter()


def is_valid_object_id(machine_id: str):
    return ObjectId.is_valid(machine_id)


async def _fetch_machine_or_none(machine_id: str):
    """Load by ObjectId or string _id (seed listings use seed_* ids)."""
    return await fetch_machine_by_id(database, machine_id)


# =========================================
# CREATE MACHINE
# =========================================

@router.post("/machines")
async def create_machine(machine: MachineModel):

    machine_dict = machine.dict()

    embedding_text = f"""
    {machine.name}
    {machine.category}
    {machine.description}
    """

    embedding = generate_embedding(
        embedding_text
    )

    machine_dict["embedding"] = embedding

    result = await database.machines.insert_one(
        machine_dict
    )

    return success_response(
        message="Machine created successfully",
        data={
            "id": str(result.inserted_id)
        }
    )


# =========================================
# GET ALL MACHINES
# =========================================

@router.get("/machines")
async def get_machines(
    scope: str = "all",
):
    """
    List machines from MongoDB.

    scope=all (default): every document in the machines collection (full dump).
    scope=active: only active + public marketplace listings (same as search filters).
    """
    scope = (scope or "all").lower().strip()

    if scope == "active":
        from app.utils.machine_repository import load_machines_for_semantic_search

        machines = await load_machines_for_semantic_search(database, {})
    else:
        machines = await fetch_machines(database)

    return success_response(
        message="Machines fetched successfully",
        data={
            "scope": scope,
            "count": len(machines),
            "machines": without_embeddings(machines),
        },
    )


# =========================================
# SEARCH MACHINES BY NAME
# =========================================

@router.get("/machines/search")
async def search_machines(query: str):

    all_machines = await fetch_machines(database)
    query_lower = (query or "").lower()

    machines = [
        m for m in all_machines
        if query_lower in str(m.get("name", "")).lower()
    ]

    return success_response(
        message="Machine search completed successfully",
        data={
            "query": query,
            "count": len(machines),
            "machines": without_embeddings(machines)
        }
    )


# =========================================
# FILTER MACHINES
# =========================================

@router.get("/machines/filter")
async def filter_machines(
    city: str = None,
    category: str = None,
    max_price: float = None
):

    machines = await repo_search_by_filters(
        database,
        category=category,
        city=city,
        max_price=max_price,
        limit=100,
        exact_category=True,
    )

    return success_response(
        message="Machine filter completed successfully",
        data={
            "filters": {
                "city": city,
                "category": category,
                "max_price": max_price
            },
            "count": len(machines),
            "machines": without_embeddings(machines)
        }
    )


# =========================================
# SEMANTIC AI SEARCH
# =========================================

@router.get("/machines/semantic-search")
async def semantic_ai_search(query: str):

    query_embedding = generate_embedding(query)

    machines = await fetch_machines(database)

    results = semantic_search(query_embedding, machines)

    clean_results = deduplicate_machines(without_embeddings(results[:5]))

    return success_response(
        message="Semantic search completed successfully",
        data={
            "query": query,
            "count": len(clean_results),
            "machines": clean_results
        }
    )


# =========================================
# INTELLIGENT AI SEARCH
# =========================================

@router.get("/machines/ai-search")
async def ai_search(query: str):

    results = await intelligent_machine_search(
        query,
        database
    )

    clean_results = deduplicate_machines(
        without_embeddings(results)
    )

    return success_response(
        message="AI search completed successfully",
        data={
            "query": query,
            "count": len(clean_results),
            "machines": clean_results
        }
    )


# =========================================
# GET SINGLE MACHINE
# =========================================

@router.get("/machines/{machine_id}")
async def get_machine(machine_id: str):

    machine = await _fetch_machine_or_none(machine_id)

    if not machine:

        return error_response(
            message="Machine not found",
            error={
                "machine_id": machine_id
            }
        )

    return success_response(
        message="Machine fetched successfully",
        data={
            "machine": without_embedding(machine)
        }
    )


# =========================================
# MACHINE RECOMMENDATIONS
# =========================================

@router.get("/machines/{machine_id}/recommendations")
async def get_recommendations(machine_id: str):

    machine = await _fetch_machine_or_none(machine_id)

    if not machine:

        return error_response(
            message="Machine not found",
            error={
                "machine_id": machine_id
            }
        )

    try:
        recommendations = await recommend_similar_machines(
            machine,
            database,
        )
    except Exception as exc:
        return error_response(
            message="Could not generate recommendations",
            error={
                "machine_id": machine_id,
                "details": str(exc),
            },
        )

    clean_recommendations = deduplicate_machines(
        without_embeddings(recommendations)
    )

    return success_response(
        message="Machine recommendations fetched successfully",
        data={
            "machine_id": machine_id,
            "count": len(clean_recommendations),
            "recommendations": clean_recommendations,
        },
    )


# =========================================
# IMAGE QUALITY CHECK
# =========================================

@router.get("/image-quality")
async def check_image_quality(image_path: str):

    result = detect_blur(
        image_path
    )

    if not result.get("success", True):

        return error_response(
            message="Image quality check failed",
            error=result
        )

    return success_response(
        message="Image quality checked successfully",
        data=result
    )


# =========================================
# IMAGE HASH / DUPLICATE CHECK
# =========================================

@router.get("/image-hash")
async def get_image_hash(image_path: str):

    result = generate_image_hash(
        image_path
    )

    if not result.get("success", True):

        return error_response(
            message="Image hash generation failed",
            error=result
        )

    return success_response(
        message="Image hash generated successfully",
        data=result
    )


# =========================================
# MACHINE COMPARISON
# =========================================

@router.get("/compare-machines")
async def compare_two_machines(
    machine1_id: str,
    machine2_id: str,
    include_summary: bool = False,
):

    machine1 = await _fetch_machine_or_none(machine1_id)
    machine2 = await _fetch_machine_or_none(machine2_id)

    if not machine1 or not machine2:

        return error_response(
            message="Machine not found",
            error={
                "machine1_found": bool(machine1),
                "machine2_found": bool(machine2)
            }
        )

    machine1["_id"] = str(machine1.get("_id", machine1_id))
    machine2["_id"] = str(machine2.get("_id", machine2_id))

    m1 = without_embedding(machine1)
    m2 = without_embedding(machine2)
    result = compare_machines(m1, m2)

    if include_summary:
        from app.ai.comparison_service import generate_comparison_summary
        result["llm_summary"] = await generate_comparison_summary(m1, m2, result)

    return success_response(
        message="Machines compared successfully",
        data=result
    )


# =========================================
# AI PRICE INSIGHT ENGINE
# =========================================

@router.get("/price-insight/{machine_id}")
async def get_price_insight(machine_id: str):

    machine = await _fetch_machine_or_none(machine_id)

    if not machine:

        return error_response(
            message="Machine not found",
            error={
                "machine_id": machine_id
            }
        )

    similar_machines = await find_similar_raw_for_insights(
        database,
        machine,
        exclude_id=machine_id,
    )

    result = calculate_price_insight(
        without_embedding(machine),
        without_embeddings(similar_machines)
    )

    return success_response(
        message="Price insight generated successfully",
        data=result
    )


# =========================================
# DEAL SCORE ENGINE
# =========================================

@router.get("/deal-score/{machine_id}")
async def get_deal_score(machine_id: str):

    machine = await _fetch_machine_or_none(machine_id)

    if not machine:

        return error_response(
            message="Machine not found",
            error={
                "machine_id": machine_id
            }
        )

    similar_machines = await find_similar_raw_for_insights(
        database,
        machine,
        exclude_id=machine_id,
    )

    prices = [
        effective_price(item)
        for item in similar_machines
        if effective_price(item) is not None
    ]

    average_market_price = (
        sum(prices) / len(prices)
        if prices
        else None
    )

    result = calculate_deal_score(
        without_embedding(machine),
        average_market_price
    )

    return success_response(
        message="Deal score calculated successfully",
        data=result
    )


# =========================================
# IMAGE CLASSIFICATION AI
# =========================================

@router.get("/classify-image")
async def classify_image(
    image_path: str
):

    result = classify_machine_image(
        image_path
    )

    if not result.get("success"):

        return error_response(
            message="Image classification failed",
            error=result
        )

    return success_response(
        message="Image classified successfully",
        data=result
    )


# =========================================
# TEXT UNDERSTANDING / MULTILINGUAL AI
# =========================================

@router.post("/understand-text")
async def understand_text(payload: dict):

    message = payload.get("message")

    if not message:

        return error_response(
            message="message is required",
            error={
                "stage": "validation"
            }
        )

    result = understand_user_text(
        message
    )

    if not result.get("success"):

        return error_response(
            message="Text understanding failed",
            error=result
        )

    return success_response(
        message="Text understood successfully",
        data=result.get("data")
    )