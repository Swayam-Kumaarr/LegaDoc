"""Org management — see SYSTEM_DESIGN.md Interface Contracts, "Endpoint Table"."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app import models, schemas
from app.audit import write_audit_log
from app.database import get_db
from app.security import require_role

router = APIRouter(tags=["orgs"])


@router.get("/orgs/{org_id}/users", response_model=list[schemas.UserSummary])
def list_org_users(
    org_id: str,
    claims: dict = Depends(require_role("config_admin")),
    db: Session = Depends(get_db),
):
    """GET /orgs/:orgId/users — Org Admin. List an org's users."""
    org_uuid = UUID(org_id)
    org = db.get(models.Organization, org_uuid)
    if org is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")

    users = db.query(models.User).filter(models.User.org_id == org_uuid).all()
    return users


@router.post("/orgs", response_model=schemas.OrgOnboardRequest, status_code=status.HTTP_201_CREATED)
def onboard_org(
    body: schemas.OrgOnboardRequest,
    claims: dict = Depends(require_role("config_admin")),
    db: Session = Depends(get_db),
):
    """POST /orgs — System Admin. Onboard external authority org.
    MVP: admin pre-registration, not self-service.
    """
    existing = db.query(models.Organization).filter(models.Organization.name == body.name).first()
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Organization with this name already exists")

    org = models.Organization(name=body.name, org_type=body.org_type)
    db.add(org)
    db.commit()
    db.refresh(org)

    write_audit_log(
        db,
        action="org_onboarded",
        actor_user_id=UUID(claims["sub"]),
        target_type="organization",
        target_id=org.id,
        metadata={"name": body.name, "org_type": body.org_type},
    )

    return body
