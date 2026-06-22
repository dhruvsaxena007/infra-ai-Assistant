"""
NumPy vector utilities (replaces scikit-learn cosine_similarity for RAG/search).
"""

from __future__ import annotations

import numpy as np


def cosine_similarity(vec1, vec2) -> float:
    """Cosine similarity between two 1-D vectors. Returns 0.0 if either norm is zero."""
    a = np.asarray(vec1, dtype=np.float64).ravel()
    b = np.asarray(vec2, dtype=np.float64).ravel()
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))


def cosine_similarity_batch(query_vec, matrix) -> np.ndarray:
    """Cosine similarity between query_vec and each row of matrix."""
    q = np.asarray(query_vec, dtype=np.float64).ravel()
    m = np.asarray(matrix, dtype=np.float64)
    if m.ndim == 1:
        m = m.reshape(1, -1)
    q_norm = np.linalg.norm(q)
    if q_norm == 0.0:
        return np.zeros(m.shape[0], dtype=np.float64)
    m_norms = np.linalg.norm(m, axis=1)
    dots = m @ q
    denom = m_norms * q_norm
    with np.errstate(divide="ignore", invalid="ignore"):
        scores = np.where(denom > 0, dots / denom, 0.0)
    return scores.astype(np.float64)
