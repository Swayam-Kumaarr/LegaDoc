"""Audit trail — see SYSTEM_DESIGN.md, "Security: ... Audit Integrity" and Flow 6.

GET /ai-parser is Security Auditor, deliberately NOT Config Admin — see
Domain 8's role split. The account that edits redaction rules should not
also be the account that inspects whether redaction is working correctly;
that's the same person checking their own work.

Every read of /audit-log/ai-parser must itself write a row to AuditLog
(action="read_ai_parser_audit") — that's the meta-audit, and it's not a
separate table or endpoint, just another write to the same audit_log. This
endpoint also needs its own tighter rate limit (20/min per user) — it's the
single most sensitive read path in the system, worth protecting from being
spammed even by a legitimate but compromised account.
"""

from datetime import datetime, timezone
from typing import Optional, Union
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app import models, schemas
from app.audit import verify_case_chain_integrity, verify_chain_intact, write_audit_log
from app.database import get_db
from app.rate_limit import ai_parser_limiter
from app.security import (
    assert_case_access,
    get_current_claims,
    require_role,
)

router = APIRouter(prefix="/cases/{case_id}/audit-log", tags=["audit"])

# Roles granted the full cryptographic audit log per SYSTEM_DESIGN.md row 704
FULL_AUDIT_ROLES = {"config_admin", "security_auditor", "court"}

# Recognizer & redaction actions that belong to the AI Parser decision audit trail
AI_PARSER_ACTIONS = {
    "auto_tag_completed",
    "auto_tag",
    "redact_tag_correction",
    "ai_parser_failed",
    "ai_parser_needs_review",
}


@router.get("", response_model=Union[schemas.CaseAuditLogFullResponse, schemas.CaseAuditLogSummaryResponse])
def get_audit_log(
    case_id: str,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    action: Optional[str] = None,
    target_type: Optional[str] = None,
    claims: dict = Depends(get_current_claims),
    db: Session = Depends(get_db),
):
    """GET /cases/:id/audit-log — Role-filtered. Full for Config Admin/
    Security Auditor/Court, summarized (aggregate lines only, e.g. "3 fields
    auto-tagged, 1 corrected") for every other role with case access. Includes chain_status.
    """
    try:
        case_uuid = UUID(str(case_id))
    except ValueError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Case not found")

    case = db.get(models.Case, case_uuid)
    if case is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Case not found")

    assert_case_access(case_uuid, claims, db)

    chain_intact = verify_chain_intact(db)
    user_role = claims.get("role")

    if user_role in FULL_AUDIT_ROLES:
        query = db.query(models.AuditLog).filter(models.AuditLog.case_id == case_uuid)
        if action:
            query = query.filter(models.AuditLog.action == action)
        if target_type:
            query = query.filter(models.AuditLog.target_type == target_type)

        total_entries = query.count()
        rows = query.order_by(models.AuditLog.created_at.desc()).offset(offset).limit(limit).all()

        actor_ids = {r.actor_user_id for r in rows if r.actor_user_id is not None}
        users = (
            {u.id: u for u in db.query(models.User).filter(models.User.id.in_(actor_ids)).all()}
            if actor_ids
            else {}
        )

        entries = []
        for r in rows:
            actor = users.get(r.actor_user_id)
            entries.append(
                schemas.AuditLogEntry(
                    id=r.id,
                    case_id=r.case_id,
                    actor_user_id=r.actor_user_id,
                    actor_name=actor.name if actor else None,
                    actor_email=actor.email if actor else None,
                    action=r.action,
                    target_type=r.target_type,
                    target_id=r.target_id,
                    action_metadata=r.action_metadata,
                    prev_hash=r.prev_hash,
                    row_hash=r.row_hash,
                    created_at=r.created_at,
                )
            )

        return schemas.CaseAuditLogFullResponse(
            case_id=case_uuid,
            view_type="full",
            chain_intact=chain_intact,
            total_entries=total_entries,
            entries=entries,
        )

    # Summarized view for IO, SHO, Prosecutor, and other operational roles
    query = db.query(models.AuditLog).filter(models.AuditLog.case_id == case_uuid)
    if action:
        query = query.filter(models.AuditLog.action == action)
    if target_type:
        query = query.filter(models.AuditLog.target_type == target_type)

    all_rows = query.order_by(models.AuditLog.created_at.asc()).all()
    action_counts: dict[str, int] = {}
    first_entry_at = None
    last_entry_at = None

    for r in all_rows:
        action_counts[r.action] = action_counts.get(r.action, 0) + 1
        if first_entry_at is None:
            first_entry_at = r.created_at
        last_entry_at = r.created_at

    return schemas.CaseAuditLogSummaryResponse(
        case_id=case_uuid,
        view_type="summary",
        chain_intact=chain_intact,
        total_entries=len(all_rows),
        action_counts=action_counts,
        first_entry_at=first_entry_at,
        last_entry_at=last_entry_at,
    )


@router.get("/ai-parser", response_model=schemas.AIParserAuditResponse)
def get_ai_parser_audit(
    case_id: str,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    claims: dict = Depends(require_role("security_auditor")),
    db: Session = Depends(get_db),
):
    """GET /cases/:id/audit-log/ai-parser — Security Auditor only (not
    Config Admin — see module docstring). Full entity-level detail of every
    AI Parser auto-tag decision and every human correction on this case's
    documents. No bulk/cross-case export — one case at a time. Apply a
    tighter per-endpoint rate limit here than the general API default (20/min).
    Atomically writes a meta-audit row recording this read access.
    """
    try:
        case_uuid = UUID(str(case_id))
    except ValueError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Case not found")

    case = db.get(models.Case, case_uuid)
    if case is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Case not found")

    # Rate limiting: 20 requests per minute per user ID
    ai_parser_limiter.check(claims["sub"])

    query = (
        db.query(models.AuditLog)
        .filter(
            models.AuditLog.case_id == case_uuid,
            models.AuditLog.action.in_(AI_PARSER_ACTIONS),
        )
    )

    total_count = query.count()
    rows = query.order_by(models.AuditLog.created_at.desc()).offset(offset).limit(limit).all()

    # Meta-audit: write an immutable audit log entry documenting this inspection
    write_audit_log(
        db,
        action="read_ai_parser_audit",
        case_id=case_uuid,
        actor_user_id=UUID(claims["sub"]),
        target_type="audit_log",
        target_id=case_uuid,
        metadata={"entries_returned": len(rows), "total_matching": total_count},
    )

    entries = []
    for r in rows:
        meta = r.action_metadata or {}
        actor_type = "system" if r.actor_user_id is None else "human"
        entries.append(
            schemas.AIParserAuditEntry(
                id=r.id,
                document_id=r.target_id if r.target_type == "document" else None,
                action=r.action,
                actor_type=actor_type,
                actor_user_id=r.actor_user_id,
                entity_type=meta.get("entity_type"),
                confidence=meta.get("confidence"),
                span_start=meta.get("span_start"),
                span_end=meta.get("span_end"),
                created_at=r.created_at,
            )
        )

    return schemas.AIParserAuditResponse(
        case_id=case_uuid,
        total_entries=total_count,
        entries=entries,
    )


@router.get("/chain-integrity", response_model=schemas.CaseChainIntegrityResponse)
def get_chain_integrity(
    case_id: str,
    claims: dict = Depends(require_role("config_admin")),
    db: Session = Depends(get_db),
):
    """GET /cases/:id/audit-log/chain-integrity — Config Admin only.
    Exposes operational tamper verification for the audit hash chain
    associated with this case.
    """
    try:
        case_uuid = UUID(str(case_id))
    except ValueError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Case not found")

    case = db.get(models.Case, case_uuid)
    if case is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Case not found")

    result = verify_case_chain_integrity(db, case_uuid)

    return schemas.CaseChainIntegrityResponse(
        case_id=result["case_id"],
        chain_intact=result["chain_intact"],
        total_entries=result["total_entries"],
        latest_hash=result["latest_hash"],
        verified_at=datetime.now(timezone.utc),
    )
