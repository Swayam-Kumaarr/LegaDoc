"""
Audit Log Pydantic schemas.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID
from pydantic import BaseModel


class AuditLogEntry(BaseModel):
    id: UUID
    case_id: Optional[UUID] = None
    actor_user_id: Optional[UUID] = None  # None = system:ai_parser
    action: str
    target_type: Optional[str] = None
    target_id: Optional[UUID] = None
    action_metadata: Optional[Dict[str, Any]] = None  # Never raw sensitive text
    prev_hash: Optional[str] = None
    row_hash: str
    fabric_tx_id: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class AuditSummaryLine(BaseModel):
    date: str
    summary: str


class AuditLogResponse(BaseModel):
    case_id: UUID
    is_full_detail: bool
    entries: Optional[List[AuditLogEntry]] = None
    summaries: Optional[List[AuditSummaryLine]] = None


class AuditIntegrityReport(BaseModel):
    valid: bool
    total_rows: int
    first_break_at: Optional[str] = None
