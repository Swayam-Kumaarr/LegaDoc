"""Evidence requests — see SYSTEM_DESIGN.md Flow 3 (parallel, AND-join)."""

import uuid
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app import models, schemas
from app.audit import write_audit_log
from app.database import get_db
from app.queue import QueueClient, get_queue
from app.security import assert_case_access, get_current_claims, require_role
from app.storage import ObjectStorage, get_storage, object_key, sha256_hex

router = APIRouter(tags=["evidence-requests"])


@router.post(
    "/cases/{case_id}/evidence-requests",
    response_model=schemas.EvidenceRequestResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_evidence_request(
    case_id: str,
    body: schemas.EvidenceRequestCreate,
    claims: dict = Depends(require_role("io")),
    db: Session = Depends(get_db),
):
    """POST /cases/:id/evidence-requests — IO. Create request to external org.
    One row per request — supports parallel N requests."""
    case_uuid = UUID(case_id)
    case = db.get(models.Case, case_uuid)
    if case is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")

    assert_case_access(case_uuid, claims, db)

    target_org = db.get(models.Organization, body.requested_org_id)
    if target_org is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Target organization not found")

    er = models.EvidenceRequest(
        case_id=case_uuid,
        requested_org_id=body.requested_org_id,
        doc_type_expected=body.doc_type_expected,
        status="requested",
    )
    db.add(er)
    db.commit()
    db.refresh(er)

    write_audit_log(
        db,
        action="evidence_request_created",
        case_id=case_uuid,
        actor_user_id=UUID(claims["sub"]),
        target_type="evidence_request",
        target_id=er.id,
        metadata={
            "requested_org_id": str(body.requested_org_id),
            "doc_type_expected": body.doc_type_expected,
        },
    )

    return er


@router.get(
    "/cases/{case_id}/evidence-requests",
    response_model=list[schemas.EvidenceRequestResponse],
)
def list_evidence_requests(
    case_id: str,
    claims: dict = Depends(get_current_claims),
    db: Session = Depends(get_db),
):
    """GET /cases/:id/evidence-requests — IO / relevant Authority. List requests + status."""
    case_uuid = UUID(case_id)
    case = db.get(models.Case, case_uuid)
    if case is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")

    assert_case_access(case_uuid, claims, db)

    query = db.query(models.EvidenceRequest).filter(models.EvidenceRequest.case_id == case_uuid)

    role = claims.get("role")
    if role not in {"config_admin", "security_auditor", "court", "prosecutor", "sho", "io"}:
        user = db.get(models.User, UUID(claims["sub"]))
        if user:
            query = query.filter(models.EvidenceRequest.requested_org_id == user.org_id)

    return query.order_by(models.EvidenceRequest.created_at.asc()).all()


@router.post("/evidence-requests/{request_id}/submit", status_code=status.HTTP_202_ACCEPTED)
async def submit_evidence_request(
    request_id: str,
    file: UploadFile = File(...),
    claims: dict = Depends(get_current_claims),
    db: Session = Depends(get_db),
    storage: ObjectStorage = Depends(get_storage),
    queue_client: QueueClient = Depends(get_queue),
):
    """POST /evidence-requests/:id/submit — The specific requested Authority.
    Fulfill request, attach document. Triggers the document upload pipeline
    (see Flow 2) — this endpoint itself should call into the same upload path
    as POST /documents, not duplicate it."""
    er = db.get(models.EvidenceRequest, UUID(request_id))
    if er is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Evidence request not found")

    if er.status == "completed":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Evidence request already completed")

    user = db.get(models.User, UUID(claims["sub"]))
    if user is None or user.org_id != er.requested_org_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to fulfill this request")

    data = await file.read()
    doc_hash = sha256_hex(data)
    doc_id = uuid.uuid4()

    latest = (
        db.query(models.Document)
        .filter(models.Document.case_id == er.case_id, models.Document.doc_type == "Evidence")
        .order_by(models.Document.version.desc())
        .first()
    )
    version = (latest.version + 1) if latest else 1

    key = object_key(user.org_id, er.case_id, doc_id, version)
    storage.put(key, data)

    document = models.Document(
        id=doc_id,
        case_id=er.case_id,
        doc_type=er.doc_type_expected or "Evidence",
        version=version,
        storage_path=key,
        doc_hash=doc_hash,
        status="processing",
        chain_status="pending",
        uploaded_by=UUID(claims["sub"]),
    )
    db.add(document)

    er.status = "completed"
    er.completed_at = models.func.now()

    db.commit()
    db.refresh(document)
    db.refresh(er)

    idempotency_key = f"{document.id}:v{document.version}"
    queue_client.enqueue("chain_worker.write_hash", document_id=str(document.id), idempotency_key=idempotency_key)
    queue_client.enqueue("ocr_worker.extract_document", document_id=str(document.id))

    write_audit_log(
        db,
        action="evidence_request_fulfilled",
        case_id=er.case_id,
        actor_user_id=UUID(claims["sub"]),
        target_type="evidence_request",
        target_id=er.id,
        metadata={"document_id": str(doc_id)},
    )

    return {"evidence_request_id": request_id, "document_id": str(doc_id), "status": "completed"}
