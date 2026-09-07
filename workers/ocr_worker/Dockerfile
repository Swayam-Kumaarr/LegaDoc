# Built with the REPO ROOT as build context (see docker-compose.yml), not
# this directory — that's what makes `COPY api/app` below possible.
FROM python:3.11-slim

WORKDIR /worker

# pip install BEFORE the apt-get system-library block below — this is the
# expensive layer (paddlepaddle/paddleocr, several hundred MB, minutes to
# reinstall from scratch) and doesn't actually depend on those system
# libraries being present to install successfully, only to import/run
# correctly. Keeping it first means iterating on the apt-get package list
# (a real, ongoing thing — see the comment below) invalidates only the
# cheap layer after it, not this one.
COPY workers/ocr_worker/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

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
#   - libglib2.0-0/libsm6/libxext6/libxrender1: opencv-python-headless's
#     other common missing-.so list on a slim base — added preemptively.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 libgl1 tesseract-ocr libglib2.0-0 libsm6 libxext6 libxrender1 \
    && rm -rf /var/lib/apt/lists/*

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
