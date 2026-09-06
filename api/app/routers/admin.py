"""Admin — API key management (user-bound programmatic access).

See SYSTEM_DESIGN.md, user-bound API key vertical slice.
"""

import secrets
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app import models, schemas
from app.audit import write_audit_log
from app.database import get_db
from app.security import require_role, hash_api_key

router = APIRouter(prefix="/admin", tags=["admin"])


# ---------- API Key Management (user-bound programmatic access) ----------

def _generate_api_key() -> str:
    """256 bits of OS entropy, prefixed so a leaked key is instantly
    recognizable and distinguishable from a JWT in any log. The prefix shown
    to admins is derived from this same key's tail — enough to match a key to
    its row in the UI, never enough to reconstruct or brute-force it."""
    return f"legadoc_{secrets.token_hex(32)}"


@router.post("/api-keys", response_model=schemas.ApiKeyCreatedResponse, status_code=status.HTTP_201_CREATED)
def create_api_key(
    body: schemas.ApiKeyCreateRequest,
    claims: dict = Depends(require_role("config_admin")),
    db: Session = Depends(get_db),
):
    """POST /admin/api-keys — Config Admin. Create a user-bound API key for
    programmatic access. The raw key is returned exactly once and is NEVER
    stored — only its SHA-256 hash is persisted, so it cannot be recovered
    from the database later. Keys act as their owning user, inheriting that
    user's org_id, role, and case-access scoping."""
    owner = db.get(models.User, body.user_id)
    if owner is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    raw_key = _generate_api_key()
    row = models.ApiKey(
        user_id=body.user_id,
        name=body.name.strip() or "api-key",
        key_hash=hash_api_key(raw_key),
        key_prefix=f"legadoc_{raw_key[-8:]}",
        created_by_user_id=UUID(claims["sub"]),
        expires_at=body.expires_at,
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    actor_id = UUID(claims["sub"]) if "sub" in claims else None
    write_audit_log(
        db,
        action="api_key_created",
        actor_user_id=actor_id,
        target_type="api_key",
        target_id=row.id,
        metadata={"key_name": row.name, "owner_user_id": str(body.user_id), "key_prefix": row.key_prefix},
    )

    return schemas.ApiKeyCreatedResponse(
        id=row.id,
        user_id=row.user_id,
        name=row.name,
        key=raw_key,
        key_prefix=row.key_prefix,
        expires_at=row.expires_at,
        created_at=row.created_at,
    )


@router.get("/api-keys", response_model=list[schemas.ApiKeyView])
def list_api_keys(
    claims: dict = Depends(require_role("config_admin")),
    db: Session = Depends(get_db),
):
    """GET /admin/api-keys — Config Admin. List API keys with their prefix
    and status. Raw keys are never returned or stored, so nothing here can
    leak them."""
    rows = db.query(models.ApiKey).order_by(models.ApiKey.created_at).all()
    owner_ids = {r.user_id for r in rows}
    owners = {u.id: u for u in db.query(models.User).filter(models.User.id.in_(owner_ids)).all()} if owner_ids else {}
    results = []
    for r in rows:
        owner = owners.get(r.user_id)
        results.append(
            schemas.ApiKeyView(
                id=r.id,
                user_id=r.user_id,
                user_name=owner.name if owner else None,
                user_email=owner.email if owner else None,
                name=r.name,
                key_prefix=r.key_prefix,
                created_at=r.created_at,
                last_used_at=r.last_used_at,
                expires_at=r.expires_at,
                revoked_at=r.revoked_at,
            )
        )
    return results


@router.post("/api-keys/{key_id}/revoke")
def revoke_api_key(
    key_id: UUID,
    claims: dict = Depends(require_role("config_admin")),
    db: Session = Depends(get_db),
):
    """POST /admin/api-keys/:id/revoke — Config Admin. Revoke an API key
    immediately (soft delete: the row stays for audit, revoked_at stops it
    being accepted). Requires a follow-up wipe from the audit trail in a real
    rotation — revocation is the breaking action, deletion is evidence."""
    row = db.get(models.ApiKey, key_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API key not found")
    if row.revoked_at is not None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="API key is already revoked")

    row.revoked_at = datetime.now(timezone.utc)
    db.commit()

    actor_id = UUID(claims["sub"]) if "sub" in claims else None
    write_audit_log(
        db,
        action="api_key_revoked",
        actor_user_id=actor_id,
        target_type="api_key",
        target_id=row.id,
        metadata={"key_name": row.name, "key_prefix": row.key_prefix},
    )

    return {"status": "revoked", "key_id": str(key_id), "key_prefix": row.key_prefix}