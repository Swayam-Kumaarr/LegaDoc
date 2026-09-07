# Autonomous E2E Verification, Browser Testing & Bug-Fixing Mission

## Mission Brief for Claude Code
You are tasked with conducting an autonomous, end-to-end browser verification of **LegaDoc**, an electronic evidence and criminal justice lifecycle management platform.
You will inspect the repository, review the open Pull Requests, launch the web application in your browser environment, systematically walk through all end-user roles and workflows, identify any runtime glitches or usability barriers, and resolve them **in the established architectural manner**.

---

## 1. Repository & Branch Context
- **Repository:** `Swayam-Kumaarr/LegaDoc`
- **Current Active Working Branch:** `hotfix/docker-bottlenecks-and-audit-fixes`
- **Active Hotfix PR:** [PR #57](https://github.com/Swayam-Kumaarr/LegaDoc/pull/57) (`[HOTFIX] Docker build bottlenecks, Celery worker queues, auth scoping, and frontend audit fixes`)
- **Baseline Feature PR:** [PR #56](https://github.com/Swayam-Kumaarr/LegaDoc/pull/56) (`fix(platform): delete dead merge artifacts, fix worker dependencies, and wire frontend to real backend API`)

Run the following commands to inspect the branch and status:
```bash
git status
git branch -vv
gh pr view 57
gh pr view 56
```

---

## 2. Live Environment & Endpoints
All backend services, database, cache, storage, and worker containers are currently up and running:
- **Web Application:** `http://localhost:5174` (mapped to internal Vite dev port 5173).
- **Backend REST API:** `http://localhost:8000` (Swagger interactive docs at `http://localhost:8000/docs`).
- **Postgres Database:** `localhost:5432` (`legadoc` / `postgres`).
- **MinIO Object Storage:** `http://localhost:9000` (Console at `http://localhost:9001`).
- **Redis Queue:** `localhost:6379`.
- **Worker Containers:** `legadoc-ocr_worker-1`, `legadoc-ai_parser_worker-1`, `legadoc-chain_worker-1`.

Verify the stack health before starting:
```bash
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
docker exec legadoc-api-1 pytest
```

---

## 3. Official Role Credentials (Password for all: `GovSecure@2026`)
| Role / Designation | User / Service Email | Primary Interface Routes |
| :--- | :--- | :--- |
| **Station Intake Duty Officer** | `duty.verma@police.gov.in` | `/dashboard`, `/cases` |
| **Station House Officer (SHO)** | `sho.rathore@delhipolice.gov.in` | `/dashboard`, `/cases`, `/reports` |
| **Investigating Officer (IO)** | `io.kumar@delhipolice.gov.in` | `/dashboard`, `/cases/:id`, `/chargesheet` |
| **Public Prosecutor** | `prosecutor.sharma@delhicourts.nic.in` | `/cases/:id`, `/judiciary` |
| **Special Judge** | `judge.singhal@delhicourts.nic.in` | `/judiciary`, `/cases/:id` |
| **Defense Advocate** | `advocate.mittal@delhibar.org` | `/defense`, `/cases/:id` |
| **Forensic Expert (CFSL)** | `forensic.rao@cfsl.gov.in` | `/external-authority` |
| **Platform Config Admin** | `admin.mishra@delhipolice.gov.in` | `/admin`, `/review-queue` |
| **Security Auditor** | `auditor.gupta@delhipolice.gov.in` | `/admin`, `/review-queue`, `/audit` |

---

## 4. End-to-End Browser Testing Scenarios

Open `http://localhost:5174` in your browser tool and execute the following flows sequentially:

### Flow 1: Station Intake & Docket Inspection (Duty Officer)
1. **Navigate to:** `http://localhost:5174`
2. **Login:** Use quick-fill button or credentials for **Sub-Inspector A. Verma** (`duty.verma@police.gov.in` / `GovSecure@2026`).
3. **Verify Dashboard Hub:**
   - Case table should populate with live records from `GET /cases`.
   - Click **Inspect Docket** on any case row:
     - **Verification Criteria:** Ensure the user is **NOT** logged out. The app must navigate smoothly to `/cases/:id`.
     - Inspect the tabs: *Evidentiary Documents*, *Section 91 Requisitions*, *Case Diary*, and *Audit Trail*.
4. **Register a New FIR:**
   - Click **Case Registry & FIR** in the sidebar (or top-right button on Dashboard).
   - Select Crime Type: e.g. `Financial Cyberfraud (Sec 66D IT Act)`.
   - Enter complaint: `Victim reported unauthorized debit of Rs 85,000 from savings account via phishing link.`
   - Click **Register Authoritative FIR**.
   - **Verification Criteria:** Case is created, green confirmation banner displays the new Case Number (`FIN-2026-XXXXXX`), and it appears in the table below.

### Flow 2: Evidentiary Ingestion & CrPC 172 Case Diary
1. On `/cases` (Case Registry & FIR page), scroll down to **Evidentiary Document Ingestion**:
   - Select the case created in Flow 1.
   - Select document type: `FIR` or `Bank Statement`.
   - Upload a test file (plain text `.txt` or image).
   - Click **Ingest into Cryptographic Vault**.
   - **Verification Criteria:** SHA-256 hash digest is computed; Track A returns immediate receipt; Track B background tasks run without crashing.
2. Scroll to **Running Case Diary (Section 172 CrPC)**:
   - Select the case.
   - Enter entry note: `Recorded statement of nodal banking compliance officer under Sec 161 CrPC.`
   - Click **Append to Running Case Diary**.
   - **Verification Criteria:** Diary entry is saved with immutable timestamp.

### Flow 3: AI Redaction & Review Queue (Config Admin / Security Auditor)
1. Click **Log Out** in the top navigation.
2. Log in as **Amit Mishra** (`admin.mishra@delhipolice.gov.in` / `GovSecure@2026`).
3. Navigate to **Needs-Review Queue** (`/review-queue`).
4. **Verification Criteria:**
   - SLA card and queue depth indicator display clean numeric metrics (no `NaN` or `-Infinity`).
   - If documents are pending redaction, review their PII flags and test the Accept / Reject tag buttons.

### Flow 4: Judicial Trial & Bail Orders (Special Judge)
1. Log out and log in as **Hon. P. K. Singhal** (`judge.singhal@delhicourts.nic.in` / `GovSecure@2026`).
2. Navigate to **Judicial & Trial Tracking** (`/judiciary`).
3. Select a case from the docket list.
4. Under **Issue Judicial Bail Order**:
   - Select Bail Decision (e.g. `Regular Bail Granted (Sec 437/439 CrPC)`).
   - Enter conditions / surety amounts.
   - Click **Issue Judicial Bail Order**.
   - **Verification Criteria:** Success banner confirms order attached to immutable ledger; case status updates.
5. Under **Schedule Trial Hearing Notice**:
   - Select Stage (e.g. `Arguments on Charge`) and date.
   - Click **Transmit Statutory Hearing Notice**.
   - **Verification Criteria:** Summons notice recorded.
6. Switch to the **Audit Trail & Custody Chain** tab:
   - **Verification Criteria:** Cryptographic audit trail loads from `/cases/:id/audit-log` without 404 errors.

### Flow 5: Defense & Accused Portal (Defense Advocate)
1. Log out and log in as **Sr. Adv. S. K. Mittal** (`advocate.mittal@delhibar.org` / `GovSecure@2026`).
2. Navigate to **Defense & Accused** (`/defense`).
3. Select a docket:
   - Verify that dropdown options display the real `case_number` and `crime_type`.
   - Submit a test Bail Application under Sec 437/439.
   - Verify submitted applications appear in the tracking ledger.

### Flow 6: Forensic & External Requisitions (CFSL Expert)
1. Log out and log in as **Dr. Sunita Rao** (`forensic.rao@cfsl.gov.in` / `GovSecure@2026`).
2. Navigate to **External Authority** (`/external-authority`).
3. Verify that assigned Section 91 evidence requisitions populate from `GET /evidence-requests`.
4. Submit a forensic examination report and verify receipt.

---

## 5. Rules for Debugging & Fixing Issues ("The Decided Manner")
If you encounter any bug, mismatch, or broken flow during your browser inspection:

1. **Safety Constraints (Strictly Enforced):**
   - **Never push directly to `main` or `master`.**
   - **Never delete files without confirmation.**
   - **Never hardcode secrets, API keys, or JWT tokens.**
   - **Never install new npm or pip packages without asking.**
   - **Never execute raw unreviewed database migrations.**
2. **Architecture & Code Locations:**
   - **Frontend:** `web/src/` (Vite auto-reloads changes in browser).
   - **Backend API:** `api/app/` (Restart `legadoc-api-1` if Python modules need reloading).
   - **Workers:** `workers/ocr_worker/` and `workers/ai_parser_worker/` (Worker code is volume-mounted; restart via `docker restart legadoc-ocr_worker-1 legadoc-ai_parser_worker-1`).
3. **Automated Test Validation:**
   - Before making any commit, run:
     ```bash
     docker exec legadoc-api-1 pytest
     ```
   - **All 169 tests MUST PASS (100% pass rate).** Never break existing regression coverage.
4. **Git Commit & PR Updates:**
   - Commit fixes directly to the active branch `hotfix/docker-bottlenecks-and-audit-fixes` with descriptive conventional commits:
     ```bash
     git add <modified-files>
     git commit -m "fix(<scope>): <concise description of fix>"
     git push origin hotfix/docker-bottlenecks-and-audit-fixes
     ```
   - Pushing to this branch automatically updates **PR #57**.
