"""
Voice transcription + language normalization.

Groq Whisper sometimes returns Hindi audio transcribed in Urdu/Arabic script or
in an unexpected language. Two defences are applied:

1. The transcription call is biased toward Hindi (Devanagari) / Hinglish (Latin)
   via `language="hi"` and a script-constraining prompt.
2. `normalize_transcribed_text` maps common Devanagari / Hinglish words to the
   Latin tokens the search parser understands and strips any leftover non-Latin
   characters, so the chatbot always searches on clean text.

The backend search must use `normalized_text`; the UI can still show
`original_text` for transparency.
"""

import re

from app.core.groq_client import client


# Bias Whisper toward Hindi/Hinglish and away from Urdu/Arabic script.
_TRANSCRIPTION_PROMPT = (
    "Transcribe this audio in Hindi using Devanagari script, or in English / "
    "Hinglish using Latin script only. Do NOT use Urdu or Arabic script. "
    "Common words: excavator, JCB, JCB 3DX, backhoe loader, crane, bulldozer, "
    "road roller, dump truck, Jaipur, Delhi, Mumbai, Pune, chahiye, sasta, kam daam."
)

# Devanagari digits -> Latin digits.
_DEV_DIGITS = {
    "०": "0", "१": "1", "२": "2", "३": "3", "४": "4",
    "५": "5", "६": "6", "७": "7", "८": "8", "९": "9",
}

# Devanagari / phrase -> Latin token the query parser understands.
# Longer phrases are applied first so multi-word terms win.
_NORMALIZE_MAP = {
    # --- machines ---
    "एक्सकेवेटर": "excavator", "एक्स्कावेटर": "excavator", "एक्सकैवेटर": "excavator",
    "एक्सावेटर": "excavator", "खुदाई मशीन": "excavator", "खुदाई": "excavator",
    "जे सी बी": "jcb", "जेसीबी": "jcb", "बैकहो लोडर": "backhoe loader", "बैकहो": "backhoe",
    "क्रेन": "crane", "हाइड्रा": "hydra",
    "बुलडोजर": "bulldozer", "डोजर": "dozer",
    "रोड रोलर": "road roller", "रोलर": "roller",
    "डंप ट्रक": "dump truck", "डंपर": "dumper", "टिप्पर": "tipper",
    "कंक्रीट मिक्सर": "concrete mixer", "मिक्सर": "mixer",
    "ग्रेडर": "grader", "व्हील लोडर": "wheel loader", "लोडर": "loader",
    # --- cities ---
    "जयपुर": "jaipur", "जैपुर": "jaipur", "दिल्ली": "delhi", "मुंबई": "mumbai", "मुम्बई": "mumbai",
    "पुणे": "pune", "पुना": "pune", "अहमदाबाद": "ahmedabad",
    "गुड़गांव": "gurgaon", "गुरुग्राम": "gurgaon", "नोएडा": "noida",
    "बैंगलोर": "bangalore", "बेंगलुरु": "bangalore", "हैदराबाद": "hyderabad",
    "चेन्नई": "chennai",
    # --- intent / connective words ---
    "के अंदर": "in", "के अन्दर": "in", "अंदर": "in", "में": "in",
    "के नीचे": "under", "से कम": "under", "तक": "under",
    "सबसे सस्ता": "cheapest", "सस्ता": "cheap", "सस्ती": "cheap", "कम कीमत": "cheap",
    "कम दाम": "cheap", "मुफ्त": "free", "फ्री": "free",
    "चाहिए": "chahiye", "मुझे": "i need", "दिखाओ": "show", "दिखाइए": "show",
    "बजट": "budget", "मशीन": "machine", "रुपये": "rupees", "रुपए": "rupees",
    "किराए": "rent", "किराया": "rent", "खरीद": "buy",
    "खरीदना": "buy", "खरीदने": "buy", "किराये": "rent",
}

# Latin transliteration / spelling fixes (whole-word).
_LATIN_FIXES = {
    "excavater": "excavator", "excavetor": "excavator", "excevator": "excavator",
    "exavator": "excavator", "jsb": "jcb",
    "andar": "in", "ander": "in", "andr": "in", "mein": "in", "mai": "in",
    "jaypur": "jaipur", "jeysibi": "jcb", "jaisibi": "jcb",
    "sasta": "cheap", "sasti": "cheap", "muft": "free",
}


def normalize_transcribed_text(text: str) -> str:
    """
    Normalize a raw transcription to clean Latin/Hinglish text the search parser
    can understand.

    Steps:
      1. Convert Devanagari digits to Latin digits.
      2. Replace known Devanagari / Hinglish words with Latin tokens
         (longest phrase first).
      3. Lowercase, then apply Latin spelling/transliteration fixes.
      4. Strip any remaining non-Latin characters (e.g. leftover Urdu/Arabic).
    """
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

    # Keep only Latin letters, digits, currency and spaces; drop anything else
    # (any leftover Devanagari/Urdu/Arabic that wasn't mapped).
    norm = re.sub(r"[^a-z0-9₹ ]+", " ", norm)
    norm = re.sub(r"\s+", " ", norm).strip()

    return norm


def transcribe_audio(audio_file_path: str):
    """
    Convert audio speech to text using Groq Whisper, biased to Hindi/Hinglish,
    and return both the original transcription and a normalized version.
    """

    try:

        with open(audio_file_path, "rb") as audio_file:

            transcription = client.audio.transcriptions.create(
                file=audio_file,
                model="whisper-large-v3",
                language="hi",
                prompt=_TRANSCRIPTION_PROMPT,
                temperature=0,
            )

        original_text = (transcription.text or "").strip()
        normalized_text = normalize_transcribed_text(original_text)

        return {
            "success": True,
            # `text` stays the search-ready value for backward compatibility.
            "text": normalized_text or original_text,
            "original_text": original_text,
            "normalized_text": normalized_text or original_text,
        }

    except Exception as e:

        return {
            "success": False,
            "error": str(e)
        }
