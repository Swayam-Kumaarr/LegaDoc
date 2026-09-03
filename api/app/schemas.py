"""
Pydantic request/response models. Kept in one file at this baseline size —
split by resource group (matching routers/) once this gets big enough that
one file is actually hard to navigate, not before.
"""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr


# ---------- Auth ----------
class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


class AccessTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


# ---------- Cases ----------
class RegisterFIRRequest(BaseModel):
    crime_type: str
    complaint_text: str


class CaseResponse(BaseModel):
    id: UUID
    case_number: str
    crime_type: str
    court_level: Optional[str] = None
    investigation_status: str
    bail_status: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AssignIORequest(BaseModel):
    io_user_id: UUID


# ---------- Documents ----------
class DocumentUploadResponse(BaseModel):
    id: UUID
    case_id: UUID
    doc_type: str
    version: int
    status: str
    chain_status: str


class DocumentView(BaseModel):
    id: UUID
    case_id: UUID
    doc_type: str
    version: int
    status: str
    chain_status: str
    text: Optional[str] = None  # None while status != "ready"; masked or full depending on role


class DocumentVersionSummary(BaseModel):
    id: UUID
    version: int
    status: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ChainStatusResponse(BaseModel):
    document_id: UUID
    chain_status: str


class RedactTagRequest(BaseModel):
    entity_type: str
    span_start: int
    span_end: int


# ---------- Case Diary ----------
class CaseDiaryEntryCreate(BaseModel):
    text: str


class CaseDiaryEntryResponse(BaseModel):
    id: UUID
    case_id: UUID
    author_user_id: UUID
    text: str
    status: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ---------- Bail ----------
class BailRecordResponse(BaseModel):
    id: UUID
    case_id: UUID
    stage: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class BailOrderRequest(BaseModel):
    decision: str  # granted | denied | absconded


# ---------- Evidence Requests ----------
class EvidenceRequestCreate(BaseModel):
    requested_org_id: UUID
    doc_type_expected: Optional[str] = None


class EvidenceRequestResponse(BaseModel):
    id: UUID
    case_id: UUID
    requested_org_id: UUID
    doc_type_expected: Optional[str] = None
    status: str
    created_at: datetime
    completed_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


# ---------- Audit Log ----------
class AuditLogEntryResponse(BaseModel):
    id: UUID
    case_id: Optional[UUID] = None
    actor_user_id: Optional[UUID] = None
    action: str
    target_type: Optional[str] = None
    target_id: Optional[UUID] = None
    action_metadata: Optional[dict] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ---------- Admin ----------
class DocumentSchemaResponse(BaseModel):
    id: UUID
    doc_type: str
    tier: int
    sensitivity_fields: Optional[dict] = None

    model_config = ConfigDict(from_attributes=True)


class RecognizerMappingRequest(BaseModel):
    entity_type: str
    field_name: str


class RecognizerMappingResponse(BaseModel):
    id: UUID
    document_schema_id: UUID
    entity_type: str
    field_name: str

    model_config = ConfigDict(from_attributes=True)


class StageRequirementResponse(BaseModel):
    id: UUID
    crime_type: str
    requirement_type: str
    requirement_key: str
    mandatory: bool

    model_config = ConfigDict(from_attributes=True)


# ---------- Orgs ----------
class OrgOnboardRequest(BaseModel):
    name: str
    org_type: str


class UserSummary(BaseModel):
    id: UUID
    org_id: UUID
    role: str
    name: str
    email: str
    mfa_enabled: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ---------- Reports ----------
class CaseMetadataReportResponse(BaseModel):
    id: UUID
    case_number: str
    crime_type: str
    investigation_status: str
    bail_status: Optional[str] = None
    court_level: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ---------- Charge Sheet ----------
class ChargeSheetResponse(BaseModel):
    status: str
    case_id: UUID
    investigation_status: str


# ---------- Trial ----------
class TrialHearingRequest(BaseModel):
    pass  # Just triggers state transition; hearing details are logged in audit


class JudgmentRequest(BaseModel):
    verdict: Optional[str] = None
