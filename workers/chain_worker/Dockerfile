# Built with the REPO ROOT as build context (see docker-compose.yml's
# chain_worker service — `context: .`, `dockerfile: workers/chain_worker/Dockerfile`),
# not this directory — that's what makes `COPY api/app` below possible.
FROM python:3.11-slim

WORKDIR /worker

COPY workers/chain_worker/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY workers/chain_worker/worker.py workers/chain_worker/fabric_client.py ./

# worker.py reuses api/app's models/database/audit/config directly instead
# of duplicating the schema — see worker.py's own comment. This lands at
# /api/app in the image, matching the relative path
# (os.path.dirname(__file__) + "../../api") worker.py's sys.path insertion
# computes from /worker/worker.py.
COPY api/app /api/app

# -Q chain_worker: listen only on this worker's own queue. Task names are
# routed queue-per-name-prefix by CeleryQueueClient (see api/app/queue.py)
# — without this flag every worker shares Celery's single default "celery"
# queue and silently drops tasks it doesn't recognize instead of leaving
# them for the worker that does.
CMD ["celery", "-A", "worker", "worker", "--loglevel=info", "-Q", "chain_worker"]
