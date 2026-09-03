"""Admin & config — schema registry, AI Parser recognizer mapping, stage
requirements, org onboarding. See SYSTEM_DESIGN.md Domain 8 (Platform / Admin).

Config Admin vs. Security Auditor (see models.py, User.role): a single
super-admin holding both schema-editing power and audit-inspection power is
one compromised account away from total control. Config Admin owns
everything in this file. Security Auditor owns audit.py's ai-parser endpoint
instead — never both from the same role.

Schema and recognizer-mapping changes (and Chain Worker manual recovery in
documents.py) are exactly the actions SYSTEM_DESIGN.md flags as needing
second-person confirmation before they take effect in a real deployment —
not enforced in this baseline, but don't build single-click execution here
and call it done.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app import models, schemas
from app.audit import write_audit_log
from app.database import get_db
from app.security import require_role

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/document-schemas", response_model=list[schemas.DocumentSchemaResponse])
def list_document_schemas(
    claims: dict = Depends(require_role("config_admin")),
    db: Session = Depends(get_db),
):
    """GET /admin/document-schemas — Config Admin. Manage the tiered
    field-sensitivity schema registry."""
    return db.query(models.DocumentSchemaConfig).all()


@router.post(
    "/document-schemas/{doc_type}/recognizers",
    response_model=list[schemas.RecognizerMappingResponse],
    status_code=status.HTTP_200_OK,
)
def set_recognizer_mapping(
    doc_type: str,
    body: list[schemas.RecognizerMappingRequest],
    claims: dict = Depends(require_role("config_admin")),
    db: Session = Depends(get_db),
):
    """POST /admin/document-schemas/:type/recognizers — Config Admin. Map
    entity types (name, phone, medical condition, ID number, ...) to a
    DocumentSchema's sensitivity fields. One-time-per-type config that drives
    the AI Parser. TODO: write an audit_log entry with the old vs new
    recognizer mapping diff — a silently-weakened recognizer is how someone
    quietly un-redacts a field, and that must be traceable.
    """
    schema_config = (
        db.query(models.DocumentSchemaConfig)
        .filter(models.DocumentSchemaConfig.doc_type == doc_type)
        .first()
    )
    if schema_config is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Document schema for '{doc_type}' not found")

    old_mappings = (
        db.query(models.RecognizerMapping)
        .filter(models.RecognizerMapping.document_schema_id == schema_config.id)
        .all()
    )
    old_mapping_data = [{"entity_type": m.entity_type, "field_name": m.field_name} for m in old_mappings]

    db.query(models.RecognizerMapping).filter(
        models.RecognizerMapping.document_schema_id == schema_config.id
    ).delete()

    new_mappings = []
    for item in body:
        mapping = models.RecognizerMapping(
            document_schema_id=schema_config.id,
            entity_type=item.entity_type,
            field_name=item.field_name,
        )
        db.add(mapping)
        new_mappings.append(mapping)

    db.commit()

    for m in new_mappings:
        db.refresh(m)

    new_mapping_data = [{"entity_type": m.entity_type, "field_name": m.field_name} for m in new_mappings]

    write_audit_log(
        db,
        action="recognizer_mapping_updated",
        actor_user_id=UUID(claims["sub"]),
        target_type="document_schema",
        target_id=schema_config.id,
        metadata={
            "doc_type": doc_type,
            "old_mappings": old_mapping_data,
            "new_mappings": new_mapping_data,
        },
    )

    return new_mappings


@router.get("/stage-requirements", response_model=list[schemas.StageRequirementResponse])
def list_stage_requirements(
    claims: dict = Depends(require_role("config_admin")),
    db: Session = Depends(get_db),
):
    """GET /admin/stage-requirements — Config Admin. Manage mandatory-document/
    evidence config per crime type. Drives Flow 3's validation check."""
    return db.query(models.StageRequirement).all()
