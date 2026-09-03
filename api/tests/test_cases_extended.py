"""Tests for case-diary, reassign-io, and file-charge-sheet endpoints."""

from uuid import UUID

from app import models
from app.audit import verify_chain_intact
from tests.conftest import auth_headers, login


def _setup_case_with_io(client, make_user, db_session):
    duty = make_user("duty_officer", email="duty@example.com", password="pw")
    sho = make_user("sho", email="sho@example.com", password="pw", org=duty.organization)
    io = make_user("io", email="io@example.com", password="pw", org=duty.organization)

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
    return case, io, io_token, sho_token


# --- Case Diary ---

def test_io_can_add_case_diary_entry(client, make_user, db_session):
    case, io, io_token, _ = _setup_case_with_io(client, make_user, db_session)

    resp = client.post(
        f"/cases/{case['id']}/case-diary",
        json={"text": "Visited the crime scene today."},
        headers=auth_headers(io_token),
    )

    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["text"] == "Visited the crime scene today."
    assert body["status"] == "processing"
    assert body["case_id"] == case["id"]
    assert body["author_user_id"] == str(io.id)


def test_unauthorized_io_cannot_add_case_diary(client, make_user, db_session):
    case, io, io_token, _ = _setup_case_with_io(client, make_user, db_session)
    other_io = make_user("io", email="other@example.com", password="pw")
    other_token = login(client, "other@example.com", "pw").json()["access_token"]

    resp = client.post(
        f"/cases/{case['id']}/case-diary",
        json={"text": "Should fail."},
        headers=auth_headers(other_token),
    )

    assert resp.status_code == 403


def test_case_diary_entry_creates_audit_log(client, make_user, db_session):
    case, io, io_token, _ = _setup_case_with_io(client, make_user, db_session)

    client.post(
        f"/cases/{case['id']}/case-diary",
        json={"text": "Noted."},
        headers=auth_headers(io_token),
    )

    entries = db_session.query(models.AuditLog).filter_by(case_id=UUID(case["id"])).all()
    assert any(e.action == "case_diary_entry_added" for e in entries)


def test_list_case_diary_entries(client, make_user, db_session):
    case, io, io_token, _ = _setup_case_with_io(client, make_user, db_session)

    client.post(f"/cases/{case['id']}/case-diary", json={"text": "Entry 1"}, headers=auth_headers(io_token))
    client.post(f"/cases/{case['id']}/case-diary", json={"text": "Entry 2"}, headers=auth_headers(io_token))

    resp = client.get(f"/cases/{case['id']}/case-diary", headers=auth_headers(io_token))

    assert resp.status_code == 200
    assert len(resp.json()) == 2
    assert resp.json()[0]["text"] == "Entry 1"
    assert resp.json()[1]["text"] == "Entry 2"


def test_unassigned_io_cannot_list_case_diary(client, make_user, db_session):
    case, io, io_token, _ = _setup_case_with_io(client, make_user, db_session)
    other_io = make_user("io", email="other@example.com", password="pw")
    other_token = login(client, "other@example.com", "pw").json()["access_token"]

    resp = client.get(f"/cases/{case['id']}/case-diary", headers=auth_headers(other_token))

    assert resp.status_code == 403


# --- Reassign IO ---

def test_sho_can_reassign_io(client, make_user, db_session):
    case, io, io_token, sho_token = _setup_case_with_io(client, make_user, db_session)
    new_io = make_user("io", email="newio@example.com", password="pw", org=io.organization)

    resp = client.post(
        f"/cases/{case['id']}/reassign-io",
        json={"io_user_id": str(new_io.id)},
        headers=auth_headers(sho_token),
    )

    assert resp.status_code == 200, resp.text
    assert resp.json()["io_user_id"] == str(new_io.id)

    assignment = (
        db_session.query(models.CaseAssignment)
        .filter(models.CaseAssignment.case_id == UUID(case["id"]))
        .order_by(models.CaseAssignment.assigned_at.desc())
        .first()
    )
    assert assignment.io_user_id == new_io.id


def test_reassign_io_creates_audit_log(client, make_user, db_session):
    case, io, io_token, sho_token = _setup_case_with_io(client, make_user, db_session)
    new_io = make_user("io", email="newio@example.com", password="pw", org=io.organization)

    client.post(
        f"/cases/{case['id']}/reassign-io",
        json={"io_user_id": str(new_io.id)},
        headers=auth_headers(sho_token),
    )

    entries = (
        db_session.query(models.AuditLog)
        .filter_by(case_id=UUID(case["id"]), action="io_reassigned")
        .all()
    )
    assert len(entries) == 1
    assert entries[0].action_metadata["new_io_user_id"] == str(new_io.id)


def test_config_admin_can_reassign_io(client, make_user, db_session):
    case, io, io_token, _ = _setup_case_with_io(client, make_user, db_session)
    make_user("config_admin", email="admin@example.com", password="pw", org=io.organization)
    admin_token = login(client, "admin@example.com", "pw").json()["access_token"]
    new_io = make_user("io", email="newio@example.com", password="pw", org=io.organization)

    resp = client.post(
        f"/cases/{case['id']}/reassign-io",
        json={"io_user_id": str(new_io.id)},
        headers=auth_headers(admin_token),
    )

    assert resp.status_code == 200


def test_prosecutor_cannot_reassign_io(client, make_user, db_session):
    case, io, io_token, _ = _setup_case_with_io(client, make_user, db_session)
    make_user("prosecutor", email="prosecutor@example.com", password="pw", org=io.organization)
    prosecutor_token = login(client, "prosecutor@example.com", "pw").json()["access_token"]
    new_io = make_user("io", email="newio@example.com", password="pw", org=io.organization)

    resp = client.post(
        f"/cases/{case['id']}/reassign-io",
        json={"io_user_id": str(new_io.id)},
        headers=auth_headers(prosecutor_token),
    )

    assert resp.status_code == 403


# --- File Charge Sheet ---

def test_prosecutor_can_file_charge_sheet_when_no_requirements(client, make_user, db_session):
    case, io, io_token, _ = _setup_case_with_io(client, make_user, db_session)
    make_user("prosecutor", email="prosecutor@example.com", password="pw", org=io.organization)
    prosecutor_token = login(client, "prosecutor@example.com", "pw").json()["access_token"]

    resp = client.post(f"/cases/{case['id']}/file-charge-sheet", headers=auth_headers(prosecutor_token))

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["investigation_status"] == "Charge_Sheet_Filed"

    case_row = db_session.get(models.Case, UUID(case["id"]))
    assert case_row.investigation_status == "Charge_Sheet_Filed"


def test_prosecutor_cannot_file_charge_sheet_with_unmet_requirements(client, make_user, db_session):
    case, io, io_token, _ = _setup_case_with_io(client, make_user, db_session)
    make_user("prosecutor", email="prosecutor@example.com", password="pw", org=io.organization)
    prosecutor_token = login(client, "prosecutor@example.com", "pw").json()["access_token"]

    req = models.StageRequirement(
        crime_type="Theft",
        requirement_type="document",
        requirement_key="Witness Statement",
        mandatory=True,
    )
    db_session.add(req)
    db_session.commit()

    resp = client.post(f"/cases/{case['id']}/file-charge-sheet", headers=auth_headers(prosecutor_token))

    assert resp.status_code == 409
    assert "missing" in resp.json()["detail"]
    assert len(resp.json()["detail"]["missing"]) == 1


def test_io_cannot_file_charge_sheet(client, make_user, db_session):
    case, io, io_token, _ = _setup_case_with_io(client, make_user, db_session)

    resp = client.post(f"/cases/{case['id']}/file-charge-sheet", headers=auth_headers(io_token))

    assert resp.status_code == 403


def test_charge_sheet_filing_creates_audit_log(client, make_user, db_session):
    case, io, io_token, _ = _setup_case_with_io(client, make_user, db_session)
    make_user("prosecutor", email="prosecutor@example.com", password="pw", org=io.organization)
    prosecutor_token = login(client, "prosecutor@example.com", "pw").json()["access_token"]

    client.post(f"/cases/{case['id']}/file-charge-sheet", headers=auth_headers(prosecutor_token))

    entries = (
        db_session.query(models.AuditLog)
        .filter_by(case_id=UUID(case["id"]), action="charge_sheet_filed")
        .all()
    )
    assert len(entries) == 1
    assert verify_chain_intact(db_session)
