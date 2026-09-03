"""Tests for evidence-requests endpoints (create, list, submit)."""

import uuid as _uuid

from app import models
from tests.conftest import auth_headers, login


def make_org_with_type(db_session, name, org_type):
    org = models.Organization(name=name, org_type=org_type)
    db_session.add(org)
    db_session.commit()
    db_session.refresh(org)
    return org


def _setup_case_with_io_and_fsl(client, make_user, db_session):
    duty = make_user("duty_officer", email="duty@example.com", password="pw")
    sho = make_user("sho", email="sho@example.com", password="pw", org=duty.organization)
    io = make_user("io", email="io@example.com", password="pw", org=duty.organization)

    fsl_org = make_org_with_type(db_session, "FSL Lab", "fsl")
    fsl = make_user("authority_staff", email="fsl@example.com", password="pw", org=fsl_org)

    duty_token = login(client, "duty@example.com", "pw").json()["access_token"]
    case = client.post(
        "/cases", json={"crime_type": "Theft", "complaint_text": "..."}, headers=auth_headers(duty_token)
    ).json()

    sho_token = login(client, "sho@example.com", "pw").json()["access_token"]
    client.post(
        f"/cases/{case['id']}/assign-io",
        json={"io_user_id": str(io.id)},
        headers=auth_headers(sho_token),
    )

    io_token = login(client, "io@example.com", "pw").json()["access_token"]
    fsl_token = login(client, "fsl@example.com", "pw").json()["access_token"]
    return case, io_token, fsl_token, fsl


def test_io_can_create_evidence_request(client, make_user, db_session):
    case, io_token, fsl_token, fsl = _setup_case_with_io_and_fsl(client, make_user, db_session)

    resp = client.post(
        f"/cases/{case['id']}/evidence-requests",
        json={"requested_org_id": str(fsl.org_id), "doc_type_expected": "Forensic Report"},
        headers=auth_headers(io_token),
    )

    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "requested"
    assert body["requested_org_id"] == str(fsl.org_id)
    assert body["doc_type_expected"] == "Forensic Report"


def test_unassigned_io_cannot_create_evidence_request(client, make_user, db_session):
    case, io_token, fsl_token, fsl = _setup_case_with_io_and_fsl(client, make_user, db_session)
    other_io = make_user("io", email="other@example.com", password="pw")
    other_token = login(client, "other@example.com", "pw").json()["access_token"]

    resp = client.post(
        f"/cases/{case['id']}/evidence-requests",
        json={"requested_org_id": str(fsl.org_id)},
        headers=auth_headers(other_token),
    )

    assert resp.status_code == 403


def test_io_can_list_evidence_requests(client, make_user, db_session):
    case, io_token, fsl_token, fsl = _setup_case_with_io_and_fsl(client, make_user, db_session)

    client.post(
        f"/cases/{case['id']}/evidence-requests",
        json={"requested_org_id": str(fsl.org_id), "doc_type_expected": "Report"},
        headers=auth_headers(io_token),
    )

    resp = client.get(f"/cases/{case['id']}/evidence-requests", headers=auth_headers(io_token))

    assert resp.status_code == 200
    assert len(resp.json()) == 1
    assert resp.json()[0]["status"] == "requested"


def test_evidence_request_creates_audit_log(client, make_user, db_session):
    case, io_token, fsl_token, fsl = _setup_case_with_io_and_fsl(client, make_user, db_session)

    client.post(
        f"/cases/{case['id']}/evidence-requests",
        json={"requested_org_id": str(fsl.org_id)},
        headers=auth_headers(io_token),
    )

    entries = (
        db_session.query(models.AuditLog)
        .filter_by(case_id=_uuid.UUID(case["id"]), action="evidence_request_created")
        .all()
    )
    assert len(entries) == 1


def test_authority_can_submit_evidence_request(client, make_user, db_session, fake_queue):
    case, io_token, fsl_token, fsl = _setup_case_with_io_and_fsl(client, make_user, db_session)

    create_resp = client.post(
        f"/cases/{case['id']}/evidence-requests",
        json={"requested_org_id": str(fsl.org_id), "doc_type_expected": "Forensic Report"},
        headers=auth_headers(io_token),
    )
    er_id = create_resp.json()["id"]

    resp = client.post(
        f"/evidence-requests/{er_id}/submit",
        files={"file": ("report.pdf", b"fake pdf content", "application/pdf")},
        headers=auth_headers(fsl_token),
    )

    assert resp.status_code == 202, resp.text
    assert resp.json()["status"] == "completed"

    er = db_session.get(models.EvidenceRequest, _uuid.UUID(er_id))
    assert er.status == "completed"
    assert er.completed_at is not None


def test_wrong_org_cannot_submit_evidence_request(client, make_user, db_session):
    case, io_token, fsl_token, fsl = _setup_case_with_io_and_fsl(client, make_user, db_session)
    other_org = make_org_with_type(db_session, "Other Lab", "fsl")
    other_authority = make_user("authority_staff", email="other@example.com", password="pw", org=other_org)

    create_resp = client.post(
        f"/cases/{case['id']}/evidence-requests",
        json={"requested_org_id": str(fsl.org_id)},
        headers=auth_headers(io_token),
    )
    er_id = create_resp.json()["id"]

    other_token = login(client, "other@example.com", "pw").json()["access_token"]
    resp = client.post(
        f"/evidence-requests/{er_id}/submit",
        files={"file": ("report.pdf", b"content", "application/pdf")},
        headers=auth_headers(other_token),
    )

    assert resp.status_code == 403


def test_submit_triggers_document_upload_pipeline(client, make_user, db_session, fake_queue):
    case, io_token, fsl_token, fsl = _setup_case_with_io_and_fsl(client, make_user, db_session)

    create_resp = client.post(
        f"/cases/{case['id']}/evidence-requests",
        json={"requested_org_id": str(fsl.org_id)},
        headers=auth_headers(io_token),
    )
    er_id = create_resp.json()["id"]

    client.post(
        f"/evidence-requests/{er_id}/submit",
        files={"file": ("report.pdf", b"content", "application/pdf")},
        headers=auth_headers(fsl_token),
    )

    task_names = {j["task_name"] for j in fake_queue.enqueued}
    assert "chain_worker.write_hash" in task_names
    assert "ocr_worker.extract_document" in task_names


def test_submit_creates_document_row(client, make_user, db_session, fake_queue):
    case, io_token, fsl_token, fsl = _setup_case_with_io_and_fsl(client, make_user, db_session)

    create_resp = client.post(
        f"/cases/{case['id']}/evidence-requests",
        json={"requested_org_id": str(fsl.org_id), "doc_type_expected": "Forensic Report"},
        headers=auth_headers(io_token),
    )
    er_id = create_resp.json()["id"]

    resp = client.post(
        f"/evidence-requests/{er_id}/submit",
        files={"file": ("report.pdf", b"content", "application/pdf")},
        headers=auth_headers(fsl_token),
    )
    doc_id = resp.json()["document_id"]

    doc = db_session.get(models.Document, _uuid.UUID(doc_id))
    assert doc is not None
    assert doc.case_id == _uuid.UUID(case["id"])
    assert doc.status == "processing"
    assert doc.doc_type == "Forensic Report"


def test_already_completed_evidence_request_returns_409(client, make_user, db_session, fake_queue):
    case, io_token, fsl_token, fsl = _setup_case_with_io_and_fsl(client, make_user, db_session)

    create_resp = client.post(
        f"/cases/{case['id']}/evidence-requests",
        json={"requested_org_id": str(fsl.org_id)},
        headers=auth_headers(io_token),
    )
    er_id = create_resp.json()["id"]

    client.post(
        f"/evidence-requests/{er_id}/submit",
        files={"file": ("report.pdf", b"content", "application/pdf")},
        headers=auth_headers(fsl_token),
    )

    resp = client.post(
        f"/evidence-requests/{er_id}/submit",
        files={"file": ("report2.pdf", b"content2", "application/pdf")},
        headers=auth_headers(fsl_token),
    )

    assert resp.status_code == 409
