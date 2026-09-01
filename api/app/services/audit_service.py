"""
Centralized Audit Logging & Hash Chaining Service.
See SYSTEM_DESIGN.md, "Security: Encryption, Key Management, Input Validation & Audit Integrity"
and Flow 6 (AI Parser Audit Trail).

Every state-changing action writes an append-only AuditLog row with:
  row_hash = SHA256(prev_hash || actor_id || action || target_type || target_id || timestamp || metadata)
This creates an internal tamper-evident hash chain independent of Hyperledger Fabric.

To prevent write races across API handlers and Celery workers, appending uses
SELECT ... FOR UPDATE on the latest row to serialize concurrent writes.
"""

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Union
from uuid import UUID

from sqlalchemy.orm import Session

from app.models import AuditLog


def compute_row_hash(
    prev_hash: Optional[str],
    actor_user_id: Optional[UUID],
    action: str,
    target_type: Optional[str],
    target_id: Optional[UUID],
    created_at: Union[datetime, str],
    action_metadata: Optional[Dict[str, Any]],
) -> str:
    """Computes SHA-256 hash chaining this row to the previous row."""
    meta_str = json.dumps(action_metadata, sort_keys=True) if action_metadata is not None else ""
    if isinstance(created_at, str):
        ts_str = created_at
    elif hasattr(created_at, "isoformat"):
        ts_str = created_at.isoformat()
    else:
        ts_str = str(created_at)

    raw = (
        f"{prev_hash or ''}|"
        f"{str(actor_user_id) if actor_user_id else ''}|"
        f"{action}|"
        f"{target_type or ''}|"
        f"{str(target_id) if target_id else ''}|"
        f"{ts_str}|"
        f"{meta_str}"
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def append_audit_log(
    db: Session,
    case_id: Optional[UUID],
    actor_user_id: Optional[UUID],  # None = system (e.g. system:ai_parser)
    action: str,
    target_type: Optional[str] = None,
    target_id: Optional[UUID] = None,
    action_metadata: Optional[Dict[str, Any]] = None,  # NEVER raw sensitive text!
    fabric_tx_id: Optional[str] = None,
) -> AuditLog:
    """
    Appends a new audit log entry with atomic hash chaining.
    Takes a SQLAlchemy Session directly so both FastAPI handlers and Celery workers can call it.
    """
    now = datetime.now(timezone.utc)

    # Serialize concurrent appends using FOR UPDATE on the latest row in audit_log
    latest = (
        db.query(AuditLog)
        .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        .with_for_update()
        .first()
    )

    prev_hash = latest.row_hash if latest else None
    row_hash = compute_row_hash(
        prev_hash=prev_hash,
        actor_user_id=actor_user_id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        created_at=now,
        action_metadata=action_metadata,
    )

    entry = AuditLog(
        case_id=case_id,
        actor_user_id=actor_user_id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        action_metadata=action_metadata,
        prev_hash=prev_hash,
        row_hash=row_hash,
        fabric_tx_id=fabric_tx_id,
        created_at=now,
    )
    db.add(entry)
    db.flush()
    return entry


def verify_audit_chain(db: Session, case_id: Optional[UUID] = None) -> dict:
    """
    Walks the audit log chain to verify cryptographic integrity.
    Detects any deletion, insertion, or reordering of audit rows.
    """
    query = db.query(AuditLog)
    if case_id:
        query = query.filter(AuditLog.case_id == case_id)

    # Global verification order
    rows = query.order_by(AuditLog.created_at.asc(), AuditLog.id.asc()).all()

    if not rows:
        return {"valid": True, "total_rows": 0, "first_break_at": None}

    expected_prev = None
    for row in rows:
        # Check prev_hash linkage
        if row.prev_hash != expected_prev:
            return {
                "valid": False,
                "total_rows": len(rows),
                "first_break_at": str(row.id),
                "reason": f"Mismatched prev_hash at row {row.id}: expected {expected_prev}, got {row.prev_hash}",
            }

        # Check row_hash calculation
        recomputed = compute_row_hash(
            prev_hash=expected_prev,
            actor_user_id=row.actor_user_id,
            action=row.action,
            target_type=row.target_type,
            target_id=row.target_id,
            created_at=row.created_at,
            action_metadata=row.action_metadata,
        )
        if recomputed != row.row_hash:
            return {
                "valid": False,
                "total_rows": len(rows),
                "first_break_at": str(row.id),
                "reason": f"Corrupted row_hash at row {row.id}: expected {recomputed}, got {row.row_hash}",
            }

        expected_prev = row.row_hash

    return {"valid": True, "total_rows": len(rows), "first_break_at": None}
