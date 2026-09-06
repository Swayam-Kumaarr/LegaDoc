# LegaDoc — Exhaustive Repository Data Flow Diagrams (DFD / DRD)

> **Repository:** [LegaDoc](file:///Users/kamalnasir/Desktop/SIH2026/LegaDoc)  
> **Standard:** Complete Data Flow Diagram set spanning Level 0 (Context), Level 1 (Macro Subsystems), and Level 2 (Micro Decompositions for all 7 submodules).  
> **Validation:** Standard Mermaid flowchart syntax without bidirectional link errors, unquoted delimiters, stateDiagram-v2 parse bugs, or recursive loops.

---

## 1. DFD Level 0 — System Context (The Macro Boundary)

```mermaid
flowchart TB
    %% External Entities (Users)
    POLICE["👤 Police Personnel<br/>(Duty Officer / SHO / IO)"]
    AUTH["🏛️ External Authorities<br/>(FSL Forensics / Hospital / Bank / Telecom)"]
    COURT["⚖️ Judiciary & Prosecution<br/>(Judge / Magistrate / Public Prosecutor)"]
    DEFENSE["🛡️ Defense & Accused<br/>(Defense Counsel / Accused)"]
    AUDITOR["🔍 Security Auditor<br/>(Independent Redaction Oversight)"]
    ANALYST["📊 NCRB / Crime Analyst<br/>(National Crime Records Bureau)"]

    %% External Systems
    FABRIC["⛓️ Hyperledger Fabric<br/>(Permissioned Blockchain Ledger)"]

    %% Central Process
    LEGADOC(["0.0 LEGADOC CRIMINAL JUSTICE OS<br/>(FastAPI Monolith, Ingestion & Lifecycle Workers)"])

    %% Data Stores
    STORAGE[("💾 MinIO Object Storage<br/>org_id/case_id/doc_id/v{version}")]
    DB[("💾 PostgreSQL 16 Multi-Tenant Core<br/>(Cases, Documents, Tags, AuditLog)")]
    REDIS[("💾 Redis 7 AOF Persistent<br/>(Celery Broker, Rate Limiter Cache)")]

    %% User Ingestion & Responses
    POLICE -->|credentials, fir dockets, evidence, case diary| LEGADOC
    AUTH -->|credentials and section 91 evidence reports| LEGADOC
    COURT -->|credentials, hearing notices, bail orders, judgments| LEGADOC
    DEFENSE -->|credentials, bail applications, surety bonds| LEGADOC
    AUDITOR -->|credentials and ai parser audit queries| LEGADOC
    ANALYST -->|credentials and metadata report filters| LEGADOC

    LEGADOC -->|case docket, assigned cases, review queues| POLICE
    LEGADOC -->|routed evidence requisitions| AUTH
    LEGADOC -->|unredacted judicial evidence, charge sheets| COURT
    LEGADOC -->|bail status and hearing schedules| DEFENSE
    LEGADOC -->|decision metrics, confidence scores, zero pii| AUDITOR
    LEGADOC -->|deidentified crime metadata analytics| ANALYST

    %% System Integrations
    LEGADOC -->|signed sha256 hash transactions| FABRIC
    FABRIC -->|block confirmation and transaction id| LEGADOC

    %% Data Storage
    LEGADOC -->|write encrypted blobs and presigned urls| STORAGE
    STORAGE -->|read binary streams| LEGADOC
    LEGADOC -->|sql transactions, rls scoping, seq audit chain| DB
    DB -->|relational records and row verification| LEGADOC
    LEGADOC -->|enqueue async jobs and check rate limits| REDIS
    REDIS -->|dequeue jobs to celery workers| LEGADOC
```

---

## 2. DFD Level 1 — Macro Repository Data Flow

```mermaid
flowchart TB
    UserPolice["👤 Duty Officer / SHO / IO"]
    UserAuth["🏛️ External Authority"]
    UserJudiciary["⚖️ Court / Prosecutor"]
    UserDefense["🛡️ Defense Counsel"]
    UserAuditor["🔍 Security Auditor / NCRB"]
    FabricLedger["⛓️ Hyperledger Fabric"]

    P_AUTH(["1.0 /auth & /admin/roles<br/>Session, Identity & Multi-Tenant RBAC"])
    P_CASES(["2.0 /cases & Reassign<br/>FIR Registration, Assignment & Case Diary"])
    P_INGEST(["3.0 /documents (Upload)<br/>Streaming Sniffer, MinIO & Celery Dispatch"])
    P_WORKER(["4.0 Workers & Review Queue<br/>OCR, AI Tagging, Redaction & Needs Review"])
    P_EVID(["5.0 /evidence-requests & Gate<br/>Sec 91 Requisitions & Charge Sheet Gate"])
    P_BAIL_TRIAL(["6.0 /bail & /trial<br/>Independent Bail FSM & Judicial Trial"])
    P_AUDIT_NCRB(["7.0 /audit-log & /reports<br/>Sequential Audit Chaining & NCRB Reporting"])

    D_USERS[("💾 D1: users & orgs<br/>users, organizations, roles, permissions")]
    D_CASES[("💾 D2: cases & assignments<br/>cases, case_assignments, case_diary_entries")]
    D_DOCS[("💾 D3: documents<br/>documents, versions, raw_text, storage_path")]
    D_TAGS[("💾 D4: sensitivity_tags<br/>document_sensitivity_tags, zero pii text")]
    D_EVID[("💾 D5: evidence_requests<br/>evidence_requests, stage_requirements")]
    D_S3[("💾 D6: MinIO S3<br/>org_id/case_id/doc_id/v{version}")]
    D_REDIS[("💾 D7: Redis Queues<br/>Celery broker, sliding rate limits")]
    D_AUDIT[("💾 D8: audit_logs<br/>pg_advisory_xact_lock, monotonic seq, row_hash")]

    %% Auth interactions
    UserPolice -->|login credentials| P_AUTH
    UserAuth -->|login credentials| P_AUTH
    UserJudiciary -->|login credentials| P_AUTH
    UserDefense -->|login credentials| P_AUTH
    UserAuditor -->|login credentials| P_AUTH
    P_AUTH -->|validate_credentials_and_constant_time_dummy| D_USERS
    D_USERS -->|user_record_and_canonical_role| P_AUTH
    P_AUTH -->|jwt_access_and_refresh_tokens| UserPolice

    %% Cases interactions
    UserPolice -->|register_fir_payload| P_CASES
    P_CASES -->|insert_case_and_status_fir_registered| D_CASES
    UserPolice -->|assign_or_reassign_io| P_CASES
    P_CASES -->|atomic_swap_case_assignments| D_CASES
    P_CASES -->|append_case_diary_entry| D_CASES
    P_CASES -->|emit_audit_event_io_assigned| D_AUDIT

    %% Ingestion interactions
    UserPolice -->|multipart_document_upload| P_INGEST
    P_INGEST -->|sniff_8kb_magic_bytes_and_50mb_cap| P_INGEST
    P_INGEST -->|stream_encrypted_file_blob| D_S3
    P_INGEST -->|insert_document_processing| D_DOCS
    P_INGEST -->|enqueue_track_a_and_track_b| D_REDIS

    %% Worker & Review interactions
    D_REDIS -->|dequeue_ocr_and_ai_jobs| P_WORKER
    P_WORKER -->|read_raw_file| D_S3
    P_WORKER -->|update_raw_text| D_DOCS
    P_WORKER -->|insert_presidio_sensitivity_tags| D_TAGS
    P_WORKER -->|submit_hash_transaction| FabricLedger
    FabricLedger -->|transaction_id_and_confirmed| P_WORKER
    P_WORKER -->|update_chain_status_confirmed| D_DOCS
    P_WORKER -->|flag_needs_review_if_confidence_low| D_DOCS
    P_WORKER -->|emit_auto_tag_completed| D_AUDIT
    UserPolice -->|review_queue_and_human_correction| P_WORKER
    P_WORKER -->|apply_redaction_masks_by_role| UserJudiciary

    %% Evidence & Charge sheet
    UserPolice -->|create_section_91_request| P_EVID
    P_EVID -->|insert_evidence_request| D_EVID
    UserAuth -->|submit_certified_evidence| P_EVID
    P_EVID -->|verify_tenant_match_and_default_deny| D_EVID
    P_EVID -->|mark_request_completed_and_attach_doc| D_EVID
    UserJudiciary -->|file_charge_sheet_attempt| P_EVID
    D_EVID -->|check_mandatory_documents_and_evidence| P_EVID
    P_EVID -->|update_status_charge_sheet_filed| D_CASES
    P_EVID -->|emit_charge_sheet_filed_event| D_AUDIT

    %% Bail & Trial
    UserPolice -->|record_arrest| P_BAIL_TRIAL
    UserDefense -->|submit_bail_petition| P_BAIL_TRIAL
    UserJudiciary -->|schedule_hearing_and_issue_order| P_BAIL_TRIAL
    P_BAIL_TRIAL -->|update_bail_fsm_state| D_CASES
    UserJudiciary -->|schedule_trial_hearing| P_BAIL_TRIAL
    P_BAIL_TRIAL -->|update_investigation_status_trial| D_CASES
    UserJudiciary -->|pronounce_judgment_verdict| P_BAIL_TRIAL
    P_BAIL_TRIAL -->|update_status_judgment_terminal| D_CASES
    P_BAIL_TRIAL -->|emit_fsm_and_judgment_audit| D_AUDIT

    %% Audit & NCRB
    UserAuditor -->|inspect_ai_parser_decisions| P_AUDIT_NCRB
    D_REDIS -->|check_sliding_window_20_per_min| P_AUDIT_NCRB
    P_AUDIT_NCRB -->|write_on_read_meta_audit_row| D_AUDIT
    P_AUDIT_NCRB -->|verify_monotonic_seq_hash_chain| D_AUDIT
    D_AUDIT -->|clean_chain_integrity_status| P_AUDIT_NCRB
    UserAuditor -->|get_deidentified_crime_metadata| P_AUDIT_NCRB
    D_CASES -->|project_non_pii_columns_only| P_AUDIT_NCRB
    P_AUDIT_NCRB -->|anonymized_statistical_records| UserAuditor
```

---

## 3. Level 2 Detailed Decompositions (Subsystem-by-Subsystem)

---

### 3.1 DFD 2.1 — Authentication, Multi-Tenant RBAC & Role Management (`/auth`, `/admin/roles`)
* **Key Files:** [`api/app/routers/auth.py`](file:///Users/kamalnasir/Desktop/SIH2026/LegaDoc/api/app/routers/auth.py), [`api/app/security.py`](file:///Users/kamalnasir/Desktop/SIH2026/LegaDoc/api/app/security.py), [`api/app/routers/admin.py`](file:///Users/kamalnasir/Desktop/SIH2026/LegaDoc/api/app/routers/admin.py), [`api/app/models.py`](file:///Users/kamalnasir/Desktop/SIH2026/LegaDoc/api/app/models.py)

```mermaid
flowchart TB
    ClientUser["👤 User (Any Role)"]
    AdminUser["👤 Config Admin"]

    P_LOGIN(["2.1.1 POST /auth/login<br/>Constant-time dummy bcrypt check"])
    P_REFRESH(["2.1.2 POST /auth/refresh<br/>Exchange refresh token for access token"])
    P_ME(["2.1.3 GET /auth/me<br/>Authoritative identity and permission profile"])
    P_ROLE_MANAGE(["2.1.4 GET/POST /admin/roles<br/>Role definitions and custom role provisioning"])
    P_ROLE_ASSIGN(["2.1.5 POST /admin/users/:id/role<br/>Assign role to government officer"])

    T_USERS[("users<br/>email, hashed_password, role, org_id")]
    T_ROLES[("roles & role_permissions<br/>code, name, is_system, permissions")]
    T_ORGS[("organizations<br/>id, name, org_type")]
    T_AUDIT[("audit_logs<br/>seq, action, actor_user_id, row_hash")]

    ClientUser -->|login_credentials| P_LOGIN
    P_LOGIN -->|query_user_by_email| T_USERS
    P_LOGIN -->|run_constant_time_dummy_if_not_found| P_LOGIN
    P_LOGIN -->|return_15m_access_and_7d_refresh_jwt| ClientUser

    ClientUser -->|refresh_token_jwt| P_REFRESH
    P_REFRESH -->|verify_expected_type_refresh| P_REFRESH
    P_REFRESH -->|issue_new_access_token| ClientUser

    ClientUser -->|bearer_access_jwt| P_ME
    P_ME -->|fetch_user_and_permissions| T_USERS
    T_USERS -->|joined_profile_and_permissions| P_ME
    P_ME -->|return_authoritative_user_summary| ClientUser

    AdminUser -->|create_custom_role_payload| P_ROLE_MANAGE
    P_ROLE_MANAGE -->|verify_config_admin_role| P_ROLE_MANAGE
    P_ROLE_MANAGE -->|insert_custom_role_record| T_ROLES
    P_ROLE_MANAGE -->|write_audit_log role_created| T_AUDIT

    AdminUser -->|assign_user_role_payload| P_ROLE_ASSIGN
    P_ROLE_ASSIGN -->|verify_config_admin_role| P_ROLE_ASSIGN
    P_ROLE_ASSIGN -->|update_user_role| T_USERS
    P_ROLE_ASSIGN -->|write_audit_log role_assigned| T_AUDIT
```

---

### 3.2 DFD 2.2 — Case Intake, Assignment & Mid-Case IO Handover (`/cases`)
* **Key Files:** [`api/app/routers/cases.py`](file:///Users/kamalnasir/Desktop/SIH2026/LegaDoc/api/app/routers/cases.py), [`api/app/models.py`](file:///Users/kamalnasir/Desktop/SIH2026/LegaDoc/api/app/models.py), [`api/app/security.py`](file:///Users/kamalnasir/Desktop/SIH2026/LegaDoc/api/app/security.py), [`api/app/audit.py`](file:///Users/kamalnasir/Desktop/SIH2026/LegaDoc/api/app/audit.py)

```mermaid
flowchart TB
    DutyOfficer["👤 Duty Officer"]
    SHO["👤 Station House Officer (SHO)"]
    IO["👤 Investigating Officer (IO)"]
    RestrictedUser["👤 Unassigned IO / Specialist"]

    P_REGISTER(["2.2.1 POST /cases<br/>Register FIR and initiate docket"])
    P_ASSIGN(["2.2.2 POST /cases/:id/assign-io<br/>Initial IO assignment"])
    P_REASSIGN(["2.2.3 POST /cases/:id/reassign-io<br/>Mid-case IO handover and atomic swap"])
    P_DIARY_ADD(["2.2.4 POST /cases/:id/case-diary<br/>Append Section 172 diary note"])
    P_DIARY_LIST(["2.2.5 GET /cases/:id/case-diary<br/>Read investigation diary timeline"])
    P_CASE_GET(["2.2.6 GET /cases/:id<br/>Case summary and linked resource docket"])

    T_CASES[("cases<br/>id, case_number, crime_type, status")]
    T_ASSIGN[("case_assignments<br/>case_id, io_user_id, assigned_at")]
    T_DIARY[("case_diary_entries<br/>id, case_id, author_user_id, entry_text")]
    T_AUDIT[("audit_logs<br/>action: fir_registered, io_reassigned")]

    DutyOfficer -->|fir_registration_payload| P_REGISTER
    P_REGISTER -->|insert_case_record| T_CASES
    P_REGISTER -->|write_audit_log fir_registered| T_AUDIT
    P_REGISTER -->|return_case_summary| DutyOfficer

    SHO -->|assign_io_payload| P_ASSIGN
    P_ASSIGN -->|insert_case_assignment| T_ASSIGN
    P_ASSIGN -->|write_audit_log io_assigned| T_AUDIT
    P_ASSIGN -->|return_assignment_confirmed| SHO

    SHO -->|reassign_io_payload_with_reason| P_REASSIGN
    P_REASSIGN -->|verify_preconditions_uuid_and_active_io| T_ASSIGN
    P_REASSIGN -->|verify_case_not_in_judgment| T_CASES
    P_REASSIGN -->|atomic_delete_old_assignment| T_ASSIGN
    P_REASSIGN -->|atomic_insert_new_assignment| T_ASSIGN
    P_REASSIGN -->|write_audit_log io_reassigned_with_ids_and_reason| T_AUDIT
    P_REASSIGN -->|return_reassign_summary| SHO

    IO -->|append_diary_note_payload| P_DIARY_ADD
    P_DIARY_ADD -->|verify_assigned_io_or_sho| T_ASSIGN
    P_DIARY_ADD -->|insert_append_only_diary_row| T_DIARY
    P_DIARY_ADD -->|write_audit_log case_diary_appended_zero_pii| T_AUDIT

    RestrictedUser -->|read_case_or_diary_request| P_CASE_GET
    P_CASE_GET -->|assert_case_access_check_assignment| T_ASSIGN
    P_CASE_GET -->|reject_with_403_if_unassigned| RestrictedUser
    P_CASE_GET -->|return_case_summary_if_permitted| IO
```

---

### 3.3 DFD 2.3 — Document Ingestion, Native MIME Sniffing & Storage (`/documents` Upload)
* **Key Files:** [`api/app/routers/documents.py`](file:///Users/kamalnasir/Desktop/SIH2026/LegaDoc/api/app/routers/documents.py), [`api/app/upload_validator.py`](file:///Users/kamalnasir/Desktop/SIH2026/LegaDoc/api/app/upload_validator.py), [`api/app/storage.py`](file:///Users/kamalnasir/Desktop/SIH2026/LegaDoc/api/app/storage.py), [`api/app/queue.py`](file:///Users/kamalnasir/Desktop/SIH2026/LegaDoc/api/app/queue.py)

```mermaid
flowchart TB
    Officer["👤 Permitted Officer / Authority"]

    P_SNIFF(["2.3.1 Stream Sniff & Deduplicate<br/>8KB chunk, native magic bytes, SHA-256"])
    P_STORAGE_PUT(["2.3.2 Write to Object Storage<br/>MinIO S3 bucket, SSE-S3 AES-256"])
    P_META_INSERT(["2.3.3 Insert Document Record<br/>status: processing, chain: pending"])
    P_DISPATCH(["2.3.4 Enqueue Dual Celery Tracks<br/>Track A: Chain Worker, Track B: OCR Worker"])

    T_CASES[("cases<br/>target case verification")]
    T_DOCS[("documents<br/>id, case_id, doc_type, version, doc_hash")]
    D_MINIO[("MinIO S3 Bucket<br/>legadoc-documents/{org}/{case}/{doc}/v{ver}")]
    D_REDIS_QUEUE[("Redis Celery Queue<br/>ocr_worker, chain_worker")]
    T_AUDIT[("audit_logs<br/>action: document_uploaded")]

    Officer -->|multipart_file_and_case_id| P_SNIFF
    P_SNIFF -->|verify_caller_case_access| T_CASES
    P_SNIFF -->|calculate_sha256_digest| P_SNIFF
    P_SNIFF -->|check_existing_hash_for_deduplication| T_DOCS
    P_SNIFF -->|reject_if_disguised_executable_415| Officer
    P_SNIFF -->|reject_if_exceeds_50mb_413| Officer

    P_SNIFF -->|verified_binary_stream| P_STORAGE_PUT
    P_STORAGE_PUT -->|put_object_with_encryption| D_MINIO

    P_STORAGE_PUT -->|storage_path_and_hash| P_META_INSERT
    P_META_INSERT -->|insert_document_row_v1| T_DOCS
    P_META_INSERT -->|write_audit_log document_uploaded| T_AUDIT

    P_META_INSERT -->|doc_id_and_idempotency_key| P_DISPATCH
    P_DISPATCH -->|enqueue chain_worker.write_hash| D_REDIS_QUEUE
    P_DISPATCH -->|enqueue ocr_worker.extract_document| D_REDIS_QUEUE
    P_DISPATCH -->|return_202_accepted_with_processing_status| Officer
```

---

### 3.4 DFD 2.4 — Dual-Track Processing, Review Queue & Redaction Engine (`workers/*`, `/documents`)
* **Key Files:** [`workers/ocr_worker/worker.py`](file:///Users/kamalnasir/Desktop/SIH2026/LegaDoc/workers/ocr_worker/worker.py), [`workers/ai_parser_worker/worker.py`](file:///Users/kamalnasir/Desktop/SIH2026/LegaDoc/workers/ai_parser_worker/worker.py), [`workers/chain_worker/worker.py`](file:///Users/kamalnasir/Desktop/SIH2026/LegaDoc/workers/chain_worker/worker.py), [`api/app/redaction.py`](file:///Users/kamalnasir/Desktop/SIH2026/LegaDoc/api/app/redaction.py), [`api/app/routers/documents.py`](file:///Users/kamalnasir/Desktop/SIH2026/LegaDoc/api/app/routers/documents.py)

```mermaid
flowchart TB
    RedisQueue["⚡ Redis / Celery Task Broker"]
    FabricNetwork["⛓️ Hyperledger Fabric Network"]
    IOUser["👤 Investigating Officer (IO)"]
    AdminUser["👤 Config Admin"]
    ReaderUser["👤 Reading Role (Specialist / Court)"]

    P_CHAIN_EXEC(["2.4.1 Chain Worker: process_hash_write<br/>Idempotent Fabric anchor & status update"])
    P_OCR_EXEC(["2.4.2 OCR Worker: extract_document<br/>Fetch S3 blob, run PaddleOCR, store raw_text"])
    P_AI_EXEC(["2.4.3 AI Parser: tag_document<br/>Presidio NER, tag spans, check 70% threshold"])
    P_REVIEW_QUEUE(["2.4.4 GET /documents?status=needs_review<br/>Scoped queue, structural PII exclusion"])
    P_HUMAN_CORRECT(["2.4.5 POST /documents/:id/redact-tag<br/>Officer manual override, extend hash chain"])
    P_READ_VIEW(["2.4.6 GET /documents/:id<br/>app/redaction.py dynamic span masking"])

    D_MINIO[("MinIO S3 Storage<br/>raw document file")]
    T_DOCS[("documents<br/>status, chain_status, raw_text")]
    T_TAGS[("document_sensitivity_tags<br/>entity_type, span_start, span_end, confidence")]
    T_AUDIT[("audit_logs<br/>auto_tag_completed, redact_tag_correction")]

    RedisQueue -->|dequeue chain_worker task| P_CHAIN_EXEC
    P_CHAIN_EXEC -->|submit_sha256_hash_transaction| FabricNetwork
    FabricNetwork -->|transaction_confirmed_id| P_CHAIN_EXEC
    P_CHAIN_EXEC -->|update_chain_status_confirmed| T_DOCS
    P_CHAIN_EXEC -->|write_audit_log chain_write_confirmed| T_AUDIT

    RedisQueue -->|dequeue ocr_worker task| P_OCR_EXEC
    P_OCR_EXEC -->|read_raw_bytes| D_MINIO
    P_OCR_EXEC -->|execute_ocr_and_store_text| T_DOCS
    P_OCR_EXEC -->|enqueue ai_parser_worker task| RedisQueue

    RedisQueue -->|dequeue ai_parser_worker task| P_AI_EXEC
    T_DOCS -->|read_raw_text| P_AI_EXEC
    P_AI_EXEC -->|write_detected_entity_tags| T_TAGS
    P_AI_EXEC -->|write_audit_log auto_tag_completed| T_AUDIT
    P_AI_EXEC -->|if_confidence_below_70_set_status_needs_review| T_DOCS
    P_AI_EXEC -->|if_confident_set_status_ready| T_DOCS

    IOUser -->|request_review_queue| P_REVIEW_QUEUE
    AdminUser -->|request_global_review_queue| P_REVIEW_QUEUE
    P_REVIEW_QUEUE -->|query_documents_status_needs_review| T_DOCS
    P_REVIEW_QUEUE -->|exclude_raw_text_and_storage_keys| P_REVIEW_QUEUE
    P_REVIEW_QUEUE -->|return_document_review_item_list| IOUser

    IOUser -->|submit_human_correction_tag| P_HUMAN_CORRECT
    P_HUMAN_CORRECT -->|insert_tag_source_human_correction| T_TAGS
    P_HUMAN_CORRECT -->|update_document_status_ready| T_DOCS
    P_HUMAN_CORRECT -->|write_audit_log redact_tag_correction| T_AUDIT

    ReaderUser -->|fetch_document_content| P_READ_VIEW
    P_READ_VIEW -->|verify_case_access| T_DOCS
    P_READ_VIEW -->|fetch_sensitivity_tags| T_TAGS
    P_READ_VIEW -->|if_full_access_role_return_unredacted| ReaderUser
    P_READ_VIEW -->|if_restricted_role_return_masked_spans| ReaderUser
```

---

### 3.5 DFD 2.5 — Section 91 Requisitions & Charge Sheet AND-Join Gate (`/evidence-requests`, `/cases`)
* **Key Files:** [`api/app/routers/evidence_requests.py`](file:///Users/kamalnasir/Desktop/SIH2026/LegaDoc/api/app/routers/evidence_requests.py), [`api/app/security.py`](file:///Users/kamalnasir/Desktop/SIH2026/LegaDoc/api/app/security.py), [`api/app/audit.py`](file:///Users/kamalnasir/Desktop/SIH2026/LegaDoc/api/app/audit.py), [`api/app/models.py`](file:///Users/kamalnasir/Desktop/SIH2026/LegaDoc/api/app/models.py)

```mermaid
flowchart TB
    IOUser["👤 Investigating Officer (IO)"]
    AuthorityStaff["🏛️ External Authority Staff"]
    Intruder["👤 Unauthorized Role (Defense / Civilian)"]
    Prosecutor["⚖️ Public Prosecutor"]

    P_REQ_CREATE(["2.5.1 POST /cases/:id/evidence-requests<br/>Dispatch requisition to FSL, Hospital, Bank"])
    P_REQ_LIST(["2.5.2 GET /cases/:id/evidence-requests<br/>Multi-tenant scoped listing"])
    P_REQ_SUBMIT(["2.5.3 POST /evidence-requests/:id/submit<br/>Default-deny gate & single-fulfillment upload"])
    P_CHARGE_SHEET(["2.5.4 POST /cases/:id/file-charge-sheet<br/>Section 173 AND-Join checklist evaluation"])

    T_CASES[("cases<br/>investigation_status, crime_type")]
    T_REQ[("evidence_requests<br/>case_id, requested_org_id, status")]
    T_STAGE_REQ[("stage_requirements<br/>crime_type, stage, required_type")]
    T_DOCS[("documents<br/>verified evidence uploads")]
    T_AUDIT[("audit_logs<br/>evidence_requested, charge_sheet_filed")]

    IOUser -->|create_requisition_payload| P_REQ_CREATE
    P_REQ_CREATE -->|verify_assigned_io| P_REQ_CREATE
    P_REQ_CREATE -->|insert_evidence_request_status_pending| T_REQ
    P_REQ_CREATE -->|write_audit_log evidence_requested| T_AUDIT
    P_REQ_CREATE -->|return_201_created_requisition| IOUser

    AuthorityStaff -->|list_requests_query| P_REQ_LIST
    P_REQ_LIST -->|filter_by_requested_org_id| T_REQ
    P_REQ_LIST -->|return_org_scoped_requests| AuthorityStaff

    Intruder -->|attempt_evidence_submission| P_REQ_SUBMIT
    P_REQ_SUBMIT -->|verify_evidence_request_org_access| P_REQ_SUBMIT
    P_REQ_SUBMIT -->|reject_with_403_forbidden_default_deny| Intruder

    AuthorityStaff -->|submit_certified_evidence_multipart| P_REQ_SUBMIT
    P_REQ_SUBMIT -->|verify_request_is_not_already_completed| T_REQ
    P_REQ_SUBMIT -->|insert_evidence_document| T_DOCS
    P_REQ_SUBMIT -->|update_request_status_completed| T_REQ
    P_REQ_SUBMIT -->|write_audit_log evidence_request_fulfilled| T_AUDIT
    P_REQ_SUBMIT -->|return_200_ok_completed| AuthorityStaff

    Prosecutor -->|file_charge_sheet_attempt| P_CHARGE_SHEET
    P_CHARGE_SHEET -->|fetch_mandatory_checklist_for_crime| T_STAGE_REQ
    P_CHARGE_SHEET -->|verify_all_required_docs_uploaded| T_DOCS
    P_CHARGE_SHEET -->|verify_all_required_evidence_completed| T_REQ
    P_CHARGE_SHEET -->|reject_with_409_if_any_item_missing| Prosecutor
    P_CHARGE_SHEET -->|update_status_charge_sheet_filed| T_CASES
    P_CHARGE_SHEET -->|write_audit_log charge_sheet_filed| T_AUDIT
    P_CHARGE_SHEET -->|return_200_ok_transition_successful| Prosecutor
```

---

### 3.6 DFD 2.6 — Decoupled Bail FSM & Judicial Trial Disposition (`/bail`, `/trial`)
* **Key Files:** [`api/app/routers/bail.py`](file:///Users/kamalnasir/Desktop/SIH2026/LegaDoc/api/app/routers/bail.py), [`api/app/routers/trial.py`](file:///Users/kamalnasir/Desktop/SIH2026/LegaDoc/api/app/routers/trial.py), [`api/app/models.py`](file:///Users/kamalnasir/Desktop/SIH2026/LegaDoc/api/app/models.py), [`api/app/audit.py`](file:///Users/kamalnasir/Desktop/SIH2026/LegaDoc/api/app/audit.py)

```mermaid
flowchart TB
    IOUser["👤 Investigating Officer (IO)"]
    DefenseUser["🛡️ Defense Counsel (Submission-Only)"]
    CourtUser["⚖️ Judiciary / Judge"]
    AccusedUser["👤 Accused / Surety"]

    P_ARREST(["2.6.1 POST /cases/:id/bail/arrest<br/>Record suspect arrest and start bail FSM"])
    P_BAIL_APP(["2.6.2 POST /cases/:id/bail/application<br/>File Section 437/439 CrPC bail petition"])
    P_BAIL_HEARING(["2.6.3 POST /cases/:id/bail/hearing-notice<br/>Court schedule bail hearing"])
    P_BAIL_ORDER(["2.6.4 POST /cases/:id/bail/order<br/>Pronounce bail grant or final denial"])
    P_BAIL_SURETY(["2.6.5 POST /cases/:id/bail/surety<br/>Register monetary/property surety bond"])
    P_TRIAL_NOTICE(["2.6.6 POST /cases/:id/trial/hearing-notice<br/>Transition to Trial (Charge Sheet prerequisite)"])
    P_JUDGMENT(["2.6.7 POST /cases/:id/judgment<br/>Record final verdict: convicted or acquitted"])

    T_CASES[("cases<br/>investigation_status, bail_status")]
    T_AUDIT[("audit_logs<br/>action: bail_*, trial_*, judgment_pronounced")]

    IOUser -->|arrest_record_payload| P_ARREST
    P_ARREST -->|transition_bail_status_arrested| T_CASES
    P_ARREST -->|write_audit_log bail_arrest_recorded| T_AUDIT

    DefenseUser -->|bail_petition_payload| P_BAIL_APP
    P_BAIL_APP -->|verify_status_is_arrested_400_if_not| T_CASES
    P_BAIL_APP -->|transition_bail_status_application_filed| T_CASES
    P_BAIL_APP -->|write_audit_log bail_application_filed| T_AUDIT

    CourtUser -->|hearing_schedule_payload| P_BAIL_HEARING
    P_BAIL_HEARING -->|transition_bail_status_hearing_scheduled| T_CASES
    P_BAIL_HEARING -->|write_audit_log bail_hearing_scheduled| T_AUDIT

    CourtUser -->|bail_decision_payload| P_BAIL_ORDER
    P_BAIL_ORDER -->|if_granted_transition_order_issued| T_CASES
    P_BAIL_ORDER -->|if_denied_transition_denied_final| T_CASES
    P_BAIL_ORDER -->|write_audit_log bail_order_issued| T_AUDIT

    AccusedUser -->|surety_bond_payload| P_BAIL_SURETY
    P_BAIL_SURETY -->|verify_status_is_order_issued| T_CASES
    P_BAIL_SURETY -->|transition_bail_status_surety_registered| T_CASES
    P_BAIL_SURETY -->|write_audit_log bail_surety_registered| T_AUDIT

    CourtUser -->|trial_hearing_payload| P_TRIAL_NOTICE
    P_TRIAL_NOTICE -->|verify_case_status_is_charge_sheet_filed| T_CASES
    P_TRIAL_NOTICE -->|transition_investigation_status_trial| T_CASES
    P_TRIAL_NOTICE -->|write_audit_log trial_hearing_scheduled| T_AUDIT

    CourtUser -->|verdict_payload_acquitted_or_convicted| P_JUDGMENT
    P_JUDGMENT -->|transition_investigation_status_judgment| T_CASES
    P_JUDGMENT -->|transition_bail_status_disposed| T_CASES
    P_JUDGMENT -->|write_audit_log judgment_pronounced| T_AUDIT
```

---

### 3.7 DFD 2.7 — Tamper-Evident Audit Trail & NCRB Crime Reporting (`/audit-log`, `/reports`)
* **Key Files:** [`api/app/audit.py`](file:///Users/kamalnasir/Desktop/SIH2026/LegaDoc/api/app/audit.py), [`api/app/routers/audit.py`](file:///Users/kamalnasir/Desktop/SIH2026/LegaDoc/api/app/routers/audit.py), [`api/app/routers/reports.py`](file:///Users/kamalnasir/Desktop/SIH2026/LegaDoc/api/app/routers/reports.py), [`api/app/rate_limit.py`](file:///Users/kamalnasir/Desktop/SIH2026/LegaDoc/api/app/rate_limit.py)

```mermaid
flowchart TB
    Auditor["👤 Security Auditor"]
    ConfigAdmin["👤 Config Admin"]
    IOUser["👤 Investigating Officer (IO)"]
    NCRBAnalyst["📊 NCRB Analyst"]
    Intruder["👤 Unauthorized Role"]

    P_AUDIT_WRITE(["2.7.1 write_audit_log<br/>pg_advisory_xact_lock & monotonic seq increment"])
    P_AUDIT_AI(["2.7.2 GET /cases/:id/audit-log/ai-parser<br/>Rate-limited 20/min, atomic write-on-read"])
    P_AUDIT_CASE(["2.7.3 GET /cases/:id/audit-log<br/>Role-filtered envelopes: Full vs Summary"])
    P_INTEGRITY(["2.7.4 GET /cases/:id/audit-log/chain-integrity<br/>Full cryptographic chain scan ordered by seq"])
    P_NCRB_REPORT(["2.7.5 GET /reports/case-metadata<br/>De-identified crime analytics, zero PII"])

    T_AUDIT[("audit_logs<br/>id, seq, case_id, actor_user_id, action, prev_hash, row_hash")]
    T_CASES[("cases<br/>case_number, crime_type, court_level, status")]
    D_RATE_LIMIT[("Rate Limiter State<br/>sliding-window request timestamps")]

    P_AUDIT_WRITE -->|acquire_pg_advisory_lock_267190| P_AUDIT_WRITE
    P_AUDIT_WRITE -->|read_last_row_by_seq_desc| T_AUDIT
    P_AUDIT_WRITE -->|assign_monotonic_seq_and_sha256_hash| P_AUDIT_WRITE
    P_AUDIT_WRITE -->|insert_immutable_audit_row| T_AUDIT

    Auditor -->|inspect_ai_parser_log_request| P_AUDIT_AI
    P_AUDIT_AI -->|check_sliding_window_limit| D_RATE_LIMIT
    P_AUDIT_AI -->|reject_if_exceeds_20_per_min_429| Auditor
    P_AUDIT_AI -->|atomic_insert_read_ai_parser_audit_row| T_AUDIT
    P_AUDIT_AI -->|return_tag_decisions_and_spans_zero_pii| Auditor

    ConfigAdmin -->|attempt_ai_parser_read| P_AUDIT_AI
    P_AUDIT_AI -->|reject_config_admin_with_403_separation_of_duties| ConfigAdmin

    IOUser -->|read_case_audit_log_request| P_AUDIT_CASE
    P_AUDIT_CASE -->|filter_to_operational_summary_envelope| IOUser

    ConfigAdmin -->|run_chain_integrity_verification| P_INTEGRITY
    P_INTEGRITY -->|read_all_rows_ordered_by_seq_asc| T_AUDIT
    P_INTEGRITY -->|recompute_sha256_hash_and_prev_hash_matches| P_INTEGRITY
    P_INTEGRITY -->|return_chain_intact_true_and_entry_count| ConfigAdmin

    Intruder -->|attempt_ncrb_report_access| P_NCRB_REPORT
    P_NCRB_REPORT -->|reject_unauthorized_with_403| Intruder

    NCRBAnalyst -->|filtered_case_metadata_request| P_NCRB_REPORT
    P_NCRB_REPORT -->|project_only_non_pii_columns| T_CASES
    P_NCRB_REPORT -->|write_audit_log ncrb_report_generated| T_AUDIT
    P_NCRB_REPORT -->|return_deidentified_case_metadata_list| NCRBAnalyst
```

---

## 4. State Ownership & Invariant Matrix

| Domain / Resource | Master Table | Authorization Model | Immutability Invariant | Tamper-Evident Proof |
|:---|:---|:---|:---|:---|
| **Identity & Sessions** | `users`, `organizations` | `require_role()`, constant-time bcrypt | Password updates mutate hash; email immutable | Session JWT signatures (HMAC-SHA256) |
| **Case Dockets** | `cases` | `assert_case_access()` | Mutable status (`investigation_status`, `bail_status`) | Tracked in `AuditLog.case_id` |
| **Case Assignment** | `case_assignments` | Only `sho` and `config_admin` | Exactly one active IO per case. Atomic deletion & insertion | `AuditLog(action='io_reassigned')` |
| **Investigation Diary**| `case_diary_entries` | Strictly assigned IO and SHO | **Append-Only** (no updates, no deletions) | Embedded in sequential audit hash chain |
| **Evidence Requisition**| `evidence_requests` | IO (create), Requested Org (fulfill) | Single-fulfillment guard (`completed` $\to$ 409) | `AuditLog(action='evidence_request_fulfilled')` |
| **Evidence Files** | `documents` | Role-filtered via `app/redaction.py` | **Append-Only** versions (`v1, v2, ...`). Storage immutable | SHA-256 in MinIO + Fabric Blockchain (`chain_tx_id`) |
| **Sensitivity Tags** | `document_sensitivity_tags` | Internal AI Parser + IO Corrections | Append-only. Raw text NEVER stored in tags | `AuditLog(action='auto_tag_completed')` |
| **Bail Lifecycle** | `cases.bail_status` | Role-gated state transitions | Strict 5-state sequential Finite State Machine | `AuditLog(action='bail_*')` |
| **Trial Progression** | `cases.investigation_status` | Gated by `Charge_Sheet_Filed` (Court only) | Sequential forward progression (`Trial` $\to$ `Judgment`) | `AuditLog(action='trial_*' \| 'judgment_pronounced')` |
| **Audit Trail** | `audit_logs` | Auditor/Admin (Full), Operational (Summary) | **Strictly Immutable & Append-Only** | Linked SHA-256 hash chain ordered by monotonic `seq` |

---

## 5. Interface & Verification Contract (110 Tests Green)

| Subsystem | Primary Endpoints | Roles Authorized | Test File | Test Count |
|:---|:---|:---|:---|:---:|
| **Auth & RBAC** | `POST /auth/login`<br/>`POST /auth/refresh`<br/>`GET /auth/me` | Public (Rate Limited)<br/>Any Authenticated | [`test_auth.py`](file:///Users/kamalnasir/Desktop/SIH2026/LegaDoc/api/tests/test_auth.py)<br/>[`test_rbac_admin.py`](file:///Users/kamalnasir/Desktop/SIH2026/LegaDoc/api/tests/test_rbac_admin.py) | 19 |
| **Case & Assignment** | `POST /cases`<br/>`POST /cases/:id/assign-io`<br/>`POST /cases/:id/reassign-io`<br/>`POST /cases/:id/case-diary` | `duty_officer`<br/>`sho`<br/>`sho`, `config_admin`<br/>Assigned `io` | [`test_cases.py`](file:///Users/kamalnasir/Desktop/SIH2026/LegaDoc/api/tests/test_cases.py) | 23 |
| **Ingestion & Storage** | `POST /documents`<br/>`GET /documents/:id`<br/>`GET /documents/:id/versions`<br/>`POST /documents/:id/retry-chain-write` | Case-Permitted Roles<br/>Role-Scoped Redaction<br/>`config_admin` | [`test_documents.py`](file:///Users/kamalnasir/Desktop/SIH2026/LegaDoc/api/tests/test_documents.py)<br/>[`test_chain_worker.py`](file:///Users/kamalnasir/Desktop/SIH2026/LegaDoc/api/tests/test_chain_worker.py) | 29 |
| **Review & Redaction** | `GET /documents?status=needs_review`<br/>`POST /documents/:id/redact-tag` | `config_admin`, Assigned `io`<br/>Assigned `io` | [`test_documents.py`](file:///Users/kamalnasir/Desktop/SIH2026/LegaDoc/api/tests/test_documents.py) | (Included above) |
| **Evidence & Gate** | `POST /cases/:id/evidence-requests`<br/>`POST /evidence-requests/:id/submit`<br/>`POST /cases/:id/file-charge-sheet` | Assigned `io`<br/>Matching `authority_staff`<br/>`prosecutor` | [`test_evidence_requests.py`](file:///Users/kamalnasir/Desktop/SIH2026/LegaDoc/api/tests/test_evidence_requests.py) | 6 |
| **Bail FSM & Trial** | `POST /cases/:id/bail/*` (5 states)<br/>`POST /cases/:id/trial/hearing-notice`<br/>`POST /cases/:id/judgment` | `io`, `defense`, `court`, `accused`<br/>`court`<br/>`court` | [`test_bail.py`](file:///Users/kamalnasir/Desktop/SIH2026/LegaDoc/api/tests/test_bail.py)<br/>[`test_trial.py`](file:///Users/kamalnasir/Desktop/SIH2026/LegaDoc/api/tests/test_trial.py) | 6 |
| **Audit & Integrity** | `GET /cases/:id/audit-log`<br/>`GET /cases/:id/audit-log/ai-parser`<br/>`GET /cases/:id/audit-log/chain-integrity` | Role-Filtered<br/>`security_auditor` ONLY<br/>`config_admin` | [`test_audit.py`](file:///Users/kamalnasir/Desktop/SIH2026/LegaDoc/api/tests/test_audit.py)<br/>[`test_audit_chain_ordering.py`](file:///Users/kamalnasir/Desktop/SIH2026/LegaDoc/api/tests/test_audit_chain_ordering.py) | 20 |
| **Domain 7 (NCRB)** | `GET /reports/case-metadata` | `records_ncrb_analyst` | [`test_reports.py`](file:///Users/kamalnasir/Desktop/SIH2026/LegaDoc/api/tests/test_reports.py) | 7 |
| **TOTAL** | **All 33 Active Endpoints Verified** | **All Roles & Default-Deny Covered** | **Entire Test Suite in Docker** | **110 PASSED (100%)** |
