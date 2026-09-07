# CLAUDE.md — LegaDoc Repository Guidelines & Agent Memory

## Project Overview
LegaDoc is a tamper-evident, dual-track evidentiary processing and case lifecycle management platform built for Indian law enforcement, prosecution, judiciary, defense, and statutory forensics.
It enforces Bharatiya Nagarik Suraksha Sanhita (BNSS) 2023, Bharatiya Sakshya Adhiniyam (BSA) 2023, and IT Act evidentiary compliance.

---

## Local Stack
Brought up with `docker compose up`:
- **Frontend (Vite + React):** `http://localhost:5173`
- **Backend API (FastAPI):** `http://localhost:8000` (Swagger at `/docs`)
- **PostgreSQL 16:** `localhost:5432` (`db: legadoc`, `user: postgres`, `password: postgres`)
- **Redis 7:** `localhost:6379`
- **MinIO S3:** API `http://localhost:9000`, console `http://localhost:9001`
- **Celery workers:** `legadoc-ocr_worker-1`, `legadoc-ai_parser_worker-1`, `legadoc-chain_worker-1`

Check what is actually published before assuming a port:
```bash
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
```

---

## Test Credentials (password for all: `GovSecure@2026`)

These are the personas the seeder actually creates, and they match
`OFFICIAL_TEST_CREDENTIALS` in `web/src/contexts/AuthContext.jsx` — the same list
the login page's **Show Personas** drawer offers. Every one is verified to
return HTTP 200 from `POST /auth/login`.

| Role | Email | `role` claim |
| :--- | :--- | :--- |
| Platform Administrator | `admin.sharma@legadoc.gov.in` | `config_admin` |
| Investigating Officer | `officer.rao@police.gov.in` | `io` |
| Duty Officer (Station Intake) | `duty.verma@police.gov.in` | `duty_officer` |
| Judicial Bench (Magistrate) | `magistrate.iyer@court.gov.in` | `court` |
| Public Prosecutor | `prosecutor.sen@court.gov.in` | `prosecutor` |
| External Authority (FSL) | `fsl.director@fsl.gov.in` | `external_authority` |
| Defense Counsel | `defense.advocate@bar.in` | `defense` |
| NCRB Analyst | `analyst.ncrb@nic.in` | `records_ncrb_analyst` |

Before adding a persona to this table, confirm it logs in. An earlier revision
of this file listed nine invented addresses (`io.kumar@delhipolice.gov.in`,
`judge.singhal@delhicourts.nic.in`, and so on); only `duty.verma` existed. They
appeared to work because `AuthContext` fell back to a client-side session on any
login failure, so testing against them exercised mock data rather than the API.

Verify the full set at any time:
```bash
docker exec legadoc-db-1 psql -U postgres -d legadoc \
  -c "SELECT email, role FROM users WHERE role_id IS NOT NULL ORDER BY role;"
```

**No `security_auditor` user is seeded.** The role exists in the `roles` table and
carries unrestricted case access, but no account holds it, so any flow written
around a Security Auditor cannot be run as written.

---

## Access Model — read before touching authorization

All role/org/case-assignment checks live in `api/app/security.py`. Do not
reimplement them per-endpoint.

Three sets, each answering a different question:

- **`_UNRESTRICTED_CASE_ROLES`** — may open any case without an assignment.
- **`_POLICE_SPECIALIST_ROLES`** — need a link to the specific case.
- **`FULL_TEXT_ACCESS_ROLES`** — see raw, unredacted PII.

`FULL_TEXT_ACCESS_ROLES` is an explicit literal and **must stay one**. It was
previously derived as `_UNRESTRICTED_CASE_ROLES | {"io"}`, which meant adding a
role to the case set silently granted it every witness name, phone number and
address in the system, with nothing at the call site to review.

A **Duty Officer** may read the FIRs it registered and nothing else. That link is
the `fir_registered` audit-log row, since `Case` has no org or registrant column.
Match that string exactly — `assert_case_access` and `list_cases` both filter on
it, so a near-miss like `register_fir` silently returns no cases rather than
failing loudly.
It is deliberately not a `CaseAssignment` row: that table means "the current IO
for this case", and `reassign_io` deletes every row for a case when the IO
changes. Duty Officer reads those documents **redacted**.

The external-authority role string is `external_authority`, exposed as
`EXTERNAL_AUTHORITY_ROLE`. Use the constant. It was previously spelled
`authority_staff` in the authorization checks — a string no seeder writes and
the `roles` table has no row for — so every real FSL/bank/telecom account was
denied its own requisitions.

Tenancy checks fail **closed**. A missing or unparseable `org_id` is a denial,
never a fallback to returning everything.

---

## Mandatory Constraints
- **Never push to `main`/`master` directly.** Use feature or hotfix branches.
- **Never delete files without explicit user confirmation.**
- **Never hardcode credentials, API keys, or secrets.**
- **Never install new packages without asking first.**
- **Never run unapproved database migrations.** Inspect the SQL first.
- **One fix at a time:** complete it, verify it, confirm it.
- **Run the suite before committing:** `docker exec legadoc-api-1 pytest`
- **Rebuild an image after changing its `requirements.txt` or `package.json`.**
  Containers keep the dependencies baked in at build time, and both failure
  modes here are silent: a stale `ocr_worker` has no `pymupdf`, so
  `_HAS_PYMUPDF` is False and PDF evidence is skipped without an error; a stale
  `web` ran Vite 5.4 against a `package.json` asking for 8.x, so `vite.config.js`
  options were ignored with no warning.
  ```bash
  docker compose build api ocr_worker ai_parser_worker web && docker compose up -d
  ```

`main` currently has **189 tests, all passing**. Treat that as the baseline and
confirm it locally rather than trusting a number in a doc — it will drift the
moment a branch adds or removes tests.

---

## Windows: always run `docker compose` from inside WSL2

`chain_worker` bind-mounts `${HOME}/fabric-samples` (the `peer` binary and
crypto material it shells out to) and attaches to the external `fabric_test`
network. Docker Desktop resolves both correctly only when `docker compose` is
invoked *from inside WSL2* against the WSL2 filesystem path. Run it from a
plain Windows terminal (PowerShell, cmd, or a Windows-side Git Bash) instead —
against a `\\wsl$\<distro>\...` UNC path — and the bind mount silently mounts
an **empty directory** instead of erroring. The container starts and looks
healthy; only the first real blockchain write fails, with
`FabricSubmissionError('peer binary not found at /root/fabric-samples/bin/peer')`,
retrying every 30s forever. Confirmed live twice in this session — restarting
`chain_worker` from Windows-side Bash silently broke it both times, with the
container reporting "Up" the whole time.

Always bring the stack up (or restart `chain_worker` specifically) from
inside WSL2:
```bash
wsl -e bash -c "cd /mnt/c/projects/LegaDoc && docker compose up -d"
```
If a document is stuck with `chain_status: failed` and this is why, no
re-upload is needed — restart `chain_worker` correctly and retry:
```bash
curl -X POST http://localhost:8000/documents/<doc_id>/retry-chain-write \
  -H "Authorization: Bearer <config_admin token>"
```

---

## Common Commands
```bash
# Backend test suite
docker exec legadoc-api-1 pytest

# Container status
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

# Logs
docker logs --tail 50 -f legadoc-api-1
docker logs --tail 50 -f legadoc-ocr_worker-1

# Restart after Python changes (code is volume-mounted)
docker restart legadoc-api-1 legadoc-ocr_worker-1 legadoc-ai_parser_worker-1

# Frontend changes under web/src hot-reload automatically
```

---

## Frontend Notes
- `VITE_OFFLINE_DEMO_MODE` is **off by default** and should stay off outside a
  deliberate offline demo. When enabled, a login that cannot reach the API at
  all resolves against the built-in persona list **without verifying a
  password**.
- Several screens still hold mock data and do not call the API. Confirm a screen
  is wired before treating its behaviour as a backend result:
  ```bash
  grep -rlE 'apiClient|apiUpload' web/src/routes/
  ```
