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


@router.post(
    "/trial/hearing-notice",
    response_model=schemas.CaseResponse,
)
def schedule_trial_hearing(
    case_id: str,
    claims: dict = Depends(require_role("court")),
    db: Session = Depends(get_db),
):
    """POST /cases/:id/trial/hearing-notice — Court. Moves investigation_status
    to Trial. Mirrors the bail hearing-notice pattern."""
    try:
        case_uuid = UUID(case_id)
    except ValueError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Case not found")

    case = db.get(models.Case, case_uuid)
    if case is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Case not found")

    if case.investigation_status != "Charge_Sheet_Filed":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot schedule trial hearing: case must be in 'Charge_Sheet_Filed' stage (current: '{case.investigation_status}')",
        )

    case.investigation_status = "Trial"
    db.commit()
    db.refresh(case)

    write_audit_log(
        db,
        action="trial_hearing_scheduled",
        case_id=case_uuid,
        actor_user_id=UUID(claims["sub"]),
        target_type="case",
        target_id=case.id,
    )

    return case


@router.post(
    "/judgment",
    response_model=schemas.CaseResponse,
)
def record_judgment(
    case_id: str,
    body: schemas.JudgmentRequest,
    claims: dict = Depends(require_role("court")),
    db: Session = Depends(get_db),
):
    """POST /cases/:id/judgment — Court. Moves investigation_status to
    Judgment — the terminal state for the investigation track."""
    try:
        case_uuid = UUID(case_id)
    except ValueError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Case not found")

    case = db.get(models.Case, case_uuid)
    if case is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Case not found")

    if case.investigation_status != "Trial":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot record judgment: case must be in 'Trial' stage (current: '{case.investigation_status}')",
        )

    verdict_clean = body.verdict.strip().lower()
    if verdict_clean not in ("acquitted", "convicted"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Verdict must be either 'acquitted' or 'convicted'",
        )

    case.investigation_status = "Judgment"
    db.commit()
    db.refresh(case)

    write_audit_log(
        db,
        action="judgment_recorded",
        case_id=case_uuid,
        actor_user_id=UUID(claims["sub"]),
        target_type="case",
        target_id=case.id,
        metadata={"verdict": verdict_clean, "summary": body.summary},
    )

    return case
