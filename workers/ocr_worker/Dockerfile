# Built with the REPO ROOT as build context (see docker-compose.yml), not
# this directory — that's what makes `COPY api/app` below possible.
FROM python:3.11-slim

WORKDIR /worker

# Install system dependencies: libgl1/libgomp1 for OpenCV/PaddleOCR, and Tesseract with Hindi language pack
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libgomp1 \
    tesseract-ocr \
    tesseract-ocr-hin \
    && rm -rf /var/lib/apt/lists/*

COPY workers/ocr_worker/requirements.txt .
RUN pip install --default-timeout=1000 --no-cache-dir -r requirements.txt

COPY workers/ocr_worker/worker.py workers/ocr_worker/layout_reconstruction.py ./

# Reuses api/app's models/database/audit/storage/config directly instead of
# duplicating them — same reasoning as chain_worker's Dockerfile. Lands at
# /api/app, matching the sys.path insertion pattern in workers/chain_worker/worker.py
COPY api/app /api/app

CMD ["celery", "-A", "worker", "worker", "--loglevel=info"]

