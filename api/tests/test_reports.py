"""Tests for Domain 7 — Records / NCRB Reporting (GET /reports/case-metadata).

Verifies that the records_ncrb_analyst role receives de-identified statistical
case metadata only, with strict exclusion of identity/PII fields, boundary
validation on pagination, filtering support, audit trail recording, and
robust default-deny on all other roles.
"""

from uuid import uuid4

from tests.conftest import auth_headers, login
from app import models
from app.audit import verify_chain_intact


def _make_ncrb_analyst(make_user, make_org):
    ncrb_org = make_org(name="National Crime Records Bureau", org_type="ncrb")
    analyst = make_user("records_ncrb_analyst", email="analyst@ncrb.gov.in", password="pw", org=ncrb_org)
    return analyst


def _seed_cases(db_session, count=3):
    cases = []
    crime_types = ["Theft", "Cybercrime", "Homicide"]
    statuses = ["FIR_Registered", "Evidence_Collection", "Charge_Sheet_Filed"]
    for i in range(count):
        c = models.Case(
            case_number=f"NCRB-TEST-{uuid4().hex[:6].upper()}",
            crime_type=crime_types[i % len(crime_types)],
            court_level="sessions",
            investigation_status=statuses[i % len(statuses)],
            bail_status="Not_Applied",
        )
        db_session.add(c)
        cases.append(c)
    db_session.commit()
    for c in cases:
        db_session.refresh(c)
    return cases


def test_ncrb_analyst_gets_deidentified_case_metadata(client, make_user, make_org, db_session):
    """Happy path: NCRB Analyst fetches de-identified case metadata."""
    analyst = _make_ncrb_analyst(make_user, make_org)
    token = login(client, analyst.email, "pw").json()["access_token"]

    cases = _seed_cases(db_session, count=3)

    resp = client.get("/reports/case-metadata", headers=auth_headers(token))
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert len(data) >= 3

    first = data[0]
    assert "id" in first
    assert "case_number" in first
    assert "crime_type" in first
    assert "court_level" in first
    assert "investigation_status" in first
    assert "bail_status" in first
    assert "created_at" in first


def test_ncrb_analyst_cannot_see_user_or_pii_fields(client, make_user, make_org, db_session):
    """Structural PII exclusion: response must contain zero personal/organizational identifiers."""
    analyst = _make_ncrb_analyst(make_user, make_org)
    token = login(client, analyst.email, "pw").json()["access_token"]

    _seed_cases(db_session, count=2)

    resp = client.get("/reports/case-metadata", headers=auth_headers(token))
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) > 0

    allowed_keys = {
        "id",
        "case_number",
        "crime_type",
        "court_level",
        "investigation_status",
        "bail_status",
        "created_at",
    }
    forbidden_substrings = ["user", "org", "password", "officer", "victim", "accused", "text", "raw"]

    for item in data:
        assert set(item.keys()) == allowed_keys
        for key in item.keys():
            for forbidden in forbidden_substrings:
                assert forbidden not in key.lower()


def test_ncrb_reports_pagination_bounds(client, make_user, make_org, db_session):
    """Validates limit/offset query parameters and ensures bounds are enforced."""
    analyst = _make_ncrb_analyst(make_user, make_org)
    token = login(client, analyst.email, "pw").json()["access_token"]

    _seed_cases(db_session, count=5)

    # Valid pagination: limit=2, offset=1
    resp = client.get("/reports/case-metadata?limit=2&offset=1", headers=auth_headers(token))
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2

    # Offset beyond available cases returns clean empty list
    resp_empty = client.get("/reports/case-metadata?limit=10&offset=500", headers=auth_headers(token))
    assert resp_empty.status_code == 200
    assert resp_empty.json() == []

    # Boundary checks: limit < 1 or limit > 500 triggers 422
    assert client.get("/reports/case-metadata?limit=0", headers=auth_headers(token)).status_code == 422
    assert client.get("/reports/case-metadata?limit=1000", headers=auth_headers(token)).status_code == 422
    # Boundary check: negative offset triggers 422
    assert client.get("/reports/case-metadata?offset=-1", headers=auth_headers(token)).status_code == 422


def test_ncrb_reports_filtering(client, make_user, make_org, db_session):
    """Validates filtering by crime_type and investigation_status."""
    analyst = _make_ncrb_analyst(make_user, make_org)
    token = login(client, analyst.email, "pw").json()["access_token"]

    c1 = models.Case(case_number="FILTER-THEFT-01", crime_type="Theft", investigation_status="FIR_Registered")
    c2 = models.Case(case_number="FILTER-CYBER-02", crime_type="Cybercrime", investigation_status="Trial")
    db_session.add_all([c1, c2])
    db_session.commit()

    # Filter by crime_type
    r1 = client.get("/reports/case-metadata?crime_type=Theft", headers=auth_headers(token))
    assert r1.status_code == 200
    data1 = r1.json()
    assert all(d["crime_type"] == "Theft" for d in data1)
    assert any(d["case_number"] == "FILTER-THEFT-01" for d in data1)

    # Filter by investigation_status
    r2 = client.get("/reports/case-metadata?investigation_status=Trial", headers=auth_headers(token))
    assert r2.status_code == 200
    data2 = r2.json()
    assert all(d["investigation_status"] == "Trial" for d in data2)
    assert any(d["case_number"] == "FILTER-CYBER-02" for d in data2)


def test_ncrb_reports_empty_database_returns_clean_list(client, make_user, make_org):
    """Empty database state must return 200 OK with [] without crashing."""
    analyst = _make_ncrb_analyst(make_user, make_org)
    token = login(client, analyst.email, "pw").json()["access_token"]

    resp = client.get("/reports/case-metadata", headers=auth_headers(token))
    assert resp.status_code == 200
    assert resp.json() == []


def test_unauthorized_roles_rejected_from_ncrb_reports(client, make_user, make_org, db_session):
    """Negative space: unauthenticated and unauthorized roles must receive 401/403."""
    _seed_cases(db_session, count=1)

    # 1. Unauthenticated request
    r_anon = client.get("/reports/case-metadata")
    assert r_anon.status_code == 401

    # 2. Unauthorized roles (IO, SHO, Prosecutor, Defense, Court, Config Admin, Security Auditor)
    unauthorized_roles = [
        "io",
        "sho",
        "prosecutor",
        "defense",
        "court",
        "config_admin",
        "security_auditor",
        "duty_officer",
    ]
    for role in unauthorized_roles:
        u = make_user(role, email=f"{role}_analyst_test@example.com", password="pw")
        tok = login(client, u.email, "pw").json()["access_token"]
        r = client.get("/reports/case-metadata", headers=auth_headers(tok))
        assert r.status_code == 403, f"Role {role} should have been denied with 403, got {r.status_code}"


def test_ncrb_report_writes_audit_log_and_chain_remains_intact(client, make_user, make_org, db_session):
    """Accessing NCRB report records an audit row and preserves tamper-evident hash chaining."""
    analyst = _make_ncrb_analyst(make_user, make_org)
    token = login(client, analyst.email, "pw").json()["access_token"]

    _seed_cases(db_session, count=2)

    resp = client.get("/reports/case-metadata?limit=10", headers=auth_headers(token))
    assert resp.status_code == 200

    # Verify audit entry was written
    audit_row = (
        db_session.query(models.AuditLog)
        .filter(models.AuditLog.action == "ncrb_report_generated")
        .first()
    )
    assert audit_row is not None
    assert audit_row.actor_user_id == analyst.id
    assert audit_row.action_metadata["limit"] == 10
    assert audit_row.action_metadata["count"] == 2

    # Verify global hash chain integrity remains intact
    assert verify_chain_intact(db_session) is True
