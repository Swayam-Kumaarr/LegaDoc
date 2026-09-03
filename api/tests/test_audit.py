"""Tests for audit-log and ai-parser audit endpoints."""

from uuid import UUID

from app import models
from app.audit import verify_chain_intact
from tests.conftest import auth_headers, login


def _setup_case_with_roles(client, make_user, db_session):
    duty = make_user("duty_officer", email="duty@example.com", password="pw")
    sho = make_user("sho", email="sho@example.com", password="pw", org=duty.organization)
    io = make_user("io", email="io@example.com", password="pw", org=duty.organization)
    security_auditor = make_user("security_auditor", email="auditor@example.com", password="pw", org=duty.organization)
    config_admin = make_user("config_admin", email="admin@example.com", password="pw", org=duty.organization)

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
    auditor_token = login(client, "auditor@example.com", "pw").json()["access_token"]
    admin_token = login(client, "admin@example.com", "pw").json()["access_token"]

    return case, io_token, auditor_token, admin_token


def test_config_admin_gets_full_audit_log(client, make_user, db_session):
    case, io_token, auditor_token, admin_token = _setup_case_with_roles(client, make_user, db_session)

    client.post(f"/cases/{case['id']}/case-diary", json={"text": "Note"}, headers=auth_headers(io_token))

    resp = client.get(f"/cases/{case['id']}/audit-log", headers=auth_headers(admin_token))

    assert resp.status_code == 200
    entries = resp.json()
    assert len(entries) >= 1


def test_io_gets_summarized_audit_log(client, make_user, db_session):
    case, io_token, auditor_token, admin_token = _setup_case_with_roles(client, make_user, db_session)

    client.post(f"/cases/{case['id']}/case-diary", json={"text": "Note 1"}, headers=auth_headers(io_token))
    client.post(f"/cases/{case['id']}/case-diary", json={"text": "Note 2"}, headers=auth_headers(io_token))

    resp = client.get(f"/cases/{case['id']}/audit-log", headers=auth_headers(io_token))

    assert resp.status_code == 200
    entries = resp.json()
    assert len(entries) >= 1


def test_unassigned_io_cannot_read_audit_log(client, make_user, db_session):
    case, io_token, auditor_token, admin_token = _setup_case_with_roles(client, make_user, db_session)
    other_io = make_user("io", email="other@example.com", password="pw")
    other_token = login(client, "other@example.com", "pw").json()["access_token"]

    resp = client.get(f"/cases/{case['id']}/audit-log", headers=auth_headers(other_token))

    assert resp.status_code == 403


def test_ai_parser_audit_requires_security_auditor_role(client, make_user, db_session):
    case, io_token, auditor_token, admin_token = _setup_case_with_roles(client, make_user, db_session)

    resp = client.get(f"/cases/{case['id']}/audit-log/ai-parser", headers=auth_headers(admin_token))

    assert resp.status_code == 403


def test_security_auditor_can_read_ai_parser_audit(client, make_user, db_session):
    case, io_token, auditor_token, admin_token = _setup_case_with_roles(client, make_user, db_session)

    resp = client.get(f"/cases/{case['id']}/audit-log/ai-parser", headers=auth_headers(auditor_token))

    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_ai_parser_audit_writes_meta_audit_row(client, make_user, db_session):
    case, io_token, auditor_token, admin_token = _setup_case_with_roles(client, make_user, db_session)

    before_count = (
        db_session.query(models.AuditLog)
        .filter_by(case_id=UUID(case["id"]), action="read_ai_parser_audit")
        .count()
    )

    client.get(f"/cases/{case['id']}/audit-log/ai-parser", headers=auth_headers(auditor_token))

    after_count = (
        db_session.query(models.AuditLog)
        .filter_by(case_id=UUID(case["id"]), action="read_ai_parser_audit")
        .count()
    )
    assert after_count == before_count + 1
    assert verify_chain_intact(db_session)


def test_audit_log_nonexistent_case_returns_404(client, make_user, db_session):
    make_user("security_auditor", email="auditor@example.com", password="pw")
    auditor_token = login(client, "auditor@example.com", "pw").json()["access_token"]

    resp = client.get(
        "/cases/00000000-0000-0000-0000-000000000000/audit-log",
        headers=auth_headers(auditor_token),
    )

    assert resp.status_code == 404
