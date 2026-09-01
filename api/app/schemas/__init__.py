"""
Pydantic schemas package for LegaDoc API.
"""

from app.schemas.auth import LoginRequest, TokenResponse, UserClaims, UserResponse
from app.schemas.common import ErrorResponse, MessageResponse, PaginatedResponse
from app.schemas.documents import (
    DocumentUploadResponse,
    DocumentView,
    DocumentSensitivityTagResponse,
    DocumentVersionResponse,
    ChainStatusResponse,
    RedactTagRequest,
)
from app.schemas.admin import (
    DocumentSchemaResponse,
    RecognizerMappingRequest,
    RecognizerMappingResponse,
    StageRequirementResponse,
    StageRequirementCreate,
)
from app.schemas.audit import (
    AuditLogEntry,
    AuditSummaryLine,
    AuditLogResponse,
    AuditIntegrityReport,
)

__all__ = [
    "LoginRequest",
    "TokenResponse",
    "UserClaims",
    "UserResponse",
    "ErrorResponse",
    "MessageResponse",
    "PaginatedResponse",
    "DocumentUploadResponse",
    "DocumentView",
    "DocumentSensitivityTagResponse",
    "DocumentVersionResponse",
    "ChainStatusResponse",
    "RedactTagRequest",
    "DocumentSchemaResponse",
    "RecognizerMappingRequest",
    "RecognizerMappingResponse",
    "StageRequirementResponse",
    "StageRequirementCreate",
    "AuditLogEntry",
    "AuditSummaryLine",
    "AuditLogResponse",
    "AuditIntegrityReport",
]
