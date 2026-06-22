import cv2
import os


def detect_blur(image_path):

    print("IMAGE PATH:", image_path)

    # Check path exists
    exists = os.path.exists(image_path)

    print("PATH EXISTS:", exists)

    if not exists:

        return {
            "error": "Image path does not exist",
            "path": image_path
        }

    # Load image
    image = cv2.imread(image_path)

    print("IMAGE OBJECT:", image)

    if image is None:

        return {
            "error": "Could not read image",
            "path": image_path
        }

    gray = cv2.cvtColor(
        image,
        cv2.COLOR_BGR2GRAY
    )

    blur_score = cv2.Laplacian(
        gray,
        cv2.CV_64F
    ).var()

    is_blurry = bool(blur_score < 100)

    quality = (
        "poor"
        if is_blurry
        else "good"
    )

    return {
        "blur_score": float(blur_score),
        "is_blurry": bool(is_blurry),
        "image_quality": quality
    }