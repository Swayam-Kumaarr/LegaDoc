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
    Column, String, Integer, Boolean, ForeignKey, DateTime, Text, JSON, Enum, func
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.database import Base


def uuid_pk():
    return Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


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
    org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    # duty_officer | sho | io | women_cell | cyber_cell | narcotics_police | traffic_police |
    # crime_scene_unit | rescue_team | counselor | authority_staff | prosecutor | court |
    # defense | admin | records_ncrb_analyst  — see SYSTEM_DESIGN.md Role & Authority Taxonomy
    role = Column(String, nullable=False)
    name = Column(String, nullable=False)
    email = Column(String, unique=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    organization = relationship("Organization", back_populates="users")


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
    case_id = Column(UUID(as_uuid=True), ForeignKey("cases.id"), nullable=False)
    io_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    assigned_at = Column(DateTime(timezone=True), server_default=func.now())


class Document(Base):
    __tablename__ = "documents"
    id = uuid_pk()
    case_id = Column(UUID(as_uuid=True), ForeignKey("cases.id"), nullable=False)
    doc_type = Column(String, nullable=False)  # one of the 57 canonical types
    version = Column(Integer, nullable=False, default=1)  # append-only — never overwritten
    storage_path = Column(String, nullable=False)  # MinIO object key
    doc_hash = Column(String, nullable=True)  # set once computed, before Chain Worker signs it
    status = Column(String, nullable=False, default="processing")  # processing | ready | needs_review
    chain_status = Column(String, nullable=False, default="pending")  # pending | confirmed | failed
    uploaded_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    original_filename = Column(String, nullable=True)  # Original upload filename for display
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class DocumentExtraction(Base):
    """Stores OCR-extracted text for a specific document version.
    Created by the upload pipeline (empty); filled by the OCR Worker.
    Read by the AI Parser Worker for sensitivity tagging.
    Never stores redacted text — only the raw extraction."""
    __tablename__ = "document_extractions"
    id = uuid_pk()
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id"), nullable=False)
    version = Column(Integer, nullable=False)
    raw_text = Column(Text, nullable=True)  # Filled by OCR Worker
    extraction_status = Column(String, nullable=False, default="pending")  # pending | completed | failed
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class DocumentSensitivityTag(Base):
    """AI Parser auto-tags (or an officer's redact-tag correction) — never the raw redacted text."""
    __tablename__ = "document_sensitivity_tags"
    id = uuid_pk()
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id"), nullable=False)
    entity_type = Column(String, nullable=False)  # e.g. PERSON, PHONE_NUMBER, MEDICAL_CONDITION
    span_start = Column(Integer, nullable=False)
    span_end = Column(Integer, nullable=False)
    confidence = Column(Integer, nullable=True)  # 0-100, null for a human correction
    source = Column(String, nullable=False, default="ai_parser")  # ai_parser | officer_correction
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class EvidenceRequest(Base):
    __tablename__ = "evidence_requests"
    id = uuid_pk()
    case_id = Column(UUID(as_uuid=True), ForeignKey("cases.id"), nullable=False)
    requested_org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    doc_type_expected = Column(String, nullable=True)
    status = Column(String, nullable=False, default="requested")  # requested | completed
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)


class BailRecord(Base):
    __tablename__ = "bail_records"
    id = uuid_pk()
    case_id = Column(UUID(as_uuid=True), ForeignKey("cases.id"), nullable=False)
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
    case_id = Column(UUID(as_uuid=True), ForeignKey("cases.id"), nullable=False)
    author_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    text = Column(Text, nullable=False)
    status = Column(String, nullable=False, default="processing")  # processing | ready
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class DocumentSchemaConfig(Base):
    """The tiered sensitivity-schema registry. Tier 1/2 types get real field
    definitions; Tier 3 types inherit the one generic default profile."""
    __tablename__ = "document_schemas"
    id = uuid_pk()
    doc_type = Column(String, unique=True, nullable=False)
    tier = Column(Integer, nullable=False)  # 1, 2, or 3
    sensitivity_fields = Column(JSON, nullable=True)  # null for Tier 3 (uses the default profile)


class RecognizerMapping(Base):
    """Maps a Presidio/spaCy entity type to a DocumentSchema's sensitivity field."""
    __tablename__ = "recognizer_mappings"
    id = uuid_pk()
    document_schema_id = Column(UUID(as_uuid=True), ForeignKey("document_schemas.id"), nullable=False)
    entity_type = Column(String, nullable=False)
    field_name = Column(String, nullable=False)


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
    """
    __tablename__ = "audit_log"
    id = uuid_pk()
    case_id = Column(UUID(as_uuid=True), ForeignKey("cases.id"), nullable=True)
    actor_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)  # null = system:ai_parser
    action = Column(String, nullable=False)
    target_type = Column(String, nullable=True)  # e.g. "document", "case", "bail_record"
    target_id = Column(UUID(as_uuid=True), nullable=True)
    action_metadata = Column(JSON, nullable=True)  # never the raw redacted text — see design doc
    prev_hash = Column(String, nullable=True)
    row_hash = Column(String, nullable=False)
    fabric_tx_id = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
