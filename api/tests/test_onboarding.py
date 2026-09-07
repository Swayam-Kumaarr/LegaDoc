"""Officer/authority onboarding & credential verification.

Covers the API flow (create application -> upload credential document ->
approve/reject) and, directly against the worker module (same dynamic-load
pattern as test_ai_parser_worker.py), the extraction/comparison logic that
decides match_status — matched / mismatch / needs_review.
"""

import importlib.util
import io
import os
import sys
from uuid import UUID, uuid4

import pytest

from app import models, security
from tests.conftest import TestSessionLocal, auth_headers, login

# Dynamically load ai_parser_worker (same pattern as test_ai_parser_worker.py)
_ai_worker_dir = (
    "/workers/ai_parser_worker"
    if os.path.exists("/workers/ai_parser_worker")
    else os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "workers", "ai_parser_worker")
)
_ai_worker_file = os.path.join(_ai_worker_dir, "worker.py")
_spec = importlib.util.spec_from_file_location("ai_parser_worker_onboarding", _ai_worker_file)
ai_worker = importlib.util.module_from_spec(_spec)
sys.modules["ai_parser_worker_onboarding"] = ai_worker
_spec.loader.exec_module(ai_worker)


@pytest.fixture(autouse=True)
def _patch_worker_session(monkeypatch):
    monkeypatch.setattr(ai_worker, "SessionLocal", TestSessionLocal)


def _make_admin(make_user):
    return make_user("config_admin", email=f"admin-{uuid4().hex[:8]}@example.com", password="pw")


# ---------- API flow ----------

def test_config_admin_can_create_an_application(client, make_user, make_org):
    admin = _make_admin(make_user)
    token = login(client, admin.email, "pw").json()["access_token"]
    org = make_org(name="Delhi Police Cyber Cell", org_type="police")

    resp = client.post(
        "/admin/applications",
        json={
            "name": "Inspector S. Rao",
            "email": "rao.applicant@police.gov.in",
            "claimed_role": "io",
            "org_id": str(org.id),
            "designation": "Inspector of Police",
            "claimed_credential_id": "DL-POL-4921",
        },
        headers=auth_headers(token),
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "pending_review"
    assert body["documents"] == []


def test_only_config_admin_can_create_an_application(client, make_user, make_org):
    io_user = make_user("io", email="io_applicant@example.com", password="pw")
    token = login(client, "io_applicant@example.com", "pw").json()["access_token"]
    org = make_org()

    resp = client.post(
        "/admin/applications",
        json={"name": "X", "email": "x@example.com", "claimed_role": "io", "org_id": str(org.id)},
        headers=auth_headers(token),
    )
    assert resp.status_code == 403


def test_cannot_create_application_for_an_email_that_already_has_an_account(client, make_user, make_org):
    admin = _make_admin(make_user)
    token = login(client, admin.email, "pw").json()["access_token"]
    org = make_org()
    existing = make_user("io", email="already.exists@example.com", password="pw", org=org)

    resp = client.post(
        "/admin/applications",
        json={"name": "Dup", "email": "already.exists@example.com", "claimed_role": "io", "org_id": str(org.id)},
        headers=auth_headers(token),
    )
    assert resp.status_code == 409


def test_upload_credential_document_enqueues_ocr_task(client, make_user, make_org, fake_queue):
    admin = _make_admin(make_user)
    token = login(client, admin.email, "pw").json()["access_token"]
    org = make_org()

    app_resp = client.post(
        "/admin/applications",
        json={"name": "Adv. K. Mehta", "email": "mehta.applicant@bar.in", "claimed_role": "defense", "org_id": str(org.id)},
        headers=auth_headers(token),
    )
    application_id = app_resp.json()["id"]

    upload_resp = client.post(
        f"/admin/applications/{application_id}/credential-documents",
        data={"doc_type": "bar_enrollment_certificate"},
        files={"file": ("cert.pdf", io.BytesIO(b"%PDF-1.4 bar council enrollment certificate"), "application/pdf")},
        headers=auth_headers(token),
    )
    assert upload_resp.status_code == 202, upload_resp.text
    doc = upload_resp.json()
    assert doc["status"] == "processing"
    assert doc["doc_hash"] is not None

    ocr_jobs = [j for j in fake_queue.enqueued if j["task_name"] == "ocr_worker.extract_credential_document"]
    assert len(ocr_jobs) == 1
    assert ocr_jobs[0]["kwargs"]["document_id"] == doc["id"]


def test_upload_rejects_unknown_doc_type(client, make_user, make_org):
    admin = _make_admin(make_user)
    token = login(client, admin.email, "pw").json()["access_token"]
    org = make_org()
    application_id = client.post(
        "/admin/applications",
        json={"name": "X", "email": "unknown-doctype@example.com", "claimed_role": "io", "org_id": str(org.id)},
        headers=auth_headers(token),
    ).json()["id"]

    resp = client.post(
        f"/admin/applications/{application_id}/credential-documents",
        data={"doc_type": "not_a_real_type"},
        files={"file": ("x.pdf", io.BytesIO(b"%PDF-1.4"), "application/pdf")},
        headers=auth_headers(token),
    )
    assert resp.status_code == 400


def test_approve_creates_a_real_user_with_working_temp_password_and_forced_reset(client, make_user, make_org, db_session):
    admin = _make_admin(make_user)
    token = login(client, admin.email, "pw").json()["access_token"]
    org = make_org(name="Delhi Police Central", org_type="police")

    application_id = client.post(
        "/admin/applications",
        json={
            "name": "Sub-Inspector A. Verma",
            "email": "verma.applicant@police.gov.in",
            "claimed_role": "duty_officer",
            "org_id": str(org.id),
            "designation": "Duty Officer",
            "claimed_credential_id": "DL-POL-1084",
        },
        headers=auth_headers(token),
    ).json()["id"]

    resp = client.post(f"/admin/applications/{application_id}/approve", headers=auth_headers(token))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["email"] == "verma.applicant@police.gov.in"
    temp_password = body["temporary_password"]
    security.validate_password_strength(temp_password)  # must never raise

    new_user = db_session.query(models.User).filter_by(email="verma.applicant@police.gov.in").first()
    assert new_user is not None
    assert new_user.role == "duty_officer"
    assert new_user.service_id == "DL-POL-1084"
    assert new_user.must_change_password is True

    # The temp password actually logs in, and /auth/me reports the forced-reset flag.
    login_resp = login(client, "verma.applicant@police.gov.in", temp_password)
    assert login_resp.status_code == 200
    new_token = login_resp.json()["access_token"]
    me = client.get("/auth/me", headers=auth_headers(new_token))
    assert me.json()["must_change_password"] is True

    # Changing the password clears the flag.
    client.post(
        "/auth/change-password",
        json={"current_password": temp_password, "new_password": "BrandNewPassw0rd!"},
        headers=auth_headers(new_token),
    )
    me2 = client.get("/auth/me", headers=auth_headers(new_token))
    assert me2.json()["must_change_password"] is False

    # The application itself is now terminal.
    reapprove = client.post(f"/admin/applications/{application_id}/approve", headers=auth_headers(token))
    assert reapprove.status_code == 409


def test_reject_records_reason_and_is_terminal(client, make_user, make_org):
    admin = _make_admin(make_user)
    token = login(client, admin.email, "pw").json()["access_token"]
    org = make_org()
    application_id = client.post(
        "/admin/applications",
        json={"name": "Suspicious Applicant", "email": "suspicious@example.com", "claimed_role": "io", "org_id": str(org.id)},
        headers=auth_headers(token),
    ).json()["id"]

    resp = client.post(
        f"/admin/applications/{application_id}/reject",
        json={"reason": "Credential document did not match claimed identity"},
        headers=auth_headers(token),
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "rejected"
    assert resp.json()["rejection_reason"] == "Credential document did not match claimed identity"

    approve_after_reject = client.post(f"/admin/applications/{application_id}/approve", headers=auth_headers(token))
    assert approve_after_reject.status_code == 409


# ---------- Extraction / matching logic (direct worker call) ----------

def _make_application(db_session, make_org, name="Inspector S. Rao", claimed_id="DL-POL-4921"):
    org = make_org()
    submitter_id = uuid4()
    application = models.UserApplication(
        name=name,
        email=f"{uuid4().hex[:8]}@example.com",
        claimed_role="io",
        org_id=org.id,
        claimed_credential_id=claimed_id,
        status="pending_review",
        submitted_by_user_id=submitter_id,
    )
    db_session.add(application)
    db_session.commit()
    db_session.refresh(application)
    return application


def _make_credential_doc(db_session, application, raw_text):
    doc = models.CredentialDocument(
        application_id=application.id,
        doc_type="police_service_id",
        storage_path="test/path/v1",
        doc_hash="fakehash",
        raw_text=raw_text,
        status="processing",
        uploaded_by=application.submitted_by_user_id,
    )
    db_session.add(doc)
    db_session.commit()
    db_session.refresh(doc)
    return doc


def test_extraction_matches_when_name_and_id_both_line_up(db_session, make_org):
    # Full given name, not an abbreviated middle initial ("S.") — the shared
    # PERSON regex (LegalPIIRecognizer, same one every case document in this
    # system is redacted with) matches multi-word names, not name+initial+
    # surname with a period in the middle; that's a pre-existing recognizer
    # limitation, not something to redesign as part of this feature.
    application = _make_application(db_session, make_org, name="Inspector Suresh Rao", claimed_id="DL-POL-4921")
    doc = _make_credential_doc(
        db_session, application,
        raw_text="GOVERNMENT OF NCT OF DELHI POLICE\nName: Inspector Suresh Rao\nService ID: DL-POL-4921\nRank: Inspector",
    )

    result = ai_worker.process_extract_credential_fields(str(doc.id), db=db_session)
    assert result == "matched"

    db_session.refresh(doc)
    assert doc.match_status == "matched"
    assert doc.extracted_fields["id_number"] == "DL-POL-4921"
    assert doc.status == "ready"


def test_extraction_flags_mismatch_when_id_number_is_wrong(db_session, make_org):
    application = _make_application(db_session, make_org, name="Inspector Suresh Rao", claimed_id="DL-POL-4921")
    # Same name, but a completely different service ID printed on the document.
    doc = _make_credential_doc(
        db_session, application,
        raw_text="Name: Inspector Suresh Rao\nService ID: MH-POL-0007\nRank: Inspector",
    )

    result = ai_worker.process_extract_credential_fields(str(doc.id), db=db_session)
    assert result == "mismatch"
    db_session.refresh(doc)
    assert doc.match_status == "mismatch"


def test_extraction_needs_review_when_document_has_no_extractable_id(db_session, make_org):
    application = _make_application(db_session, make_org, name="Inspector S. Rao", claimed_id="DL-POL-4921")
    doc = _make_credential_doc(db_session, application, raw_text="Name: Inspector S. Rao\n(illegible scan, no ID visible)")

    result = ai_worker.process_extract_credential_fields(str(doc.id), db=db_session)
    assert result == "needs_review"
    db_session.refresh(doc)
    assert doc.match_status == "needs_review"


def test_extraction_fails_closed_on_empty_ocr_text(db_session, make_org):
    application = _make_application(db_session, make_org)
    doc = _make_credential_doc(db_session, application, raw_text="")

    result = ai_worker.process_extract_credential_fields(str(doc.id), db=db_session)
    assert result == "needs_review"
    db_session.refresh(doc)
    assert doc.status == "needs_review"
    assert doc.match_status == "needs_review"
