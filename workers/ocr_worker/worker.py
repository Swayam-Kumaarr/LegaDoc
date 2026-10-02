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
from typing import Any, Dict, Iterator, List, Optional
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
    from layout_reconstruction import is_devanagari_page, process_ocr_boxes_to_layout, select_devanagari_words
except ImportError:
    from workers.ocr_worker.layout_reconstruction import is_devanagari_page, process_ocr_boxes_to_layout, select_devanagari_words

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


def iter_pdf_page_images(pdf_bytes: bytes, dpi: int = 200) -> Iterator[bytes]:
    """Rasterizes each page of a PDF to PNG bytes via PyMuPDF — no external
    binary dependency (unlike pdf2image, which needs poppler installed
    separately), just a pip package. Confirmed live: a real submitted FIR
    PDF previously went straight through cv2.imdecode (which silently
    returns None on non-raster bytes, so preprocessing was skipped
    unnoticed) and then failed both OCR engines outright, since neither
    PaddleOCR nor Tesseract reads a raw PDF as an image — every real PDF
    upload was quietly failing OCR entirely, not just running degraded.

    A generator: each page is rasterized only when the OCR loop reaches it,
    so one page image is held at a time instead of all of them (up to
    MAX_PDF_PAGES PNGs of a 200 dpi scan) for the whole job."""
    if not _HAS_PYMUPDF:
        raise RuntimeError("PyMuPDF not installed — cannot rasterize PDF pages for OCR")
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        for i, page in enumerate(doc):
            if i >= MAX_PDF_PAGES:
                logger.warning(f"PDF has more than {MAX_PDF_PAGES} pages — truncating OCR to the first {MAX_PDF_PAGES}")
                break
            yield page.get_pixmap(dpi=dpi).tobytes("png")
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

    page_images = iter_pdf_page_images(data) if _is_pdf(data) else iter([data])
    page_count = 0

    page_texts: List[str] = []
    row_count = 0
    token_count = 0
    first_layout: Optional[Dict[str, Any]] = None
    engine_used = "paddleocr"

    for page_bytes in page_images:
        page_count += 1
        processed_bytes = preprocess_image_bytes(page_bytes)

        # Tesseract's `hin` pass runs first, on every page. It is cheap (1-5 s,
        # ~470 MiB in its own process) and says where this page's Hindi is. On
        # a page that has Hindi, those words are painted out before PaddleOCR
        # reads it, so the English model never sees Devanagari and cannot
        # transliterate it into Latin junk (issue #107); Tesseract's reading
        # of them is fused back in by position. PaddleOCR's own Hindi model is
        # no longer loaded: since #91 its Devanagari was discarded in favour
        # of Tesseract's, and what was left of it — the page-is-bilingual
        # signal and Latin residue — was the other source of the junk.
        devanagari_boxes = run_tesseract_devanagari(processed_bytes)
        hindi_page = is_devanagari_page(devanagari_boxes)
        english_input = processed_bytes
        if hindi_page:
            trusted, glosses = select_devanagari_words(devanagari_boxes)
            english_input = mask_regions(processed_bytes, [b["box"] for b in trusted + glosses])

        try:
            raw_boxes = run_paddle_ocr(english_input)
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
            devanagari_boxes = None  # the fallback read the unmasked page in hin+eng already
        elif hindi_page:
            engine_used = "paddleocr+tesseract_hin"
        else:
            devanagari_boxes = None

        layout = process_ocr_boxes_to_layout(raw_boxes, devanagari_boxes)
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
        "page_count": page_count,
    }


def upscale_factor(width: int) -> float:
    """How much to enlarge a scan of this width before OCR; 1.0 means leave it.

    This was a flat 1.5x, which leaves the small print on a typical 768px
    phone scan too small to read. On the Delhi FIR fixture it read the FIR
    number itself wrong — 035009 against the 035008 printed on the page —
    and missed the district and the BNS section entirely. Scaling to a 1920px
    target (2.5x for 768px) reads all three correctly.

    This only became affordable with #129. Before it, recogniser memory
    tracked the width of the widest line crop, so the larger image took the
    dense Delhi page from 4.9 GB to 5.8 GB. With wide crops recognised in
    pieces, the same page at 2.5x peaks at 2.3 GB on x86 — lower than 1.5x
    on main.

    A target width rather than a fixed factor, so a 1100px scan is not blown
    up by the same 2.5x. The set of images that get upscaled at all is the
    same as before (narrower than 1200px). Kept separate from
    preprocess_image_bytes so the rule is testable without OpenCV, which the
    API's test environment does not install.
    """
    if width <= 0 or width >= 1200:
        return 1.0
    return min(_OCR_TARGET_WIDTH / width, _OCR_MAX_UPSCALE)


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
        scale = upscale_factor(w)
        if scale > 1.0:
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

# PaddleOCR defaults to 10 CPU threads and recognition batches of 6, and every
# thread keeps its own working buffers. Measured on one 768x1024 FIR scan with
# both engines loaded (scripts/ocr_mem_probe.py): at the defaults the process
# was OOM-killed above a 2.2 GB cap; with 2 threads and batch 1 both passes
# peaked at 1,707 MiB and found the same 138 text boxes. That OOM is what
# SIGKILLed this worker on 8 GB machines. Override per deployment if a larger
# VM should trade memory for speed.
_OCR_CPU_THREADS = int(os.environ.get("OCR_CPU_THREADS", "2"))
# See upscale_factor. A 768px scan becomes 1920px; nothing is enlarged past 3x.
_OCR_TARGET_WIDTH = int(os.environ.get("OCR_TARGET_WIDTH", "1920"))
_OCR_MAX_UPSCALE = float(os.environ.get("OCR_MAX_UPSCALE", "3.0"))
_OCR_REC_BATCH_NUM = int(os.environ.get("OCR_REC_BATCH_NUM", "1"))


# Widest line crop, as width/height, handed to the recognizer in one piece.
# The PP-OCR recognizers resize every crop to a fixed 48 px height and keep
# its aspect ratio, and their memory grows with the resulting width and is
# never returned. Measured on the Delhi FIR (768x1024, English pass alone):
# crops up to ~320 px wide add nothing over detection, but the full-width
# form lines (ratio 20-53, 1,000-2,500 px) take the process from 733 MiB to
# 1,846 MiB — they, not the page size or the number of lines, set the peak.
#
# 14 is measured, not picked. The whole OCR job (both Paddle passes and
# Tesseract) peaked at 1,213 MiB on the Haryana FIR and 1,235 MiB on Delhi,
# against 2,717 and 4,911 before, with every extracted field unchanged. 10
# held both near 1,050 MiB but cut often enough to split the transliterated
# Hindi glosses issue #107 relies on finding in one piece, and a header's
# Latin junk and `type_of_information` came back. 18 kept the text but let
# Delhi back up to 1,527 MiB.
_MAX_REC_RATIO = float(os.environ.get("OCR_MAX_REC_RATIO", "14"))


def _blank_runs(ink: List[int]) -> List[tuple]:
    """(start, end) runs of columns whose ink count is zero."""
    runs, start = [], None
    for x, v in enumerate(ink):
        if v == 0 and start is None:
            start = x
        elif v != 0 and start is not None:
            runs.append((start, x))
            start = None
    return runs


def plan_line_cuts(band_ink: List[int], full_ink: List[int], height: int, max_ratio: float) -> List[tuple]:
    """Where to cut a line crop so no piece is wider than max_ratio * height.

    band_ink / full_ink are per-column counts of ink pixels, over the middle
    band of rows and over the whole height. Returns [(column, gap_width)].

    Each cut goes in the widest ink-free gap of its window, read from the
    middle band so an underlined heading, whose rule touches every column,
    still shows the gaps between its words. That is the space between words,
    not the 1-2 px between letters. gap_width is 0 when a window has no gap
    at all and the cut falls on its emptiest column instead — the bound on
    piece width is what keeps memory flat, so it always holds.
    """
    w = len(full_ink)
    limit = max_ratio * height
    if height <= 0 or w <= limit:
        return []
    runs = [(a, b) for a, b in _blank_runs(band_ink) if a > 0 and b < w]
    cuts, x = [], 0
    while w - x > limit:
        lo, hi = x + 2 * height, x + limit
        window = [(a, b) for a, b in runs if lo < (a + b) / 2 <= hi]
        if window:
            a, b = max(window, key=lambda r: (r[1] - r[0], r[0]))
            cut, gap = (a + b) // 2, b - a
        else:
            lo_i, hi_i = int(lo), int(hi)
            span = full_ink[lo_i:hi_i]
            cut, gap = lo_i + span.index(min(span)), 0
        cuts.append((cut, gap))
        x = cut
    return cuts


def split_wide_crop(crop) -> List[tuple]:
    """Splits a line crop wider than _MAX_REC_RATIO into pieces for the
    recognizer; returns [(piece, joiner)], joiner being the text that goes
    before that piece's reading when the line is put back together.

    A piece is joined back with a space only when it was cut at a
    space-sized gap, so an identifier with no spaces ("DL3SDF1124",
    "JF32AAFG037425") that had to be cut comes back without one.
    """
    h, w = crop.shape[:2]
    if h <= 0 or w <= _MAX_REC_RATIO * h:
        return [(crop, "")]
    gray = crop.mean(axis=2) if crop.ndim == 3 else crop
    dark = gray < 128
    band = dark[int(0.15 * h): max(int(0.85 * h), int(0.15 * h) + 1)]
    cuts = plan_line_cuts(band.sum(axis=0).tolist(), dark.sum(axis=0).tolist(), h, _MAX_REC_RATIO)

    pieces, x, joiner = [], 0, ""
    for cut, gap in cuts:
        pieces.append((crop[:, x:cut], joiner))
        joiner = " " if gap >= 0.25 * h else ""
        x = cut
    pieces.append((crop[:, x:], joiner))
    return pieces


class _BoundedRecognizer:
    """Wraps a PaddleOCR engine's text recognizer so no crop wider than
    _MAX_REC_RATIO reaches the model (see _MAX_REC_RATIO).

    Everything else in the engine — detection, rotated cropping, the angle
    classifier, reading order, the drop-score filter, the result format — is
    PaddleOCR's own, so a line narrower than the bound is recognized exactly
    as before. A wider one is recognized piece by piece and returned as one
    reading, scored by the pieces' width-weighted confidence.
    """

    def __init__(self, recognizer):
        self._recognizer = recognizer

    def __call__(self, img_crop_list):
        plan, flat = [], []
        for crop in img_crop_list:
            pieces = split_wide_crop(crop)
            plan.append([(len(flat) + i, joiner, piece.shape[1]) for i, (piece, joiner) in enumerate(pieces)])
            flat.extend(piece for piece, _ in pieces)

        results, elapse = self._recognizer(flat)

        merged = []
        for parts in plan:
            if len(parts) == 1:
                merged.append(results[parts[0][0]])
                continue
            text, weighted, width = "", 0.0, 0
            for idx, joiner, piece_w in parts:
                piece_text, score = results[idx][0], float(results[idx][1])
                if piece_text.strip():
                    text += (joiner if text else "") + piece_text.strip()
                weighted += score * piece_w
                width += piece_w
            merged.append((text, weighted / width if width else 0.0))
        return merged, elapse


def get_paddle_ocr_engine():
    """Initializes and caches the PaddleOCR English engine.

    English only: Devanagari is read by Tesseract (run_tesseract_devanagari)
    and masked out of this engine's input — see run_ocr_on_document_bytes.

    No angle classifier. Its job is to flip text it thinks is upside down,
    and on these upright scans it flipped small print instead: "Time From"
    on the Haryana FIR came back as "mog #!L". Dropping it also skips one
    model per line.
    """
    global _OCR_EN
    if not _HAS_PADDLE:
        raise RuntimeError("PaddleOCR engine not installed")

    if _OCR_EN is None:
        logger.info("Initializing PaddleOCR English model (lang='en')...")
        _OCR_EN = PaddleOCR(
            lang="en",
            use_angle_cls=False,
            show_log=False,
            cpu_threads=_OCR_CPU_THREADS,
            rec_batch_num=_OCR_REC_BATCH_NUM,
        )
        _OCR_EN.text_recognizer = _BoundedRecognizer(_OCR_EN.text_recognizer)

    return _OCR_EN


def mask_regions(image_bytes: bytes, boxes: List[List[int]]) -> bytes:
    """Paints the given [x1, y1, x2, y2] regions white, so the English engine
    reads the page as if they were blank. Returns the input unchanged if it
    cannot be decoded."""
    if not _HAS_CV2 or not boxes:
        return image_bytes
    img = cv2.imdecode(np.frombuffer(image_bytes, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        return image_bytes
    for x1, y1, x2, y2 in boxes:
        cv2.rectangle(img, (int(x1) - 1, int(y1) - 1), (int(x2) + 1, int(y2) + 1), (255, 255, 255), -1)
    ok, encoded = cv2.imencode(".png", img)
    return encoded.tobytes() if ok else image_bytes


def run_paddle_ocr(image_bytes: bytes) -> List[Dict[str, Any]]:
    """Runs PaddleOCR's English engine on image bytes:
    [{"text": str, "confidence": float, "box": [x1, y1, x2, y2], "lang": "en"}, ...]
    """
    ocr_en = get_paddle_ocr_engine()

    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".png", delete=True) as tmp:
        tmp.write(image_bytes)
        tmp.flush()
        result = ocr_en.ocr(tmp.name, cls=False)

    words = []
    if result and result[0]:
        for line in result[0]:
            box_pts = line[0]
            words.append({
                "text": line[1][0],
                "confidence": float(line[1][1]),
                "box": [
                    int(min(p[0] for p in box_pts)),
                    int(min(p[1] for p in box_pts)),
                    int(max(p[0] for p in box_pts)),
                    int(max(p[1] for p in box_pts)),
                ],
                "lang": "en",
            })

    return words


def run_tesseract_devanagari(image_bytes: bytes) -> List[Dict[str, Any]]:
    """Word-level Tesseract `hin` detections: where a page's Hindi is (to mask
    it out of the English pass) and what it says (fused back in by
    fuse_devanagari_boxes). See run_ocr_on_document_bytes.

    Not the fallback engine. Returns [] on any failure, which leaves the page
    to be read as English, unmasked.
    """
    if not _HAS_TESSERACT or not _HAS_PIL:
        return []

    try:
        img = Image.open(io.BytesIO(image_bytes))
        data = pytesseract.image_to_data(img, lang="hin", output_type=pytesseract.Output.DICT)
    except Exception as exc:
        logger.warning(f"Tesseract Devanagari pass unavailable, keeping PaddleOCR only: {exc}")
        return []

    words = []
    for i in range(len(data["text"])):
        text = (data["text"][i] or "").strip()
        conf = float(data["conf"][i])
        if not text or conf < 0:
            continue
        x, y, w, h = data["left"][i], data["top"][i], data["width"][i], data["height"][i]
        words.append({
            "text": text,
            "confidence": conf / 100.0,
            "box": [x, y, x + w, y + h],
            "lang": "hi_tesseract",
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
