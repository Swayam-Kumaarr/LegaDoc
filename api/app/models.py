"""
SQLAlchemy models — one class per entity in SYSTEM_DESIGN.md's State Ownership Map.
Columns are the minimum each entity needs to exist; add fields as each domain's
work requires them, but don't add a new *entity* without updating the State
Ownership Map and the endpoint table first — that's what keeps this consistent
as multiple people build on it at once.
"""

import enum
import uuid

from sqlalchemy import (
    Column, String, Integer, Boolean, ForeignKey, DateTime, Text, JSON, Enum, func, Table
)
from app.db_types import GUID
from sqlalchemy.orm import relationship

from app.database import Base


def uuid_pk():
    return Column(GUID(), primary_key=True, default=uuid.uuid4)


role_permissions = Table(
    "role_permissions",
    Base.metadata,
    Column("role_id", GUID(), ForeignKey("roles.id"), primary_key=True),
    Column("permission_id", GUID(), ForeignKey("permissions.id"), primary_key=True),
)


class Permission(Base):
    __tablename__ = "permissions"
    id = uuid_pk()
    code = Column(String, unique=True, nullable=False)
    name = Column(String, nullable=False)
    category = Column(String, nullable=False)
    description = Column(String, nullable=True)


class Role(Base):
    __tablename__ = "roles"
    id = uuid_pk()
    code = Column(String, unique=True, nullable=False)
    name = Column(String, nullable=False)
    description = Column(String, nullable=True)
    is_system = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    permissions = relationship("Permission", secondary=role_permissions, backref="roles")
    users = relationship("User", back_populates="role_rel")


class Organization(Base):
    __tablename__ = "organizations"
    id = uuid_pk()
    name = Column(String, nullable=False)
    # police | fsl | digital_fsl | hospital | bank | telecom | rto | court | ncrb | admin
    org_type = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    users = relationship("User", back_populates="organization")


class User(Base):
    __tablename__ = "users"
    id = uuid_pk()
    org_id = Column(GUID(), ForeignKey("organizations.id"), nullable=False)
    role = Column(String, nullable=False)
    role_id = Column(GUID(), ForeignKey("roles.id"), nullable=True)
    service_id = Column(String, nullable=True)  # Government Service ID / Badge ID
    designation = Column(String, nullable=True)  # Official rank / title
    language_preference = Column(String, nullable=False, default="en")
    mfa_enabled = Column(Boolean, nullable=False, default=False)  # required for config_admin/security_auditor/court
    name = Column(String, nullable=False)
    email = Column(String, unique=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    organization = relationship("Organization", back_populates="users")
    role_rel = relationship("Role", back_populates="users")


class ApiKey(Base):
    """A user-bound bearer token for programmatic access (machine-to-machine
    or headless clients acting on a user's behalf). The raw key is shown to
    the creator exactly once; only its SHA-256 hash is ever stored, so a
    leaked database dump doesn't expose usable keys. Revocation is a soft
    delete — revoking sets revoked_at so the key stops working while its
    creation/use remains visible in the audit trail."""
    __tablename__ = "api_keys"
    id = uuid_pk()
    user_id = Column(GUID(), ForeignKey("users.id"), nullable=False)  # the user the key acts as
    name = Column(String, nullable=False)  # human label, e.g. "CCTNS integration"
    key_hash = Column(String, unique=True, nullable=False)  # sha256 of the raw key — never the raw key
    key_prefix = Column(String, nullable=False)  # short display prefix (e.g. "legadoc_a1b2c3"), never enough to reconstruct the key
    created_by_user_id = Column(GUID(), ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    last_used_at = Column(DateTime(timezone=True), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)  # null = never
    revoked_at = Column(DateTime(timezone=True), nullable=True)  # null = active


class Case(Base):
    __tablename__ = "cases"
    id = uuid_pk()
    case_number = Column(String, unique=True, nullable=False)
    crime_type = Column(String, nullable=False)
    court_level = Column(String, nullable=True)  # magistrate | sessions | ndps
    investigation_status = Column(
        String, nullable=False, default="FIR_Registered"
    )  # FIR_Registered -> Evidence_Collection -> Charge_Sheet_Ready -> Charge_Sheet_Filed -> Trial -> Judgment
    bail_status = Column(String, nullable=True)  # independent of investigation_status — see Flow 4
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class CaseAssignment(Base):
    """Current IO for a case. History of reassignment lives in AuditLog, not here."""
    __tablename__ = "case_assignments"
    id = uuid_pk()
    case_id = Column(GUID(), ForeignKey("cases.id"), nullable=False)
    io_user_id = Column(GUID(), ForeignKey("users.id"), nullable=False)
    assigned_at = Column(DateTime(timezone=True), server_default=func.now())


class Document(Base):
    __tablename__ = "documents"
    id = uuid_pk()
    case_id = Column(GUID(), ForeignKey("cases.id"), nullable=False)
    doc_type = Column(String, nullable=False)  # one of the 57 canonical types
    version = Column(Integer, nullable=False, default=1)  # append-only — never overwritten
    storage_path = Column(String, nullable=False)  # MinIO key: {org_id}/{case_id}/{doc_id}/v{version}
    raw_text = Column(Text, nullable=True)  # OCR output — the AI Parser has nothing to tag without this
    ocr_engine = Column(String, nullable=True)  # "paddleocr" | "tesseract_fallback"
    doc_hash = Column(String, nullable=True)  # set once computed, before Chain Worker signs it
    status = Column(String, nullable=False, default="processing")  # processing | ready | needs_review
    chain_status = Column(String, nullable=False, default="pending")  # pending | confirmed | failed
    schema_version = Column(Integer, nullable=False, default=1)  # which DocumentSchema revision tagged this
    retention_legal_hold = Column(Boolean, nullable=False, default=False)  # blocks any future deletion/archival
    uploaded_by = Column(GUID(), ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class DocumentSensitivityTag(Base):
    """AI Parser auto-tags (or an officer's redact-tag correction) — never the raw redacted text."""
    __tablename__ = "document_sensitivity_tags"
    id = uuid_pk()
    document_id = Column(GUID(), ForeignKey("documents.id"), nullable=False)
    entity_type = Column(String, nullable=False)  # e.g. PERSON, PHONE_NUMBER, MEDICAL_CONDITION
    span_start = Column(Integer, nullable=False)
    span_end = Column(Integer, nullable=False)
    # 0-100 (Presidio returns 0.0-1.0 float — convert via int(round(score * 100))
    # before insert, never store the raw float). Null for a human correction.
    # Anything below the confidence threshold (default 70) must be auto-flagged
    # for manual review even when tagging technically "succeeded" — see
    # SYSTEM_DESIGN.md, AI Parser fail-safe rule.
    confidence = Column(Integer, nullable=True)
    source = Column(String, nullable=False, default="ai_parser")  # ai_parser | officer_correction
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class EvidenceRequest(Base):
    __tablename__ = "evidence_requests"
    id = uuid_pk()
    case_id = Column(GUID(), ForeignKey("cases.id"), nullable=False)
    requested_org_id = Column(GUID(), ForeignKey("organizations.id"), nullable=False)
    doc_type_expected = Column(String, nullable=True)
    status = Column(String, nullable=False, default="requested")  # requested | completed
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)


class BailRecord(Base):
    __tablename__ = "bail_records"
    id = uuid_pk()
    case_id = Column(GUID(), ForeignKey("cases.id"), nullable=False)
    # Arrested -> Application_Filed -> Hearing_Scheduled -> Order_Issued -> Surety_Registered
    # terminal alternates: Denied_Final | Absconded
    stage = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class CaseDiaryEntry(Base):
    """Append-only running log — NOT a Document upload. Routed through the AI Parser
    for auto-redaction before being visible beyond the assigned IO/SHO (see
    SYSTEM_DESIGN.md, "Case Diary now routes through the redaction pipeline")."""
    __tablename__ = "case_diary_entries"
    id = uuid_pk()
    case_id = Column(GUID(), ForeignKey("cases.id"), nullable=False)
    author_user_id = Column(GUID(), ForeignKey("users.id"), nullable=False)
    text = Column(Text, nullable=False)
    status = Column(String, nullable=False, default="processing")  # processing | ready
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class DocumentSchemaConfig(Base):
    """The tiered sensitivity-schema registry. Tier 1/2 types get real field
    definitions; Tier 3 types inherit the one generic default profile.

    sensitivity_fields JSON shape:
    [
        {"field_name": "victim_name", "sensitive": true},
        {"field_name": "complaint_text", "sensitive": false}
    ]
    """
    __tablename__ = "document_schemas"
    id = uuid_pk()
    doc_type = Column(String, unique=True, nullable=False)
    tier = Column(Integer, nullable=False)  # 1, 2, or 3
    sensitivity_fields = Column(JSON, nullable=True)  # null for Tier 3 (uses the default profile)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    recognizer_mappings = relationship("RecognizerMapping", back_populates="document_schema", cascade="all, delete-orphan")


class RecognizerMapping(Base):
    """Maps a Presidio/spaCy entity type to a DocumentSchema's sensitivity field."""
    __tablename__ = "recognizer_mappings"
    id = uuid_pk()
    document_schema_id = Column(GUID(), ForeignKey("document_schemas.id"), nullable=False)
    entity_type = Column(String, nullable=False)
    field_name = Column(String, nullable=False)

    document_schema = relationship("DocumentSchemaConfig", back_populates="recognizer_mappings")


class StageRequirement(Base):
    __tablename__ = "stage_requirements"
    id = uuid_pk()
    crime_type = Column(String, nullable=False)
    requirement_type = Column(String, nullable=False)  # "document" | "evidence_request"
    requirement_key = Column(String, nullable=False)  # doc_type or org_type expected
    mandatory = Column(Boolean, nullable=False, default=True)


class AuditLog(Base):
    """Append-only. Every state-changing action, including AI Parser auto-tags,
    human corrections, and reads of the AI-parser audit endpoint (meta-audit —
    same table, action='read_ai_parser_audit', no separate table needed).

    row_hash = hash(prev_row_hash + this row's content) — an internal chain
    independent of Fabric, so deleting/reordering a row is detectable even
    though each individual entry is also separately hash-chained to Fabric.
    See SYSTEM_DESIGN.md, "Audit log integrity — closing a real gap".

    CONCURRENCY WARNING: the API and multiple Celery workers all append to
    this table. Two writers reading the same prev_hash at once and both
    appending forks the chain silently. Every write MUST take
    `pg_advisory_xact_lock(<a fixed key>)` for the duration of the
    read-prev-hash + insert-new-row transaction, serializing all appends
    across every process. This is not optional — an unserialized hash chain
    is a broken tamper-evidence guarantee, not a working one.
    """
    __tablename__ = "audit_log"
    id = uuid_pk()
    case_id = Column(GUID(), ForeignKey("cases.id"), nullable=True)
    actor_user_id = Column(GUID(), ForeignKey("users.id"), nullable=True)  # null = system:ai_parser
    action = Column(String, nullable=False)
    target_type = Column(String, nullable=True)  # e.g. "document", "case", "bail_record"
    target_id = Column(GUID(), nullable=True)
    action_metadata = Column(JSON, nullable=True)  # never the raw redacted text — see design doc
    prev_hash = Column(String, nullable=True)
    row_hash = Column(String, nullable=False)
    # The chain's actual ordering/linking key — see app/audit.py's write_audit_log.
    # NOT created_at: wall-clock time is not guaranteed to differ between two
    # writes issued microseconds apart (proven in practice on this stack —
    # several same-request writes landed with an IDENTICAL timestamp down to
    # the microsecond, which silently broke prev_hash linkage for all but the
    # first of them). seq is assigned as strictly prev.seq + 1 inside the same
    # locked critical section as the hash computation, so it can never tie.
    seq = Column(Integer, nullable=False)
    fabric_tx_id = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
