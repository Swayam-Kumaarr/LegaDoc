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

try:
    import fitz  # PyMuPDF
    _HAS_PYMUPDF = True
except ImportError:
    _HAS_PYMUPDF = False

MAX_PDF_PAGES = 20  # a runaway page count shouldn't silently hang a worker on one upload


def _is_pdf(data: bytes) -> bool:
    return bool(data) and data[:5] == b"%PDF-"


def pdf_bytes_to_page_images(pdf_bytes: bytes, dpi: int = 200) -> List[bytes]:
    """Rasterizes each page of a PDF to PNG bytes via PyMuPDF — no external
    binary dependency (unlike pdf2image, which needs poppler installed
    separately), just a pip package. Confirmed live: a real submitted FIR
    PDF previously went straight through cv2.imdecode (which silently
    returns None on non-raster bytes, so preprocessing was skipped
    unnoticed) and then failed both OCR engines outright, since neither
    PaddleOCR nor Tesseract reads a raw PDF as an image — every real PDF
    upload was quietly failing OCR entirely, not just running degraded."""
    if not _HAS_PYMUPDF:
        raise RuntimeError("PyMuPDF not installed — cannot rasterize PDF pages for OCR")
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        images = []
        for i, page in enumerate(doc):
            if i >= MAX_PDF_PAGES:
                logger.warning(f"PDF has more than {MAX_PDF_PAGES} pages — truncating OCR to the first {MAX_PDF_PAGES}")
                break
            pix = page.get_pixmap(dpi=dpi)
            images.append(pix.tobytes("png"))
        return images
    finally:
        doc.close()


MIN_NATIVE_TEXT_CHARS = 20  # below this, treat the PDF as image-only and OCR it instead


def _extract_pdf_native_text(pdf_bytes: bytes) -> Optional[str]:
    """Many real government e-filing PDFs (confirmed live against an actual
    submitted FIR export) already carry a real embedded text layer — they
    were generated from a form/HTML print, not scanned from paper. Reading
    that directly is both faster and far more accurate than rasterizing to
    an image and OCRing it, so try this first and only fall back to OCR
    for genuinely image-only (scanned) PDFs. Returns None if there's no
    usable text layer."""
    if not _HAS_PYMUPDF:
        return None
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        try:
            pages = [doc[i].get_text() for i in range(min(doc.page_count, MAX_PDF_PAGES))]
        finally:
            doc.close()
    except Exception as exc:
        logger.warning(f"PDF native text extraction failed, will fall back to OCR: {exc}")
        return None

    combined = "\n\n--- Page Break ---\n\n".join(p.strip() for p in pages if p and p.strip())
    return combined if len(combined) >= MIN_NATIVE_TEXT_CHARS else None


def run_ocr_on_document_bytes(data: bytes, log_label: str) -> Dict[str, Any]:
    """Single entrypoint for turning a document's raw file bytes (image OR
    PDF, one page or many) into reconstructed text — used by both
    process_extract_document (case evidence) and
    process_extract_credential_document (onboarding proof documents), so
    the PDF-handling, preprocessing, and dual-engine fallback logic exists
    exactly once. For a PDF with a real text layer, that's read directly
    (see _extract_pdf_native_text) — no OCR needed or run. For a PDF
    without one (a genuine paper scan) or a bare image, each page runs
    through the same single-image OCR pipeline independently and results
    are joined with a page-break marker — merging raw OCR boxes across
    pages before layout reconstruction would let page 2's row-0
    coordinates collide with page 1's, corrupting the row clustering that
    reconstructs reading order.
    Returns {"reconstructed_text", "engine_used", "row_count", "token_count",
    "template", "fields", "page_count"}.
    """
    if _is_pdf(data):
        native_text = _extract_pdf_native_text(data)
        if native_text is not None:
            doc = fitz.open(stream=data, filetype="pdf")
            page_count = doc.page_count
            doc.close()
            return {
                "reconstructed_text": native_text,
                "engine_used": "pdf_native_text",
                "row_count": native_text.count("\n") + 1,
                "token_count": len(native_text.split()),
                "template": "pdf_native_text",
                "fields": {},
                "page_count": page_count,
            }

    page_images = pdf_bytes_to_page_images(data) if _is_pdf(data) else [data]

    page_texts: List[str] = []
    row_count = 0
    token_count = 0
    first_layout: Optional[Dict[str, Any]] = None
    engine_used = "paddleocr"

    for page_bytes in page_images:
        processed_bytes = preprocess_image_bytes(page_bytes)
        try:
            raw_boxes = run_paddle_ocr(processed_bytes)
            page_engine = "paddleocr"
        except Exception as paddle_err:
            logger.warning(f"PaddleOCR failed for {log_label}, attempting Tesseract fallback: {paddle_err}")
            try:
                raw_boxes = run_tesseract_fallback(processed_bytes)
                page_engine = "tesseract_fallback"
            except Exception as tess_err:
                logger.error(f"Both OCR engines failed on a page of {log_label}: {tess_err}")
                continue  # skip this page rather than failing the whole document
        if page_engine == "tesseract_fallback":
            engine_used = "tesseract_fallback"  # any page needing fallback marks the whole document

        layout = process_ocr_boxes_to_layout(raw_boxes)
        if first_layout is None:
            first_layout = layout
        row_count += layout["row_count"]
        token_count += layout["token_count"]
        if layout["reconstructed_text"] and layout["reconstructed_text"].strip():
            page_texts.append(layout["reconstructed_text"])

    return {
        "reconstructed_text": "\n\n--- Page Break ---\n\n".join(page_texts),
        "engine_used": engine_used,
        "row_count": row_count,
        "token_count": token_count,
        "template": first_layout["template"] if first_layout else "unknown",
        "fields": first_layout["fields"] if first_layout else {},
        "page_count": len(page_images),
    }


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


def run_paddle_ocr(image_bytes: bytes) -> List[Dict[str, Any]]:
    """Runs PaddleOCR on image bytes and returns raw bounding box dicts:
    [{"text": str, "confidence": float, "box": [x1, y1, x2, y2]}, ...]
    """
    if not _HAS_PADDLE:
        raise RuntimeError("PaddleOCR engine not installed")

    # Initialize English & Hindi engines lazily or per-call
    ocr_en = PaddleOCR(use_angle_cls=True, lang="en", show_log=False)
    ocr_hi = PaddleOCR(use_angle_cls=True, lang="hi", show_log=False)

    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".png", delete=True) as tmp:
        tmp.write(image_bytes)
        tmp.flush()

        res_en = ocr_en.ocr(tmp.name, cls=True)
        res_hi = ocr_hi.ocr(tmp.name, cls=True)

    words = []
    for result_set in (res_en, res_hi):
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
                })

    return words


def run_tesseract_fallback(image_bytes: bytes) -> List[Dict[str, Any]]:
    """Tesseract fallback when PaddleOCR fails or is unavailable."""
    if not _HAS_TESSERACT or not _HAS_PIL:
        raise RuntimeError("Tesseract fallback engine not available")

    img = Image.open(io.BytesIO(image_bytes))
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

        if mock_boxes is not None:
            layout = process_ocr_boxes_to_layout(mock_boxes)
            ocr_result = {
                "reconstructed_text": layout["reconstructed_text"],
                "engine_used": "paddleocr",
                "row_count": layout["row_count"],
                "token_count": layout["token_count"],
                "template": layout["template"],
                "fields": layout["fields"],
                "page_count": 1,
            }
        else:
            file_bytes = obj_storage.get(document.storage_path)
            if not file_bytes:
                raise ValueError(f"Empty storage payload at {document.storage_path}")
            ocr_result = run_ocr_on_document_bytes(file_bytes, log_label=f"doc {document_id}")

        engine_used = ocr_result["engine_used"]
        reconstructed_text = ocr_result["reconstructed_text"]

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
                "template": ocr_result["template"],
                "row_count": ocr_result["row_count"],
                "token_count": ocr_result["token_count"],
                "extracted_fields": ocr_result["fields"],
                "page_count": ocr_result["page_count"],
            },
        )

        # Enqueue downstream AI Parser worker (Flow 2 Track B). queue=
        # explicitly, matching the routing api/app/queue.py's producer uses
        # — each worker only listens on its own named queue now (see the
        # Dockerfiles' -Q flag); a raw send_task with no queue= lands on
        # Celery's default "celery" queue, which nothing consumes anymore,
        # and this internal hop would silently never run.
        try:
            app.send_task(
                "ai_parser_worker.tag_document",
                kwargs={"document_id": str(document.id)},
                queue="ai_parser_worker",
            )
        except Exception as enqueue_err:
            logger.warning(f"Could not enqueue ai_parser_worker task: {enqueue_err}")

        return {
            "status": "success",
            "document_id": str(document.id),
            "ocr_engine": engine_used,
            "template": ocr_result["template"],
            "fields": ocr_result["fields"],
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


def process_extract_credential_document(
    document_id: str,
    db: Optional[Any] = None,
    storage: Optional[Any] = None,
    mock_boxes: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Same OCR pipeline as process_extract_document (preprocessing,
    PaddleOCR -> Tesseract fallback, layout reconstruction), but reading and
    writing CredentialDocument instead of Document — an onboarding proof-of-
    identity scan (police ID, Bar Council certificate, appointment order),
    not case evidence. No FIR-field extraction (that layout template doesn't
    apply here); the reconstructed text is handed to
    ai_parser_worker.extract_credential_fields, a positive-extraction task,
    not the redaction one case documents get."""
    session = db if db is not None else SessionLocal()
    obj_storage = storage if storage is not None else get_storage()

    try:
        doc_uuid = document_id if isinstance(document_id, UUID) else UUID(str(document_id))
        document = session.get(models.CredentialDocument, doc_uuid)
        if document is None:
            raise ValueError(f"CredentialDocument {document_id} not found")

        if mock_boxes is not None:
            layout = process_ocr_boxes_to_layout(mock_boxes)
            ocr_result = {
                "reconstructed_text": layout["reconstructed_text"],
                "row_count": layout["row_count"],
                "token_count": layout["token_count"],
                "page_count": 1,
            }
        else:
            file_bytes = obj_storage.get(document.storage_path)
            if not file_bytes:
                raise ValueError(f"Empty storage payload at {document.storage_path}")
            ocr_result = run_ocr_on_document_bytes(file_bytes, log_label=f"credential doc {document_id}")

        reconstructed_text = ocr_result["reconstructed_text"]

        if not reconstructed_text or not reconstructed_text.strip():
            document.status = "needs_review"
            session.commit()
            return {"status": "needs_review", "reason": "empty_ocr_text"}

        document.raw_text = reconstructed_text
        session.commit()
        session.refresh(document)

        write_audit_log(
            session,
            action="credential_document_ocr_extracted",
            actor_user_id=document.uploaded_by,
            target_type="credential_document",
            target_id=document.id,
            metadata={"row_count": ocr_result["row_count"], "token_count": ocr_result["token_count"], "page_count": ocr_result["page_count"]},
        )

        try:
            app.send_task(
                "ai_parser_worker.extract_credential_fields",
                kwargs={"credential_document_id": str(document.id)},
                queue="ai_parser_worker",
            )
        except Exception as enqueue_err:
            logger.warning(f"Could not enqueue ai_parser_worker credential extraction task: {enqueue_err}")

        return {"status": "success", "credential_document_id": str(document.id), "raw_text": document.raw_text}

    except Exception as exc:
        logger.exception(f"OCR Worker failure on credential document {document_id}: {exc}")
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


@app.task(name="ocr_worker.extract_credential_document", bind=True, max_retries=5)
def extract_credential_document(self, document_id: str):
    """Celery task entrypoint — OCR for onboarding credential proof documents."""
    return process_extract_credential_document(document_id)
