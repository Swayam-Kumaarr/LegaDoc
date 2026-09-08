# Built with the REPO ROOT as build context (see docker-compose.yml), not
# this directory — that's what makes `COPY api/app` below possible.
FROM python:3.11-slim

WORKDIR /worker

# Both OCR engines need system libraries `python:3.11-slim` doesn't ship —
# neither actually worked in this image before this fix, both failing in a
# way that looked like a Python/pip problem but wasn't:
#   - paddlepaddle's native libpaddle.so needs libgomp.so.1 (GNU OpenMP) —
#     without it, `from paddleocr import PaddleOCR` throws at import time,
#     which worker.py catches and treats as "PaddleOCR not installed".
#   - paddleocr's own import chain pulls in cv2 (opencv), which needs
#     libGL.so.1 — confirmed live: fixing libgomp1 alone just traded one
#     ImportError for this one.
#   - pytesseract is only a wrapper — it shells out to a real `tesseract`
#     binary that was never apt-installed, so the fallback engine failed
#     too, with BOTH engines down every real (non-mocked) OCR job silently
#     degraded to needs_review.
#   - tesseract-ocr-hin: worker.py runs a bilingual (en+hi) PaddleOCR pass
#     and falls back to Tesseract for either — without the Hindi language
#     pack, the Tesseract fallback silently can't read Hindi/Devanagari text.
#   - libglib2.0-0/libsm6/libxext6/libxrender1: opencv-python-headless's
#     other common missing-.so list on a slim base — added preemptively.
# Installed BEFORE pip so the model-preload step below can actually import
# and run PaddleOCR at build time (it needs these libs to load at all).
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 libgl1 tesseract-ocr tesseract-ocr-hin \
    libglib2.0-0 libsm6 libxext6 libxrender1 \
    && rm -rf /var/lib/apt/lists/*

COPY workers/ocr_worker/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Pre-download and cache PaddleOCR English and Hindi models at build time
# (Issue #37) — without this, the first real OCR request in a fresh
# container pays the full model-download cost inline (confirmed live: ~80s
# on first use) instead of at build time where it belongs.
RUN python -c "from paddleocr import PaddleOCR; PaddleOCR(use_angle_cls=True, lang='en', show_log=False); PaddleOCR(use_angle_cls=True, lang='hi', show_log=False)"

COPY workers/ocr_worker/worker.py .
# worker.py imports this as a bare module (`from layout_reconstruction
# import ...`), which only resolves because it inserts its own directory
# into sys.path at startup — that only works if this file actually lands
# next to worker.py in the image. It didn't: this COPY was missing, so the
# container crashed at import time with "ModuleNotFoundError: No module
# named 'layout_reconstruction'" and never got as far as starting Celery.
COPY workers/ocr_worker/layout_reconstruction.py .

# Reuses api/app's models/database/audit/storage/config directly instead of
# duplicating them — same reasoning as chain_worker's Dockerfile. Lands at
# /api/app, matching the sys.path insertion pattern in workers/chain_worker/worker.py.
COPY api/app /api/app

# -Q ocr_worker: see chain_worker/Dockerfile for why this flag is required
# — without it this container silently discards tasks meant for the other
# workers (and vice versa), since all three would otherwise share Celery's
# single default "celery" queue.
CMD ["celery", "-A", "worker", "worker", "--loglevel=info", "-Q", "ocr_worker"]
