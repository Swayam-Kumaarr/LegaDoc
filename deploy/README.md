# Single-VM demo deployment

Runs the whole LegaDoc stack on one VM (8 GB minimum, 12 GB comfortable) behind
Cloudflare. Uses the same `docker-compose.yml` as local dev, with
`docker-compose.prod.yml` layered on top.

| File | Purpose |
|---|---|
| `docker-compose.prod.yml` | Publishes only the web container, on 127.0.0.1. No source mounts, no `--reload`, no Vite dev server. Required secrets, memory caps, restart policies. `chain_worker` behind `--profile fabric`, `cloudflared` behind `--profile tunnel`. |
| `Caddyfile` | Serves the React build on `APP_HOST` and proxies `/api`. Serves MinIO on `FILES_HOST`, so presigned download links work for visitors. |
| `web.Dockerfile` | `vite build`, then served by Caddy. |
| `env.production.example` | Every value production needs; copy to `.env` at the repo root. |

## Quick start (on the VM, from the repo root)

```bash
cp deploy/env.production.example .env          # replace every CHANGE_ME
alias dc='docker compose -f docker-compose.yml -f deploy/docker-compose.prod.yml'
docker network create fabric_test 2>/dev/null || true
dc build ocr_worker && dc build                   # OCR first: its build runs the models
dc up -d
dc exec api python -c "
from app.database import Base, engine, SessionLocal
from app import models
from app.seed_data import seed_all
Base.metadata.create_all(bind=engine)
db = SessionLocal(); seed_all(db); db.close()"
dc --profile tunnel up -d                         # after CLOUDFLARE_TUNNEL_TOKEN is set
```

Point both tunnel hostnames (app and files) at `http://web:80`.

## Before the URL is shared

- **Gate the site with Cloudflare Access.** Every seeded persona's password is published in this repo.
- **Or rotate the persona passwords** right after seeding.
- **Secrets must be real.** `ENV=production` makes the API and workers refuse to start with the repository's default JWT secret, MinIO secret or database password.
- **`MINIO_KMS_SECRET_KEY` is required.** In production the API requests server-side encryption, and MinIO rejects it without a key.

## What has been verified

These files were rehearsed locally on arm64 with `ENV=production`:
- only the web port was reachable;
- the full case lifecycle and redaction contrast passed through Caddy;
- uploads were stored encrypted;
- download links worked through `FILES_HOST`;
- a missing secret stopped startup.

Not yet verified: provisioning on a cloud provider, x86 builds, Cloudflare Tunnel/Access, and Fabric on the VM.
