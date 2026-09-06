# Built with the REPO ROOT as build context (see docker-compose.yml), not
# this directory — that's what makes `COPY api/app` below possible.
FROM python:3.11-slim

WORKDIR /worker

COPY workers/ocr_worker/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY workers/ocr_worker/worker.py workers/ocr_worker/layout_reconstruction.py ./

# Reuses api/app's models/database/audit/storage/config directly instead of
# duplicating them — same reasoning as chain_worker's Dockerfile. Lands at
# /api/app, matching the sys.path insertion pattern in workers/chain_worker/worker.py
# — add the same import + sys.path lines here once this worker's real logic
# needs to read/write Document rows or fetch the raw file from storage.
COPY api/app /api/app

CMD ["celery", "-A", "worker", "worker", "--loglevel=info"]
