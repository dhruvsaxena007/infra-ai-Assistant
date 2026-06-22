import numpy as np


# COSINE SIMILARITY
def cosine_similarity(vec1, vec2):

    vec1 = np.array(vec1)
    vec2 = np.array(vec2)

    dot_product = np.dot(vec1, vec2)

    norm_vec1 = np.linalg.norm(vec1)
    norm_vec2 = np.linalg.norm(vec2)

    similarity = dot_product / (norm_vec1 * norm_vec2)

    return similarity


# SEMANTIC SEARCH
def semantic_search(query_embedding, machines):

    results = []

    for machine in machines:

        # SKIP IF EMBEDDING DOES NOT EXIST
        if "embedding" not in machine:
            continue

        machine_embedding = machine["embedding"]

        # SKIP EMPTY EMBEDDINGS
        if not machine_embedding:
            continue

        similarity = cosine_similarity(
            query_embedding,
            machine_embedding
        )

        machine["similarity_score"] = float(similarity)

        results.append(machine)

    # SORT BEST RESULTS
    results = sorted(
        results,
        key=lambda x: x["similarity_score"],
        reverse=True
    )

    return results