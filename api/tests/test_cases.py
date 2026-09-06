"""Case lifecycle + the CRITICAL cross-case access fix.

The single most important test in this file is
test_unassigned_io_cannot_read_other_ios_case — it's the automated,
permanent version of the finding "any IO officer could browse any sensitive
case across the state." A regression here is a real, dangerous leak, not a
cosmetic bug.
"""

from uuid import UUID, uuid4

from tests.conftest import login, auth_headers
from app import models
from app.audit import verify_case_chain_integrity, verify_chain_intact


def _register_fir(client, token, crime_type="Theft"):
    resp = client.post(
        "/cases",
        json={"crime_type": crime_type, "complaint_text": "Something was stolen."},
        headers=auth_headers(token),
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_duty_officer_can_register_a_fir(client, make_user):
    make_user("duty_officer", email="duty@example.com", password="pw")
    token = login(client, "duty@example.com", "pw").json()["access_token"]

    case = _register_fir(client, token, crime_type="Theft")

    assert case["crime_type"] == "Theft"
    assert case["investigation_status"] == "FIR_Registered"
    assert case["case_number"].startswith("THE-")


def test_only_duty_officer_can_register_a_fir(client, make_user):
    make_user("io", email="io@example.com", password="pw")
    token = login(client, "io@example.com", "pw").json()["access_token"]

    resp = client.post(
        "/cases",
        json={"crime_type": "Theft", "complaint_text": "..."},
        headers=auth_headers(token),
    )

    assert resp.status_code == 403


def test_sho_can_assign_io_and_assigned_io_can_then_read_the_case(client, make_user):
    duty = make_user("duty_officer", email="duty@example.com", password="pw")
    sho = make_user("sho", email="sho@example.com", password="pw", org=duty.organization)
    io = make_user("io", email="io@example.com", password="pw", org=duty.organization)

    duty_token = login(client, "duty@example.com", "pw").json()["access_token"]
    case = _register_fir(client, duty_token)

    sho_token = login(client, "sho@example.com", "pw").json()["access_token"]
    assign_resp = client.post(
        f"/cases/{case['id']}/assign-io",
        json={"io_user_id": str(io.id)},
        headers=auth_headers(sho_token),
    )
    assert assign_resp.status_code == 201, assign_resp.text

    io_token = login(client, "io@example.com", "pw").json()["access_token"]
    get_resp = client.get(f"/cases/{case['id']}", headers=auth_headers(io_token))

    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == case["id"]


def test_unassigned_io_cannot_read_other_ios_case(client, make_user):
    """THE critical regression test. An IO with zero connection to a case
    must get 403, not the case file, no matter how the request is shaped."""
    duty = make_user("duty_officer", email="duty@example.com", password="pw")
    sho = make_user("sho", email="sho@example.com", password="pw", org=duty.organization)
    assigned_io = make_user("io", email="io1@example.com", password="pw", org=duty.organization)
    other_io = make_user("io", email="io2@example.com", password="pw", org=duty.organization)

    duty_token = login(client, "duty@example.com", "pw").json()["access_token"]
    case = _register_fir(client, duty_token, crime_type="SexualAssault")

    sho_token = login(client, "sho@example.com", "pw").json()["access_token"]
    client.post(
        f"/cases/{case['id']}/assign-io",
        json={"io_user_id": str(assigned_io.id)},
        headers=auth_headers(sho_token),
    )

    other_io_token = login(client, "io2@example.com", "pw").json()["access_token"]
    resp = client.get(f"/cases/{case['id']}", headers=auth_headers(other_io_token))

    assert resp.status_code == 403


def test_io_list_cases_only_shows_assigned_cases(client, make_user):
    duty = make_user("duty_officer", email="duty@example.com", password="pw")
    sho = make_user("sho", email="sho@example.com", password="pw", org=duty.organization)
    io = make_user("io", email="io@example.com", password="pw", org=duty.organization)

    duty_token = login(client, "duty@example.com", "pw").json()["access_token"]
    assigned_case = _register_fir(client, duty_token, crime_type="Theft")
    unassigned_case = _register_fir(client, duty_token, crime_type="Robbery")

    sho_token = login(client, "sho@example.com", "pw").json()["access_token"]
    client.post(
        f"/cases/{assigned_case['id']}/assign-io",
        json={"io_user_id": str(io.id)},
        headers=auth_headers(sho_token),
    )

    io_token = login(client, "io@example.com", "pw").json()["access_token"]
    resp = client.get("/cases", headers=auth_headers(io_token))

    assert resp.status_code == 200
    ids = {c["id"] for c in resp.json()}
    assert assigned_case["id"] in ids
    assert unassigned_case["id"] not in ids


def test_config_admin_sees_every_case_regardless_of_assignment(client, make_user):
    duty = make_user("duty_officer", email="duty@example.com", password="pw")
    make_user("config_admin", email="admin@example.com", password="pw", org=duty.organization)

    duty_token = login(client, "duty@example.com", "pw").json()["access_token"]
    case = _register_fir(client, duty_token)

    admin_token = login(client, "admin@example.com", "pw").json()["access_token"]
    resp = client.get(f"/cases/{case['id']}", headers=auth_headers(admin_token))

    assert resp.status_code == 200


def test_police_specialist_cannot_read_unassigned_case(client, make_user):
    """Police specialist roles (women_cell, cyber_cell, traffic_police, etc.)
    cannot view a case without an active CaseAssignment record (closes RBAC security hole)."""
    duty = make_user("duty_officer", email="duty@example.com", password="pw")
    make_user("sho", email="sho@example.com", password="pw", org=duty.organization)
    specialist = make_user("women_cell", email="wc@example.com", password="pw", org=duty.organization)

    duty_token = login(client, "duty@example.com", "pw").json()["access_token"]
    case = _register_fir(client, duty_token)

    specialist_token = login(client, "wc@example.com", "pw").json()["access_token"]
    resp = client.get(f"/cases/{case['id']}", headers=auth_headers(specialist_token))

    assert resp.status_code == 403
    assert resp.json()["detail"] == "Not assigned to this case"


def test_police_specialist_can_read_assigned_case(client, make_user):
    """Police specialist assigned to a case via CaseAssignment can read case details."""
    duty = make_user("duty_officer", email="duty@example.com", password="pw")
    sho = make_user("sho", email="sho@example.com", password="pw", org=duty.organization)
    cyber_officer = make_user("cyber_cell", email="cyber@example.com", password="pw", org=duty.organization)

    duty_token = login(client, "duty@example.com", "pw").json()["access_token"]
    case = _register_fir(client, duty_token)

    sho_token = login(client, "sho@example.com", "pw").json()["access_token"]
    client.post(
        f"/cases/{case['id']}/assign-io",
        json={"io_user_id": str(cyber_officer.id)},
        headers=auth_headers(sho_token),
    )

    cyber_token = login(client, "cyber@example.com", "pw").json()["access_token"]
    resp = client.get(f"/cases/{case['id']}", headers=auth_headers(cyber_token))

    assert resp.status_code == 200
    assert resp.json()["id"] == case["id"]


def test_assigned_io_can_add_and_list_case_diary_entries(client, make_user):
    duty = make_user("duty_officer", email="duty_cd@example.com", password="pw")
    sho = make_user("sho", email="sho_cd@example.com", password="pw", org=duty.organization)
    io = make_user("io", email="io_cd@example.com", password="pw", org=duty.organization)

    duty_token = login(client, "duty_cd@example.com", "pw").json()["access_token"]
    case = _register_fir(client, duty_token)

    sho_token = login(client, "sho_cd@example.com", "pw").json()["access_token"]
    client.post(
        f"/cases/{case['id']}/assign-io",
        json={"io_user_id": str(io.id)},
        headers=auth_headers(sho_token),
    )

    io_token = login(client, "io_cd@example.com", "pw").json()["access_token"]

    # IO adds diary entry
    cd_resp = client.post(
        f"/cases/{case['id']}/case-diary",
        json={"text": "Visited scene of crime at 10:30 AM. Recovered suspicious tool."},
        headers=auth_headers(io_token),
    )
    assert cd_resp.status_code == 201
    entry = cd_resp.json()
    assert entry["case_id"] == case["id"]
    # "processing", not "ready" — it hasn't been through the AI Parser yet.
    # See test_case_diary_entry_is_dispatched_to_ai_parser below: this used
    # to be a real gap, entries were marked "ready" immediately and never
    # actually redacted.
    assert entry["status"] == "processing"
    assert "Visited scene" in entry["text"]

    # IO (assigned) sees it even while still processing
    list_resp = client.get(f"/cases/{case['id']}/case-diary", headers=auth_headers(io_token))
    assert list_resp.status_code == 200
    assert len(list_resp.json()) == 1


def test_case_diary_entry_is_dispatched_to_ai_parser(client, make_user, fake_queue):
    """The actual fix: adding a diary entry must enqueue AI Parser tagging,
    not just create the row and call it done."""
    duty = make_user("duty_officer", email="duty_cd2@example.com", password="pw")
    sho = make_user("sho", email="sho_cd2@example.com", password="pw", org=duty.organization)
    io = make_user("io", email="io_cd2@example.com", password="pw", org=duty.organization)

    duty_token = login(client, "duty_cd2@example.com", "pw").json()["access_token"]
    case = _register_fir(client, duty_token)

    sho_token = login(client, "sho_cd2@example.com", "pw").json()["access_token"]
    client.post(
        f"/cases/{case['id']}/assign-io",
        json={"io_user_id": str(io.id)},
        headers=auth_headers(sho_token),
    )

    io_token = login(client, "io_cd2@example.com", "pw").json()["access_token"]
    cd_resp = client.post(
        f"/cases/{case['id']}/case-diary",
        json={"text": "Informant Ramesh Kumar, phone 9876543210, tipped off location."},
        headers=auth_headers(io_token),
    )
    assert cd_resp.status_code == 201
    entry_id = cd_resp.json()["id"]

    dispatched = [j for j in fake_queue.enqueued if j["task_name"] == "ai_parser_worker.tag_case_diary_entry"]
    assert len(dispatched) == 1
    assert dispatched[0]["kwargs"]["case_diary_entry_id"] == entry_id


def test_unassigned_role_only_sees_ready_diary_entries_not_processing(client, make_user):
    """A non-IO/SHO role with case access (e.g. court) must never see a
    diary entry that hasn't been through redaction yet."""
    duty = make_user("duty_officer", email="duty_cd3@example.com", password="pw")
    sho = make_user("sho", email="sho_cd3@example.com", password="pw", org=duty.organization)
    io = make_user("io", email="io_cd3@example.com", password="pw", org=duty.organization)
    court = make_user("court", email="court_cd3@example.com", password="pw", org=duty.organization)

    duty_token = login(client, "duty_cd3@example.com", "pw").json()["access_token"]
    case = _register_fir(client, duty_token)

    sho_token = login(client, "sho_cd3@example.com", "pw").json()["access_token"]
    client.post(
        f"/cases/{case['id']}/assign-io",
        json={"io_user_id": str(io.id)},
        headers=auth_headers(sho_token),
    )

    io_token = login(client, "io_cd3@example.com", "pw").json()["access_token"]
    client.post(
        f"/cases/{case['id']}/case-diary",
        json={"text": "Still processing, not yet redacted."},
        headers=auth_headers(io_token),
    )

    court_token = login(client, "court_cd3@example.com", "pw").json()["access_token"]
    court_view = client.get(f"/cases/{case['id']}/case-diary", headers=auth_headers(court_token))
    assert court_view.status_code == 200
    assert court_view.json() == []  # the "processing" entry is correctly hidden


def test_unassigned_io_cannot_add_or_list_case_diary(client, make_user):
    duty = make_user("duty_officer", email="duty_cd2@example.com", password="pw")
    io_assigned = make_user("io", email="io_assigned@example.com", password="pw", org=duty.organization)
    io_unassigned = make_user("io", email="io_unassigned@example.com", password="pw", org=duty.organization)

    duty_token = login(client, "duty_cd2@example.com", "pw").json()["access_token"]
    case = _register_fir(client, duty_token)

    sho = make_user("sho", email="sho_cd2@example.com", password="pw", org=duty.organization)
    sho_token = login(client, "sho_cd2@example.com", "pw").json()["access_token"]
    client.post(
        f"/cases/{case['id']}/assign-io",
        json={"io_user_id": str(io_assigned.id)},
        headers=auth_headers(sho_token),
    )

    unassigned_token = login(client, "io_unassigned@example.com", "pw").json()["access_token"]

    # Cannot add entry
    add_fail = client.post(
        f"/cases/{case['id']}/case-diary",
        json={"text": "Unauthorized note"},
        headers=auth_headers(unassigned_token),
    )
    assert add_fail.status_code == 403

    # Cannot list entries
    list_fail = client.get(f"/cases/{case['id']}/case-diary", headers=auth_headers(unassigned_token))
    assert list_fail.status_code == 403


def test_empty_case_diary_entry_rejected(client, make_user):
    duty = make_user("duty_officer", email="duty_cd3@example.com", password="pw")
    io = make_user("io", email="io_cd3@example.com", password="pw", org=duty.organization)

    duty_token = login(client, "duty_cd3@example.com", "pw").json()["access_token"]
    case = _register_fir(client, duty_token)

    sho = make_user("sho", email="sho_cd3@example.com", password="pw", org=duty.organization)
    sho_token = login(client, "sho_cd3@example.com", "pw").json()["access_token"]
    client.post(
        f"/cases/{case['id']}/assign-io",
        json={"io_user_id": str(io.id)},
        headers=auth_headers(sho_token),
    )

    io_token = login(client, "io_cd3@example.com", "pw").json()["access_token"]

    bad_resp = client.post(
        f"/cases/{case['id']}/case-diary",
        json={"text": "   "},
        headers=auth_headers(io_token),
    )
    assert bad_resp.status_code == 400


# ==================== IO Mid-Case Reassignment Tests (Flow 1) ====================

def _setup_reassignment_fixture(client, make_user):
    duty = make_user("duty_officer", email=f"duty_{uuid4().hex[:6]}@example.com", password="pw")
    sho = make_user("sho", email=f"sho_{uuid4().hex[:6]}@example.com", password="pw", org=duty.organization)
    io1 = make_user("io", email=f"io1_{uuid4().hex[:6]}@example.com", password="pw", org=duty.organization)
    io2 = make_user("io", email=f"io2_{uuid4().hex[:6]}@example.com", password="pw", org=duty.organization)

    duty_token = login(client, duty.email, "pw").json()["access_token"]
    case = _register_fir(client, duty_token)

    sho_token = login(client, sho.email, "pw").json()["access_token"]
    client.post(
        f"/cases/{case['id']}/assign-io",
        json={"io_user_id": str(io1.id)},
        headers=auth_headers(sho_token),
    )

    io1_token = login(client, io1.email, "pw").json()["access_token"]
    io2_token = login(client, io2.email, "pw").json()["access_token"]

    return case, sho_token, io1, io1_token, io2, io2_token


def test_sho_can_reassign_io_midcase(client, make_user):
    """Happy path: SHO reassigns case from IO1 to IO2."""
    case, sho_token, io1, io1_token, io2, io2_token = _setup_reassignment_fixture(client, make_user)

    resp = client.post(
        f"/cases/{case['id']}/reassign-io",
        json={"new_io_user_id": str(io2.id), "reason": "Officer relocated"},
        headers=auth_headers(sho_token),
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["case_id"] == case["id"]
    assert data["previous_io_user_id"] == str(io1.id)
    assert data["new_io_user_id"] == str(io2.id)
    assert "reassigned_at" in data


def test_reassigned_old_io_loses_case_access_and_new_io_gains_it(client, make_user):
    """Access Control Invariant: Old IO gets 403 on case endpoints; New IO gets 200."""
    case, sho_token, io1, io1_token, io2, io2_token = _setup_reassignment_fixture(client, make_user)

    # Before reassignment: IO1 can read case; IO2 is forbidden
    assert client.get(f"/cases/{case['id']}", headers=auth_headers(io1_token)).status_code == 200
    assert client.get(f"/cases/{case['id']}", headers=auth_headers(io2_token)).status_code == 403

    # Reassign to IO2
    client.post(
        f"/cases/{case['id']}/reassign-io",
        json={"new_io_user_id": str(io2.id)},
        headers=auth_headers(sho_token),
    )

    # After reassignment: IO1 loses access immediately (403); IO2 gains access (200)
    assert client.get(f"/cases/{case['id']}", headers=auth_headers(io1_token)).status_code == 403
    assert client.get(f"/cases/{case['id']}", headers=auth_headers(io2_token)).status_code == 200


def test_reassign_io_writes_audit_log_with_both_ids_and_reason(client, make_user, db_session):
    """Tamper-evident audit log records previous_io_id, new_io_id, and sanitized reason."""
    case, sho_token, io1, _, io2, _ = _setup_reassignment_fixture(client, make_user)

    resp = client.post(
        f"/cases/{case['id']}/reassign-io",
        json={"new_io_user_id": str(io2.id), "reason": "Conflict of interest identified"},
        headers=auth_headers(sho_token),
    )
    assert resp.status_code == 200

    audit_entry = (
        db_session.query(models.AuditLog)
        .filter(models.AuditLog.case_id == UUID(case["id"]), models.AuditLog.action == "io_reassigned")
        .first()
    )
    assert audit_entry is not None
    assert audit_entry.target_type == "case_assignment"
    assert audit_entry.action_metadata["previous_io_id"] == str(io1.id)
    assert audit_entry.action_metadata["new_io_id"] == str(io2.id)
    assert audit_entry.action_metadata["reason"] == "Conflict of interest identified"


def test_reassign_io_preserves_case_chain_integrity(client, make_user, db_session):
    """Audit hash chain remains cryptographically intact after reassignment."""
    case, sho_token, _, _, io2, _ = _setup_reassignment_fixture(client, make_user)

    client.post(
        f"/cases/{case['id']}/reassign-io",
        json={"new_io_user_id": str(io2.id)},
        headers=auth_headers(sho_token),
    )

    integrity = verify_case_chain_integrity(db_session, case["id"])
    assert integrity["chain_intact"] is True
    assert integrity["total_entries"] >= 1
    assert integrity["latest_hash"] is not None


def test_reassign_to_same_io_rejected_409(client, make_user):
    """Self-reassignment / assigning the currently assigned IO is rejected with 409."""
    case, sho_token, io1, _, _, _ = _setup_reassignment_fixture(client, make_user)

    resp = client.post(
        f"/cases/{case['id']}/reassign-io",
        json={"new_io_user_id": str(io1.id)},
        headers=auth_headers(sho_token),
    )
    assert resp.status_code == 409
    assert "already assigned" in resp.json()["detail"].lower()


def test_reassign_when_no_active_assignment_rejected_409(client, make_user):
    """Reassigning an unassigned case is rejected with 409 (must use assign-io first)."""
    duty = make_user("duty_officer", email=f"duty_{uuid4().hex[:6]}@example.com", password="pw")
    sho = make_user("sho", email=f"sho_{uuid4().hex[:6]}@example.com", password="pw", org=duty.organization)
    io = make_user("io", email=f"io_{uuid4().hex[:6]}@example.com", password="pw", org=duty.organization)

    duty_token = login(client, duty.email, "pw").json()["access_token"]
    case = _register_fir(client, duty_token)

    sho_token = login(client, sho.email, "pw").json()["access_token"]
    resp = client.post(
        f"/cases/{case['id']}/reassign-io",
        json={"new_io_user_id": str(io.id)},
        headers=auth_headers(sho_token),
    )
    assert resp.status_code == 409
    assert "use assign-io instead" in resp.json()["detail"].lower()


def test_reassign_nonexistent_case_returns_404(client, make_user):
    """Non-existent case UUID returns 404."""
    sho = make_user("sho", email=f"sho_{uuid4().hex[:6]}@example.com", password="pw")
    io = make_user("io", email=f"io_{uuid4().hex[:6]}@example.com", password="pw", org=sho.organization)
    sho_token = login(client, sho.email, "pw").json()["access_token"]

    fake_case_id = str(uuid4())
    resp = client.post(
        f"/cases/{fake_case_id}/reassign-io",
        json={"new_io_user_id": str(io.id)},
        headers=auth_headers(sho_token),
    )
    assert resp.status_code == 404
    assert "Case not found" in resp.json()["detail"]


def test_reassign_malformed_case_uuid_returns_404(client, make_user):
    """Malformed non-UUID string returns clean 404 (not unhandled 500)."""
    sho = make_user("sho", email=f"sho_{uuid4().hex[:6]}@example.com", password="pw")
    io = make_user("io", email=f"io_{uuid4().hex[:6]}@example.com", password="pw", org=sho.organization)
    sho_token = login(client, sho.email, "pw").json()["access_token"]

    resp = client.post(
        "/cases/not-a-valid-uuid/reassign-io",
        json={"new_io_user_id": str(io.id)},
        headers=auth_headers(sho_token),
    )
    assert resp.status_code == 404
    assert "Case not found" in resp.json()["detail"]


def test_reassign_non_io_user_role_rejected_400(client, make_user):
    """Attempting to assign a non-IO role (e.g. prosecutor or defense) returns 400."""
    case, sho_token, _, _, _, _ = _setup_reassignment_fixture(client, make_user)

    prosecutor = make_user("prosecutor", email=f"pros_{uuid4().hex[:6]}@example.com", password="pw")
    resp = client.post(
        f"/cases/{case['id']}/reassign-io",
        json={"new_io_user_id": str(prosecutor.id)},
        headers=auth_headers(sho_token),
    )
    assert resp.status_code == 400
    assert "must have 'io' role" in resp.json()["detail"].lower()


def test_reassign_on_concluded_case_rejected_409(client, make_user, db_session):
    """State Invariant: IO cannot be reassigned on a concluded/judgment case."""
    case, sho_token, _, _, io2, _ = _setup_reassignment_fixture(client, make_user)

    case_row = db_session.get(models.Case, UUID(case["id"]))
    case_row.investigation_status = "Judgment"
    db_session.commit()

    resp = client.post(
        f"/cases/{case['id']}/reassign-io",
        json={"new_io_user_id": str(io2.id)},
        headers=auth_headers(sho_token),
    )
    assert resp.status_code == 409
    assert "concluded case" in resp.json()["detail"].lower()


def test_config_admin_can_also_reassign_io(client, make_user):
    """Config Admin can reassign IO as authorized by require_role('sho', 'config_admin')."""
    case, _, io1, _, io2, _ = _setup_reassignment_fixture(client, make_user)
    admin = make_user("config_admin", email=f"admin_{uuid4().hex[:6]}@example.com", password="pw")
    admin_token = login(client, admin.email, "pw").json()["access_token"]

    resp = client.post(
        f"/cases/{case['id']}/reassign-io",
        json={"new_io_user_id": str(io2.id), "reason": "Administrative reassignment"},
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 200
    assert resp.json()["new_io_user_id"] == str(io2.id)


def test_unauthorized_roles_cannot_reassign_io(client, make_user):
    """Negative space: unauthenticated and non-SHO/admin roles receive 401/403."""
    case, _, _, _, io2, _ = _setup_reassignment_fixture(client, make_user)

    # 1. Unauthenticated
    assert client.post(f"/cases/{case['id']}/reassign-io", json={"new_io_user_id": str(io2.id)}).status_code == 401

    # 2. Unauthorized roles
    unauthorized_roles = ["io", "duty_officer", "prosecutor", "defense", "court", "records_ncrb_analyst"]
    for role in unauthorized_roles:
        u = make_user(role, email=f"{role}_{uuid4().hex[:6]}@example.com", password="pw")
        tok = login(client, u.email, "pw").json()["access_token"]
        r = client.post(
            f"/cases/{case['id']}/reassign-io",
            json={"new_io_user_id": str(io2.id)},
            headers=auth_headers(tok),
        )
        assert r.status_code == 403, f"Role {role} should have been rejected with 403, got {r.status_code}"
