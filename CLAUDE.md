# CLAUDE.md — LegaDoc Repository Guidelines & Agent Memory

## Project Overview
LegaDoc is a tamper-evident, dual-track evidentiary processing and case lifecycle management platform built for Indian law enforcement, prosecution, judiciary, defense, and statutory forensics.
It enforces the Bharatiya Nagarik Suraksha Sanhita (BNSS) 2023, Bharatiya Sakshya Adhiniyam (BSA) 2023, and IT Act evidentiary compliance.

---

## Active Environment & Local Stack
All services are running locally via Docker Compose:
- **Frontend (Vite + React):** `http://localhost:5174` (mapped to container port 5173).
- **Backend API (FastAPI):** `http://localhost:8000` (OpenAPI Swagger at `http://localhost:8000/docs`).
- **PostgreSQL 16:** `localhost:5432` (`db: legadoc`, `user: postgres`, `password: postgres`).
- **Redis 7 (AOF enabled):** `localhost:6379`.
- **MinIO S3 Storage:** API at `http://localhost:9000`, Web Console at `http://localhost:9001` (`minioadmin:minioadmin`).
- **Celery Workers:**
  - `legadoc-ocr_worker-1` (queue: `ocr`)
  - `legadoc-ai_parser_worker-1` (queue: `ai_parser`)
  - `legadoc-chain_worker-1` (queue: `chain`)

---

## Official Test Credentials (Password for all: `GovSecure@2026`)
- **Duty Officer (Station Intake):** `duty.verma@police.gov.in` (Sub-Inspector A. Verma)
- **Station House Officer (SHO):** `sho.rathore@delhipolice.gov.in` (Inspector Vikram Rathore)
- **Investigating Officer (IO):** `io.kumar@delhipolice.gov.in` (Inspector Rajesh Kumar)
- **Public Prosecutor:** `prosecutor.sharma@delhicourts.nic.in` (Adv. Meera Sharma)
- **Special Judge:** `judge.singhal@delhicourts.nic.in` (Hon. P. K. Singhal)
- **Defense Advocate:** `advocate.mittal@delhibar.org` (Sr. Adv. S. K. Mittal)
- **External Authority (CFSL Forensic):** `forensic.rao@cfsl.gov.in` (Dr. Sunita Rao)
- **Platform Config Admin:** `admin.mishra@delhipolice.gov.in` (Amit Mishra)
- **Security Auditor:** `auditor.gupta@delhipolice.gov.in` (Neha Gupta)

---

## Key Workflows & Dual-Track Pipeline
1. **Track A (Synchronous):** Document upload computes SHA-256 digest immediately, registers tamper-evident record in DB, and returns HTTP 202 Accepted.
2. **Track B (Asynchronous):**
   - Dispatches to `ocr_worker` via Celery queue `ocr`. Text documents bypass OCR; images/scans run PaddleOCR / Tesseract fallback.
   - Dispatches to `ai_parser_worker` via Celery queue `ai_parser`. Runs Presidio Analyzer with `en_core_web_sm` and fallback regexes for Indian legal PII (Aadhaar, PAN, phone, names).
   - Generates redaction suggestions. Low confidence (<85%) or critical tags queue to `NeedsReviewQueue` (`/documents?status=needs_review`).
   - Dispatches to `chain_worker` via Celery queue `chain` for ledger hashing.

---

## Mandatory Constraints & Agent Rules
- **Never push to `main`/`master` branch directly.** Always use feature or hotfix branches.
- **Never delete files without explicit user confirmation.**
- **Never hardcode credentials, API keys, or secrets in any file.**
- **Never install new packages without asking the user first.**
- **Never run unapproved database migrations.** Always inspect SQL first.
- **One feature / fix at a time:** complete, verify with tests, confirm.
- **Always verify automated tests before committing:**
  `docker exec legadoc-api-1 pytest` (must pass 169/169 tests).

---

## Common Development Commands
```bash
# Run backend test suite (target: 169 passed)
docker exec legadoc-api-1 pytest

# Check container status
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

# Inspect logs
docker logs --tail 50 -f legadoc-api-1
docker logs --tail 50 -f legadoc-ocr_worker-1
docker logs --tail 50 -f legadoc-ai_parser_worker-1
docker logs --tail 50 -f legadoc-web-1

# Restart worker or API after python code changes (code is volume mounted)
docker restart legadoc-api-1 legadoc-ocr_worker-1 legadoc-ai_parser_worker-1

# Frontend changes in web/src are automatically hot-reloaded by Vite on http://localhost:5174
```

---

## Active Branches & Pull Requests
- **Branch:** `hotfix/docker-bottlenecks-and-audit-fixes`
- **Active Hotfix PR:** PR #57 (`[HOTFIX] Docker build bottlenecks, Celery worker queues, auth scoping, and frontend audit fixes`)
- **Baseline Feature PR:** PR #56 (`fix(platform): delete dead merge artifacts, fix worker dependencies, and wire frontend to real backend API`)
