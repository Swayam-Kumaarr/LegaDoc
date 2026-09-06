"""Org management — see SYSTEM_DESIGN.md Interface Contracts, "Endpoint Table"."""

from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app import models, schemas
from app.audit import write_audit_log
from app.database import get_db
from app.security import require_role

router = APIRouter(tags=["orgs"])


@router.get("/orgs", response_model=list[schemas.OrganizationResponse])
def list_orgs(
    claims: dict = Depends(require_role("config_admin")),
    db: Session = Depends(get_db)
):
    """GET /orgs — Config Admin. List all organizations."""
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


@router.get("/orgs/{org_id}/users", response_model=list[schemas.UserSummaryResponse])
def list_org_users(
    org_id: UUID,
    claims: dict = Depends(require_role("config_admin")),
    db: Session = Depends(get_db)
):
    """GET /orgs/:orgId/users — Config Admin. List an org's users."""
    org = db.get(models.Organization, org_id)
    if not org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")

    users = db.query(models.User).filter(models.User.org_id == org_id).order_by(models.User.name).all()
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
                org_name=org.name
            )
        )
    return results


@router.post("/orgs", response_model=schemas.OrganizationResponse, status_code=status.HTTP_201_CREATED)
def onboard_org(
    body: schemas.OrganizationCreateRequest,
    claims: dict = Depends(require_role("config_admin")),
    db: Session = Depends(get_db)
):
    """POST /orgs — System Admin. Onboard external authority org.
    MVP: admin pre-registration, not self-service.
    """
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
