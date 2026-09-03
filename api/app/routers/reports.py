"""Records/NCRB reporting — see SYSTEM_DESIGN.md Domain 7.

This endpoint MUST read from a dedicated de-identified DB view (e.g.
`case_metadata_deidentified`), never a filtered pass through the normal
/cases or /documents endpoints. That separation is the whole point — it makes
"someone forgot to apply the redaction filter here" structurally impossible
for this role, rather than just tested against.

NOTE: In this baseline, the de-identified view is simulated by querying
the cases table and stripping identity fields at the application level.
A real deployment MUST create a Postgres view and bind a read-only
SQLAlchemy model to it — the application-level filter here is a stopgap,
not the security boundary.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db
from app.security import require_role

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/case-metadata", response_model=list[schemas.CaseMetadataReportResponse])
def get_case_metadata(
    claims: dict = Depends(require_role("records_ncrb_analyst")),
    db: Session = Depends(get_db),
):
    """GET /reports/case-metadata — Records / NCRB Analyst. De-identified case
    metadata only (crime_type, status, dates, court_level — no identity or
    sensitive fields, even in redacted form)."""
    cases = db.query(models.Case).all()

    return [
        schemas.CaseMetadataReportResponse(
            id=c.id,
            case_number=c.case_number,
            crime_type=c.crime_type,
            investigation_status=c.investigation_status,
            bail_status=c.bail_status,
            court_level=c.court_level,
            created_at=c.created_at,
        )
        for c in cases
    ]
