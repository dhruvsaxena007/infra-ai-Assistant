"""
Shared Hindi/Latin transliteration for query parsing and voice STT output.

Used by query_parser (text) and voice_input (voice boundary only).
Not voice-specific — no audio or upload logic belongs here.
"""

from __future__ import annotations

import re

from app.ai.industry_lexicon import COMMON_TYPOS

_DEV_DIGITS = {
    "०": "0", "१": "1", "२": "2", "३": "3", "४": "4",
    "५": "5", "६": "6", "७": "7", "८": "8", "९": "9",
}

_NORMALIZE_MAP = {
    "एक्सकेवेटर": "excavator", "एक्स्कावेटर": "excavator", "एक्सकैवेटर": "excavator",
    "एक्सावेटर": "excavator", "खुदाई मशीन": "excavator", "खुदाई": "excavator",
    "जे सी बी": "jcb", "जेसीबी": "jcb", "बैकहो लोडर": "backhoe loader", "बैकहो": "backhoe",
    "क्रेन": "crane", "हाइड्रा": "hydra",
    "बुलडोजर": "bulldozer", "डोजर": "dozer",
    "रोड रोलर": "road roller", "रोलर": "roller",
    "डंप ट्रक": "dump truck", "डंपर": "dumper", "टिप्पर": "tipper",
    "कंक्रीट मिक्सर": "concrete mixer", "मिक्सर": "mixer",
    "ग्रेडर": "grader", "व्हील लोडर": "wheel loader", "लोडर": "loader",
    "जयपुर": "jaipur", "जैपुर": "jaipur", "दिल्ली": "delhi", "मुंबई": "mumbai", "मुम्बई": "mumbai",
    "पुणे": "pune", "पुना": "pune", "अहमदाबाद": "ahmedabad",
    "गुड़गांव": "gurgaon", "गुरुग्राम": "gurgaon", "नोएडा": "noida",
    "बैंगलोर": "bangalore", "बेंगलुरु": "bangalore", "हैदराबाद": "hyderabad",
    "चेन्नई": "chennai",
    "के अंदर": "under", "के अन्दर": "under", "अंदर": "in", "में": "in",
    "के नीचे": "under", "से कम": "under", "तक": "under",
    "सबसे सस्ता": "cheapest", "सस्ता": "cheap", "सस्ती": "cheap", "कम कीमत": "cheap",
    "कम दाम": "cheap", "मुफ्त": "free", "फ्री": "free",
    "चाहिए": "chahiye", "मुझे": "i need", "दिखाओ": "show", "दिखाइए": "show",
    "बजट": "budget", "मशीन": "machine", "रुपये": "rupees", "रुपए": "rupees",
    "किराए": "rent", "किराया": "rent", "खरीद": "buy",
    "खरीदना": "buy", "खरीदने": "buy", "किराये": "rent",
}

_LATIN_FIXES = {
    **COMMON_TYPOS,
    "jsb": "jcb",
    "specifcation": "specification", "specifcations": "specifications",
    "specifictions": "specifications", "especifications": "specifications",
    "geive": "give", "gve": "give",
    "patthar": "pathar", "chaiye": "chahiye",
    "seedhi": "leveling", "sidha": "leveling",
    "andar": "in", "ander": "in", "andr": "in", "mein": "in", "mai": "in",
    "jaypur": "jaipur", "jeysibi": "jcb", "jaisibi": "jcb",
    "sasta": "cheap", "sasti": "cheap", "muft": "free",
}


def normalize_transcribed_text(text: str, *, strip_unmapped_non_latin: bool = True) -> str:
    if not text:
        return ""

    norm = text
    for dev, latin in _DEV_DIGITS.items():
        norm = norm.replace(dev, latin)

    for src in sorted(_NORMALIZE_MAP, key=len, reverse=True):
        if src in norm:
            norm = norm.replace(src, f" {_NORMALIZE_MAP[src]} ")

    norm = norm.lower()

    for src, dst in _LATIN_FIXES.items():
        norm = re.sub(rf"\b{re.escape(src)}\b", dst, norm)

    if strip_unmapped_non_latin:
        norm = re.sub(r"[^a-z0-9₹ ]+", " ", norm)
    else:
        norm = re.sub(r"[^\w\s₹]", " ", norm, flags=re.UNICODE)

    norm = re.sub(r"\s+", " ", norm).strip()
    return norm
