# Built with the REPO ROOT as build context (see docker-compose.yml), not
# this directory — that's what makes `COPY api/app` below possible.
FROM python:3.11-slim

WORKDIR /worker

COPY workers/ai_parser_worker/requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r requirements.txt \
    && python -m spacy download en_core_web_sm

COPY workers/ai_parser_worker/worker.py .

# Reuses api/app's models/database/audit/config directly instead of
# duplicating them — same reasoning as chain_worker's Dockerfile. Lands at
# /api/app, matching the sys.path insertion pattern in workers/chain_worker/worker.py
# — add the same import + sys.path lines here once this worker's real logic
# needs to read Document.raw_text or write DocumentSensitivityTag rows.
COPY api/app /api/app

# -Q ai_parser_worker: see chain_worker/Dockerfile for why this flag is
# required — without it this container silently discards tasks meant for
# the other workers (and vice versa), since all three would otherwise
# share Celery's single default "celery" queue.
# --pool=solo --prefetch-multiplier=1: one process, one job at a time.
# Celery's default prefork pool starts one child per CPU, and each child
# loads its own copy of this worker's models on first use — on an 8-core
# laptop that is eight model sets. The default prefetch also reserves up to
# 4 jobs ahead; a worker stopped before running them leaves those jobs in
# Redis's "unacked" set until the 1-hour visibility timeout, and the
# document shows "processing" for that hour with no error. Both were hit
# live (scripts/staged_test.sh). Demo-scale throughput does not need more.
CMD ["celery", "-A", "worker", "worker", "--loglevel=info", "-Q", "ai_parser_worker", "--pool=solo", "--prefetch-multiplier=1"]
