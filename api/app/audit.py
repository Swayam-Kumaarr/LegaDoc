"""
The one place every audit_log row gets written — see SYSTEM_DESIGN.md,
"Audit log integrity". Never construct models.AuditLog directly anywhere
else; the row_hash chain is only correct if every write goes through here.
"""

import hashlib
import json
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from app import models

# Any fixed integer works — pg_advisory_xact_lock just needs every writer to
# contend on the SAME key so appends are serialized against each other.
_AUDIT_LOCK_KEY = 267190  # arbitrary, matches the problem statement number for memorability


def _row_content(case_id, actor_user_id, action, target_type, target_id, metadata, created_at) -> str:
    # SQLite has no real tz-aware storage — a value written as UTC-aware
    # comes back naive after a round-trip through the DB, even though the
    # wall-clock value is unchanged. Normalize here (we only ever write
    # UTC) so the hash a fresh write computes and the hash a later
    # verification pass recomputes from the stored row always agree.
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    return json.dumps(
        {
            "case_id": str(case_id) if case_id else None,
            "actor_user_id": str(actor_user_id) if actor_user_id else None,
            "action": action,
            "target_type": target_type,
            "target_id": str(target_id) if target_id else None,
            "metadata": metadata or {},
            "created_at": created_at.isoformat(),
        },
        sort_keys=True,
    )


def write_audit_log(
    db: Session,
    *,
    action: str,
    case_id=None,
    actor_user_id=None,
    target_type: str = None,
    target_id=None,
    metadata: dict = None,
) -> models.AuditLog:
    """Appends one row to the hash chain. Concurrency-safe on Postgres via
    pg_advisory_xact_lock (every writer — the API, every Celery worker —
    contends on the same key for the duration of this transaction, so two
    processes can never read the same prev_hash and both insert). SQLite has
    no advisory-lock primitive and no real concurrent writers in a test
    process, so the lock is skipped there — this means the hash CHAIN LOGIC
    is verified by the test suite, but the CONCURRENCY GUARANTEE is only
    real on Postgres. Don't mistake a passing SQLite test for proof the lock
    isn't needed in production.
    """
    if db.bind.dialect.name == "postgresql":
        db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": _AUDIT_LOCK_KEY})

    # Ordered by seq, not created_at — see models.AuditLog.seq's docstring.
    # Wall-clock time can tie between two writes microseconds apart (this is
    # not hypothetical: several writes in the same request landed with an
    # identical created_at and silently broke the chain — see git history /
    # PR #20 review). seq is a plain monotonic counter, safe under the same
    # advisory lock that already serializes writers.
    prev = db.query(models.AuditLog).order_by(models.AuditLog.seq.desc()).first()
    prev_hash = prev.row_hash if prev else None
    next_seq = (prev.seq if prev else 0) + 1

    created_at = datetime.now(timezone.utc)
    content = _row_content(case_id, actor_user_id, action, target_type, target_id, metadata, created_at)
    row_hash = hashlib.sha256(f"{prev_hash}|{content}".encode("utf-8")).hexdigest()

    entry = models.AuditLog(
        case_id=case_id,
        actor_user_id=actor_user_id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        action_metadata=metadata or {},
        prev_hash=prev_hash,
        row_hash=row_hash,
        seq=next_seq,
        created_at=created_at,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


def verify_chain_intact(db: Session) -> bool:
    """Walks every row in order and recomputes each hash — a debugging/ops
    tool, not something a normal request path calls. Returns False the
    moment any row's stored row_hash doesn't match what its content +
    prev_hash actually hash to, which is exactly what "someone tampered
    with or deleted a row" looks like."""
    rows = db.query(models.AuditLog).order_by(models.AuditLog.seq.asc()).all()
    prev_hash = None
    for row in rows:
        content = _row_content(row.case_id, row.actor_user_id, row.action, row.target_type, row.target_id, row.action_metadata, row.created_at)
        expected = hashlib.sha256(f"{prev_hash}|{content}".encode("utf-8")).hexdigest()
        if expected != row.row_hash or row.prev_hash != prev_hash:
            return False
        prev_hash = row.row_hash
    return True


def verify_case_chain_integrity(db: Session, case_id) -> dict:
    """Verifies tamper-evident integrity for audit entries associated with a specific case.
    Validates that:
      1. Every audit row in the global table maintains valid hash chaining (row_hash == hash(prev_hash + content)
         and prev_hash == previous_row.row_hash).
      2. The case's entries are properly embedded in this intact chain.
    Returns a dict matching schemas.CaseChainIntegrityResponse:
      case_id, chain_intact, total_entries, latest_hash
    """
    case_uuid = case_id if isinstance(case_id, UUID) else UUID(str(case_id))
    rows = db.query(models.AuditLog).order_by(models.AuditLog.seq.asc()).all()
    prev_hash = None
    chain_intact = True
    case_rows = []

    for row in rows:
        content = _row_content(row.case_id, row.actor_user_id, row.action, row.target_type, row.target_id, row.action_metadata, row.created_at)
        expected = hashlib.sha256(f"{prev_hash}|{content}".encode("utf-8")).hexdigest()
        if expected != row.row_hash or row.prev_hash != prev_hash:
            chain_intact = False
            break
        prev_hash = row.row_hash
        if row.case_id == case_uuid:
            case_rows.append(row)

    total_entries = len(case_rows) if chain_intact else db.query(models.AuditLog).filter(models.AuditLog.case_id == case_uuid).count()
    latest_hash = case_rows[-1].row_hash if (chain_intact and case_rows) else None

    return {
        "case_id": case_uuid,
        "chain_intact": chain_intact,
        "total_entries": total_entries,
        "latest_hash": latest_hash,
    }

