import cv2
import hashlib


def generate_image_hash(image_path):
    """
    Generate hash for image.

    Similar images produce similar hashes.
    """

    # =====================================
    # STEP 1 — Load image
    # =====================================

    image = cv2.imread(image_path)

    if image is None:

        return {
            "error": "Could not read image"
        }

    # =====================================
    # STEP 2 — Resize image
    # =====================================

    resized = cv2.resize(
        image,
        (8, 8)
    )

    # =====================================
    # STEP 3 — Convert to grayscale
    # =====================================

    gray = cv2.cvtColor(
        resized,
        cv2.COLOR_BGR2GRAY
    )

    # =====================================
    # STEP 4 — Convert to bytes
    # =====================================

    image_bytes = gray.tobytes()

    # =====================================
    # STEP 5 — Generate hash
    # =====================================

    image_hash = hashlib.md5(
        image_bytes
    ).hexdigest()

    # =====================================
    # STEP 6 — Return hash
    # =====================================

    return {
        "image_hash": image_hash
    }