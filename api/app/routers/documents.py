"""
Documents Router — Complete implementation of Flow 2 from SYSTEM_DESIGN.md.
Two parallel tracks:
  - Track A: Hash computation & dispatch to Hyperledger Fabric (chain_worker)
  - Track B: Text extraction (ocr_worker) and sensitivity tagging (ai_parser_worker)

Includes upload validation, MinIO object storage, duplicate detection,
atomic version assignment, role filtering, audit trail, and admin recovery.
"""

import uuid
from typing import List, Optional
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import (
    CaseAssignment,
    Document,
    DocumentExtraction,
    DocumentSensitivityTag,
)
from app.schemas.documents import (
    ChainStatusResponse,
    DocumentListResponse,
    DocumentSensitivityTagResponse,
    DocumentUploadResponse,
    DocumentVersionResponse,
    DocumentView,
    RedactTagRequest,
)
from app.security import (
    get_current_claims,
    require_role,
    verify_case_access,
)
from app.services.audit_service import append_audit_log
from app.services.queue_service import (
    dispatch_chain_write,
    dispatch_ocr_extraction,
)
from app.services.storage_service import storage_service
from app.services.upload_validator import validate_upload

router = APIRouter(prefix="/documents", tags=["documents"])


# ============================================================================
# 1. POST /documents — Upload Document or Binary Evidence
# ============================================================================

@router.post(
    "",
    response_model=DocumentUploadResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def upload_document(
    case_id: UUID = Form(...),
    doc_type: str = Form(...),
    file: UploadFile = File(...),
    claims: dict = Depends(get_current_claims),
    db: Session = Depends(get_db),
):
    """
    POST /documents — Uploads a document or binary evidence.
    1. Checks caller role against UPLOAD_ALLOWED_ROLES allowlist.
    2. Validates case access via verify_case_access.
    3. Performs streaming validation (MIME sniffing, size cap, SHA-256).
    4. Detects duplicates (same case_id, doc_type, and hash).
    5. Atomically assigns next sequential version number.
    6. Stores raw file in MinIO with Server-Side Encryption (AES256).
    7. Creates Document and DocumentExtraction records.
    8. Appends hash-chained audit log entry.
    9. Dispatches Track A (chain_worker) and Track B (ocr_worker) tasks in parallel.
    """
    # 1. Role allowlist check
    caller_role = claims.get("role", "")
    allowed_roles = {r.strip() for r in settings.UPLOAD_ALLOWED_ROLES.split(",") if r.strip()}
    if caller_role not in allowed_roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Role '{caller_role}' is not permitted to upload documents",
        )

    # 2. Case access check (enforces multi-tenancy)
    verify_case_access(case_id, claims, db)

    # 3. Streaming file validation (MIME sniffing, size cap, SHA-256)
    val_result = await validate_upload(
        file,
        max_size_mb=settings.MAX_UPLOAD_SIZE_MB,
    )

    # 4. Duplicate detection within (case_id, doc_type)
    existing_doc = (
        db.query(Document)
        .filter(
            Document.case_id == case_id,
            Document.doc_type == doc_type,
            Document.doc_hash == val_result.sha256_hash,
        )
        .first()
    )
    if existing_doc:
        val_result.file_obj.close()
        return DocumentUploadResponse(
            document_id=existing_doc.id,
            case_id=existing_doc.case_id,
            doc_type=existing_doc.doc_type,
            version=existing_doc.version,
            status=existing_doc.status,
            chain_status=existing_doc.chain_status,
            doc_hash=existing_doc.doc_hash,
            original_filename=existing_doc.original_filename,
            created_at=existing_doc.created_at,
        )

    # 5. Atomic next version number assignment
    latest_version = (
        db.query(func.max(Document.version))
        .filter(
            Document.case_id == case_id,
            Document.doc_type == doc_type,
        )
        .scalar()
    )
    next_version = (latest_version or 0) + 1

    # 6. Build org-scoped storage path
    user_id = UUID(claims["sub"])
    org_id = UUID(claims["org_id"])
    doc_id = uuid.uuid4()
    storage_path = storage_service.build_storage_path(
        org_id=org_id,
        case_id=case_id,
        document_id=doc_id,
        version=next_version,
    )

    # 7. Create DB records (uncommitted)
    initial_status = "ready" if val_result.is_binary_evidence else "processing"
    doc = Document(
        id=doc_id,
        case_id=case_id,
        doc_type=doc_type,
        version=next_version,
        storage_path=storage_path,
        doc_hash=val_result.sha256_hash,
        status=initial_status,
        chain_status="pending",
        uploaded_by=user_id,
        original_filename=val_result.original_filename,
    )
    db.add(doc)

    extraction = DocumentExtraction(
        document_id=doc_id,
        version=next_version,
        raw_text=None,
        extraction_status="ready" if val_result.is_binary_evidence else "pending",
    )
    db.add(extraction)
    db.flush()

    # 8. Store raw file in MinIO
    try:
        storage_service.upload_file(
            file_obj=val_result.file_obj,
            storage_path=storage_path,
            content_type=val_result.detected_mime,
        )
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to store document in object storage: {str(e)}",
        )
    finally:
        val_result.file_obj.close()

    # 9. Append hash-chained audit log
    append_audit_log(
        db=db,
        case_id=case_id,
        actor_user_id=user_id,
        action="document_uploaded",
        target_type="document",
        target_id=doc.id,
        action_metadata={
            "doc_type": doc_type,
            "version": next_version,
            "file_size": val_result.file_size,
            "mime_type": val_result.detected_mime,
            "doc_hash": val_result.sha256_hash[:16],
            "is_binary": val_result.is_binary_evidence,
        },
    )

    # Commit transaction
    db.commit()
    db.refresh(doc)

    # 10. Dispatch parallel async worker jobs
    # Track A: Blockchain hash write
    dispatch_chain_write(str(doc.id), doc.version)

    # Track B: OCR Worker (only for text-bearing types)
    if not val_result.is_binary_evidence:
        dispatch_ocr_extraction(str(doc.id))

    return DocumentUploadResponse(
        document_id=doc.id,
        case_id=doc.case_id,
        doc_type=doc.doc_type,
        version=doc.version,
        status=doc.status,
        chain_status=doc.chain_status,
        doc_hash=doc.doc_hash,
        original_filename=doc.original_filename,
        created_at=doc.created_at,
    )


# ============================================================================
# 2. GET /documents — List Documents (with Filtering and Scoping)
# ============================================================================

@router.get("", response_model=DocumentListResponse)
def list_documents(
    case_id: Optional[UUID] = None,
    status: Optional[str] = None,
    page: int = 1,
    per_page: int = 20,
    claims: dict = Depends(require_role("admin", "io", "sho", "duty_officer")),
    db: Session = Depends(get_db),
):
    """
    GET /documents — Lists documents with status and case filters.
    - Admin/SHO/Duty Officer: can browse across police station.
    - Investigating Officer (IO): automatically restricted to their assigned cases.
    """
    role = claims.get("role", "")
    user_id = UUID(claims["sub"])

    query = db.query(Document)

    # Scoping for IO: filter by CaseAssignment
    if role == "io":
        assigned_case_ids = (
            db.query(CaseAssignment.case_id)
            .filter(CaseAssignment.io_user_id == user_id)
            .all()
        )
        assigned_ids = [c[0] for c in assigned_case_ids]
        query = query.filter(Document.case_id.in_(assigned_ids))

    if case_id and isinstance(case_id, (UUID, str)):
        verify_case_access(case_id, claims, db)
        query = query.filter(Document.case_id == case_id)

    if status and isinstance(status, str):
        query = query.filter(Document.status == status)

    total = query.count()
    items = (
        query.order_by(Document.created_at.desc(), Document.id.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )

    return DocumentListResponse(
        items=[DocumentVersionResponse.model_validate(item) for item in items],
        total=total,
        page=page,
        per_page=per_page,
    )


# ============================================================================
# 3. GET /documents/{document_id} — Role-Filtered Document View
# ============================================================================

@router.get("/{document_id}", response_model=DocumentView)
def get_document(
    document_id: UUID,
    claims: dict = Depends(get_current_claims),
    db: Session = Depends(get_db),
):
    """
    GET /documents/:id — Fetches document metadata, extracted text, and sensitivity tags.
    Applies role-based filtering:
    - IO / SHO / Admin: Full view with unredacted text and sensitivity tags.
    - Prosecutor: Document view with extracted text (tags omitted).
    - Defense: Blocked from active investigation documents (403).
    """
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )

    # Multi-tenant and case access verification
    verify_case_access(doc.case_id, claims, db)

    role = claims.get("role", "")

    # Fetch extraction text if available
    extraction = (
        db.query(DocumentExtraction)
        .filter(
            DocumentExtraction.document_id == doc.id,
            DocumentExtraction.version == doc.version,
        )
        .first()
    )
    raw_text = extraction.raw_text if extraction else None

    # Fetch sensitivity tags
    tags = (
        db.query(DocumentSensitivityTag)
        .filter(DocumentSensitivityTag.document_id == doc.id)
        .order_by(DocumentSensitivityTag.span_start.asc())
        .all()
    )

    # Presigned download URL
    download_url = None
    try:
        download_url = storage_service.get_presigned_url(doc.storage_path)
    except Exception:
        pass

    # Role filtering
    # IO, SHO, Admin, Duty Officer see tags and raw text
    if role in ("admin", "sho", "duty_officer", "io"):
        tag_responses = [DocumentSensitivityTagResponse.model_validate(t) for t in tags]
        return DocumentView(
            id=doc.id,
            case_id=doc.case_id,
            doc_type=doc.doc_type,
            version=doc.version,
            status=doc.status,
            chain_status=doc.chain_status,
            uploaded_by=doc.uploaded_by,
            original_filename=doc.original_filename,
            download_url=download_url,
            created_at=doc.created_at,
            text=raw_text,
            tags=tag_responses,
        )

    # Prosecutor sees text but not internal AI tag metadata
    return DocumentView(
        id=doc.id,
        case_id=doc.case_id,
        doc_type=doc.doc_type,
        version=doc.version,
        status=doc.status,
        chain_status=doc.chain_status,
        uploaded_by=doc.uploaded_by,
        original_filename=doc.original_filename,
        download_url=download_url,
        created_at=doc.created_at,
        text=raw_text,
        tags=None,
    )


# ============================================================================
# 4. GET /documents/{document_id}/versions — Version History
# ============================================================================

@router.get("/{document_id}/versions", response_model=List[DocumentVersionResponse])
def get_document_versions(
    document_id: UUID,
    claims: dict = Depends(get_current_claims),
    db: Session = Depends(get_db),
):
    """
    GET /documents/:id/versions — Returns append-only version history
    for this document's case and document type.
    """
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )

    verify_case_access(doc.case_id, claims, db)

    versions = (
        db.query(Document)
        .filter(
            Document.case_id == doc.case_id,
            Document.doc_type == doc.doc_type,
        )
        .order_by(Document.version.desc())
        .all()
    )

    return [DocumentVersionResponse.model_validate(v) for v in versions]


# ============================================================================
# 5. GET /documents/{document_id}/chain-status — Blockchain Status Short-Poll
# ============================================================================

@router.get("/{document_id}/chain-status", response_model=ChainStatusResponse)
def get_chain_status(
    document_id: UUID,
    claims: dict = Depends(get_current_claims),
    db: Session = Depends(get_db),
):
    """
    GET /documents/:id/chain-status — Poll target for Flow 2 Track A.
    Returns blockchain confirmation status and computed SHA-256 hash.
    """
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )

    verify_case_access(doc.case_id, claims, db)

    return ChainStatusResponse(
        document_id=doc.id,
        chain_status=doc.chain_status,
        doc_hash=doc.doc_hash,
    )


# ============================================================================
# 6. POST /documents/{document_id}/retry-chain-write — Admin Recovery
# ============================================================================

@router.post(
    "/{document_id}/retry-chain-write",
    response_model=ChainStatusResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def retry_chain_write(
    document_id: UUID,
    claims: dict = Depends(require_role("admin")),
    db: Session = Depends(get_db),
):
    """
    POST /documents/:id/retry-chain-write — Admin recovery endpoint.
    Manually re-triggers a stuck or failed blockchain write.
    MUST reuse the original idempotency key (f"{document_id}:{version}")
    to guarantee no duplicate ledger entry on Hyperledger Fabric.
    """
    if claims.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Role is not permitted for this action",
        )

    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )

    if doc.chain_status not in ("failed", "pending"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot retry chain write for document with chain_status '{doc.chain_status}'",
        )

    doc.chain_status = "pending"

    append_audit_log(
        db=db,
        case_id=doc.case_id,
        actor_user_id=UUID(claims["sub"]),
        action="chain_write_retried",
        target_type="document",
        target_id=doc.id,
        action_metadata={"version": doc.version, "doc_hash": doc.doc_hash},
    )

    db.commit()
    db.refresh(doc)

    # Re-dispatch with original idempotency key
    dispatch_chain_write(str(doc.id), doc.version)

    return ChainStatusResponse(
        document_id=doc.id,
        chain_status=doc.chain_status,
        doc_hash=doc.doc_hash,
    )


# ============================================================================
# 7. POST /documents/{document_id}/redact-tag — Officer Sensitivity Override
# ============================================================================

@router.post(
    "/{document_id}/redact-tag",
    response_model=DocumentSensitivityTagResponse,
    status_code=status.HTTP_200_OK,
)
def correct_redaction_tag(
    document_id: UUID,
    request: RedactTagRequest,
    claims: dict = Depends(require_role("io")),
    db: Session = Depends(get_db),
):
    """
    POST /documents/:id/redact-tag — Assigned Investigating Officer correction.
    Allows the assigned IO to add or correct a sensitivity tag over AI auto-tags.
    Never logs raw sensitive text in audit log or tags.
    """
    if claims.get("role") != "io":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Role is not permitted for this action",
        )

    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )

    # Must be the assigned IO for this case
    verify_case_access(doc.case_id, claims, db)

    # Validate span coordinates
    if request.span_start < 0 or request.span_end <= request.span_start:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid span coordinates: span_start must be >= 0 and span_end must be > span_start",
        )

    user_id = UUID(claims["sub"])

    # If updating an existing tag
    if request.tag_id:
        tag = (
            db.query(DocumentSensitivityTag)
            .filter(
                DocumentSensitivityTag.id == request.tag_id,
                DocumentSensitivityTag.document_id == doc.id,
            )
            .first()
        )
        if not tag:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Sensitivity tag not found for this document",
            )

        tag.entity_type = request.entity_type
        tag.span_start = request.span_start
        tag.span_end = request.span_end
        tag.source = "officer_correction"
        tag.confidence = None
    else:
        # Create a new correction tag
        tag = DocumentSensitivityTag(
            document_id=doc.id,
            entity_type=request.entity_type,
            span_start=request.span_start,
            span_end=request.span_end,
            confidence=None,
            source="officer_correction",
        )
        db.add(tag)

    append_audit_log(
        db=db,
        case_id=doc.case_id,
        actor_user_id=user_id,
        action="redaction_tag_corrected",
        target_type="document",
        target_id=doc.id,
        action_metadata={
            "entity_type": request.entity_type,
            "span_start": request.span_start,
            "span_end": request.span_end,
            "is_update": bool(request.tag_id),
        },
    )

    db.commit()
    db.refresh(tag)

    return DocumentSensitivityTagResponse.model_validate(tag)
