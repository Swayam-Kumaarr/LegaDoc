"""Records/NCRB reporting — see SYSTEM_DESIGN.md Domain 7.

This endpoint reads de-identified case metadata for the National Crime Records
Bureau. It explicitly projects only statistical columns (crime_type, status,
dates, court_level), structurally excluding all identity or sensitive fields
(names, accused, victim, officer, raw documents).
"""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app import models, schemas
from app.audit import write_audit_log
from app.database import get_db
from app.security import require_role

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/case-metadata", response_model=list[schemas.CaseMetadataDeidentified])
def get_case_metadata(
    crime_type: Optional[str] = Query(default=None),
    investigation_status: Optional[str] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    claims: dict = Depends(require_role("records_ncrb_analyst")),
    db: Session = Depends(get_db),
):
    """GET /reports/case-metadata — Records / NCRB Analyst. De-identified case
    metadata only (crime_type, status, dates, court_level — no identity or
    sensitive fields, even in redacted form)."""
    query = db.query(
        models.Case.id,
        models.Case.case_number,
        models.Case.crime_type,
        models.Case.court_level,
        models.Case.investigation_status,
        models.Case.bail_status,
        models.Case.created_at,
    )
    if crime_type:
        query = query.filter(models.Case.crime_type == crime_type)
    if investigation_status:
        query = query.filter(models.Case.investigation_status == investigation_status)

    rows = query.order_by(models.Case.created_at.asc()).offset(offset).limit(limit).all()

    results = [
        schemas.CaseMetadataDeidentified(
            id=r.id,
            case_number=r.case_number,
            crime_type=r.crime_type,
            court_level=r.court_level,
            investigation_status=r.investigation_status,
            bail_status=r.bail_status,
            created_at=r.created_at,
        )
        for r in rows
    ]

    actor_user_id = UUID(claims["sub"]) if "sub" in claims else None
    write_audit_log(
        db,
        action="ncrb_report_generated",
        actor_user_id=actor_user_id,
        target_type="report",
        metadata={
            "limit": limit,
            "offset": offset,
            "crime_type": crime_type,
            "investigation_status": investigation_status,
            "count": len(results),
        },
    )

    return results
