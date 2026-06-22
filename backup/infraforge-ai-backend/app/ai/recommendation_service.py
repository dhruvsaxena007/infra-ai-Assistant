from app.ai.embedding_service import generate_embedding, is_model_ready
from app.ai.search_service import semantic_search
from app.utils.machine_normalizer import build_machine_search_text, rating_score_neutral
from app.utils.machine_repository import fetch_machines, find_similar_raw_for_insights
from app.utils.sanitize import deduplicate_machines


def _rule_based_score(source: dict, candidate: dict) -> float:
    """Fallback ranking when embeddings are missing or semantic search is empty."""
    score = 0.0
    if (
        str(candidate.get("category") or "").lower()
        == str(source.get("category") or "").lower()
    ):
        score += 0.55
    if (
        str(candidate.get("city") or "").lower()
        == str(source.get("city") or "").lower()
    ):
        score += 0.25
    if (
        str(candidate.get("brand") or "").lower()
        == str(source.get("brand") or "").lower()
    ):
        score += 0.10
    score += rating_score_neutral(candidate) * 0.10
    return score


def _rank_recommendations(source: dict, candidates: list) -> list:
    for item in candidates:
        similarity = float(item.get("similarity_score", 0))

        category_score = 1.0 if (
            str(item.get("category", "")).lower()
            == str(source.get("category", "")).lower()
        ) else 0.0

        city_score = 1.0 if (
            str(item.get("city", "")).lower()
            == str(source.get("city", "")).lower()
        ) else 0.0

        rating_score = rating_score_neutral(item)

        if similarity > 0:
            item["recommendation_score"] = (
                similarity * 0.5
                + category_score * 0.25
                + city_score * 0.15
                + rating_score * 0.10
            )
        else:
            item["recommendation_score"] = _rule_based_score(source, item)

    candidates.sort(
        key=lambda x: x.get("recommendation_score", 0),
        reverse=True,
    )
    return candidates


async def _load_candidate_pool(database, machine: dict, machine_id: str) -> list:
    """Prefer same category/city; broaden to same category if needed."""
    primary = await find_similar_raw_for_insights(
        database,
        machine,
        exclude_id=machine_id,
        limit=80,
    )
    if len(primary) >= 3:
        return primary

    category = (machine.get("category") or "").lower()
    if not category:
        return primary

    all_machines = await fetch_machines(database)
    source_id = str(machine.get("_id") or machine_id)
    broad = [
        m for m in all_machines
        if str(m.get("_id")) != source_id
        and str(m.get("category") or "").lower() == category
    ]
    return broad or primary


async def recommend_similar_machines(machine, database):
    """
    Recommend similar machines using embeddings + hybrid recommendation ranking.
    Falls back to category/city/brand rules when embeddings are unavailable.
    """
    machine_id = str(machine.get("_id") or machine.get("id") or "")
    candidates = await _load_candidate_pool(database, machine, machine_id)
    if not candidates:
        return []

    query = build_machine_search_text(machine) or " ".join(
        filter(
            None,
            [
                machine.get("name"),
                machine.get("category"),
                machine.get("description"),
            ],
        )
    )

    ranked = candidates
    if is_model_ready():
        try:
            query_embedding = generate_embedding(query)
            semantic_hits = semantic_search(query_embedding, candidates)
            if semantic_hits:
                ranked = semantic_hits
        except Exception as exc:
            print(f"[recommendations] semantic ranking fallback: {exc}")

    ranked = _rank_recommendations(machine, ranked)
    return deduplicate_machines(ranked[:5])
