"""Admin & config — schema registry, AI Parser recognizer mapping, stage
requirements, org onboarding, role & permission governance, and tamper-evident audit logs.
See SYSTEM_DESIGN.md Domain 8 (Platform / Admin).

Config Admin vs. Security Auditor (see models.py, User.role): a single
super-admin holding both schema-editing power and audit-inspection power is
one compromised account away from total control. Config Admin owns
everything in this file. Security Auditor owns audit.py's ai-parser endpoint
instead — never both from the same role.
"""

import secrets
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app import models, schemas
from app.audit import write_audit_log
from app.database import get_db
from app.security import require_role, hash_api_key

router = APIRouter(prefix="/admin", tags=["admin"])


# ---------- Dynamic Role & Permission Management ----------

@router.get("/permissions", response_model=list[schemas.PermissionResponse])
def list_permissions(
    claims: dict = Depends(require_role("config_admin")),
    db: Session = Depends(get_db)
):
    """GET /admin/permissions — Config Admin. List all system permissions grouped by category."""
    return db.query(models.Permission).order_by(models.Permission.category, models.Permission.code).all()


@router.get("/roles", response_model=list[schemas.RoleResponse])
def list_roles(
    claims: dict = Depends(require_role("config_admin")),
    db: Session = Depends(get_db)
):
    """GET /admin/roles — Config Admin. List all system and custom roles with their permissions and member counts."""
    roles = db.query(models.Role).order_by(models.Role.created_at).all()
    results = []
    for r in roles:
        user_count = db.query(models.User).filter((models.User.role_id == r.id) | (models.User.role == r.code)).count()
        perm_codes = [p.code for p in r.permissions]
        results.append(
            schemas.RoleResponse(
                id=r.id,
                code=r.code,
                name=r.name,
                description=r.description,
                is_system=r.is_system,
                permission_codes=perm_codes,
                user_count=user_count
            )
        )
    return results


@router.post("/roles", response_model=schemas.RoleResponse, status_code=status.HTTP_201_CREATED)
def create_role(
    body: schemas.RoleCreateRequest,
    claims: dict = Depends(require_role("config_admin")),
    db: Session = Depends(get_db)
):
    """POST /admin/roles — Config Admin. Create a new custom role and assign permissions."""
    code_normalized = body.code.strip().lower().replace(" ", "_")
    existing = db.query(models.Role).filter(models.Role.code == code_normalized).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Role with code '{code_normalized}' already exists."
        )

    new_role = models.Role(
        code=code_normalized,
        name=body.name.strip(),
        description=body.description,
        is_system=False
    )

    if body.permission_codes:
        perms = db.query(models.Permission).filter(models.Permission.code.in_(body.permission_codes)).all()
        new_role.permissions.extend(perms)

    db.add(new_role)
    db.commit()
    db.refresh(new_role)

    actor_id = UUID(claims["sub"]) if "sub" in claims else None
    write_audit_log(
        db,
        action="role_created",
        actor_user_id=actor_id,
        target_type="role",
        target_id=new_role.id,
        metadata={
            "role_code": new_role.code,
            "role_name": new_role.name,
            "permissions": [p.code for p in new_role.permissions]
        }
    )

    return schemas.RoleResponse(
        id=new_role.id,
        code=new_role.code,
        name=new_role.name,
        description=new_role.description,
        is_system=new_role.is_system,
        permission_codes=[p.code for p in new_role.permissions],
        user_count=0
    )


@router.put("/roles/{role_id}", response_model=schemas.RoleResponse)
def update_role(
    role_id: UUID,
    body: schemas.RoleUpdateRequest,
    claims: dict = Depends(require_role("config_admin")),
    db: Session = Depends(get_db)
):
    """PUT /admin/roles/{role_id} — Config Admin. Update role name, description, or permissions."""
    role = db.get(models.Role, role_id)
    if not role:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found")

    prev_perms = [p.code for p in role.permissions]
    prev_name = role.name

    if body.name is not None:
        role.name = body.name.strip()
    if body.description is not None:
        role.description = body.description

    if body.permission_codes is not None:
        perms = db.query(models.Permission).filter(models.Permission.code.in_(body.permission_codes)).all()
        role.permissions = perms

    db.commit()
    db.refresh(role)

    actor_id = UUID(claims["sub"]) if "sub" in claims else None
    write_audit_log(
        db,
        action="role_updated",
        actor_user_id=actor_id,
        target_type="role",
        target_id=role.id,
        metadata={
            "role_code": role.code,
            "previous_permissions": prev_perms,
            "new_permissions": [p.code for p in role.permissions],
            "name_updated": body.name is not None and body.name.strip() != prev_name,
            "description_updated": body.description is not None
        }
    )

    user_count = db.query(models.User).filter((models.User.role_id == role.id) | (models.User.role == role.code)).count()
    return schemas.RoleResponse(
        id=role.id,
        code=role.code,
        name=role.name,
        description=role.description,
        is_system=role.is_system,
        permission_codes=[p.code for p in role.permissions],
        user_count=user_count
    )


@router.delete("/roles/{role_id}")
def delete_role(
    role_id: UUID,
    claims: dict = Depends(require_role("config_admin")),
    db: Session = Depends(get_db)
):
    """DELETE /admin/roles/{role_id} — Config Admin. Delete a custom role."""
    role = db.get(models.Role, role_id)
    if not role:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found")
    if role.is_system:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="System protected roles cannot be deleted.")

    role_code = role.code
    role_name = role.name
    db.delete(role)
    db.commit()

    actor_id = UUID(claims["sub"]) if "sub" in claims else None
    write_audit_log(
        db,
        action="role_deleted",
        actor_user_id=actor_id,
        target_type="role",
        target_id=role_id,
        metadata={
            "role_code": role_code,
            "role_name": role_name
        }
    )

    return {"status": "deleted", "role_code": role_code}


@router.get("/users", response_model=list[schemas.UserSummaryResponse])
def list_users(
    claims: dict = Depends(require_role("config_admin")),
    db: Session = Depends(get_db)
):
    """GET /admin/users — Config Admin. List users across organizations with assigned roles."""
    users = db.query(models.User).order_by(models.User.created_at).all()
    results = []
    for u in users:
        results.append(
            schemas.UserSummaryResponse(
                id=u.id,
                name=u.name,
                email=u.email,
                service_id=u.service_id,
                designation=u.designation,
                role=u.role,
                org_name=u.organization.name if u.organization else None
            )
        )
    return results


@router.post("/users/{user_id}/assign-role")
def assign_user_role(
    user_id: UUID,
    body: schemas.AssignRoleRequest,
    claims: dict = Depends(require_role("config_admin")),
    db: Session = Depends(get_db)
):
    """POST /admin/users/{user_id}/assign-role — Config Admin.
    Authoritatively assign a role to a user. Writes a tamper-evident audit log entry.
    """
    user = db.get(models.User, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    target_role = db.query(models.Role).filter(models.Role.code == body.role_code).first()
    if not target_role:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Role '{body.role_code}' does not exist.")

    previous_role = user.role
    previous_role_id = str(user.role_id) if user.role_id else None

    user.role = target_role.code
    user.role_id = target_role.id
    db.commit()
    db.refresh(user)

    actor_id = UUID(claims["sub"]) if "sub" in claims else None
    write_audit_log(
        db,
        action="role_assigned",
        actor_user_id=actor_id,
        target_type="user",
        target_id=user.id,
        metadata={
            "target_user_id": str(user.id),
            "target_user_name": user.name,
            "target_user_email": user.email,
            "previous_role": previous_role,
            "previous_role_id": previous_role_id,
            "new_role": target_role.code,
            "new_role_id": str(target_role.id),
            "role_name": target_role.name
        }
    )

    return {
        "status": "success",
        "user_id": str(user.id),
        "user_name": user.name,
        "previous_role": previous_role,
        "assigned_role": target_role.code,
        "role_name": target_role.name
    }


@router.post("/users/{user_id}/remove-role")
def remove_user_role(
    user_id: UUID,
    claims: dict = Depends(require_role("config_admin")),
    db: Session = Depends(get_db)
):
    """POST /admin/users/{user_id}/remove-role — Config Admin.
    Revoke an assigned role from a user. Writes a tamper-evident audit log entry.
    """
    user = db.get(models.User, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    previous_role = user.role
    user.role = "unassigned"
    user.role_id = None
    db.commit()
    db.refresh(user)

    actor_id = UUID(claims["sub"]) if "sub" in claims else None
    write_audit_log(
        db,
        action="role_removed",
        actor_user_id=actor_id,
        target_type="user",
        target_id=user.id,
        metadata={
            "target_user_id": str(user.id),
            "target_user_name": user.name,
            "target_user_email": user.email,
            "previous_role": previous_role,
            "new_role": "unassigned"
        }
    )

    return {
        "status": "success",
        "user_id": str(user.id),
        "user_name": user.name,
        "previous_role": previous_role,
        "current_role": "unassigned"
    }


# ---------- Real Organization Onboarding & Management ----------

@router.get("/orgs", response_model=list[schemas.OrganizationResponse])
def list_organizations(
    claims: dict = Depends(require_role("config_admin")),
    db: Session = Depends(get_db)
):
    """GET /admin/orgs — Config Admin. List all registered tenant organizations with member counts."""
    orgs = db.query(models.Organization).order_by(models.Organization.name).all()
    results = []
    for o in orgs:
        count = db.query(models.User).filter(models.User.org_id == o.id).count()
        results.append(
            schemas.OrganizationResponse(
                id=o.id,
                name=o.name,
                org_type=o.org_type,
                created_at=o.created_at,
                user_count=count
            )
        )
    return results


@router.post("/orgs", response_model=schemas.OrganizationResponse, status_code=status.HTTP_201_CREATED)
def onboard_organization(
    body: schemas.OrganizationCreateRequest,
    claims: dict = Depends(require_role("config_admin")),
    db: Session = Depends(get_db)
):
    """POST /admin/orgs — Config Admin. Onboard external authority / stakeholder organization."""
    name_clean = body.name.strip()
    if not name_clean:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Organization name cannot be empty.")

    existing = db.query(models.Organization).filter(models.Organization.name == name_clean).first()
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Organization '{name_clean}' already exists.")

    new_org = models.Organization(
        name=name_clean,
        org_type=body.org_type.strip().lower()
    )
    db.add(new_org)
    db.commit()
    db.refresh(new_org)

    actor_id = UUID(claims["sub"]) if "sub" in claims else None
    write_audit_log(
        db,
        action="organization_onboarded",
        actor_user_id=actor_id,
        target_type="organization",
        target_id=new_org.id,
        metadata={
            "org_name": new_org.name,
            "org_type": new_org.org_type
        }
    )

    return schemas.OrganizationResponse(
        id=new_org.id,
        name=new_org.name,
        org_type=new_org.org_type,
        created_at=new_org.created_at,
        user_count=0
    )


# ---------- Administrative & Role Audit Trail ----------

@router.get("/audit-logs", response_model=list[schemas.AdminAuditLogEntry])
def list_admin_audit_logs(
    limit: int = 50,
    offset: int = 0,
    action: Optional[str] = None,
    target_type: Optional[str] = None,
    claims: dict = Depends(require_role("config_admin", "security_auditor")),
    db: Session = Depends(get_db)
):
    """GET /admin/audit-logs — Config Admin / Security Auditor.
    Retrieve immutable, hash-chained system and role audit logs.
    """
    query = db.query(models.AuditLog)
    if action:
        query = query.filter(models.AuditLog.action == action)
    if target_type:
        query = query.filter(models.AuditLog.target_type == target_type)

    # seq, not created_at — see models.AuditLog.seq: wall-clock timestamps can tie
    # between rapid writes, seq is the actual write-order guarantee.
    rows = query.order_by(models.AuditLog.seq.desc()).offset(offset).limit(limit).all()

    # Pre-fetch user map for actor names
    actor_ids = {r.actor_user_id for r in rows if r.actor_user_id is not None}
    users = {u.id: u for u in db.query(models.User).filter(models.User.id.in_(actor_ids)).all()} if actor_ids else {}

    results = []
    for r in rows:
        actor = users.get(r.actor_user_id)
        results.append(
            schemas.AdminAuditLogEntry(
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
                created_at=r.created_at
            )
        )
    return results


# ---------- Document Schema & Recognizer Configuration ----------

@router.get("/document-schemas", response_model=list[schemas.DocumentSchemaResponse])
def list_document_schemas(
    claims: dict = Depends(require_role("config_admin")),
    db: Session = Depends(get_db)
):
    """GET /admin/document-schemas — Config Admin. List all configured document schemas with their recognizer mappings."""
    return db.query(models.DocumentSchemaConfig).order_by(models.DocumentSchemaConfig.created_at).all()


@router.post("/document-schemas", response_model=schemas.DocumentSchemaResponse, status_code=status.HTTP_201_CREATED)
def create_document_schema(
    body: schemas.DocumentSchemaCreateRequest,
    claims: dict = Depends(require_role("config_admin")),
    db: Session = Depends(get_db)
):
    """POST /admin/document-schemas — Config Admin. Create a new document schema."""
    doc_type_normalized = body.doc_type.strip()
    if not doc_type_normalized:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="doc_type cannot be empty."
        )

    if body.tier not in (1, 2, 3):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="tier must be 1, 2, or 3."
        )

    if body.tier == 3:
        if body.sensitivity_fields is not None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Tier 3 schemas must have null sensitivity_fields (inherits generic default profile)."
            )
    else:
        if not body.sensitivity_fields:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Tier 1 and Tier 2 schemas must specify non-empty sensitivity_fields."
            )

    existing = db.query(models.DocumentSchemaConfig).filter(
        models.DocumentSchemaConfig.doc_type == doc_type_normalized
    ).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Document schema for '{doc_type_normalized}' already exists."
        )

    fields_data = [f.model_dump() for f in body.sensitivity_fields] if body.sensitivity_fields is not None else None
    schema_config = models.DocumentSchemaConfig(
        doc_type=doc_type_normalized,
        tier=body.tier,
        sensitivity_fields=fields_data,
    )
    db.add(schema_config)
    db.commit()
    db.refresh(schema_config)

    actor_id = UUID(claims["sub"]) if "sub" in claims else None
    write_audit_log(
        db,
        action="document_schema_created",
        actor_user_id=actor_id,
        target_type="document_schema",
        target_id=schema_config.id,
        metadata={
            "doc_type": schema_config.doc_type,
            "tier": schema_config.tier,
            "sensitivity_fields": schema_config.sensitivity_fields,
        }
    )

    return schema_config


@router.put("/document-schemas/{doc_type}", response_model=schemas.DocumentSchemaResponse)
def update_document_schema(
    doc_type: str,
    body: schemas.DocumentSchemaUpdateRequest,
    claims: dict = Depends(require_role("config_admin")),
    db: Session = Depends(get_db)
):
    """PUT /admin/document-schemas/{doc_type} — Config Admin. Update an existing document schema."""
    schema_config = db.query(models.DocumentSchemaConfig).filter(
        models.DocumentSchemaConfig.doc_type == doc_type.strip()
    ).first()
    if not schema_config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document schema for '{doc_type}' not found."
        )

    target_tier = body.tier if body.tier is not None else schema_config.tier
    if target_tier not in (1, 2, 3):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="tier must be 1, 2, or 3."
        )

    if "sensitivity_fields" in body.model_fields_set:
        target_fields = [f.model_dump() for f in body.sensitivity_fields] if body.sensitivity_fields is not None else None
    else:
        target_fields = schema_config.sensitivity_fields

    if target_tier == 3:
        if target_fields is not None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Tier 3 schemas must have null sensitivity_fields (inherits generic default profile)."
            )
    else:
        if not target_fields:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Tier 1 and Tier 2 schemas must specify non-empty sensitivity_fields."
            )

    prev_tier = schema_config.tier
    prev_fields = schema_config.sensitivity_fields

    schema_config.tier = target_tier
    schema_config.sensitivity_fields = target_fields

    db.commit()
    db.refresh(schema_config)

    actor_id = UUID(claims["sub"]) if "sub" in claims else None
    write_audit_log(
        db,
        action="document_schema_updated",
        actor_user_id=actor_id,
        target_type="document_schema",
        target_id=schema_config.id,
        metadata={
            "doc_type": schema_config.doc_type,
            "previous_tier": prev_tier,
            "new_tier": schema_config.tier,
            "previous_sensitivity_fields": prev_fields,
            "new_sensitivity_fields": schema_config.sensitivity_fields,
        }
    )

    return schema_config


@router.post("/document-schemas/{doc_type}/recognizers", response_model=list[schemas.RecognizerMappingResponse])
def set_recognizer_mappings(
    doc_type: str,
    body: schemas.RecognizerMappingSetRequest,
    claims: dict = Depends(require_role("config_admin")),
    db: Session = Depends(get_db)
):
    """POST /admin/document-schemas/{doc_type}/recognizers — Config Admin. Full replace of recognizer mappings for a doc type."""
    schema_config = db.query(models.DocumentSchemaConfig).filter(
        models.DocumentSchemaConfig.doc_type == doc_type.strip()
    ).first()
    if not schema_config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document schema for '{doc_type}' not found."
        )

    # Validate referential integrity: every field_name in body must match sensitivity_fields in schema
    valid_fields = set()
    if schema_config.sensitivity_fields:
        for f in schema_config.sensitivity_fields:
            if isinstance(f, dict) and "field_name" in f:
                valid_fields.add(f["field_name"])

    for item in body.mappings:
        if item.field_name not in valid_fields:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Field '{item.field_name}' does not exist in sensitivity_fields for schema '{doc_type}'."
            )

    prev_mappings = [
        {"entity_type": rm.entity_type, "field_name": rm.field_name}
        for rm in schema_config.recognizer_mappings
    ]

    # Full replace: delete existing mappings for this document_schema_id
    db.query(models.RecognizerMapping).filter(
        models.RecognizerMapping.document_schema_id == schema_config.id
    ).delete()

    # Insert new mappings
    for item in body.mappings:
        rm = models.RecognizerMapping(
            document_schema_id=schema_config.id,
            entity_type=item.entity_type.strip(),
            field_name=item.field_name.strip(),
        )
        db.add(rm)

    db.commit()
    db.refresh(schema_config)

    new_mappings = schema_config.recognizer_mappings
    new_mappings_audit = [
        {"entity_type": item.entity_type.strip(), "field_name": item.field_name.strip()}
        for item in body.mappings
    ]

    actor_id = UUID(claims["sub"]) if "sub" in claims else None
    write_audit_log(
        db,
        action="recognizer_mapping_updated",
        actor_user_id=actor_id,
        target_type="document_schema",
        target_id=schema_config.id,
        metadata={
            "doc_type": schema_config.doc_type,
            "previous_mappings": prev_mappings,
            "new_mappings": new_mappings_audit,
        }
    )

    return new_mappings


@router.get("/stage-requirements")
def list_stage_requirements(claims: dict = Depends(require_role("config_admin"))):
    """GET /admin/stage-requirements — Config Admin.
    Explicit 501: Dynamic stage requirements configuration is not implemented in this build.
    """
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Dynamic stage requirements configuration is not implemented in this build. Case stage progression rules are currently static."
    )


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
