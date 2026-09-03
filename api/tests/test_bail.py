"""Tests for all 5 bail endpoints."""

from uuid import UUID

from app import models
from app.audit import verify_chain_intact
from tests.conftest import auth_headers, login


def _setup_case_with_roles(client, make_user, db_session):
    duty = make_user("duty_officer", email="duty@example.com", password="pw")
    sho = make_user("sho", email="sho@example.com", password="pw", org=duty.organization)
    io = make_user("io", email="io@example.com", password="pw", org=duty.organization)
    defense = make_user("defense", email="defense@example.com", password="pw", org=duty.organization)
    court = make_user("court", email="court@example.com", password="pw", org=duty.organization)

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
    defense_token = login(client, "defense@example.com", "pw").json()["access_token"]
    court_token = login(client, "court@example.com", "pw").json()["access_token"]

    return case, io_token, defense_token, court_token


def test_record_arrest_starts_bail_track(client, make_user, db_session):
    case, io_token, _, _ = _setup_case_with_roles(client, make_user, db_session)

    resp = client.post(f"/cases/{case['id']}/bail/arrest", headers=auth_headers(io_token))

    assert resp.status_code == 201, resp.text
    assert resp.json()["stage"] == "Arrested"

    case_row = db_session.get(models.Case, UUID(case["id"]))
    assert case_row.bail_status == "Arrested"


def test_duty_officer_recording_arrest_requires_case_access(client, make_user, db_session):
    duty = make_user("duty_officer", email="duty@example.com", password="pw")
    duty_token = login(client, "duty@example.com", "pw").json()["access_token"]
    case = client.post(
        "/cases", json={"crime_type": "Theft", "complaint_text": "..."}, headers=auth_headers(duty_token)
    ).json()

    resp = client.post(f"/cases/{case['id']}/bail/arrest", headers=auth_headers(duty_token))

    assert resp.status_code == 403


def test_defense_cannot_record_arrest(client, make_user, db_session):
    case, _, defense_token, _ = _setup_case_with_roles(client, make_user, db_session)

    resp = client.post(f"/cases/{case['id']}/bail/arrest", headers=auth_headers(defense_token))

    assert resp.status_code == 403


def test_file_bail_application(client, make_user, db_session):
    case, _, defense_token, _ = _setup_case_with_roles(client, make_user, db_session)

    resp = client.post(f"/cases/{case['id']}/bail/application", headers=auth_headers(defense_token))

    assert resp.status_code == 201, resp.text
    assert resp.json()["stage"] == "Application_Filed"

    case_row = db_session.get(models.Case, UUID(case["id"]))
    assert case_row.bail_status == "Application_Filed"


def test_court_cannot_file_bail_application(client, make_user, db_session):
    case, _, _, court_token = _setup_case_with_roles(client, make_user, db_session)

    resp = client.post(f"/cases/{case['id']}/bail/application", headers=auth_headers(court_token))

    assert resp.status_code == 403


def test_schedule_bail_hearing(client, make_user, db_session):
    case, _, _, court_token = _setup_case_with_roles(client, make_user, db_session)

    resp = client.post(f"/cases/{case['id']}/bail/hearing-notice", headers=auth_headers(court_token))

    assert resp.status_code == 201, resp.text
    assert resp.json()["stage"] == "Hearing_Scheduled"

    case_row = db_session.get(models.Case, UUID(case["id"]))
    assert case_row.bail_status == "Hearing_Scheduled"


def test_issue_bail_order_granted(client, make_user, db_session):
    case, _, _, court_token = _setup_case_with_roles(client, make_user, db_session)

    resp = client.post(
        f"/cases/{case['id']}/bail/order",
        json={"decision": "granted"},
        headers=auth_headers(court_token),
    )

    assert resp.status_code == 201, resp.text
    assert resp.json()["stage"] == "Order_Issued"

    case_row = db_session.get(models.Case, UUID(case["id"]))
    assert case_row.bail_status == "Order_Issued"


def test_issue_bail_order_denied(client, make_user, db_session):
    case, _, _, court_token = _setup_case_with_roles(client, make_user, db_session)

    resp = client.post(
        f"/cases/{case['id']}/bail/order",
        json={"decision": "denied"},
        headers=auth_headers(court_token),
    )

    assert resp.status_code == 201, resp.text
    assert resp.json()["stage"] == "Denied_Final"


def test_issue_bail_order_invalid_decision(client, make_user, db_session):
    case, _, _, court_token = _setup_case_with_roles(client, make_user, db_session)

    resp = client.post(
        f"/cases/{case['id']}/bail/order",
        json={"decision": "maybe"},
        headers=auth_headers(court_token),
    )

    assert resp.status_code == 422


def test_register_surety(client, make_user, db_session):
    case, _, defense_token, _ = _setup_case_with_roles(client, make_user, db_session)

    resp = client.post(f"/cases/{case['id']}/bail/surety", headers=auth_headers(defense_token))

    assert resp.status_code == 201, resp.text
    assert resp.json()["stage"] == "Surety_Registered"

    case_row = db_session.get(models.Case, UUID(case["id"]))
    assert case_row.bail_status == "Surety_Registered"


def test_bail_track_creates_audit_log(client, make_user, db_session):
    case, io_token, defense_token, court_token = _setup_case_with_roles(client, make_user, db_session)

    client.post(f"/cases/{case['id']}/bail/arrest", headers=auth_headers(io_token))
    client.post(f"/cases/{case['id']}/bail/application", headers=auth_headers(defense_token))
    client.post(f"/cases/{case['id']}/bail/hearing-notice", headers=auth_headers(court_token))
    client.post(
        f"/cases/{case['id']}/bail/order",
        json={"decision": "granted"},
        headers=auth_headers(court_token),
    )
    client.post(f"/cases/{case['id']}/bail/surety", headers=auth_headers(defense_token))

    entries = (
        db_session.query(models.AuditLog)
        .filter_by(case_id=UUID(case["id"]))
        .order_by(models.AuditLog.created_at.asc())
        .all()
    )
    actions = [e.action for e in entries]
    assert "bail_arrest_recorded" in actions
    assert "bail_application_filed" in actions
    assert "bail_hearing_scheduled" in actions
    assert "bail_order_issued" in actions
    assert "bail_surety_registered" in actions
    assert verify_chain_intact(db_session)


def test_full_bail_lifecycle(client, make_user, db_session):
    case, io_token, defense_token, court_token = _setup_case_with_roles(client, make_user, db_session)

    resp = client.post(f"/cases/{case['id']}/bail/arrest", headers=auth_headers(io_token))
    assert resp.json()["stage"] == "Arrested"

    resp = client.post(f"/cases/{case['id']}/bail/application", headers=auth_headers(defense_token))
    assert resp.json()["stage"] == "Application_Filed"

    resp = client.post(f"/cases/{case['id']}/bail/hearing-notice", headers=auth_headers(court_token))
    assert resp.json()["stage"] == "Hearing_Scheduled"

    resp = client.post(
        f"/cases/{case['id']}/bail/order",
        json={"decision": "granted"},
        headers=auth_headers(court_token),
    )
    assert resp.json()["stage"] == "Order_Issued"

    resp = client.post(f"/cases/{case['id']}/bail/surety", headers=auth_headers(defense_token))
    assert resp.json()["stage"] == "Surety_Registered"

    case_row = db_session.get(models.Case, UUID(case["id"]))
    assert case_row.bail_status == "Surety_Registered"
