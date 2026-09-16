#!/usr/bin/env bash
# One-time local setup: copy env template, build+start everything, create tables.
set -e

if [ ! -f .env ]; then
  cp .env.example .env
  echo "Created .env from .env.example — edit it if your local ports/creds differ."
fi

docker compose up -d --build
echo "Waiting for the database to accept connections..."
sleep 5

docker compose exec api python -m app.init_db

# Tables without rows are not a usable stack: every persona in CLAUDE.md and
# in the DevLogin picker lives in seed_data.py, and until this step existed
# nothing ever called it — a fresh setup had zero users and every sign-in
# returned "Invalid email or password". Idempotent, so it is safe to re-run
# whenever a persona is added.
echo "Seeding roles, permissions and the canonical personas..."
docker compose exec api python -m app.seed_db

echo "Up. API: http://localhost:8000/health   Web: http://localhost:5173   MinIO console: http://localhost:9001"
