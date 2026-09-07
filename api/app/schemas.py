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
    email: str  # Official email or Government Service ID / Badge Number
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


class CaseAccessGrantRequest(BaseModel):
    user_id: UUID
    access_role: str  # court | prosecutor | defense


class CaseAccessGrantResponse(BaseModel):
    id: UUID
    case_id: UUID
    user_id: UUID
    access_role: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AssignIORequest(BaseModel):
    io_user_id: UUID


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


class ChargeSheetResponse(BaseModel):
    status: str
    case_id: UUID
    investigation_status: str


class EvidenceRequestCreate(BaseModel):
    requested_org_id: UUID
    doc_type_expected: Optional[str] = None


class EvidenceRequestResponse(EvidenceRequestCreate):
    id: UUID
    case_id: UUID
    status: str
    created_at: datetime
    completed_at: Optional[datetime] = None
    model_config = ConfigDict(from_attributes=True)


class BailOrderRequest(BaseModel):
    decision: str


class BailRecordResponse(BaseModel):
    id: UUID
    case_id: UUID
    stage: str
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class JudgmentRequest(BaseModel):
    verdict: Optional[str] = None


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


class OrgOnboardRequest(BaseModel):
    name: str
    org_type: str


class UserSummary(BaseModel):
    id: UUID
    name: str
    email: str
    role: str
    model_config = ConfigDict(from_attributes=True)


class CaseMetadataReportResponse(BaseModel):
    id: UUID
    case_number: Optional[str] = None
    crime_type: str
    investigation_status: str
    bail_status: Optional[str] = None
    court_level: Optional[str] = None
    created_at: datetime


# ---------- Documents ----------
class DocumentUploadResponse(BaseModel):
    id: UUID
    case_id: UUID
    doc_type: str
    version: int
    status: str
    chain_status: str
    doc_hash: Optional[str] = None
    processing_error: Optional[str] = None
    fabric_tx_id: Optional[str] = None


class DocumentView(BaseModel):
    id: UUID
    case_id: UUID
    doc_type: str
    version: int
    status: str
    chain_status: str
    text: Optional[str] = None  # None while status != "ready"; masked or full depending on role
    download_url: Optional[str] = None
    doc_hash: Optional[str] = None
    processing_error: Optional[str] = None
    fabric_tx_id: Optional[str] = None


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


# ---------- Document Schemas & Stage Requirements ----------
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


