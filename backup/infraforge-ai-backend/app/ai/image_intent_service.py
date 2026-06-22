"""
Free local image → marketplace category intent.

Combines:
  1. MobileNet ImageNet labels (weighted top-K)
  2. OpenCV shape/color heuristics (no paid API)

Does NOT use Groq/OpenAI vision.
"""

from __future__ import annotations

import re
from typing import Any

from app.ai.clip_image_classifier import clip_category_scores
from app.ai.opencv_visual_classifier import opencv_machine_hints

# (canonical_category, keywords, per-hit multiplier)
# Order matters for tie-break — more specific categories first.
_CATEGORY_RULES: list[tuple[str, list[str], float]] = [
    (
        "road roller",
        [
            "steamroller", "steam roller", "road roller", "roller",
            "compactor", "vibratory", "paver", "steam-roller",
        ],
        1.2,
    ),
    (
        "crawler drill",
        [
            "drill", "drilling", "drill rig", "oil rig", "rig",
            "pneumatic", "boring", "well drilling",
        ],
        1.1,
    ),
    (
        "hydra crane",
        ["hydra", "truck crane", "mobile crane"],
        1.0,
    ),
    (
        "crane",
        ["crane", "tower crane", "crawler crane", "gantry", "winch", "hoist"],
        1.0,
    ),
    (
        "backhoe loader",
        [
            "backhoe", "backhoe loader", "jcb", "loader backhoe",
            "forklift",  # often confused with JCB in field photos
        ],
        1.0,
    ),
    (
        "wheel loader",
        ["wheel loader", "front loader", "front-end loader", "skip loader"],
        1.0,
    ),
    (
        "bulldozer",
        ["bulldozer", "dozer", "crawler dozer"],
        1.0,
    ),
    (
        "dump truck",
        [
            "dump truck", "tipper", "dumper", "lorry", "trailer truck",
            "garbage truck", "haul truck", "mining truck", "ton truck",
            "articulated truck", "heavy truck",
        ],
        1.05,
    ),
    (
        "concrete mixer",
        ["concrete mixer", "cement mixer", "transit mixer"],
        1.0,
    ),
    (
        "concrete pump",
        ["concrete pump", "boom pump", "trailer pump"],
        1.0,
    ),
    (
        "motor grader",
        ["grader", "motor grader"],
        1.0,
    ),
    (
        "air compressor",
        ["air compressor", "compressor"],
        0.9,
    ),
    (
        "mobile crusher",
        ["crusher", "crushing", "screen"],
        0.9,
    ),
    (
        "excavator",
        [
            "excavator", "power shovel", "digger", "mining shovel",
            "hydraulic excavator",
        ],
        1.0,
    ),
]

# Labels that must NOT trigger excavator on substring match
_EXCAVATOR_BLOCKLIST = (
    "steamroller", "steam roller", "roller", "compactor", "drill", "crane",
    "mixer", "grader", "compressor", "forklift", "bulldozer", "dozer",
    "truck", "dumper", "tipper", "tractor",
)

_MIN_INTENT_SCORE = 0.08
_STRONG_INTENT_SCORE = 0.18

# ImageNet often mislabels clear product photos on white backgrounds
_NOISE_LABELS = frozenset({
    "web_site", "website", "desktop_computer", "laptop", "monitor",
    "screen", "television", "entertainment_center", "notebook",
    "cash_machine", "ipod", "cellular_telephone", "mouse",
    "keyboard", "printer", "tape_player", "hand-held_computer",
})


def _normalize_label(label: str) -> str:
    return re.sub(r"[_\-]+", " ", (label or "").lower()).strip()


def _keyword_in_label(keyword: str, label: str) -> bool:
    kw = keyword.lower().strip()
    if not kw or not label:
        return False
    if " " in kw:
        return kw in label
    return re.search(rf"\b{re.escape(kw)}\b", label) is not None


def _predictions_are_noise(predictions: list[dict]) -> bool:
    if not predictions:
        return True
    top_label = _normalize_label(predictions[0].get("label", ""))
    if top_label in _NOISE_LABELS:
        return True
    return any(
        _normalize_label(p.get("label", "")) in _NOISE_LABELS
        for p in predictions[:3]
    )


def score_predictions(predictions: list[dict]) -> dict[str, float]:
    """Aggregate MobileNet top-K labels into canonical category scores."""
    scores: dict[str, float] = {}

    if _predictions_are_noise(predictions):
        return scores

    for pred in predictions:
        label = _normalize_label(pred.get("label", ""))
        conf = float(pred.get("confidence") or 0.0)
        if not label or conf <= 0:
            continue

        for category, keywords, multiplier in _CATEGORY_RULES:
            for keyword in keywords:
                if not _keyword_in_label(keyword, label):
                    continue

                if category == "excavator":
                    if any(_keyword_in_label(b, label) for b in _EXCAVATOR_BLOCKLIST):
                        continue
                    if keyword == "shovel" and "power" not in label and "excavator" not in label:
                        continue

                if category == "backhoe loader" and keyword == "forklift":
                    if _keyword_in_label("roller", label) or _keyword_in_label("crane", label):
                        continue

                scores[category] = scores.get(category, 0.0) + conf * multiplier
                break

    return scores


def get_visual_category_scores(
    image_path: str | None,
) -> tuple[dict[str, float], dict[str, float]]:
    """CLIP zero-shot + OpenCV heuristics (no TensorFlow). Returns (merged, clip_only)."""
    if not image_path:
        return {}, {}
    clip_scores = clip_category_scores(image_path)
    cv_scores = opencv_machine_hints(image_path)
    if not clip_scores and not cv_scores:
        return {}, {}
    if not clip_scores:
        return cv_scores, {}
    if not cv_scores:
        return clip_scores, clip_scores

    ranked = sorted(clip_scores.items(), key=lambda x: float(x[1]), reverse=True)
    best_score = float(ranked[0][1]) if ranked else 0.0
    second_score = float(ranked[1][1]) if len(ranked) > 1 else 0.0
    clip_confident = best_score >= 0.26 and (best_score - second_score) >= 0.05

    merged = dict(clip_scores)
    cv_weight = 0.22 if clip_confident else 0.55
    for cat, val in cv_scores.items():
        merged[cat] = merged.get(cat, 0.0) + float(val) * cv_weight
    return merged, clip_scores


def merge_hint_scores(
    model_scores: dict[str, float],
    hint_scores: dict[str, float],
) -> dict[str, float]:
    merged = dict(model_scores)
    for cat, val in hint_scores.items():
        merged[cat] = merged.get(cat, 0.0) + val
    return merged


def extract_machine_search_intent(
    predictions: list[dict],
    *,
    image_path: str | None = None,
) -> dict[str, Any]:
    """
    Map classifier output (+ optional OpenCV hints) to marketplace search intent.
    """
    model_scores = score_predictions(predictions)
    visual_scores, clip_only = get_visual_category_scores(image_path)
    if _predictions_are_noise(predictions) and clip_only:
        clip_ranked = sorted(clip_only.items(), key=lambda x: float(x[1]), reverse=True)
        c_best, c_score = clip_ranked[0]
        cv_scores = opencv_machine_hints(image_path) if image_path else {}
        combined = {c_best: float(c_score) + float(cv_scores.get(c_best, 0)) * 0.18}
        for cat, sc in clip_ranked[1:4]:
            if float(sc) >= float(c_score) - 0.05:
                combined[cat] = float(sc) + float(cv_scores.get(cat, 0)) * 0.12
    elif _predictions_are_noise(predictions) and visual_scores:
        combined = dict(visual_scores)
    elif visual_scores:
        combined = merge_hint_scores(model_scores, visual_scores)
    else:
        combined = dict(model_scores)

    labels_debug = " | ".join(
        f"{p.get('label')} ({float(p.get('confidence', 0)):.3f})"
        for p in predictions[:5]
    )
    print("IMAGE LABELS:", labels_debug)
    print("IMAGE CATEGORY SCORES:", combined)

    if not combined:
        if _predictions_are_noise(predictions):
            return _unknown_intent(
                "Could not analyze this image as equipment (it may be a screenshot or "
                "compressed preview). Upload the original machine photo file (JPG/PNG), "
                "or search by text (e.g. road roller in Jaipur)."
            )
        return _unknown_intent(
            "Could not map this image to a construction machine category. "
            "Try a clearer side photo or search by text (e.g. road roller in Jaipur)."
        )

    # Drop invalid keys from scoring
    combined = {
        k: v for k, v in combined.items()
        if k and str(k).lower().replace("_", " ") not in ("unknown", "other", "misc")
    }

    if not combined:
        return _unknown_intent(
            "Could not map this image to a construction machine category. "
            "Try a clearer side photo or search by text (e.g. dump truck in Delhi)."
        )

    # When CLIP has a clear winner, prefer it over noisy OpenCV overrides.
    if clip_only:
        clip_ranked = sorted(clip_only.items(), key=lambda x: float(x[1]), reverse=True)
        c_best, c_score = clip_ranked[0]
        c_second = float(clip_ranked[1][1]) if len(clip_ranked) > 1 else 0.0
        if c_score >= 0.24 and (c_score - c_second) >= 0.035:
            combined[c_best] = max(float(combined.get(c_best, 0)), c_score)

    ranked = sorted(combined.items(), key=lambda x: x[1], reverse=True)
    best_cat, best_score = ranked[0]
    second_score = ranked[1][1] if len(ranked) > 1 else 0.0

    # Ambiguous only when scores are genuinely close (not flat CLIP noise).
    if (
        len(ranked) > 1
        and (best_score - second_score) < 0.045
        and second_score >= best_score * 0.92
    ):
        alts = [c for c, _ in ranked[:3]]
        return {
            "match_type": "broad",
            "machine_type": None,
            "search_query": " ".join(alts[:2]),
            "suggested_categories": alts,
            "category_scores": combined,
            "intent_confidence": round(best_score, 4),
            "message": (
                "Image may match more than one machine type "
                f"({', '.join(alts[:2])}). Showing closest matches — "
                "refine with text (e.g. crawler drill in Jaipur)."
            ),
        }

    if best_score < _MIN_INTENT_SCORE:
        return _unknown_intent(
            "Could not confidently identify the machine type from this image. "
            "Please upload a clearer photo or search by text (e.g. crawler drill in Jaipur)."
        )

    confident = best_score >= _STRONG_INTENT_SCORE
    from app.ai.category_mapping import category_label

    msg = f"Detected machine type: {category_label(best_cat)}"
    if not confident:
        msg += (
            " (moderate confidence — results may include similar equipment; "
            "add city or model in chat to refine)."
        )

    if predictions and not _predictions_are_noise(predictions):
        classifier = "mobilenet+visual"
    elif visual_scores:
        classifier = "clip+opencv"
    else:
        classifier = "visual"

    return {
        "match_type": "exact",
        "machine_type": best_cat,
        "search_query": best_cat,
        "suggested_categories": [best_cat],
        "category_scores": combined,
        "intent_confidence": round(best_score, 4),
        "confident": confident,
        "message": msg,
        "classifier": classifier,
    }


def _unknown_intent(message: str) -> dict[str, Any]:
    return {
        "match_type": "unknown",
        "machine_type": None,
        "search_query": None,
        "suggested_categories": [],
        "category_scores": {},
        "intent_confidence": 0.0,
        "confident": False,
        "message": message,
    }


def should_accept_classification(
    predictions: list[dict],
    image_path: str | None = None,
) -> bool:
    """
    Accept image when category intent is strong enough, even if MobileNet top-1 < 0.35.
    """
    intent = extract_machine_search_intent(predictions, image_path=image_path)
    if intent.get("match_type") == "unknown":
        return False
    return float(intent.get("intent_confidence") or 0) >= _MIN_INTENT_SCORE
