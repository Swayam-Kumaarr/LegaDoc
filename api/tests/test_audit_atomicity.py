"""
A state change and the audit row that records it commit together (issue #140).

Each test makes write_audit_log fail and checks that the change it would have
recorded was not saved either. Before, the change was committed first and the
audit row written in a second commit, so a failure between the two (a lock
timeout, a dropped connection, the process being killed) left an action that
happened with nothing in the tamper-evident record — and since the chain
itself stayed valid, verify_chain_intact could not notice.

The test client shares db_session with the app, so after the failed request
the test rolls it back, as the real per-request session teardown would.
"""
import importlib.util
import os
import sys
from uuid import UUID, uuid4

import pytest

from app import models
from tests.conftest import TestSessionLocal, auth_headers, login


class AuditUnavailable(RuntimeError):
    pass


def _failing_audit(*args, **kwargs):
    raise AuditUnavailable("audit write failed")


def _case_with_io(client, make_user):
    duty = make_user("duty_officer", email="duty-at@example.com", password="pw")
    sho = make_user("sho", email="sho-at@example.com", password="pw", org=duty.organization)
    io = make_user("io", email="io-at@example.com", password="pw", org=duty.organization)
    court = make_user("court", email="court-at@example.com", password="pw", org=duty.organization)

    duty_token = login(client, "duty-at@example.com", "pw").json()["access_token"]
    case = client.post("/cases", json={"crime_type": "Theft", "complaint_text": "..."},
                       headers=auth_headers(duty_token)).json()
    sho_token = login(client, "sho-at@example.com", "pw").json()["access_token"]
    client.post(f"/cases/{case['id']}/assign-io", json={"io_user_id": str(io.id)}, headers=auth_headers(sho_token))
    return case, io, login(client, "io-at@example.com", "pw").json()["access_token"], \
        login(client, "court-at@example.com", "pw").json()["access_token"]


def _upload(client, case, token, body=b"The witness said hello."):
    resp = client.post("/documents", data={"case_id": case["id"], "doc_type": "Witness Statement"},
                       files={"file": ("statement.txt", body, "text/plain")}, headers=auth_headers(token))
    assert resp.status_code == 202, resp.text
    return resp.json()["id"]


def test_upload_is_not_saved_or_enqueued_without_its_audit_row(client, make_user, db_session, fake_queue, monkeypatch):
    case, _, io_token, _ = _case_with_io(client, make_user)
    before = db_session.query(models.Document).count()
    jobs_before = len(fake_queue.enqueued)

    monkeypatch.setattr("app.routers.documents.write_audit_log", _failing_audit)
    with pytest.raises(AuditUnavailable):
        _upload(client, case, io_token, body=b"Never recorded.")
    db_session.rollback()

    assert db_session.query(models.Document).count() == before
    # The workers are told only after the commit, so nothing was queued for a
    # document that does not exist.
    assert len(fake_queue.enqueued) == jobs_before


def test_redaction_correction_is_not_saved_without_its_audit_row(client, make_user, db_session, monkeypatch):
    case, _, io_token, _ = _case_with_io(client, make_user)
    doc_id = _upload(client, case, io_token)
    tags_before = db_session.query(models.DocumentSensitivityTag).count()

    monkeypatch.setattr("app.routers.documents.write_audit_log", _failing_audit)
    with pytest.raises(AuditUnavailable):
        client.post(f"/documents/{doc_id}/redact-tag",
                    json={"entity_type": "PERSON", "span_start": 4, "span_end": 11},
                    headers=auth_headers(io_token))
    db_session.rollback()

    assert db_session.query(models.DocumentSensitivityTag).count() == tags_before


def test_review_release_is_not_saved_without_its_audit_row(client, make_user, db_session, monkeypatch):
    case, io, io_token, _ = _case_with_io(client, make_user)
    doc = models.Document(case_id=UUID(case["id"]), doc_type="FIR", version=1, storage_path="t/v1",
                          raw_text="Complainant Ramesh Kumar", status="needs_review", chain_status="pending",
                          uploaded_by=io.id)
    db_session.add(doc)
    db_session.commit()

    monkeypatch.setattr("app.routers.documents.write_audit_log", _failing_audit)
    with pytest.raises(AuditUnavailable):
        client.post(f"/documents/{doc.id}/release-review", headers=auth_headers(io_token))
    db_session.rollback()

    assert db_session.get(models.Document, doc.id).status == "needs_review"


def test_purge_keeps_the_document_and_its_file_without_an_audit_row(client, make_user, db_session, monkeypatch, tmp_path):
    case, _, io_token, court_token = _case_with_io(client, make_user)
    doc_id = _upload(client, case, io_token)
    stored = db_session.get(models.Document, UUID(doc_id))
    stored_file = tmp_path / "objects" / stored.storage_path
    assert stored_file.exists()

    monkeypatch.setattr("app.routers.documents.write_audit_log", _failing_audit)
    with pytest.raises(AuditUnavailable):
        client.delete(f"/documents/{doc_id}", headers=auth_headers(court_token))
    db_session.rollback()

    assert db_session.get(models.Document, UUID(doc_id)) is not None
    # The stored object is removed only after the commit, so it survives too.
    assert stored_file.exists()


def test_purge_still_removes_row_and_file_when_audit_succeeds(client, make_user, db_session, tmp_path):
    case, _, io_token, court_token = _case_with_io(client, make_user)
    doc_id = _upload(client, case, io_token)
    stored_file = tmp_path / "objects" / db_session.get(models.Document, UUID(doc_id)).storage_path

    assert client.delete(f"/documents/{doc_id}", headers=auth_headers(court_token)).status_code == 200
    db_session.expire_all()
    assert db_session.get(models.Document, UUID(doc_id)) is None
    assert not stored_file.exists()
    purged = db_session.query(models.AuditLog).filter(models.AuditLog.action == "document_purged").one()
    assert purged.target_id == UUID(doc_id)


def test_custom_role_is_not_created_without_its_audit_row(client, make_user, db_session, monkeypatch):
    make_user("config_admin", email="admin-at@example.com", password="pw")
    token = login(client, "admin-at@example.com", "pw").json()["access_token"]

    monkeypatch.setattr("app.routers.admin.write_audit_log", _failing_audit)
    with pytest.raises(AuditUnavailable):
        client.post("/admin/roles", json={"code": "atomic_test_role", "name": "Atomic", "permission_codes": []},
                    headers=auth_headers(token))
    db_session.rollback()

    assert db_session.query(models.Role).filter(models.Role.code == "atomic_test_role").first() is None


# --- AI parser -----------------------------------------------------------

_worker_dir = (
    "/workers/ai_parser_worker" if os.path.exists("/workers/ai_parser_worker")
    else os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "workers", "ai_parser_worker")
)
_spec = importlib.util.spec_from_file_location("ai_parser_worker_atomicity", os.path.join(_worker_dir, "worker.py"))
ai_worker = importlib.util.module_from_spec(_spec)
sys.modules["ai_parser_worker_atomicity"] = ai_worker
_spec.loader.exec_module(ai_worker)


def test_parser_tags_are_not_saved_without_their_audit_row_and_the_document_fails_closed(db_session, make_org, make_user, monkeypatch):
    monkeypatch.setattr(ai_worker, "SessionLocal", TestSessionLocal)
    io = make_user("io", email=f"io-{uuid4().hex[:6]}@example.com", password="pw", org=make_org())
    case = models.Case(case_number=f"CASE-{uuid4().hex[:6]}", crime_type="Theft", investigation_status="Under_Investigation")
    db_session.add(case)
    db_session.commit()
    doc = models.Document(case_id=case.id, doc_type="Witness Statement", version=1, storage_path="t/v1",
                          raw_text="Call Ramesh on 9876543210, Aadhaar 2345 6789 0123.", status="processing",
                          chain_status="pending", uploaded_by=io.id)
    db_session.add(doc)
    db_session.commit()

    monkeypatch.setattr(ai_worker, "write_audit_log", _failing_audit)
    result = ai_worker.process_tag_document(str(doc.id), db=db_session)

    db_session.expire_all()
    assert result == "needs_review"
    # Rolled back with the failed audit row, then held for review: never
    # left "ready" with tags nobody recorded, and never stuck at "processing".
    assert db_session.get(models.Document, doc.id).status == "needs_review"
    assert db_session.query(models.DocumentSensitivityTag).filter(
        models.DocumentSensitivityTag.document_id == doc.id).count() == 0
