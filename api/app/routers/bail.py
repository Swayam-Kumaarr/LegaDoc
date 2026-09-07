"""Bail track — see SYSTEM_DESIGN.md Flow 4. Runs entirely independently of
investigation_status; never gate one on the other."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app import models, schemas
from app.audit import write_audit_log
from app.database import get_db
from app.security import assert_case_access, require_role

router = APIRouter(prefix="/cases/{case_id}/bail", tags=["bail"])


@router.post("/arrest", response_model=schemas.BailRecordResponse, status_code=status.HTTP_201_CREATED)
def record_arrest(
    case_id: str,
    claims: dict = Depends(require_role("io", "duty_officer")),
    db: Session = Depends(get_db),
):
    """POST /cases/:id/bail/arrest — Investigating Officer / Duty Officer.
    Record arrest. Starts the independent bail track (bail_status = Arrested)."""
    case_uuid = UUID(case_id)
    case = db.get(models.Case, case_uuid)
    if case is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")

    assert_case_access(case_uuid, claims, db)

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


@router.post("/application", response_model=schemas.BailRecordResponse, status_code=status.HTTP_201_CREATED)
def file_bail_application(
    case_id: str,
    claims: dict = Depends(require_role("defense")),
    db: Session = Depends(get_db),
):
    """POST /cases/:id/bail/application — Defense (submission-only)."""
    case_uuid = UUID(case_id)
    case = db.get(models.Case, case_uuid)
    if case is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")

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


@router.post("/hearing-notice", response_model=schemas.BailRecordResponse, status_code=status.HTTP_201_CREATED)
def schedule_bail_hearing(
    case_id: str,
    claims: dict = Depends(require_role("court")),
    db: Session = Depends(get_db),
):
    """POST /cases/:id/bail/hearing-notice — Court."""
    case_uuid = UUID(case_id)
    case = db.get(models.Case, case_uuid)
    if case is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")

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


@router.post("/order", response_model=schemas.BailRecordResponse, status_code=status.HTTP_201_CREATED)
def issue_bail_order(
    case_id: str,
    body: schemas.BailOrderRequest,
    claims: dict = Depends(require_role("court")),
    db: Session = Depends(get_db),
):
    """POST /cases/:id/bail/order — Court. Same role as hearing-notice;
    differentiated by audit-log action, not a separate "Judge" role."""
    case_uuid = UUID(case_id)
    case = db.get(models.Case, case_uuid)
    if case is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")

    stage_map = {
        "granted": "Order_Issued",
        "denied": "Denied_Final",
        "absconded": "Absconded",
    }
    stage = stage_map.get(body.decision)
    if stage is None:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Decision must be granted, denied, or absconded")

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
        metadata={"decision": body.decision},
    )

    return record


@router.post("/surety", response_model=schemas.BailRecordResponse, status_code=status.HTTP_201_CREATED)
def register_surety(
    case_id: str,
    claims: dict = Depends(require_role("defense")),
    db: Session = Depends(get_db),
):
    """POST /cases/:id/bail/surety — Accused (submission-only)."""
    case_uuid = UUID(case_id)
    case = db.get(models.Case, case_uuid)
    if case is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")

    case.bail_status = "Surety_Registered"
    record = models.BailRecord(case_id=case_uuid, stage="Surety_Registered")
    db.add(record)
    db.commit()
    db.refresh(record)

    write_audit_log(
        db,
        action="bail_surety_registered",
        case_id=case_uuid,
        actor_user_id=UUID(claims["sub"]),
        target_type="bail_record",
        target_id=record.id,
    )

    return record
