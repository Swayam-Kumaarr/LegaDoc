"""
Pydantic request/response models. Kept in one file at this baseline size —
split by resource group (matching routers/) once this gets big enough that
one file is actually hard to navigate, not before.
"""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field


# ---------- Auth ----------
class LoginRequest(BaseModel):
    email: str  # Official email or Government Service ID / Badge Number
    password: str
    mfa_code: Optional[str] = None


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


class AccessTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


class MFASetupResponse(BaseModel):
    secret: str
    provisioning_uri: str
    mfa_enabled: bool


class MFAVerifyRequest(BaseModel):
    code: str


class MFADisableRequest(BaseModel):
    password: str


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
    doc_hash: Optional[str] = None


class DocumentView(BaseModel):
    id: UUID
    case_id: UUID
    doc_type: str
    version: int
    status: str
    chain_status: str
    retention_legal_hold: bool = False
    text: Optional[str] = None  # None while status != "ready"; masked or full depending on role
    download_url: Optional[str] = None
    doc_hash: Optional[str] = None


class DocumentVersionSummary(BaseModel):
    id: UUID
    version: int
    status: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ChainStatusResponse(BaseModel):
    document_id: UUID
    chain_status: str


class LegalHoldRequest(BaseModel):
    legal_hold: bool
    reason: str = Field(..., min_length=3, max_length=500)


class LegalHoldResponse(BaseModel):
    document_id: UUID
    case_id: UUID
    retention_legal_hold: bool
    status: str


class RedactTagRequest(BaseModel):
    entity_type: str

    span_start: int
    span_end: int


# ---------- User Profile & Authoritative Identity ----------
class UserProfileResponse(BaseModel):
    id: UUID
    name: str
    email: str
    service_id: Optional[str] = None
    designation: Optional[str] = None
    role: str
    org_id: UUID
    org_name: Optional[str] = None
    org_type: Optional[str] = None
    language_preference: str = "en"
    permissions: list[str] = []

    model_config = ConfigDict(from_attributes=True)


# ---------- Dynamic Role & Permission Management ----------
class PermissionResponse(BaseModel):
    id: UUID
    code: str
    name: str
    category: str
    description: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class RoleResponse(BaseModel):
    id: UUID
    code: str
    name: str
    description: Optional[str] = None
    is_system: bool
    permission_codes: list[str] = []
    user_count: int = 0

    model_config = ConfigDict(from_attributes=True)


class RoleCreateRequest(BaseModel):
    code: str
    name: str
    description: Optional[str] = None
    permission_codes: list[str] = []


class RoleUpdateRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    permission_codes: Optional[list[str]] = None


class AssignRoleRequest(BaseModel):
    role_code: str


class UserSummaryResponse(BaseModel):
    id: UUID
    name: str
    email: str
    service_id: Optional[str] = None
    designation: Optional[str] = None
    role: str
    org_name: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


# ---------- Organization Management ----------
class OrganizationResponse(BaseModel):
    id: UUID
    name: str
    org_type: str
    created_at: datetime
    user_count: int = 0

    model_config = ConfigDict(from_attributes=True)


class OrganizationCreateRequest(BaseModel):
    name: str
    org_type: str


# ---------- API Keys (user-bound programmatic access) ----------
class ApiKeyCreateRequest(BaseModel):
    user_id: UUID  # the user whose org_id/role the key will act as
    name: str = "api-key"  # human label, e.g. "CCTNS integration"
    expires_at: Optional[datetime] = None  # null = no expiry


class ApiKeyCreatedResponse(BaseModel):
    id: UUID
    user_id: UUID
    name: str
    key: str  # the raw key — returned exactly ONCE, never stored
    key_prefix: str
    expires_at: Optional[datetime] = None
    created_at: datetime


class ApiKeyView(BaseModel):
    """Admin-facing list item — never contains the raw key or its hash."""
    id: UUID
    user_id: UUID
    user_name: Optional[str] = None
    user_email: Optional[str] = None
    name: str
    key_prefix: str
    created_at: datetime
    last_used_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    revoked_at: Optional[datetime] = None


# ---------- Administrative Audit Log ----------
class AdminAuditLogEntry(BaseModel):
    id: UUID
    case_id: Optional[UUID] = None
    actor_user_id: Optional[UUID] = None
    actor_name: Optional[str] = None
    actor_email: Optional[str] = None
    action: str
    target_type: Optional[str] = None
    target_id: Optional[UUID] = None
    action_metadata: Optional[dict] = None
    prev_hash: Optional[str] = None
    row_hash: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ---------- Document Schema & Recognizer Configuration ----------
class SensitivityFieldSpec(BaseModel):
    field_name: str
    sensitive: bool


class RecognizerMappingResponse(BaseModel):
    id: UUID
    entity_type: str
    field_name: str

    model_config = ConfigDict(from_attributes=True)


class DocumentSchemaResponse(BaseModel):
    id: UUID
    doc_type: str
    tier: int
    sensitivity_fields: Optional[list[SensitivityFieldSpec]] = None
    recognizer_mappings: list[RecognizerMappingResponse] = []

    model_config = ConfigDict(from_attributes=True)


class DocumentSchemaCreateRequest(BaseModel):
    doc_type: str
    tier: int  # 1, 2, or 3
    sensitivity_fields: Optional[list[SensitivityFieldSpec]] = None


class DocumentSchemaUpdateRequest(BaseModel):
    tier: Optional[int] = None
    sensitivity_fields: Optional[list[SensitivityFieldSpec]] = None


class RecognizerMappingItem(BaseModel):
    entity_type: str
    field_name: str


class RecognizerMappingSetRequest(BaseModel):
    mappings: list[RecognizerMappingItem]


# ---------- Evidence Requests (Flow 3) ----------
class CreateEvidenceRequest(BaseModel):
    requested_org_id: UUID
    doc_type_expected: Optional[str] = None
    notes: Optional[str] = None


class EvidenceRequestResponse(BaseModel):
    id: UUID
    case_id: UUID
    requested_org_id: UUID
    doc_type_expected: Optional[str] = None
    status: str
    created_at: datetime
    completed_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


# ---------- Bail Track (Flow 4) ----------
class BailOrderRequest(BaseModel):
    granted: bool
    conditions: Optional[str] = None


class BailSuretyRequest(BaseModel):
    surety_name: str
    bond_amount: float


class BailRecordResponse(BaseModel):
    id: UUID
    case_id: UUID
    stage: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ---------- Trial & Judgment (Flow 5) ----------
class JudgmentRequest(BaseModel):
    verdict: str  # "acquitted" | "convicted"
    summary: Optional[str] = None


# ---------- Case Diary ----------
class CaseDiaryCreate(BaseModel):
    text: str


class CaseDiaryResponse(BaseModel):
    id: UUID
    case_id: UUID
    author_user_id: UUID
    text: str
    status: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ---------- Case Audit Trail & Verification (Flow 6) ----------
class AuditLogEntry(BaseModel):
    id: UUID
    case_id: Optional[UUID] = None
    actor_user_id: Optional[UUID] = None
    actor_name: Optional[str] = None
    actor_email: Optional[str] = None
    action: str
    target_type: Optional[str] = None
    target_id: Optional[UUID] = None
    action_metadata: Optional[dict] = None
    prev_hash: Optional[str] = None
    row_hash: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CaseAuditLogFullResponse(BaseModel):
    case_id: UUID
    view_type: str = "full"
    chain_intact: bool
    total_entries: int
    entries: list[AuditLogEntry]


class CaseAuditLogSummaryResponse(BaseModel):
    case_id: UUID
    view_type: str = "summary"
    chain_intact: bool
    total_entries: int
    action_counts: dict[str, int]
    first_entry_at: Optional[datetime] = None
    last_entry_at: Optional[datetime] = None


class AIParserAuditEntry(BaseModel):
    id: UUID
    document_id: Optional[UUID] = None
    action: str
    actor_type: str  # "system" or "human"
    actor_user_id: Optional[UUID] = None
    entity_type: Optional[str] = None
    confidence: Optional[int] = None
    span_start: Optional[int] = None
    span_end: Optional[int] = None
    created_at: datetime


class AIParserAuditResponse(BaseModel):
    case_id: UUID
    total_entries: int
    entries: list[AIParserAuditEntry]


class CaseChainIntegrityResponse(BaseModel):
    case_id: UUID
    chain_intact: bool
    total_entries: int
    latest_hash: Optional[str] = None
    verified_at: datetime


# ---------- NCRB De-Identified Reporting (Domain 7) ----------
class CaseMetadataDeidentified(BaseModel):
    """Structurally excludes all identity fields. Only aggregate/statistical fields."""
    id: UUID
    case_number: str
    crime_type: str
    court_level: Optional[str] = None
    investigation_status: str
    bail_status: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ---------- IO Reassignment (Flow 1) ----------
class ReassignIORequest(BaseModel):
    new_io_user_id: UUID
    reason: Optional[str] = Field(None, max_length=250)


class ReassignIOResponse(BaseModel):
    case_id: UUID
    previous_io_user_id: UUID
    new_io_user_id: UUID
    reassigned_at: datetime


# ---------- Document Review Queue (Flow 2) ----------
class DocumentReviewItem(BaseModel):
    """List queue item. raw_text is intentionally excluded to prevent bulk PII leaks."""
    id: UUID
    case_id: UUID
    doc_type: str
    version: int
    status: str
    chain_status: str
    doc_hash: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


