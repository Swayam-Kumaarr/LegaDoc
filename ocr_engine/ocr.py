from paddleocr import PaddleOCR

# Load model once when the worker starts
ocr = PaddleOCR(
    use_angle_cls=True,
    lang="en",
)


def run_ocr(image_path: str) -> list:
    """
    Run PaddleOCR on an image and return:
    [
        {"text": "...", "confidence": 0.98},
        ...
    ]
    """

    result = ocr.ocr(image_path, cls=True)

    extracted = []

    if result and result[0]:
        for line in result[0]:
            extracted.append({
                "text": line[1][0],
                "confidence": float(line[1][1]),
            })

    return extracted