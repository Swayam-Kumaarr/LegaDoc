"""Tests for Flow 6: Case Audit Trail & AI Parser Decision Inspection.

Validates:
  - Role-filtered audit log access (Full view for Config Admin/Security Auditor/Court;
    summarized aggregate view for IO, SHO, Prosecutor).
  - IDOR and case assignment enforcement (unassigned IO gets 403).
  - Domain 8 separation of duties (Security Auditor only for /ai-parser, Config Admin gets 403).
  - Mandatory meta-audit write on every /ai-parser read.
  - Per-user rate limiting on /ai-parser (20/min).
  - Cryptographic chain integrity verification and tamper detection.
"""

from uuid import uuid4

import pytest
from app import models, security
from app.audit import write_audit_log
from app.rate_limit import ai_parser_limiter
from tests.conftest import auth_headers


@pytest.fixture(autouse=True)
def _reset_limiter():
    ai_parser_limiter.reset()
    yield
    ai_parser_limiter.reset()


def _setup_case_with_audit_trail(db_session, make_org, make_user):
    """Creates an org, users with different roles, a case, and seeded audit log entries."""
    police_org = make_org("Central Police Station", "police")
    config_admin = make_user("config_admin", email="admin@legadoc.gov", org=police_org)
    sec_auditor = make_user("security_auditor", email="auditor@legadoc.gov", org=police_org)
    court_user = make_user("court", email="judge@court.gov", org=police_org)
    assigned_io = make_user("io", email="io_assigned@police.gov", org=police_org)
    unassigned_io = make_user("io", email="io_other@police.gov", org=police_org)
    prosecutor = make_user("prosecutor", email="prosecutor@state.gov", org=police_org)

    case = models.Case(
        case_number="FIR-2026-009988",
        crime_type="cyber_fraud",
        investigation_status="FIR_Registered",
    )
    db_session.add(case)
    db_session.commit()
    db_session.refresh(case)

    # Assign IO
    assignment = models.CaseAssignment(
        case_id=case.id,
        io_user_id=assigned_io.id,
    )
    db_session.add(assignment)
    db_session.commit()

    # Seed general audit log entries
    write_audit_log(
        db_session,
        action="fir_registered",
        case_id=case.id,
        actor_user_id=assigned_io.id,
        target_type="case",
        target_id=case.id,
        metadata={"crime_type": "cyber_fraud"},
    )
    write_audit_log(
        db_session,
        action="io_assigned",
        case_id=case.id,
        actor_user_id=config_admin.id,
        target_type="case",
        target_id=case.id,
        metadata={"io_user_id": str(assigned_io.id)},
    )
    # Seed AI Parser & Redaction decisions
    write_audit_log(
        db_session,
        action="auto_tag_completed",
        case_id=case.id,
        actor_user_id=None,  # system
        target_type="document",
        target_id=uuid4(),
        metadata={"entity_type": "phone_number", "confidence": 98, "span_start": 12, "span_end": 22},
    )
    write_audit_log(
        db_session,
        action="auto_tag_completed",
        case_id=case.id,
        actor_user_id=None,  # system
        target_type="document",
        target_id=uuid4(),
        metadata={"entity_type": "aadhaar", "confidence": 94, "span_start": 45, "span_end": 57},
    )
    write_audit_log(
        db_session,
        action="redact_tag_correction",
        case_id=case.id,
        actor_user_id=assigned_io.id,
        target_type="document",
        target_id=uuid4(),
        metadata={"entity_type": "name", "span_start": 0, "span_end": 10},
    )

    tokens = {
        "config_admin": security.create_access_token(str(config_admin.id), str(police_org.id), "config_admin"),
        "security_auditor": security.create_access_token(str(sec_auditor.id), str(police_org.id), "security_auditor"),
        "court": security.create_access_token(str(court_user.id), str(police_org.id), "court"),
        "assigned_io": security.create_access_token(str(assigned_io.id), str(police_org.id), "io"),
        "unassigned_io": security.create_access_token(str(unassigned_io.id), str(police_org.id), "io"),
        "prosecutor": security.create_access_token(str(prosecutor.id), str(police_org.id), "prosecutor"),
    }

    return case, tokens, sec_auditor


def test_config_admin_sees_full_audit_log_with_hashes(client, db_session, make_org, make_user):
    case, tokens, _ = _setup_case_with_audit_trail(db_session, make_org, make_user)
    resp = client.get(
        f"/cases/{case.id}/audit-log",
        headers=auth_headers(tokens["config_admin"]),
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["view_type"] == "full"
    assert data["chain_intact"] is True
    assert data["total_entries"] == 5
    assert len(data["entries"]) == 5

    # Check cryptographic fields are present in full view
    first_entry = data["entries"][0]
    assert "row_hash" in first_entry
    assert "prev_hash" in first_entry
    assert first_entry["row_hash"] is not None


def test_security_auditor_sees_full_audit_log(client, db_session, make_org, make_user):
    case, tokens, _ = _setup_case_with_audit_trail(db_session, make_org, make_user)
    resp = client.get(
        f"/cases/{case.id}/audit-log",
        headers=auth_headers(tokens["security_auditor"]),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["view_type"] == "full"
    assert data["chain_intact"] is True
    assert len(data["entries"]) == 5


def test_court_sees_full_audit_log(client, db_session, make_org, make_user):
    case, tokens, _ = _setup_case_with_audit_trail(db_session, make_org, make_user)
    resp = client.get(
        f"/cases/{case.id}/audit-log",
        headers=auth_headers(tokens["court"]),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["view_type"] == "full"
    assert data["chain_intact"] is True


def test_assigned_io_sees_summary_view_only(client, db_session, make_org, make_user):
    case, tokens, _ = _setup_case_with_audit_trail(db_session, make_org, make_user)
    resp = client.get(
        f"/cases/{case.id}/audit-log",
        headers=auth_headers(tokens["assigned_io"]),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["view_type"] == "summary"
    assert data["chain_intact"] is True
    assert data["total_entries"] == 5
    assert "entries" not in data
    assert data["action_counts"]["auto_tag_completed"] == 2
    assert data["action_counts"]["redact_tag_correction"] == 1
    assert data["action_counts"]["fir_registered"] == 1
    assert data["first_entry_at"] is not None


def test_prosecutor_sees_summary_view_only(client, db_session, make_org, make_user):
    case, tokens, _ = _setup_case_with_audit_trail(db_session, make_org, make_user)
    resp = client.get(
        f"/cases/{case.id}/audit-log",
        headers=auth_headers(tokens["prosecutor"]),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["view_type"] == "summary"
    assert data["total_entries"] == 5


def test_unassigned_io_rejected_with_403(client, db_session, make_org, make_user):
    case, tokens, _ = _setup_case_with_audit_trail(db_session, make_org, make_user)
    resp = client.get(
        f"/cases/{case.id}/audit-log",
        headers=auth_headers(tokens["unassigned_io"]),
    )
    assert resp.status_code == 403
    assert "Not assigned to this case" in resp.json()["detail"]


def test_nonexistent_case_returns_404(client, db_session, make_org, make_user):
    _, tokens, _ = _setup_case_with_audit_trail(db_session, make_org, make_user)
    random_id = uuid4()
    resp = client.get(
        f"/cases/{random_id}/audit-log",
        headers=auth_headers(tokens["config_admin"]),
    )
    assert resp.status_code == 404
    assert "Case not found" in resp.json()["detail"]


def test_security_auditor_can_read_ai_parser_audit(client, db_session, make_org, make_user):
    case, tokens, _ = _setup_case_with_audit_trail(db_session, make_org, make_user)
    resp = client.get(
        f"/cases/{case.id}/audit-log/ai-parser",
        headers=auth_headers(tokens["security_auditor"]),
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["case_id"] == str(case.id)
    assert data["total_entries"] == 3  # 2 auto_tag_completed + 1 redact_tag_correction

    actions = [e["action"] for e in data["entries"]]
    assert "auto_tag_completed" in actions
    assert "redact_tag_correction" in actions

    # Check span and confidence parsing
    auto_tags = [e for e in data["entries"] if e["action"] == "auto_tag_completed"]
    assert auto_tags[0]["confidence"] in (98, 94)
    assert auto_tags[0]["actor_type"] == "system"


def test_config_admin_denied_ai_parser_audit_with_403(client, db_session, make_org, make_user):
    """Domain 8 separation of duties: Config Admin can edit rules, but CANNOT inspect AI decisions."""
    case, tokens, _ = _setup_case_with_audit_trail(db_session, make_org, make_user)
    resp = client.get(
        f"/cases/{case.id}/audit-log/ai-parser",
        headers=auth_headers(tokens["config_admin"]),
    )
    assert resp.status_code == 403
    assert "Role not permitted" in resp.json()["detail"]


def test_ai_parser_read_writes_committed_meta_audit_row(client, db_session, make_org, make_user):
    case, tokens, sec_auditor = _setup_case_with_audit_trail(db_session, make_org, make_user)
    before_count = db_session.query(models.AuditLog).filter(models.AuditLog.action == "read_ai_parser_audit").count()
    assert before_count == 0

    resp = client.get(
        f"/cases/{case.id}/audit-log/ai-parser",
        headers=auth_headers(tokens["security_auditor"]),
    )
    assert resp.status_code == 200

    after_rows = db_session.query(models.AuditLog).filter(models.AuditLog.action == "read_ai_parser_audit").all()
    assert len(after_rows) == 1
    meta_row = after_rows[0]
    assert meta_row.actor_user_id == sec_auditor.id
    assert meta_row.case_id == case.id
    assert meta_row.target_type == "audit_log"
    assert meta_row.action_metadata["entries_returned"] == 3


def test_ai_parser_rate_limiter_blocks_21st_request(client, db_session, make_org, make_user):
    case, tokens, _ = _setup_case_with_audit_trail(db_session, make_org, make_user)
    headers = auth_headers(tokens["security_auditor"])

    for i in range(20):
        r = client.get(f"/cases/{case.id}/audit-log/ai-parser", headers=headers)
        assert r.status_code == 200, f"Request {i+1} failed"

    # 21st request must fail with 429
    r21 = client.get(f"/cases/{case.id}/audit-log/ai-parser", headers=headers)
    assert r21.status_code == 429
    assert "Rate limit exceeded" in r21.json()["detail"]
    assert "Retry-After" in r21.headers


def test_chain_integrity_clean_database_returns_intact(client, db_session, make_org, make_user):
    case, tokens, _ = _setup_case_with_audit_trail(db_session, make_org, make_user)
    resp = client.get(
        f"/cases/{case.id}/audit-log/chain-integrity",
        headers=auth_headers(tokens["config_admin"]),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["case_id"] == str(case.id)
    assert data["chain_intact"] is True
    assert data["total_entries"] == 5
    assert data["latest_hash"] is not None


def test_chain_integrity_detects_tampered_hash(client, db_session, make_org, make_user):
    case, tokens, _ = _setup_case_with_audit_trail(db_session, make_org, make_user)
    # Corrupt an audit log row's hash
    tampered = db_session.query(models.AuditLog).filter(models.AuditLog.case_id == case.id).first()
    tampered.row_hash = "deadbeef" * 8
    db_session.commit()

    resp = client.get(
        f"/cases/{case.id}/audit-log/chain-integrity",
        headers=auth_headers(tokens["config_admin"]),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["chain_intact"] is False


def test_chain_integrity_forbidden_for_non_admin(client, db_session, make_org, make_user):
    case, tokens, _ = _setup_case_with_audit_trail(db_session, make_org, make_user)
    resp = client.get(
        f"/cases/{case.id}/audit-log/chain-integrity",
        headers=auth_headers(tokens["assigned_io"]),
    )
    assert resp.status_code == 403


def test_audit_log_empty_case_returns_clean_response(client, db_session, make_org, make_user):
    """A case with zero audit log rows must return valid responses without crashing."""
    police_org = make_org("North Station", "police")
    admin = make_user("config_admin", email="admin_empty@police.gov", org=police_org)
    io_user = make_user("io", email="io_empty@police.gov", org=police_org)
    admin_token = security.create_access_token(str(admin.id), str(police_org.id), "config_admin")
    io_token = security.create_access_token(str(io_user.id), str(police_org.id), "io")

    empty_case = models.Case(
        case_number="FIR-2026-EMPTY",
        crime_type="theft",
        investigation_status="FIR_Registered",
    )
    db_session.add(empty_case)
    db_session.commit()
    db_session.refresh(empty_case)

    # Assign IO so case access succeeds
    db_session.add(models.CaseAssignment(case_id=empty_case.id, io_user_id=io_user.id))
    db_session.commit()

    # Admin (Full view)
    r_admin = client.get(f"/cases/{empty_case.id}/audit-log", headers=auth_headers(admin_token))
    assert r_admin.status_code == 200
    d_admin = r_admin.json()
    assert d_admin["total_entries"] == 0
    assert d_admin["entries"] == []
    assert d_admin["chain_intact"] is True

    # IO (Summary view)
    r_io = client.get(f"/cases/{empty_case.id}/audit-log", headers=auth_headers(io_token))
    assert r_io.status_code == 200
    d_io = r_io.json()
    assert d_io["total_entries"] == 0
    assert d_io["action_counts"] == {}
    assert d_io["first_entry_at"] is None
    assert d_io["chain_intact"] is True


def test_audit_log_malformed_case_id_returns_404(client, db_session, make_org, make_user):
    _, tokens, _ = _setup_case_with_audit_trail(db_session, make_org, make_user)
    # Non-UUID string must return 404, not 500
    resp = client.get("/cases/not-a-valid-uuid/audit-log", headers=auth_headers(tokens["config_admin"]))
    assert resp.status_code == 404
    assert "Case not found" in resp.json()["detail"]

    resp_ai = client.get("/cases/not-a-valid-uuid/audit-log/ai-parser", headers=auth_headers(tokens["security_auditor"]))
    assert resp_ai.status_code == 404

    resp_chain = client.get("/cases/not-a-valid-uuid/audit-log/chain-integrity", headers=auth_headers(tokens["config_admin"]))
    assert resp_chain.status_code == 404


def test_audit_log_query_filters_and_pagination(client, db_session, make_org, make_user):
    case, tokens, _ = _setup_case_with_audit_trail(db_session, make_org, make_user)

    # Filter by action=auto_tag_completed
    resp = client.get(
        f"/cases/{case.id}/audit-log?action=auto_tag_completed",
        headers=auth_headers(tokens["config_admin"]),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_entries"] == 2
    assert all(e["action"] == "auto_tag_completed" for e in data["entries"])

    # Pagination: limit=1, offset=1
    paged = client.get(
        f"/cases/{case.id}/audit-log?limit=1&offset=1",
        headers=auth_headers(tokens["config_admin"]),
    )
    assert paged.status_code == 200
    assert len(paged.json()["entries"]) == 1
    assert paged.json()["total_entries"] == 5


def test_chain_integrity_detects_row_deletion(client, db_session, make_org, make_user):
    """Deleting any row in the middle must break the cryptographic hash chain."""
    case, tokens, _ = _setup_case_with_audit_trail(db_session, make_org, make_user)
    rows = db_session.query(models.AuditLog).order_by(models.AuditLog.created_at.asc()).all()
    assert len(rows) >= 3

    # Delete the second row
    db_session.delete(rows[1])
    db_session.commit()

    resp = client.get(
        f"/cases/{case.id}/audit-log/chain-integrity",
        headers=auth_headers(tokens["config_admin"]),
    )
    assert resp.status_code == 200
    assert resp.json()["chain_intact"] is False

