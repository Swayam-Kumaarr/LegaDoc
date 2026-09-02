"""
Document & Redaction Pydantic schemas.
"""

from datetime import datetime
from typing import List, Optional
from uuid import UUID
from pydantic import BaseModel


class DocumentUploadResponse(BaseModel):
    document_id: UUID
    case_id: UUID
    doc_type: str
    version: int
    status: str
    chain_status: str
    doc_hash: Optional[str] = None
    original_filename: Optional[str] = None
    created_at: datetime


class DocumentListResponse(BaseModel):
    items: List["DocumentVersionResponse"]
    total: int
    page: int = 1
    per_page: int = 20


class DocumentSensitivityTagResponse(BaseModel):
    id: UUID
    document_id: UUID
    entity_type: str
    span_start: int
    span_end: int
    confidence: Optional[int] = None
    source: str
    created_at: datetime

    class Config:
        from_attributes = True


class DocumentView(BaseModel):
    id: UUID
    case_id: UUID
    doc_type: str
    version: int
    status: str  # processing | ready | needs_review
    chain_status: str  # pending | confirmed | failed
    uploaded_by: UUID
    original_filename: Optional[str] = None
    download_url: Optional[str] = None
    created_at: datetime
    text: Optional[str] = None  # Role-filtered redacted text
    tags: Optional[List[DocumentSensitivityTagResponse]] = None  # Only visible to authorized roles

    class Config:
        from_attributes = True


class DocumentVersionResponse(BaseModel):
    id: UUID
    case_id: UUID
    doc_type: str
    version: int
    status: str
    chain_status: str
    doc_hash: Optional[str] = None
    original_filename: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class ChainStatusResponse(BaseModel):
    document_id: UUID
    chain_status: str  # pending | confirmed | failed
    doc_hash: Optional[str] = None

    class Config:
        from_attributes = True


class RedactTagRequest(BaseModel):
    entity_type: str
    span_start: int
    span_end: int
    tag_id: Optional[UUID] = None  # If correcting an existing auto-tag
