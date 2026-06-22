"""
Shared helpers for price insight, deal score, and comparison services.
"""

from __future__ import annotations

from app.utils.machine_normalizer import effective_price, rating_score_neutral


def filter_priced_peers(machines: list, exclude_id=None) -> list[dict]:
    """Peers with a valid effective price, optionally excluding one machine id."""
    peers = []
    for item in machines:
        if exclude_id and item.get("_id") == exclude_id:
            continue
        if effective_price(item) is not None:
            peers.append(item)
    return peers


def average_peer_price(peers: list) -> tuple[float | None, int]:
    total = 0.0
    count = 0
    for item in peers:
        price = effective_price(item)
        if price is not None:
            total += price
            count += 1
    if count == 0:
        return None, 0
    return total / count, count


def peer_average_rating_score(peers: list) -> float:
    """Mean neutral rating score (0–1) for peers; 0.5 if none rated."""
    scores = [rating_score_neutral(p) for p in peers]
    if not scores:
        return 0.5
    return sum(scores) / len(scores)
