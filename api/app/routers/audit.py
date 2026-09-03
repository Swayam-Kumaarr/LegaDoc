"""Audit trail — see SYSTEM_DESIGN.md, "Security: ... Audit Integrity" and Flow 6.

GET /ai-parser is Security Auditor, deliberately NOT Config Admin — see
Domain 8's role split. The account that edits redaction rules should not
also be the account that inspects whether redaction is working correctly;
that's the same person checking their own work.

Every read of /audit-log/ai-parser must itself write a row to AuditLog
(action="read_ai_parser_audit") — that's the meta-audit, and it's not a
separate table or endpoint, just another write to the same audit_log. This
endpoint also needs its own tighter rate limit — it's the single most
sensitive read path in the system, worth protecting from being spammed
even by a legitimate but compromised account.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app import models, schemas
from app.audit import write_audit_log
from app.database import get_db
from app.security import assert_case_access, require_role, get_current_claims

router = APIRouter(prefix="/cases/{case_id}/audit-log", tags=["audit"])

_FULL_ACCESS_AUDIT_ROLES = {"config_admin", "security_auditor", "court"}


@router.get("", response_model=list[schemas.AuditLogEntryResponse])
def get_audit_log(
    case_id: str,
    claims: dict = Depends(get_current_claims),
    db: Session = Depends(get_db),
):
    """GET /cases/:id/audit-log — Role-filtered. Full for Config Admin/
    Security Auditor/Court, summarized (aggregate lines only, e.g. "3 fields
    auto-tagged, 1 corrected") for every other role."""
    case_uuid = UUID(case_id)
    case = db.get(models.Case, case_uuid)
    if case is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")

    assert_case_access(case_uuid, claims, db)

    entries = (
        db.query(models.AuditLog)
        .filter(models.AuditLog.case_id == case_uuid)
        .order_by(models.AuditLog.created_at.asc())
        .all()
    )

    role = claims.get("role")
    if role in _FULL_ACCESS_AUDIT_ROLES:
        return entries

    seen_actions = {}
    for entry in entries:
        action = entry.action
        if action not in seen_actions:
            seen_actions[action] = 0
        seen_actions[action] += 1

    summarized = []
    for action, count in seen_actions.items():
        summarized.append(
            schemas.AuditLogEntryResponse(
                id=entries[0].id if entries else UUID(int=0),
                case_id=case_uuid,
                actor_user_id=None,
                action=f"{action} (x{count})",
                target_type=None,
                target_id=None,
                action_metadata=None,
                created_at=entries[0].created_at if entries else entries[-1].created_at,
            )
        )
    return summarized


@router.get("/ai-parser", response_model=list[schemas.AuditLogEntryResponse])
def get_ai_parser_audit(
    case_id: str,
    claims: dict = Depends(require_role("security_auditor")),
    db: Session = Depends(get_db),
):
    """GET /cases/:id/audit-log/ai-parser — Security Auditor only (not
    Config Admin — see module docstring). Full entity-level detail of every
    AI Parser auto-tag decision and every human correction on this case's
    documents. No bulk/cross-case export — one case at a time. Apply a
    tighter per-endpoint rate limit here than the general API default.
    TODO: write the meta-audit row (this read is itself an audited event)
    before returning the response.
    """
    case_uuid = UUID(case_id)
    case = db.get(models.Case, case_uuid)
    if case is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")

    assert_case_access(case_uuid, claims, db)

    ai_parser_actions = {
        "ai_parser_auto_tag",
        "redact_tag_correction",
        "case_diary_entry_added",
    }

    entries = (
        db.query(models.AuditLog)
        .filter(
            models.AuditLog.case_id == case_uuid,
            models.AuditLog.action.in_(ai_parser_actions),
        )
        .order_by(models.AuditLog.created_at.asc())
        .all()
    )

    write_audit_log(
        db,
        action="read_ai_parser_audit",
        case_id=case_uuid,
        actor_user_id=UUID(claims["sub"]),
        target_type="case",
        target_id=case_uuid,
    )

    return entries
