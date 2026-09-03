"""Trial / judgment — court disposition, see SYSTEM_DESIGN.md Flow 5.
Closes the investigation-track state diagram's final transition."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app import models, schemas
from app.audit import write_audit_log
from app.database import get_db
from app.security import require_role

router = APIRouter(prefix="/cases/{case_id}", tags=["trial"])


@router.post("/trial/hearing-notice")
def schedule_trial_hearing(
    case_id: str,
    claims: dict = Depends(require_role("court")),
    db: Session = Depends(get_db),
):
    """POST /cases/:id/trial/hearing-notice — Court. Moves investigation_status
    to Trial. Mirrors the bail hearing-notice pattern."""
    case_uuid = UUID(case_id)
    case = db.get(models.Case, case_uuid)
    if case is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")

    case.investigation_status = "Trial"
    db.commit()

    write_audit_log(
        db,
        action="trial_hearing_scheduled",
        case_id=case_uuid,
        actor_user_id=UUID(claims["sub"]),
        target_type="case",
        target_id=case_uuid,
    )

    return {"case_id": case_id, "investigation_status": case.investigation_status}


@router.post("/judgment")
def record_judgment(
    case_id: str,
    body: schemas.JudgmentRequest,
    claims: dict = Depends(require_role("court")),
    db: Session = Depends(get_db),
):
    """POST /cases/:id/judgment — Court. Moves investigation_status to
    Judgment — the terminal state for the investigation track."""
    case_uuid = UUID(case_id)
    case = db.get(models.Case, case_uuid)
    if case is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")

    case.investigation_status = "Judgment"
    db.commit()

    write_audit_log(
        db,
        action="judgment_recorded",
        case_id=case_uuid,
        actor_user_id=UUID(claims["sub"]),
        target_type="case",
        target_id=case_uuid,
        metadata={"verdict": body.verdict} if body.verdict else None,
    )

    return {"case_id": case_id, "investigation_status": case.investigation_status}
