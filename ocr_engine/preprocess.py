import cv2
import os

def preprocess_image(image_path: str) -> str:
    """
    Preprocess an uploaded image and return the processed image path.
    """

    image = cv2.imread(image_path)

    if image is None:
        raise FileNotFoundError(f"Image not found: {image_path}")

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    gray = cv2.GaussianBlur(gray, (3, 3), 0)

    _, thresh = cv2.threshold(
        gray, 0, 255,
        cv2.THRESH_BINARY + cv2.THRESH_OTSU
    )

    os.makedirs("processed", exist_ok=True)

    output_path = os.path.join(
        "processed",
        os.path.basename(image_path)
    )

    cv2.imwrite(output_path, thresh)

    return output_path