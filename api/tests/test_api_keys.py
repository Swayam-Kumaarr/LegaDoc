"""API-key management + auth tests.

Covers the full vertical slice:
- Config Admin creates a key for a target user; the raw key is returned once
- The X-API-Key header authenticates and acts as its owning user (org + role
  claims feed the normal RBAC / case-scoping path)
- Revocation, expiry, unknown keys, and non-admin access are all rejected
- List responses never leak the raw key or its hash

No external services needed — in-memory SQLite via conftest fixtures.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app import models, security
from tests.conftest import auth_headers


@pytest.fixture
def config_admin(client, make_user):
    """A config_admin user (created fresh per test) plus a valid JWT for them."""
    make_user(role="config_admin", email="config_admin@example.com")
    login = client.post(
        "/auth/login",
        json={"email": "config_admin@example.com", "password": "correct-horse-battery-staple"},
    )
    admin_token = login.json()["access_token"]
    me = client.get("/auth/me", headers=auth_headers(admin_token))
    return me.json()["id"], admin_token


def _create_key(client, admin_token, user_id, name="integration", **extra):
    body = {"user_id": str(user_id), "name": name}
    body.update(extra)
    return client.post("/admin/api-keys", headers=auth_headers(admin_token), json=body)


def test_create_key_returns_raw_key_exactly_once(client, db_session, config_admin, make_org, make_user):
    io = make_user(role="io", email="io1@police.gov.in")
    _, admin_token = config_admin

    res = _create_key(client, admin_token, io.id, name="cctns sync")
    assert res.status_code == 201
    data = res.json()
    assert data["key"].startswith("legadoc_")
    assert len(data["key"]) > 32
    assert data["key_prefix"].startswith("legadoc_")
    assert data["name"] == "cctns sync"

    # Only the SHA-256 hash is stored — the raw key must NOT be recoverable.
    stored = db_session.query(models.ApiKey).filter(models.ApiKey.id == data["id"]).first()
    assert stored is not None
    assert stored.key_hash == security.hash_api_key(data["key"])
    assert stored.key_hash != data["key"]
    assert stored.user_id == io.id


def test_api_key_authenticates_acting_as_owner(client, config_admin, make_user):
    io = make_user(role="io", email="io1@police.gov.in")
    _, admin_token = config_admin
    created = _create_key(client, admin_token, io.id).json()

    me = client.get("/auth/me", headers={"X-API-Key": created["key"]})
    assert me.status_code == 200
    assert me.json()["email"] == "io1@police.gov.in"
    assert me.json()["role"] == "io"

    # last_used_at is stamped after the first authenticated call.
    listing = client.get("/admin/api-keys", headers=auth_headers(admin_token)).json()
    assert listing[0]["last_used_at"] is not None


def test_api_key_acts_with_owner_role_for_rbac(client, config_admin, make_org, make_user):
    cm_id, admin_token = config_admin
    io = make_user(role="io", email="io2@police.gov.in")
    cm_other = make_user(role="config_admin", email="cm2@police.gov.in")

    cm_key = _create_key(client, admin_token, cm_other.id).json()["key"]
    io_key = _create_key(client, admin_token, io.id).json()["key"]

    assert client.get("/admin/permissions", headers={"X-API-Key": cm_key}).status_code == 200
    assert client.get("/admin/permissions", headers={"X-API-Key": io_key}).status_code == 403


def test_non_admin_cannot_manage_keys(client, make_user):
    io = make_user(role="io", email="io3@police.gov.in")
    login = client.post("/auth/login", json={"email": "io3@police.gov.in", "password": "correct-horse-battery-staple"})
    io_token = login.json()["access_token"]

    assert client.get("/admin/api-keys", headers=auth_headers(io_token)).status_code == 403
    assert _create_key(client, io_token, io.id).status_code == 403


def test_invalid_api_key_rejected(client):
    assert client.get("/auth/me", headers={"X-API-Key": "legadoc_not-a-real-key"}).status_code == 401


def test_missing_credentials_still_401(client):
    assert client.get("/auth/me").status_code == 401


def test_revoked_api_key_rejected(client, config_admin, make_user):
    io = make_user(role="io", email="io4@police.gov.in")
    _, admin_token = config_admin
    created = _create_key(client, admin_token, io.id).json()
    raw = created["key"]

    assert client.get("/auth/me", headers={"X-API-Key": raw}).status_code == 200

    assert client.post(f"/admin/api-keys/{created['id']}/revoke", headers=auth_headers(admin_token)).status_code == 200
    assert client.get("/auth/me", headers={"X-API-Key": raw}).status_code == 401
    assert client.post(f"/admin/api-keys/{created['id']}/revoke", headers=auth_headers(admin_token)).status_code == 400


def test_expired_api_key_rejected(client, config_admin, make_user):
    io = make_user(role="io", email="io5@police.gov.in")
    _, admin_token = config_admin
    past = datetime.now(timezone.utc) - timedelta(hours=1)
    created = _create_key(client, admin_token, io.id, expires_at=past.isoformat()).json()

    assert client.get("/auth/me", headers={"X-API-Key": created["key"]}).status_code == 401


def test_list_never_leaks_raw_key(client, config_admin, make_user):
    io = make_user(role="io", email="io6@police.gov.in")
    _, admin_token = config_admin
    created = _create_key(client, admin_token, io.id, name="leaky test").json()

    listing = client.get("/admin/api-keys", headers=auth_headers(admin_token))
    assert listing.status_code == 200
    row = listing.json()[0]
    assert row["key_prefix"] == created["key_prefix"]
    assert row["name"] == "leaky test"
    assert "key" not in row
    assert "key_hash" not in row
    assert created["key"] not in str(listing.json())


def test_api_key_org_scoping_preserved(client, config_admin, make_org, make_user):
    # The whole point of (org, role) claims: a key for an IO in Org A must
    # NOT let someone read Org B's case — same rule as a normal login.
    io_a = make_user(role="io", email="ioa@police.gov.in")
    duty_b = make_user(role="duty_officer", email="dutyb@police.gov.in")
    cm_id, admin_token = config_admin

    # Org B registers a case as its duty officer (claims org_id = duty user's org).
    duty_login = client.post("/auth/login", json={"email": "dutyb@police.gov.in", "password": "correct-horse-battery-staple"})
    case_res = client.post(
        "/cases",
        headers=auth_headers(duty_login.json()["access_token"]),
        json={"crime_type": "theft", "complaint_text": "reported"},
    )
    assert case_res.status_code == 201
    case_id = case_res.json()["id"]

    io_a_key = _create_key(client, admin_token, io_a.id).json()["key"]
    cm_key = _create_key(client, admin_token, cm_id).json()["key"]

    # IO A's key: 403 — no CaseAssignment, not in any unrestricted role.
    assert client.get(f"/cases/{case_id}", headers={"X-API-Key": io_a_key}).status_code == 403

    # Config Admin's key: 200 — unrestricted roles still see every case.
    assert client.get(f"/cases/{case_id}", headers={"X-API-Key": cm_key}).status_code == 200
