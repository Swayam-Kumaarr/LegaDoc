"""
Admin & Schema Registry Pydantic schemas.
"""

from typing import Any, Dict, List, Optional
from uuid import UUID
from pydantic import BaseModel


class RecognizerMappingRequest(BaseModel):
    entity_type: str
    field_name: str


class RecognizerMappingResponse(BaseModel):
    id: UUID
    document_schema_id: UUID
    entity_type: str
    field_name: str

    class Config:
        from_attributes = True


class DocumentSchemaResponse(BaseModel):
    id: UUID
    doc_type: str
    tier: int
    sensitivity_fields: Optional[Dict[str, Any]] = None
    recognizer_mappings: Optional[List[RecognizerMappingResponse]] = None

    class Config:
        from_attributes = True


class StageRequirementResponse(BaseModel):
    id: UUID
    crime_type: str
    requirement_type: str  # "document" | "evidence_request"
    requirement_key: str  # doc_type or org_type expected
    mandatory: bool

    class Config:
        from_attributes = True


class StageRequirementCreate(BaseModel):
    crime_type: str
    requirement_type: str
    requirement_key: str
    mandatory: bool = True
