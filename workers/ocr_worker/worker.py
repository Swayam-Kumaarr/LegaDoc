"""
OCR & Extraction Worker — see SYSTEM_DESIGN.md Container Diagram and Flow 2, Track B.
Consumes jobs from the queue; runs preprocessing, PaddleOCR (with Tesseract fallback),
executes spatial IoU NMS and layout row reconstruction, writes Document.raw_text
and extracted fields, and enqueues the AI-parse job (System Connections table, arrow #11).
"""

import io
import logging
import os
import sys
from typing import Any, Dict, List, Optional
from uuid import UUID

# Adjust sys.path to locate api/app as a package
_api_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "api")
if _api_path not in sys.path:
    sys.path.insert(0, _api_path)

# Adjust sys.path to import layout_reconstruction
_worker_dir = os.path.dirname(os.path.abspath(__file__))
if _worker_dir not in sys.path:
    sys.path.insert(0, _worker_dir)

from celery import Celery

from app import models
from app.audit import write_audit_log
from app.config import settings
from app.database import SessionLocal
from app.storage import get_storage

try:
    from layout_reconstruction import process_ocr_boxes_to_layout
except ImportError:
    from workers.ocr_worker.layout_reconstruction import process_ocr_boxes_to_layout

logger = logging.getLogger(__name__)

app = Celery(
    "ocr_worker",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
)

# Optional image processing libraries
try:
    import cv2
    import numpy as np
    _HAS_CV2 = True
except ImportError:
    _HAS_CV2 = False

try:
    from PIL import Image
    _HAS_PIL = True
except ImportError:
    _HAS_PIL = False

try:
    from paddleocr import PaddleOCR
    _HAS_PADDLE = True
except ImportError:
    _HAS_PADDLE = False

try:
    import pytesseract
    _HAS_TESSERACT = True
except ImportError:
    _HAS_TESSERACT = False


def preprocess_image_bytes(image_bytes: bytes) -> bytes:
    """Enhances scanned document image for OCR:
    - Grayscale conversion
    - Noise reduction
    - Adaptive thresholding / contrast normalization
    """
    if not _HAS_CV2 or not image_bytes:
        return image_bytes

    try:
        nparr = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None:
            return image_bytes

        # Resize 1.5x if resolution is low
        h, w = img.shape[:2]
        if w < 1200:
            scale = 1.5
            img = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)

        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        denoised = cv2.fastNlMeansDenoising(gray, h=10)
        enhanced = cv2.adaptiveThreshold(
            denoised,
            255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY,
            31,
            15,
        )

        success, encoded = cv2.imencode(".png", enhanced)
        if success:
            return encoded.tobytes()
    except Exception as exc:
        logger.warning(f"Image preprocessing exception, falling back to raw bytes: {exc}")

    return image_bytes


# Module-level cached OCR engines (Issue #37)
_OCR_EN = None
_OCR_HI = None


def get_paddle_ocr_engines():
    """Initializes and caches PaddleOCR engines for English and Hindi.
    Explicitly loads and validates Hindi language model (PP-OCR Devanagari) to prevent
    silent fallback to English weights.
    """
    global _OCR_EN, _OCR_HI
    if not _HAS_PADDLE:
        raise RuntimeError("PaddleOCR engine not installed")

    if _OCR_EN is None:
        logger.info("Initializing PaddleOCR English model (lang='en')...")
        _OCR_EN = PaddleOCR(use_angle_cls=True, lang="en", show_log=False)

    if _OCR_HI is None:
        logger.info("Initializing PaddleOCR Hindi model (lang='hi')...")
        try:
            _OCR_HI = PaddleOCR(use_angle_cls=True, lang="hi", show_log=False)
        except Exception as exc:
            logger.error(f"Failed to load PaddleOCR Hindi language pack: {exc}")
            raise RuntimeError(f"PaddleOCR Hindi language pack failed to initialize: {exc}")

    return _OCR_EN, _OCR_HI


def run_paddle_ocr(image_bytes: bytes) -> List[Dict[str, Any]]:
    """Runs PaddleOCR on image bytes with explicit Hindi and English models:
    [{"text": str, "confidence": float, "box": [x1, y1, x2, y2], "lang": str}, ...]
    """
    ocr_en, ocr_hi = get_paddle_ocr_engines()

    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".png", delete=True) as tmp:
        tmp.write(image_bytes)
        tmp.flush()

        # Run Hindi engine (covers Devanagari script, numerals, and bilingual headers)
        res_hi = ocr_hi.ocr(tmp.name, cls=True)
        # Run English engine (covers Latin script and English legal terms)
        res_en = ocr_en.ocr(tmp.name, cls=True)

    words = []
    # Place Hindi results first so Devanagari glyphs take precedence
    for result_set, lang in ((res_hi, "hi"), (res_en, "en")):
        if result_set and result_set[0]:
            for line in result_set[0]:
                box_pts = line[0]
                text = line[1][0]
                score = float(line[1][1])

                x1 = int(min(p[0] for p in box_pts))
                y1 = int(min(p[1] for p in box_pts))
                x2 = int(max(p[0] for p in box_pts))
                y2 = int(max(p[1] for p in box_pts))

                words.append({
                    "text": text,
                    "confidence": score,
                    "box": [x1, y1, x2, y2],
                    "lang": lang,
                })

    return words


def run_tesseract_fallback(image_bytes: bytes) -> List[Dict[str, Any]]:
    """Tesseract fallback when PaddleOCR fails or is unavailable.
    Attempts bilingual Hindi+English recognition before falling back to English.
    """
    if not _HAS_TESSERACT or not _HAS_PIL:
        raise RuntimeError("Tesseract fallback engine not available")

    img = Image.open(io.BytesIO(image_bytes))

    # Attempt bilingual hin+eng first if tesseract-ocr-hin traineddata is installed
    data = None
    try:
        data = pytesseract.image_to_data(img, lang="hin+eng", output_type=pytesseract.Output.DICT)
    except Exception as exc:
        logger.warning(f"Tesseract bilingual (hin+eng) failed, falling back to default: {exc}")
        data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)

    words = []
    n_boxes = len(data["text"])
    for i in range(n_boxes):
        text = data["text"][i].strip()
        conf = float(data["conf"][i])
        if text and conf > 0:
            x = data["left"][i]
            y = data["top"][i]
            w = data["width"][i]
            h = data["height"][i]
            words.append({
                "text": text,
                "confidence": conf / 100.0,
                "box": [x, y, x + w, y + h],
            })

    return words


def process_extract_document(
    document_id: str,
    db: Optional[Any] = None,
    storage: Optional[Any] = None,
    mock_boxes: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Core orchestration for OCR worker:
    1. Reads Document record from DB.
    2. Fetches raw file bytes from ObjectStorage.
    3. Runs preprocessing & multi-engine OCR (PaddleOCR -> Tesseract fallback).
    4. Applies spatial IoU NMS and row-level layout reconstruction.
    5. Saves clean natural-reading text to Document.raw_text.
    6. Emits tamper-evident audit log with extracted FIR fields under pg_advisory_xact_lock.
    7. Enqueues ai_parser_worker.tag_document.
    8. Enforces fail-closed safety on error (status='needs_review').
    """
    session = db if db is not None else SessionLocal()
    obj_storage = storage if storage is not None else get_storage()

    try:
        doc_uuid = document_id if isinstance(document_id, UUID) else UUID(str(document_id))
        document = session.get(models.Document, doc_uuid)
        if document is None:
            raise ValueError(f"Document {document_id} not found")

        raw_boxes = []
        engine_used = "paddleocr"

        if mock_boxes is not None:
            raw_boxes = mock_boxes
            engine_used = "paddleocr"
        else:
            file_bytes = obj_storage.get(document.storage_path)
            if not file_bytes:
                raise ValueError(f"Empty storage payload at {document.storage_path}")

            processed_bytes = preprocess_image_bytes(file_bytes)

            try:
                raw_boxes = run_paddle_ocr(processed_bytes)
                engine_used = "paddleocr"
            except Exception as paddle_err:
                logger.warning(f"PaddleOCR failed for doc {document_id}, attempting Tesseract fallback: {paddle_err}")
                try:
                    raw_boxes = run_tesseract_fallback(processed_bytes)
                    engine_used = "tesseract_fallback"
                except Exception as tess_err:
                    logger.error(f"Both OCR engines failed for doc {document_id}: {tess_err}")
                    raise RuntimeError(f"All OCR engines failed: {tess_err}")

        # Execute layout reconstruction and field extraction
        layout = process_ocr_boxes_to_layout(raw_boxes)

        reconstructed_text = layout["reconstructed_text"]
        if not reconstructed_text or not reconstructed_text.strip():
            # Fail closed on empty OCR extraction
            document.status = "needs_review"
            document.ocr_engine = engine_used
            session.commit()
            return {"status": "needs_review", "reason": "empty_ocr_text"}

        document.raw_text = reconstructed_text
        document.ocr_engine = engine_used
        session.commit()
        session.refresh(document)

        # Write audit trail entry with extracted fields
        write_audit_log(
            session,
            action="document_ocr_extracted",
            case_id=document.case_id,
            actor_user_id=document.uploaded_by,
            target_type="document",
            target_id=document.id,
            metadata={
                "ocr_engine": engine_used,
                "template": layout["template"],
                "row_count": layout["row_count"],
                "token_count": layout["token_count"],
                "extracted_fields": layout["fields"],
            },
        )

        # Enqueue downstream AI Parser worker (Flow 2 Track B)
        try:
            app.send_task(
                "ai_parser_worker.tag_document",
                args=[str(document.id)],
            )
        except Exception as enqueue_err:
            logger.warning(f"Could not enqueue ai_parser_worker task: {enqueue_err}")

        return {
            "status": "success",
            "document_id": str(document.id),
            "ocr_engine": engine_used,
            "template": layout["template"],
            "fields": layout["fields"],
            "raw_text": document.raw_text,
        }

    except Exception as exc:
        logger.exception(f"OCR Worker failure on document {document_id}: {exc}")
        try:
            if "document" in locals() and document is not None:
                document.status = "needs_review"
                session.commit()
        except Exception:
            session.rollback()
        return {"status": "needs_review", "error": str(exc)}
    finally:
        if db is None:
            session.close()


@app.task(name="ocr_worker.extract_document", bind=True, max_retries=5)
def extract_document(self, document_id: str):
    """Celery task entrypoint for OCR worker."""
    return process_extract_document(document_id)
