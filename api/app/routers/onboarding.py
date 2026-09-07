"""Officer/authority onboarding & credential verification.

A new account is never created directly — it starts as a UserApplication
(a claimed identity, no login capability at all) that a config_admin
provisions with a claimed name/role/org and one or more scanned credential
documents (police service ID, Bar Council enrollment certificate, judicial
appointment order, institutional authorization letter). Those documents run
through the same OCR pipeline every other document in this system uses,
then a POSITIVE-extraction AI Parser task (not the redaction one) pulls out
a candidate name and ID number and compares them against what was claimed.

That comparison (match_status) is advisory only — approval is always an
explicit config_admin action (POST .../approve), never automatic, no
matter how clean the match. There is no real government API this system
can call to actually verify a Bar Council number or a police service ID
against an authoritative registry; claiming otherwise would be dishonest.
What this DOES provide: a documented, OCR-cross-checked paper trail behind
every account, and a hash-chained audit entry for who approved it and on
what evidence.
"""

import secrets
import string
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app import models, schemas
from app.audit import write_audit_log
from app.database import get_db
from app.queue import QueueClient, get_queue
from app.security import hash_password, require_role
from app.storage import ObjectStorage, get_storage, object_key, sha256_hex
from app.upload_validator import validate_upload_stream

router = APIRouter(prefix="/admin/applications", tags=["onboarding"])

CREDENTIAL_DOC_TYPES = {
    "police_service_id",
    "bar_enrollment_certificate",
    "judicial_appointment_order",
    "institutional_authorization_letter",
    "nabl_accreditation_certificate",
    "government_employee_id",
}


def _generate_temp_password() -> str:
    """Always satisfies security.validate_password_strength (letter + digit
    + special guaranteed by construction, not left to chance)."""
    alphabet = string.ascii_letters + string.digits
    body = "".join(secrets.choice(alphabet) for _ in range(10))
    return body + secrets.choice(string.digits) + secrets.choice("!@#$%&*")


@router.post("", response_model=schemas.UserApplicationResponse, status_code=status.HTTP_201_CREATED)
def create_application(
    body: schemas.UserApplicationCreateRequest,
    claims: dict = Depends(require_role("config_admin")),
    db: Session = Depends(get_db),
):
    """POST /admin/applications — Config Admin. Opens a pending onboarding
    application. Not a real account yet — no role, no permissions, cannot
    authenticate — until approved."""
    org = db.get(models.Organization, body.org_id)
    if org is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Organization not found")

    existing_user = db.query(models.User).filter(models.User.email == body.email).first()
    if existing_user:
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with this email already exists")

    application = models.UserApplication(
        name=body.name,
        email=body.email,
        claimed_role=body.claimed_role,
        org_id=body.org_id,
        designation=body.designation,
        claimed_credential_id=body.claimed_credential_id,
        status="pending_review",
        submitted_by_user_id=UUID(claims["sub"]),
    )
    db.add(application)
    db.commit()
    db.refresh(application)

    write_audit_log(
        db,
        action="user_application_created",
        actor_user_id=UUID(claims["sub"]),
        target_type="user_application",
        target_id=application.id,
        metadata={"claimed_role": body.claimed_role, "org_id": str(body.org_id)},
    )

    result = schemas.UserApplicationResponse.model_validate(application)
    result.documents = []
    return result


@router.get("", response_model=list[schemas.UserApplicationResponse])
def list_applications(
    status_filter: str | None = None,
    claims: dict = Depends(require_role("config_admin")),
    db: Session = Depends(get_db),
):
    """GET /admin/applications — Config Admin. Optional ?status_filter=pending_review|approved|rejected."""
    query = db.query(models.UserApplication)
    if status_filter:
        query = query.filter(models.UserApplication.status == status_filter)
    applications = query.order_by(models.UserApplication.created_at.desc()).all()

    results = []
    for app_row in applications:
        docs = (
            db.query(models.CredentialDocument)
            .filter(models.CredentialDocument.application_id == app_row.id)
            .order_by(models.CredentialDocument.created_at.asc())
            .all()
        )
        item = schemas.UserApplicationResponse.model_validate(app_row)
        item.documents = [schemas.CredentialDocumentResponse.model_validate(d) for d in docs]
        results.append(item)
    return results


@router.get("/{application_id}", response_model=schemas.UserApplicationResponse)
def get_application(
    application_id: str,
    claims: dict = Depends(require_role("config_admin")),
    db: Session = Depends(get_db),
):
    """GET /admin/applications/:id — Config Admin. Full detail with all uploaded credential documents."""
    try:
        app_uuid = UUID(application_id)
    except ValueError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Application not found")

    application = db.get(models.UserApplication, app_uuid)
    if application is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Application not found")

    docs = (
        db.query(models.CredentialDocument)
        .filter(models.CredentialDocument.application_id == app_uuid)
        .order_by(models.CredentialDocument.created_at.asc())
        .all()
    )
    result = schemas.UserApplicationResponse.model_validate(application)
    result.documents = [schemas.CredentialDocumentResponse.model_validate(d) for d in docs]
    return result


@router.post(
    "/{application_id}/credential-documents",
    response_model=schemas.CredentialDocumentResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def upload_credential_document(
    application_id: str,
    doc_type: str = Form(...),
    file: UploadFile = File(...),
    claims: dict = Depends(require_role("config_admin")),
    db: Session = Depends(get_db),
    storage: ObjectStorage = Depends(get_storage),
    queue_client: QueueClient = Depends(get_queue),
):
    """POST /admin/applications/:id/credential-documents — Config Admin.
    Uploads a proof-of-identity scan. Same streaming validation as case
    document uploads (magic-byte MIME sniffing, size cap), then OCR ->
    extraction, same two-worker-hop shape as any other document, just
    routed to the credential pipeline instead of the case one."""
    if doc_type not in CREDENTIAL_DOC_TYPES:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"doc_type must be one of: {', '.join(sorted(CREDENTIAL_DOC_TYPES))}",
        )

    try:
        app_uuid = UUID(application_id)
    except ValueError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Application not found")

    application = db.get(models.UserApplication, app_uuid)
    if application is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Application not found")
    if application.status != "pending_review":
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Cannot attach documents to an application in status '{application.status}'",
        )

    validation = await validate_upload_stream(file, max_size_mb=25)
    doc_id = UUID(int=secrets.randbits(128))
    key = object_key(application.org_id, application.id, doc_id, 1)
    storage.put(key, validation.data, content_type=validation.detected_mime)

    cred_doc = models.CredentialDocument(
        id=doc_id,
        application_id=app_uuid,
        doc_type=doc_type,
        storage_path=key,
        doc_hash=validation.sha256_hash,
        status="processing",
        uploaded_by=UUID(claims["sub"]),
    )
    db.add(cred_doc)
    db.commit()
    db.refresh(cred_doc)

    queue_client.enqueue("ocr_worker.extract_credential_document", document_id=str(cred_doc.id))

    write_audit_log(
        db,
        action="credential_document_uploaded",
        actor_user_id=UUID(claims["sub"]),
        target_type="credential_document",
        target_id=cred_doc.id,
        metadata={"application_id": application_id, "doc_type": doc_type, "doc_hash": validation.sha256_hash},
    )

    return cred_doc


@router.post("/{application_id}/approve", response_model=schemas.ApplicationApproveResponse)
def approve_application(
    application_id: str,
    claims: dict = Depends(require_role("config_admin")),
    db: Session = Depends(get_db),
):
    """POST /admin/applications/:id/approve — Config Admin. Always an
    explicit human decision — match_status on the uploaded documents is
    advisory context for this call, never a substitute for it. Creates the
    real User row, assigns a one-time temporary password (shown exactly
    once in this response — the approving admin communicates it out of
    band), and forces a password change on first login."""
    try:
        app_uuid = UUID(application_id)
    except ValueError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Application not found")

    application = db.get(models.UserApplication, app_uuid)
    if application is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Application not found")
    if application.status != "pending_review":
        raise HTTPException(status.HTTP_409_CONFLICT, f"Application is already '{application.status}'")

    existing_user = db.query(models.User).filter(models.User.email == application.email).first()
    if existing_user:
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with this email already exists")

    role_obj = db.query(models.Role).filter(models.Role.code == application.claimed_role).first()

    temp_password = _generate_temp_password()
    new_user = models.User(
        org_id=application.org_id,
        role=application.claimed_role,
        role_id=role_obj.id if role_obj else None,
        service_id=application.claimed_credential_id,
        designation=application.designation,
        name=application.name,
        email=application.email,
        hashed_password=hash_password(temp_password),
        must_change_password=True,
    )
    db.add(new_user)
    db.flush()

    application.status = "approved"
    application.reviewed_by_user_id = UUID(claims["sub"])
    application.reviewed_at = datetime.now(timezone.utc)
    application.created_user_id = new_user.id
    db.commit()
    db.refresh(new_user)

    write_audit_log(
        db,
        action="user_application_approved",
        actor_user_id=UUID(claims["sub"]),
        target_type="user_application",
        target_id=application.id,
        metadata={"created_user_id": str(new_user.id), "role": application.claimed_role},
    )

    return schemas.ApplicationApproveResponse(
        user_id=new_user.id,
        email=new_user.email,
        temporary_password=temp_password,
    )


@router.post("/{application_id}/reject", response_model=schemas.UserApplicationResponse)
def reject_application(
    application_id: str,
    body: schemas.ApplicationRejectRequest,
    claims: dict = Depends(require_role("config_admin")),
    db: Session = Depends(get_db),
):
    """POST /admin/applications/:id/reject — Config Admin. Terminal — a
    rejected application is never reopened; submit a fresh one instead."""
    try:
        app_uuid = UUID(application_id)
    except ValueError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Application not found")

    application = db.get(models.UserApplication, app_uuid)
    if application is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Application not found")
    if application.status != "pending_review":
        raise HTTPException(status.HTTP_409_CONFLICT, f"Application is already '{application.status}'")

    application.status = "rejected"
    application.reviewed_by_user_id = UUID(claims["sub"])
    application.reviewed_at = datetime.now(timezone.utc)
    application.rejection_reason = body.reason
    db.commit()
    db.refresh(application)

    write_audit_log(
        db,
        action="user_application_rejected",
        actor_user_id=UUID(claims["sub"]),
        target_type="user_application",
        target_id=application.id,
        metadata={"reason": body.reason},
    )

    docs = (
        db.query(models.CredentialDocument)
        .filter(models.CredentialDocument.application_id == app_uuid)
        .order_by(models.CredentialDocument.created_at.asc())
        .all()
    )
    result = schemas.UserApplicationResponse.model_validate(application)
    result.documents = [schemas.CredentialDocumentResponse.model_validate(d) for d in docs]
    return result
