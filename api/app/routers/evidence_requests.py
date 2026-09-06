"""Evidence requests — see SYSTEM_DESIGN.md Flow 3 (parallel, AND-join)."""

import uuid
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app import models, schemas
from app.audit import write_audit_log
from app.config import settings
from app.database import get_db
from app.queue import QueueClient, get_queue
from app.routers.documents import _next_version
from app.security import (
    _UNRESTRICTED_CASE_ROLES,
    assert_case_access,
    get_current_claims,
    require_role,
    verify_evidence_request_org_access,
)
from app.storage import ObjectStorage, get_storage, object_key
from app.upload_validator import validate_upload_stream

router = APIRouter(tags=["evidence-requests"])


@router.post(
    "/cases/{case_id}/evidence-requests",
    response_model=schemas.EvidenceRequestResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_evidence_request(
    case_id: str,
    body: schemas.CreateEvidenceRequest,
    claims: dict = Depends(require_role("io", "sho")),
    db: Session = Depends(get_db),
):
    """POST /cases/:id/evidence-requests — IO / SHO. Create request to external org.
    One row per request — supports parallel N requests."""
    try:
        case_uuid = UUID(case_id)
    except ValueError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Case not found")

    case = db.get(models.Case, case_uuid)
    if case is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Case not found")

    assert_case_access(case_uuid, claims, db)

    target_org = db.get(models.Organization, body.requested_org_id)
    if target_org is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Requested organization not found")

    req = models.EvidenceRequest(
        case_id=case_uuid,
        requested_org_id=body.requested_org_id,
        doc_type_expected=body.doc_type_expected,
        status="requested",
    )
    db.add(req)
    db.commit()
    db.refresh(req)

    write_audit_log(
        db,
        action="evidence_requested",
        case_id=case_uuid,
        actor_user_id=UUID(claims["sub"]),
        target_type="evidence_request",
        target_id=req.id,
        metadata={
            "requested_org_id": str(body.requested_org_id),
            "doc_type_expected": body.doc_type_expected,
            "notes": body.notes,
        },
    )

    return req


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
    try:
        case_uuid = UUID(case_id)
    except ValueError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Case not found")

    case = db.get(models.Case, case_uuid)
    if case is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Case not found")

    role = claims.get("role", "")
    if role == "authority_staff":
        user_org_id = claims.get("org_id")
        if not user_org_id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Organization context missing")
        requests = (
            db.query(models.EvidenceRequest)
            .filter(
                models.EvidenceRequest.case_id == case_uuid,
                models.EvidenceRequest.requested_org_id == UUID(user_org_id),
            )
            .order_by(models.EvidenceRequest.created_at.desc())
            .all()
        )
        return requests

    # All other roles must pass case access
    assert_case_access(case_uuid, claims, db)

    return (
        db.query(models.EvidenceRequest)
        .filter(models.EvidenceRequest.case_id == case_uuid)
        .order_by(models.EvidenceRequest.created_at.desc())
        .all()
    )


@router.post(
    "/evidence-requests/{request_id}/submit",
    response_model=schemas.EvidenceRequestResponse,
)
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
    (see Flow 2) with pure-Python MIME validation and size cap.
    """
    req = verify_evidence_request_org_access(request_id, claims, db)

    if req.status == "completed":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Evidence request has already been fulfilled",
        )

    # 1. Streaming validation with magic-byte MIME sniffing and size capping
    validation = await validate_upload_stream(
        file,
        max_size_mb=getattr(settings, "MAX_UPLOAD_SIZE_MB", 50),
    )
    data = validation.data
    doc_hash = validation.sha256_hash
    is_binary = validation.is_binary_evidence

    doc_type = req.doc_type_expected or "Evidence"
    version = _next_version(db, req.case_id, doc_type)
    doc_id = uuid.uuid4()

    key = object_key(req.requested_org_id, req.case_id, doc_id, version)
    storage.put(key, data, content_type=validation.detected_mime)

    document = models.Document(
        id=doc_id,
        case_id=req.case_id,
        doc_type=doc_type,
        version=version,
        storage_path=key,
        doc_hash=doc_hash,
        status="ready" if is_binary else "processing",
        chain_status="pending",
        uploaded_by=UUID(claims["sub"]),
    )
    db.add(document)

    # Mark evidence request completed
    req.status = "completed"
    req.completed_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(req)

    # Deterministic worker dispatch
    idempotency_key = f"{document.id}:v{document.version}"
    queue_client.enqueue("chain_worker.write_hash", document_id=str(document.id), idempotency_key=idempotency_key)
    if not is_binary:
        queue_client.enqueue("ocr_worker.extract_document", document_id=str(document.id))

    write_audit_log(
        db,
        action="evidence_request_fulfilled",
        case_id=req.case_id,
        actor_user_id=UUID(claims["sub"]),
        target_type="evidence_request",
        target_id=req.id,
        metadata={
            "document_id": str(document.id),
            "doc_type": doc_type,
            "version": version,
            "doc_hash": doc_hash,
        },
    )

    return req
