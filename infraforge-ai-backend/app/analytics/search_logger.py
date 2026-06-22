from datetime import datetime


async def save_search_log(
    database,
    session_id: str,
    user_message: str,
    search_query: str,
    filters: dict,
    result_count: int,
    fallback_used: bool = False,
    fallback_query: str = None
):
    log = {
        "session_id": session_id,
        "user_message": user_message,
        "search_query": search_query,
        "filters": filters,
        "result_count": result_count,
        "fallback_used": fallback_used,
        "fallback_query": fallback_query,
        "created_at": datetime.utcnow()
    }

    await database.search_logs.insert_one(log)

    return True
