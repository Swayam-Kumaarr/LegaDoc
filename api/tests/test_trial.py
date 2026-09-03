"""Tests for trial hearing-notice and judgment endpoints."""

from uuid import UUID

from app import models
from app.audit import verify_chain_intact
from tests.conftest import auth_headers, login


def _setup_case_with_court(client, make_user, db_session):
    duty = make_user("duty_officer", email="duty@example.com", password="pw")
    court = make_user("court", email="court@example.com", password="pw", org=duty.organization)

    duty_token = login(client, "duty@example.com", "pw").json()["access_token"]
    case = client.post(
        "/cases", json={"crime_type": "Theft", "complaint_text": "..."}, headers=auth_headers(duty_token)
    ).json()

    court_token = login(client, "court@example.com", "pw").json()["access_token"]
    return case, court_token


def test_court_can_schedule_trial_hearing(client, make_user, db_session):
    case, court_token = _setup_case_with_court(client, make_user, db_session)

    resp = client.post(f"/cases/{case['id']}/trial/hearing-notice", headers=auth_headers(court_token))

    assert resp.status_code == 200, resp.text
    assert resp.json()["investigation_status"] == "Trial"

    case_row = db_session.get(models.Case, UUID(case["id"]))
    assert case_row.investigation_status == "Trial"


def test_io_cannot_schedule_trial_hearing(client, make_user, db_session):
    duty = make_user("duty_officer", email="duty@example.com", password="pw")
    io = make_user("io", email="io@example.com", password="pw", org=duty.organization)
    sho = make_user("sho", email="sho@example.com", password="pw", org=duty.organization)

    duty_token = login(client, "duty@example.com", "pw").json()["access_token"]
    case = client.post(
        "/cases", json={"crime_type": "Theft", "complaint_text": "..."}, headers=auth_headers(duty_token)
    ).json()

    sho_token = login(client, "sho@example.com", "pw").json()["access_token"]
    client.post(f"/cases/{case['id']}/assign-io", json={"io_user_id": str(io.id)}, headers=auth_headers(sho_token))

    io_token = login(client, "io@example.com", "pw").json()["access_token"]
    resp = client.post(f"/cases/{case['id']}/trial/hearing-notice", headers=auth_headers(io_token))

    assert resp.status_code == 403


def test_court_can_record_judgment(client, make_user, db_session):
    case, court_token = _setup_case_with_court(client, make_user, db_session)

    resp = client.post(
        f"/cases/{case['id']}/judgment",
        json={"verdict": "guilty"},
        headers=auth_headers(court_token),
    )

    assert resp.status_code == 200, resp.text
    assert resp.json()["investigation_status"] == "Judgment"

    case_row = db_session.get(models.Case, UUID(case["id"]))
    assert case_row.investigation_status == "Judgment"


def test_judgment_is_terminal(client, make_user, db_session):
    case, court_token = _setup_case_with_court(client, make_user, db_session)

    client.post(f"/cases/{case['id']}/trial/hearing-notice", headers=auth_headers(court_token))
    client.post(f"/cases/{case['id']}/judgment", json={}, headers=auth_headers(court_token))

    case_row = db_session.get(models.Case, UUID(case["id"]))
    assert case_row.investigation_status == "Judgment"


def test_trial_and_judgment_create_audit_log(client, make_user, db_session):
    case, court_token = _setup_case_with_court(client, make_user, db_session)

    client.post(f"/cases/{case['id']}/trial/hearing-notice", headers=auth_headers(court_token))
    client.post(f"/cases/{case['id']}/judgment", json={"verdict": "not_guilty"}, headers=auth_headers(court_token))

    entries = (
        db_session.query(models.AuditLog)
        .filter_by(case_id=UUID(case["id"]))
        .order_by(models.AuditLog.created_at.asc())
        .all()
    )
    actions = [e.action for e in entries]
    assert "trial_hearing_scheduled" in actions
    assert "judgment_recorded" in actions
    assert entries[-1].action_metadata["verdict"] == "not_guilty"
    assert verify_chain_intact(db_session)


def test_nonexistent_case_returns_404(client, make_user, db_session):
    court = make_user("court", email="court@example.com", password="pw")
    court_token = login(client, "court@example.com", "pw").json()["access_token"]

    resp = client.post(
        "/cases/00000000-0000-0000-0000-000000000000/trial/hearing-notice",
        headers=auth_headers(court_token),
    )

    assert resp.status_code == 404
