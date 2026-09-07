"""Bail track — see SYSTEM_DESIGN.md Flow 4. Runs entirely independently of
investigation_status; never gate one on the other."""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app import models, schemas
from app.audit import write_audit_log
from app.database import get_db
from app.security import (
    _UNRESTRICTED_CASE_ROLES,
    assert_case_access,
    get_current_claims,
    require_role,
)

router = APIRouter(prefix="/cases/{case_id}/bail", tags=["bail"])


@router.post(
    "/arrest",
    response_model=schemas.BailRecordResponse,
    status_code=status.HTTP_201_CREATED,
)
def record_arrest(
    case_id: str,
    claims: dict = Depends(require_role("io", "duty_officer", "sho")),
    db: Session = Depends(get_db),
):
    """POST /cases/:id/bail/arrest — Investigating Officer / Duty Officer / SHO.
    Record arrest. Starts the independent bail track (bail_status = Arrested)."""
    try:
        case_uuid = UUID(case_id)
    except ValueError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Case not found")

    case = db.get(models.Case, case_uuid)
    if case is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Case not found")

    assert_case_access(case_uuid, claims, db)

    if case.bail_status in ("Arrested", "Application_Filed", "Hearing_Scheduled", "Order_Issued", "Surety_Registered"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot record arrest: case is already in active bail stage '{case.bail_status}'",
        )

    case.bail_status = "Arrested"
    record = models.BailRecord(case_id=case_uuid, stage="Arrested")
    db.add(record)
    db.commit()
    db.refresh(record)

    write_audit_log(
        db,
        action="bail_arrest_recorded",
        case_id=case_uuid,
        actor_user_id=UUID(claims["sub"]),
        target_type="bail_record",
        target_id=record.id,
    )

    return record


@router.post(
    "/application",
    response_model=schemas.BailRecordResponse,
    status_code=status.HTTP_201_CREATED,
)
def file_bail_application(
    case_id: str,
    claims: dict = Depends(require_role("defense")),
    db: Session = Depends(get_db),
):
    """POST /cases/:id/bail/application — Defense (submission-only)."""
    try:
        case_uuid = UUID(case_id)
    except ValueError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Case not found")

    case = db.get(models.Case, case_uuid)
    if case is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Case not found")

    if case.bail_status not in ("Arrested", "Denied_Final"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot file bail application: accused must be arrested first (current stage: '{case.bail_status}')",
        )

    case.bail_status = "Application_Filed"
    record = models.BailRecord(case_id=case_uuid, stage="Application_Filed")
    db.add(record)
    db.commit()
    db.refresh(record)

    write_audit_log(
        db,
        action="bail_application_filed",
        case_id=case_uuid,
        actor_user_id=UUID(claims["sub"]),
        target_type="bail_record",
        target_id=record.id,
    )

    return record


@router.post(
    "/hearing-notice",
    response_model=schemas.BailRecordResponse,
    status_code=status.HTTP_201_CREATED,
)
def schedule_bail_hearing(
    case_id: str,
    claims: dict = Depends(require_role("court")),
    db: Session = Depends(get_db),
):
    """POST /cases/:id/bail/hearing-notice — Court."""
    try:
        case_uuid = UUID(case_id)
    except ValueError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Case not found")

    case = db.get(models.Case, case_uuid)
    if case is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Case not found")

    if case.bail_status != "Application_Filed":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot schedule bail hearing: application must be filed first (current stage: '{case.bail_status}')",
        )

    case.bail_status = "Hearing_Scheduled"
    record = models.BailRecord(case_id=case_uuid, stage="Hearing_Scheduled")
    db.add(record)
    db.commit()
    db.refresh(record)

    write_audit_log(
        db,
        action="bail_hearing_scheduled",
        case_id=case_uuid,
        actor_user_id=UUID(claims["sub"]),
        target_type="bail_record",
        target_id=record.id,
    )

    return record


@router.post(
    "/order",
    response_model=schemas.BailRecordResponse,
    status_code=status.HTTP_201_CREATED,
)
def issue_bail_order(
    case_id: str,
    body: schemas.BailOrderRequest,
    claims: dict = Depends(require_role("court")),
    db: Session = Depends(get_db),
):
    """POST /cases/:id/bail/order — Court. Issues grant or deny order."""
    try:
        case_uuid = UUID(case_id)
    except ValueError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Case not found")

    case = db.get(models.Case, case_uuid)
    if case is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Case not found")

    if case.bail_status != "Hearing_Scheduled":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot issue bail order: hearing has not been scheduled (current stage: '{case.bail_status}')",
        )

    stage = "Order_Issued" if body.granted else "Denied_Final"
    case.bail_status = stage
    record = models.BailRecord(case_id=case_uuid, stage=stage)
    db.add(record)
    db.commit()
    db.refresh(record)

    write_audit_log(
        db,
        action="bail_order_issued",
        case_id=case_uuid,
        actor_user_id=UUID(claims["sub"]),
        target_type="bail_record",
        target_id=record.id,
        metadata={"granted": body.granted, "conditions": body.conditions},
    )

    return record


@router.post(
    "/surety",
    response_model=schemas.BailRecordResponse,
    status_code=status.HTTP_201_CREATED,
)
def register_surety(
    case_id: str,
    body: Optional[schemas.BailSuretyRequest] = None,
    claims: dict = Depends(require_role("defense")),
    db: Session = Depends(get_db),
):
    """POST /cases/:id/bail/surety — Accused / Defense (submission-only)."""
    try:
        case_uuid = UUID(case_id)
    except ValueError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Case not found")

    case = db.get(models.Case, case_uuid)
    if case is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Case not found")

    if case.bail_status != "Order_Issued":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot register surety: bail has not been granted (current stage: '{case.bail_status}')",
        )

    case.bail_status = "Surety_Registered"
    record = models.BailRecord(case_id=case_uuid, stage="Surety_Registered")
    db.add(record)
    db.commit()
    db.refresh(record)

    metadata = {}
    if body:
        metadata = {"surety_name": body.surety_name, "bond_amount": body.bond_amount}

    write_audit_log(
        db,
        action="bail_surety_registered",
        case_id=case_uuid,
        actor_user_id=UUID(claims["sub"]),
        target_type="bail_record",
        target_id=record.id,
        metadata=metadata,
    )

    return record


@router.get(
    "",
    response_model=list[schemas.BailRecordResponse],
)
def list_bail_records(
    case_id: str,
    claims: dict = Depends(get_current_claims),
    db: Session = Depends(get_db),
):
    """GET /cases/:id/bail — List all historical bail records for a case."""
    try:
        case_uuid = UUID(case_id)
    except ValueError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Case not found")

    case = db.get(models.Case, case_uuid)
    if case is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Case not found")

    role = claims.get("role", "")
    if role not in ("defense", "court") and role not in _UNRESTRICTED_CASE_ROLES:
        assert_case_access(case_uuid, claims, db)

    return (
        db.query(models.BailRecord)
        .filter(models.BailRecord.case_id == case_uuid)
        .order_by(models.BailRecord.created_at.asc())
        .all()
    )


@router.get(
    "/pathway",
    summary="Fetch statutory bail pathway for a specific case's crime type",
)
def get_case_bail_pathway(
    case_id: str,
    claims: dict = Depends(get_current_claims),
    db: Session = Depends(get_db),
):
    """GET /cases/:id/bail/pathway — Returns the confirmed statutory bail pathway
    for the specific crime type of the case."""
    try:
        case_uuid = UUID(case_id)
    except ValueError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Case not found")

    case = db.get(models.Case, case_uuid)
    if case is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Case not found")

    role = claims.get("role", "")
    if role not in ("defense", "court") and role not in _UNRESTRICTED_CASE_ROLES:
        assert_case_access(case_uuid, claims, db)

    from app.bail_pathways import BAIL_PATHWAYS_TAXONOMY

    # Normalize crime type lookup
    crime_key = case.crime_type
    matched = None
    for k, v in BAIL_PATHWAYS_TAXONOMY.items():
        if k.lower() in crime_key.lower() or crime_key.lower() in k.lower():
            matched = {"crime_type": k, **v}
            break

    if not matched:
        matched = {"crime_type": crime_key, **BAIL_PATHWAYS_TAXONOMY["General Cognizable Offense"]}

    return {
        "case_id": str(case.id),
        "case_number": case.case_number,
        "current_bail_status": case.bail_status,
        "statutory_pathway": matched,
    }

