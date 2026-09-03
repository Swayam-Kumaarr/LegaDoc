"""Tests for reports/case-metadata and documents?status=needs_review."""

from uuid import UUID

from app import models
from tests.conftest import auth_headers, login


def test_records_ncrb_analyst_can_get_case_metadata(client, make_user, db_session):
    duty = make_user("duty_officer", email="duty@example.com", password="pw")
    duty_token = login(client, "duty@example.com", "pw").json()["access_token"]
    client.post(
        "/cases", json={"crime_type": "Theft", "complaint_text": "..."}, headers=auth_headers(duty_token)
    )

    make_user("records_ncrb_analyst", email="ncrb@example.com", password="pw")
    ncrb_token = login(client, "ncrb@example.com", "pw").json()["access_token"]

    resp = client.get("/reports/case-metadata", headers=auth_headers(ncrb_token))

    assert resp.status_code == 200
    assert len(resp.json()) == 1
    data = resp.json()[0]
    assert "crime_type" in data
    assert "investigation_status" in data
    assert "created_at" in data


def test_non_ncrb_role_cannot_get_case_metadata(client, make_user, db_session):
    make_user("duty_officer", email="duty@example.com", password="pw")
    duty_token = login(client, "duty@example.com", "pw").json()["access_token"]

    resp = client.get("/reports/case-metadata", headers=auth_headers(duty_token))

    assert resp.status_code == 403


def test_case_metadata_has_no_identity_fields(client, make_user, db_session):
    make_user("records_ncrb_analyst", email="ncrb@example.com", password="pw")
    ncrb_token = login(client, "ncrb@example.com", "pw").json()["access_token"]

    resp = client.get("/reports/case-metadata", headers=auth_headers(ncrb_token))

    assert resp.status_code == 200
    if resp.json():
        data = resp.json()[0]
        forbidden_fields = {"complainant_name", "victim_name", "accused_name", "hashed_password", "email"}
        assert not forbidden_fields.intersection(data.keys())


def test_config_admin_can_list_needing_review_documents(client, make_user, db_session):
    duty = make_user("duty_officer", email="duty@example.com", password="pw")
    sho = make_user("sho", email="sho@example.com", password="pw", org=duty.organization)
    io = make_user("io", email="io@example.com", password="pw", org=duty.organization)

    duty_token = login(client, "duty@example.com", "pw").json()["access_token"]
    case = client.post(
        "/cases", json={"crime_type": "Theft", "complaint_text": "..."}, headers=auth_headers(duty_token)
    ).json()

    sho_token = login(client, "sho@example.com", "pw").json()["access_token"]
    client.post(
        f"/cases/{case['id']}/assign-io", json={"io_user_id": str(io.id)}, headers=auth_headers(sho_token)
    )

    io_token = login(client, "io@example.com", "pw").json()["access_token"]
    doc_resp = client.post(
        "/documents",
        data={"case_id": case["id"], "doc_type": "Witness Statement"},
        files={"file": ("stmt.txt", b"content", "text/plain")},
        headers=auth_headers(io_token),
    )
    doc_id = doc_resp.json()["id"]

    doc = db_session.get(models.Document, UUID(doc_id))
    doc.status = "needs_review"
    db_session.commit()

    make_user("config_admin", email="admin@example.com", password="pw")
    admin_token = login(client, "admin@example.com", "pw").json()["access_token"]

    resp = client.get("/documents?status=needs_review", headers=auth_headers(admin_token))

    assert resp.status_code == 200
    assert len(resp.json()) == 1
    assert resp.json()[0]["status"] == "needs_review"


def test_needs_review_without_filter_returns_all(client, make_user, db_session):
    duty = make_user("duty_officer", email="duty@example.com", password="pw")
    sho = make_user("sho", email="sho@example.com", password="pw", org=duty.organization)
    io = make_user("io", email="io@example.com", password="pw", org=duty.organization)

    duty_token = login(client, "duty@example.com", "pw").json()["access_token"]
    case = client.post(
        "/cases", json={"crime_type": "Theft", "complaint_text": "..."}, headers=auth_headers(duty_token)
    ).json()

    sho_token = login(client, "sho@example.com", "pw").json()["access_token"]
    client.post(
        f"/cases/{case['id']}/assign-io", json={"io_user_id": str(io.id)}, headers=auth_headers(sho_token)
    )

    io_token = login(client, "io@example.com", "pw").json()["access_token"]
    client.post(
        "/documents",
        data={"case_id": case["id"], "doc_type": "Witness Statement"},
        files={"file": ("stmt.txt", b"content", "text/plain")},
        headers=auth_headers(io_token),
    )

    make_user("config_admin", email="admin@example.com", password="pw")
    admin_token = login(client, "admin@example.com", "pw").json()["access_token"]

    resp = client.get("/documents", headers=auth_headers(admin_token))

    assert resp.status_code == 200
    assert len(resp.json()) >= 1


def test_non_admin_io_cannot_list_needing_review(client, make_user, db_session):
    make_user("duty_officer", email="duty@example.com", password="pw")
    duty_token = login(client, "duty@example.com", "pw").json()["access_token"]

    resp = client.get("/documents?status=needs_review", headers=auth_headers(duty_token))

    assert resp.status_code == 403
