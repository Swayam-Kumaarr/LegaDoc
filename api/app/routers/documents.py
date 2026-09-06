"""Documents — see SYSTEM_DESIGN.md Flow 2 (the core technical differentiator:
upload -> OCR -> AI Parser redaction -> blockchain hash-write, two parallel tracks).

Scope actually implemented in this pass: upload (storage + DB row + job
dispatch), read with redaction-view masking, versions, chain-status, and the
officer correction path (redact-tag). The OCR/AI-Parser/Chain Worker task
BODIES stay stubs (workers/*/worker.py) — this environment has no PaddleOCR
model, no Presidio/spaCy model, and no Fabric network to verify them
against. `needs_review` filtering and retry-chain-write remain stubs too,
deliberately deferred to keep this slice fully tested rather than partially
faked.
"""

import uuid
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy.orm import Session

from app import models, schemas
from app.audit import write_audit_log
from app.config import settings
from app.database import get_db
from app.queue import QueueClient, get_queue
from app.redaction import get_document_view
from app.security import FULL_TEXT_ACCESS_ROLES, assert_case_access, get_current_claims, require_role
from app.storage import ObjectStorage, get_storage, object_key, sha256_hex
from app.upload_validator import validate_upload_stream

router = APIRouter(prefix="/documents", tags=["documents"])


def _next_version(db: Session, case_id: UUID, doc_type: str) -> int:
    latest = (
        db.query(models.Document)
        .filter(models.Document.case_id == case_id, models.Document.doc_type == doc_type)
        .order_by(models.Document.version.desc())
        .first()
    )
    return (latest.version + 1) if latest else 1


@router.post("", response_model=schemas.DocumentUploadResponse, status_code=status.HTTP_202_ACCEPTED)
async def upload_document(
    case_id: str = Form(...),
    doc_type: str = Form(...),
    file: UploadFile = File(...),
    claims: dict = Depends(get_current_claims),
    db: Session = Depends(get_db),
    storage: ObjectStorage = Depends(get_storage),
    queue_client: QueueClient = Depends(get_queue),
):
    """POST /documents — multipart. Upload document or binary evidence.

    Security & Validation Enhancements:
    - Enforces UPLOAD_ALLOWED_ROLES allowlist check.
    - Streaming magic-byte MIME detection (python-magic) preventing extension spoofing.
    - Early abort on streaming size cap exceeding MAX_UPLOAD_SIZE_MB (default: 50MB).
    - SHA-256 deduplication: returns existing document if identical hash uploaded.
    - Dual-track worker dispatch (Track A: Blockchain, Track B: OCR for text).
    """
    allowed_roles = [r.strip() for r in getattr(settings, "UPLOAD_ALLOWED_ROLES", "").split(",") if r.strip()]
    if allowed_roles and claims.get("role") not in allowed_roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Role '{claims.get('role')}' is not authorized to upload evidence",
        )

    try:
        case_uuid = UUID(case_id)
    except ValueError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Case not found")

    case = db.get(models.Case, case_uuid)
    if case is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Case not found")

    assert_case_access(case_uuid, claims, db)

    # 1. Streaming validation with magic-byte MIME sniffing and size capping
    validation = await validate_upload_stream(
        file,
        max_size_mb=getattr(settings, "MAX_UPLOAD_SIZE_MB", 50),
    )
    data = validation.data
    doc_hash = validation.sha256_hash
    is_binary = validation.is_binary_evidence

    # 2. Deduplication check — if exact file content already uploaded for this case & doc_type, return existing
    existing = (
        db.query(models.Document)
        .filter(
            models.Document.case_id == case_uuid,
            models.Document.doc_type == doc_type,
            models.Document.doc_hash == doc_hash,
        )
        .first()
    )
    if existing:
        return existing

    version = _next_version(db, case_uuid, doc_type)
    doc_id = uuid.uuid4()

    user = db.get(models.User, UUID(claims["sub"]))
    org_id = user.org_id if user else case_uuid  # fallback keeps the path stable even if user lookup ever fails

    key = object_key(org_id, case_uuid, doc_id, version)
    storage.put(key, data, content_type=validation.detected_mime)

    document = models.Document(
        id=doc_id,
        case_id=case_uuid,
        doc_type=doc_type,
        version=version,
        storage_path=key,
        doc_hash=doc_hash,
        status="ready" if is_binary else "processing",
        chain_status="pending",
        uploaded_by=UUID(claims["sub"]),
    )
    db.add(document)
    db.commit()
    db.refresh(document)

    # Deterministic, not random — a retry derives the exact same key from
    # the same (document_id, version) pair.
    idempotency_key = f"{document.id}:v{document.version}"

    # Track A — always, independent of Track B. See System Connections #8.
    queue_client.enqueue("chain_worker.write_hash", document_id=str(document.id), idempotency_key=idempotency_key)
    # Track B — text-bearing documents only. See System Connections #6.
    if not is_binary:
        queue_client.enqueue("ocr_worker.extract_document", document_id=str(document.id))

    write_audit_log(
        db,
        action="document_uploaded",
        case_id=case_uuid,
        actor_user_id=UUID(claims["sub"]),
        target_type="document",
        target_id=document.id,
        metadata={
            "doc_type": doc_type,
            "version": version,
            "content_type": validation.detected_mime,
            "is_binary": is_binary,
            "doc_hash": doc_hash,
        },
    )

    return document


@router.get("", response_model=list[schemas.DocumentReviewItem])
def list_documents_needing_review(
    status_filter: Optional[str] = Query(default="needs_review", alias="status"),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    claims: dict = Depends(require_role("config_admin", "io")),
    db: Session = Depends(get_db),
):
    """GET /documents?status=needs_review — Config Admin / Investigating
    Officer. Lists documents flagged for manual review or falling back from OCR/AI-Parser.
    - When called by an IO: scoped strictly to cases assigned to that IO.
    - When called by Config Admin: across all cases.
    - raw_text is structurally excluded from the list schema to prevent bulk PII leaks.
    """
    target_status = status_filter if status_filter is not None else "needs_review"
    if target_status not in ("needs_review", "processing", "ready"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid document status filter '{target_status}'. Must be one of: needs_review, processing, ready",
        )

    query = db.query(models.Document).filter(models.Document.status == target_status)

    user_role = claims.get("role")
    if user_role == "io":
        user_id = UUID(claims["sub"])
        query = query.join(
            models.CaseAssignment,
            models.CaseAssignment.case_id == models.Document.case_id,
        ).filter(models.CaseAssignment.io_user_id == user_id)

    # Order FIFO (oldest first) so review backlogs don't starve
    docs = query.order_by(models.Document.created_at.asc()).offset(offset).limit(limit).all()

    return docs


@router.get("/{document_id}", response_model=schemas.DocumentView)
def get_document(
    document_id: str,
    claims: dict = Depends(get_current_claims),
    db: Session = Depends(get_db),
    storage: ObjectStorage = Depends(get_storage),
):
    """GET /documents/:id — Role-filtered. Returns the redacted or full view
    per auto-tagged sensitivity spans + role, via app.redaction — never a
    bespoke redacted-vs-full branch written ad hoc in this handler."""
    document = db.get(models.Document, UUID(document_id))
    if document is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")

    assert_case_access(document.case_id, claims, db)

    tags = db.query(models.DocumentSensitivityTag).filter(models.DocumentSensitivityTag.document_id == document.id).all()
    view = get_document_view(document, tags, claims.get("role"), FULL_TEXT_ACCESS_ROLES)
    download_url = storage.get_presigned_url(document.storage_path) if document.storage_path else None

    return schemas.DocumentView(
        id=document.id,
        case_id=document.case_id,
        doc_type=document.doc_type,
        version=document.version,
        status=document.status,
        chain_status=document.chain_status,
        retention_legal_hold=document.retention_legal_hold or False,
        text=view["text"],
        download_url=download_url,
        doc_hash=document.doc_hash,
    )



@router.get("/{document_id}/versions", response_model=list[schemas.DocumentVersionSummary])
def get_document_versions(document_id: str, claims: dict = Depends(get_current_claims), db: Session = Depends(get_db)):
    """GET /documents/:id/versions — Role-filtered. Version history.
    Append-only — originals never overwritten."""
    document = db.get(models.Document, UUID(document_id))
    if document is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")

    assert_case_access(document.case_id, claims, db)

    return (
        db.query(models.Document)
        .filter(models.Document.case_id == document.case_id, models.Document.doc_type == document.doc_type)
        .order_by(models.Document.version.asc())
        .all()
    )


@router.get("/{document_id}/chain-status", response_model=schemas.ChainStatusResponse)
def get_chain_status(document_id: str, claims: dict = Depends(get_current_claims), db: Session = Depends(get_db)):
    """GET /documents/:id/chain-status — Role-filtered. Poll blockchain
    confirmation. Short-poll target for Flow 2."""
    document = db.get(models.Document, UUID(document_id))
    if document is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")

    assert_case_access(document.case_id, claims, db)

    return schemas.ChainStatusResponse(document_id=document.id, chain_status=document.chain_status)


@router.post("/{document_id}/retry-chain-write")
def retry_chain_write(
    document_id: str,
    claims: dict = Depends(require_role("config_admin")),
    db: Session = Depends(get_db),
    queue_client: QueueClient = Depends(get_queue),
):
    """POST /documents/:id/retry-chain-write — Config Admin. Manually
    re-trigger a stuck chain-write. Reuses the SAME deterministic
    idempotency key the original upload used (see upload_document above) —
    never mints a new one, so if Fabric actually confirmed the transaction
    before a prior crash, the chaincode's own idempotent RecordHash (see
    hashledger.go) plus this same key together prevent a duplicate ledger
    entry. A no-op if the document is already confirmed.
    """
    document = db.get(models.Document, UUID(document_id))
    if document is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")

    if document.chain_status == "confirmed":
        return {"chain_status": "confirmed", "retry_enqueued": False, "note": "already confirmed, nothing to retry"}

    idempotency_key = f"{document.id}:v{document.version}"
    queue_client.enqueue("chain_worker.write_hash", document_id=str(document.id), idempotency_key=idempotency_key)

    write_audit_log(
        db,
        action="chain_write_retry_triggered",
        case_id=document.case_id,
        actor_user_id=UUID(claims["sub"]),
        target_type="document",
        target_id=document.id,
        metadata={"idempotency_key": idempotency_key},
    )

    return {"chain_status": document.chain_status, "retry_enqueued": True, "idempotency_key": idempotency_key}


@router.post("/{document_id}/redact-tag", response_model=schemas.DocumentView)
def correct_redaction_tag(
    document_id: str,
    body: schemas.RedactTagRequest,
    claims: dict = Depends(require_role("io")),
    db: Session = Depends(get_db),
):
    """POST /documents/:id/redact-tag — Investigating Officer (assigned to
    this document's case — checked via assert_case_access, role alone isn't
    enough). Correct/override an AI Parser sensitivity tag. Writes an
    audit_log entry recording the span that was corrected — never the
    underlying text, same rule as every other tag write in this system.
    """
    document = db.get(models.Document, UUID(document_id))
    if document is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")

    assert_case_access(document.case_id, claims, db)

    tag = models.DocumentSensitivityTag(
        document_id=document.id,
        entity_type=body.entity_type,
        span_start=body.span_start,
        span_end=body.span_end,
        confidence=None,
        source="officer_correction",
    )
    db.add(tag)
    db.commit()

    write_audit_log(
        db,
        action="redact_tag_correction",
        case_id=document.case_id,
        actor_user_id=UUID(claims["sub"]),
        target_type="document",
        target_id=document.id,
        metadata={"entity_type": body.entity_type, "span_start": body.span_start, "span_end": body.span_end},
    )

    tags = db.query(models.DocumentSensitivityTag).filter(models.DocumentSensitivityTag.document_id == document.id).all()
    view = get_document_view(document, tags, claims.get("role"), FULL_TEXT_ACCESS_ROLES)
    return schemas.DocumentView(
        id=document.id,
        case_id=document.case_id,
        doc_type=document.doc_type,
        version=document.version,
        status=document.status,
        chain_status=document.chain_status,
        retention_legal_hold=document.retention_legal_hold or False,
        text=view["text"],
    )


@router.post("/{document_id}/legal-hold", response_model=schemas.LegalHoldResponse)
def set_document_legal_hold(
    document_id: str,
    body: schemas.LegalHoldRequest,
    claims: dict = Depends(require_role("court", "prosecutor", "sho", "config_admin")),
    db: Session = Depends(get_db),
):
    """POST /documents/:id/legal-hold — Court, Prosecutor, SHO, or Config Admin.
    Places or releases an evidentiary retention legal hold on a document.
    When active, the document is protected against deletion/purging (HTTP 409).
    """
    try:
        doc_uuid = UUID(document_id)
    except ValueError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")

    document = db.get(models.Document, doc_uuid)
    if document is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")

    assert_case_access(document.case_id, claims, db)

    document.retention_legal_hold = body.legal_hold
    db.commit()
    db.refresh(document)

    action = "document_legal_hold_placed" if body.legal_hold else "document_legal_hold_released"
    write_audit_log(
        db,
        action=action,
        case_id=document.case_id,
        actor_user_id=UUID(claims["sub"]),
        target_type="document",
        target_id=document.id,
        metadata={"reason": body.reason, "legal_hold": body.legal_hold},
    )

    return schemas.LegalHoldResponse(
        document_id=document.id,
        case_id=document.case_id,
        retention_legal_hold=document.retention_legal_hold,
        status=document.status,
    )


@router.delete("/{document_id}", status_code=status.HTTP_200_OK)
def delete_document(
    document_id: str,
    claims: dict = Depends(require_role("court", "config_admin")),
    db: Session = Depends(get_db),
    storage: ObjectStorage = Depends(get_storage),
):
    """DELETE /documents/:id — Court or Config Admin.
    Permanently purges a document and its stored object, PROVIDED no retention legal hold is active.
    If retention_legal_hold is True, deletion is strictly prohibited and returns HTTP 409 Conflict.
    """
    try:
        doc_uuid = UUID(document_id)
    except ValueError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")

    document = db.get(models.Document, doc_uuid)
    if document is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")

    assert_case_access(document.case_id, claims, db)

    if document.retention_legal_hold:
        write_audit_log(
            db,
            action="document_deletion_blocked_legal_hold",
            case_id=document.case_id,
            actor_user_id=UUID(claims["sub"]),
            target_type="document",
            target_id=document.id,
            metadata={"reason": "Active retention legal hold prevents destruction"},
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Document is subject to an active retention legal hold and cannot be deleted or purged.",
        )

    # Clean up physical storage object
    if document.storage_path:
        storage.delete(document.storage_path)

    # Delete any related sensitivity tags
    db.query(models.DocumentSensitivityTag).filter(models.DocumentSensitivityTag.document_id == document.id).delete()

    write_audit_log(
        db,
        action="document_purged",
        case_id=document.case_id,
        actor_user_id=UUID(claims["sub"]),
        target_type="document",
        target_id=document.id,
        metadata={"doc_type": document.doc_type, "version": document.version},
    )

    db.delete(document)
    db.commit()

    return {"detail": "Document successfully purged", "document_id": str(doc_uuid)}

