import pytest
from app import models, security
from app.seed_data import seed_all, DEFAULT_TEST_PASSWORD


@pytest.fixture(autouse=True)
def _seed_db(db_session):
    seed_all(db_session)


def test_auth_me_authoritative_profile(client, db_session):
    # Login as Inspector Rao (IO)
    res = client.post("/auth/login", json={"email": "officer.rao@police.gov.in", "password": DEFAULT_TEST_PASSWORD})
    assert res.status_code == 200
    token = res.json()["access_token"]

    # Request authoritative profile
    me_res = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me_res.status_code == 200
    data = me_res.json()
    assert data["email"] == "officer.rao@police.gov.in"
    assert data["service_id"] == "DL-POL-4921"
    assert data["role"] == "io"
    assert data["designation"] == "Inspector of Police (Cyber Cell)"
    assert "cases:read" in data["permissions"]
    assert "documents:upload" in data["permissions"]


def test_login_by_government_service_id(client):
    # Authenticate using Government Service ID instead of email
    res = client.post("/auth/login", json={"email": "MHA-ADM-001", "password": DEFAULT_TEST_PASSWORD})
    assert res.status_code == 200
    data = res.json()
    assert "access_token" in data

    claims = security.decode_token(data["access_token"])
    assert claims["role"] == "config_admin"


def test_admin_list_roles_and_permissions(client):
    # Authenticate as Config Admin
    res = client.post("/auth/login", json={"email": "admin.sharma@legadoc.gov.in", "password": DEFAULT_TEST_PASSWORD})
    token = res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # List permissions
    perm_res = client.get("/admin/permissions", headers=headers)
    assert perm_res.status_code == 200
    perms = perm_res.json()
    assert len(perms) > 10
    perm_codes = [p["code"] for p in perms]
    assert "admin:roles_manage" in perm_codes

    # List roles
    roles_res = client.get("/admin/roles", headers=headers)
    assert roles_res.status_code == 200
    roles = roles_res.json()
    role_codes = [r["code"] for r in roles]
    assert "io" in role_codes
    assert "court" in role_codes
    assert "config_admin" in role_codes


def test_admin_create_custom_role(client):
    res = client.post("/auth/login", json={"email": "admin.sharma@legadoc.gov.in", "password": DEFAULT_TEST_PASSWORD})
    token = res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    create_res = client.post(
        "/admin/roles",
        headers=headers,
        json={
            "code": "special_investigator",
            "name": "Special Task Force Investigator",
            "description": "Specialized officer for financial and high-profile narcotics cases",
            "permission_codes": ["cases:read", "cases:diary_write", "documents:read"]
        }
    )
    assert create_res.status_code == 201
    created = create_res.json()
    assert created["code"] == "special_investigator"
    assert created["is_system"] is False
    assert "cases:read" in created["permission_codes"]


def test_non_admin_cannot_access_role_management(client):
    # Login as Defense Counsel
    res = client.post("/auth/login", json={"email": "defense.advocate@bar.in", "password": DEFAULT_TEST_PASSWORD})
    token = res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Attempt to list roles -> 403 Forbidden
    list_res = client.get("/admin/roles", headers=headers)
    assert list_res.status_code == 403

    # Attempt to create a role -> 403 Forbidden
    create_res = client.post(
        "/admin/roles",
        headers=headers,
        json={"code": "hacked_admin", "name": "Fake Admin", "permission_codes": ["admin:roles_manage"]}
    )
    assert create_res.status_code == 403


def test_system_role_deletion_blocked(client, db_session):
    res = client.post("/auth/login", json={"email": "admin.sharma@legadoc.gov.in", "password": DEFAULT_TEST_PASSWORD})
    token = res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    court_role = db_session.query(models.Role).filter(models.Role.code == "court").first()
    del_res = client.delete(f"/admin/roles/{court_role.id}", headers=headers)
    assert del_res.status_code == 400
    assert "System protected roles cannot be deleted" in del_res.json()["detail"]


def test_admin_assign_user_role(client, db_session):
    res = client.post("/auth/login", json={"email": "admin.sharma@legadoc.gov.in", "password": DEFAULT_TEST_PASSWORD})
    token = res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Assign duty officer to 'sho' role
    duty_officer = db_session.query(models.User).filter(models.User.email == "duty.verma@police.gov.in").first()
    assign_res = client.post(
        f"/admin/users/{duty_officer.id}/assign-role",
        headers=headers,
        json={"role_code": "sho"}
    )
    assert assign_res.status_code == 200
    assert assign_res.json()["assigned_role"] == "sho"

    # Verify updated
    db_session.refresh(duty_officer)
    assert duty_officer.role == "sho"


def test_unimplemented_admin_endpoints_explicit_501(client):
    res = client.post("/auth/login", json={"email": "admin.sharma@legadoc.gov.in", "password": DEFAULT_TEST_PASSWORD})
    token = res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # stage-requirements must return explicit 501
    stage_res = client.get("/admin/stage-requirements", headers=headers)
    assert stage_res.status_code == 501
    assert "not implemented" in stage_res.json()["detail"].lower()


def test_role_assignment_and_removal_audit_logging(client, db_session):
    from app.audit import verify_chain_intact

    # Login as Config Admin (Sharma)
    res = client.post("/auth/login", json={"email": "admin.sharma@legadoc.gov.in", "password": DEFAULT_TEST_PASSWORD})
    token = res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    admin_user = db_session.query(models.User).filter(models.User.email == "admin.sharma@legadoc.gov.in").first()
    target_user = db_session.query(models.User).filter(models.User.email == "duty.verma@police.gov.in").first()
    initial_role = target_user.role

    # 1. Assign role
    assign_res = client.post(
        f"/admin/users/{target_user.id}/assign-role",
        headers=headers,
        json={"role_code": "sho"}
    )
    assert assign_res.status_code == 200

    # Query audit log for role_assigned
    assign_log = (
        db_session.query(models.AuditLog)
        .filter(models.AuditLog.action == "role_assigned", models.AuditLog.target_id == target_user.id)
        .order_by(models.AuditLog.created_at.desc())
        .first()
    )
    assert assign_log is not None
    assert assign_log.actor_user_id == admin_user.id
    assert assign_log.target_type == "user"
    assert assign_log.action_metadata["previous_role"] == initial_role
    assert assign_log.action_metadata["new_role"] == "sho"
    assert assign_log.action_metadata["target_user_email"] == target_user.email
    assert assign_log.row_hash is not None

    # 2. Remove / revoke role
    revoke_res = client.post(f"/admin/users/{target_user.id}/remove-role", headers=headers)
    assert revoke_res.status_code == 200
    assert revoke_res.json()["current_role"] == "unassigned"

    db_session.refresh(target_user)
    assert target_user.role == "unassigned"

    # Query audit log for role_removed
    remove_log = (
        db_session.query(models.AuditLog)
        .filter(models.AuditLog.action == "role_removed", models.AuditLog.target_id == target_user.id)
        .order_by(models.AuditLog.created_at.desc())
        .first()
    )
    assert remove_log is not None
    assert remove_log.actor_user_id == admin_user.id
    assert remove_log.action_metadata["previous_role"] == "sho"
    assert remove_log.action_metadata["new_role"] == "unassigned"

    # Verify cryptographic hash chain remains intact
    assert verify_chain_intact(db_session) is True


def test_role_lifecycle_audit_logging(client, db_session):
    from app.audit import verify_chain_intact

    res = client.post("/auth/login", json={"email": "admin.sharma@legadoc.gov.in", "password": DEFAULT_TEST_PASSWORD})
    token = res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Create custom role
    create_res = client.post(
        "/admin/roles",
        headers=headers,
        json={
            "code": "audit_test_role",
            "name": "Audit Test Role",
            "description": "Role for verifying audit event creation",
            "permission_codes": ["cases:read"]
        }
    )
    assert create_res.status_code == 201
    role_id = create_res.json()["id"]

    # Verify role_created audit entry
    create_log = (
        db_session.query(models.AuditLog)
        .filter(models.AuditLog.action == "role_created", models.AuditLog.target_type == "role")
        .order_by(models.AuditLog.created_at.desc())
        .first()
    )
    assert create_log is not None
    assert create_log.action_metadata["role_code"] == "audit_test_role"
    assert "cases:read" in create_log.action_metadata["permissions"]

    # 2. Update role
    update_res = client.put(
        f"/admin/roles/{role_id}",
        headers=headers,
        json={
            "name": "Updated Audit Test Role",
            "permission_codes": ["cases:read", "documents:read"]
        }
    )
    assert update_res.status_code == 200

    update_log = (
        db_session.query(models.AuditLog)
        .filter(models.AuditLog.action == "role_updated", models.AuditLog.target_type == "role")
        .order_by(models.AuditLog.created_at.desc())
        .first()
    )
    assert update_log is not None
    assert set(update_log.action_metadata["new_permissions"]) == {"cases:read", "documents:read"}


    # 3. Delete role
    del_res = client.delete(f"/admin/roles/{role_id}", headers=headers)
    assert del_res.status_code == 200

    del_log = (
        db_session.query(models.AuditLog)
        .filter(models.AuditLog.action == "role_deleted", models.AuditLog.target_type == "role")
        .order_by(models.AuditLog.created_at.desc())
        .first()
    )
    assert del_log is not None
    assert del_log.action_metadata["role_code"] == "audit_test_role"

    assert verify_chain_intact(db_session) is True


def test_admin_audit_logs_query_and_access_control(client):
    # 1. Non-admin cannot access audit logs
    user_res = client.post("/auth/login", json={"email": "duty.verma@police.gov.in", "password": DEFAULT_TEST_PASSWORD})
    user_token = user_res.json()["access_token"]
    forbidden_res = client.get("/admin/audit-logs", headers={"Authorization": f"Bearer {user_token}"})
    assert forbidden_res.status_code == 403

    # 2. Admin can access audit logs
    admin_res = client.post("/auth/login", json={"email": "admin.sharma@legadoc.gov.in", "password": DEFAULT_TEST_PASSWORD})
    admin_token = admin_res.json()["access_token"]
    audit_res = client.get("/admin/audit-logs?limit=20", headers={"Authorization": f"Bearer {admin_token}"})
    assert audit_res.status_code == 200
    logs = audit_res.json()
    assert isinstance(logs, list)
    if logs:
        first = logs[0]
        assert "row_hash" in first
        assert "action" in first


def test_organization_management_and_audit(client, db_session):
    res = client.post("/auth/login", json={"email": "admin.sharma@legadoc.gov.in", "password": DEFAULT_TEST_PASSWORD})
    token = res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 1. List organizations (real DB data)
    list_res = client.get("/admin/orgs", headers=headers)
    assert list_res.status_code == 200
    orgs = list_res.json()
    assert len(orgs) > 0
    org_names = [o["name"] for o in orgs]
    assert "Ministry of Home Affairs / NIC" in org_names

    # 2. Onboard new organization
    onboard_res = client.post(
        "/admin/orgs",
        headers=headers,
        json={"name": "State Cyber Cell Rajasthan", "org_type": "police"}
    )
    assert onboard_res.status_code == 201
    created_org = onboard_res.json()
    assert created_org["name"] == "State Cyber Cell Rajasthan"

    # Verify audit log for org onboarding
    org_log = (
        db_session.query(models.AuditLog)
        .filter(models.AuditLog.action == "organization_onboarded")
        .order_by(models.AuditLog.created_at.desc())
        .first()
    )
    assert org_log is not None
    assert org_log.action_metadata["org_name"] == "State Cyber Cell Rajasthan"


# ---------- Document Schema & Recognizer Endpoint Tests (Issue #42) ----------

def test_admin_create_document_schema(client):
    res = client.post("/auth/login", json={"email": "admin.sharma@legadoc.gov.in", "password": DEFAULT_TEST_PASSWORD})
    token = res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    payload = {
        "doc_type": "FIR",
        "tier": 1,
        "sensitivity_fields": [
            {"field_name": "victim_name", "sensitive": True},
            {"field_name": "complaint_text", "sensitive": False},
        ],
    }
    create_res = client.post("/admin/document-schemas", headers=headers, json=payload)
    assert create_res.status_code == 201
    data = create_res.json()
    assert data["doc_type"] == "FIR"
    assert data["tier"] == 1
    assert len(data["sensitivity_fields"]) == 2
    assert data["sensitivity_fields"][0]["field_name"] == "victim_name"
    assert data["sensitivity_fields"][0]["sensitive"] is True
    assert data["recognizer_mappings"] == []


def test_admin_create_document_schema_duplicate_conflict(client):
    res = client.post("/auth/login", json={"email": "admin.sharma@legadoc.gov.in", "password": DEFAULT_TEST_PASSWORD})
    token = res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    payload = {
        "doc_type": "WITNESS_STATEMENT",
        "tier": 2,
        "sensitivity_fields": [
            {"field_name": "witness_name", "sensitive": True},
        ],
    }
    res1 = client.post("/admin/document-schemas", headers=headers, json=payload)
    assert res1.status_code == 201

    res2 = client.post("/admin/document-schemas", headers=headers, json=payload)
    assert res2.status_code == 409
    assert "already exists" in res2.json()["detail"].lower()


def test_admin_create_tier3_schema_rejects_fields(client):
    res = client.post("/auth/login", json={"email": "admin.sharma@legadoc.gov.in", "password": DEFAULT_TEST_PASSWORD})
    token = res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Reject tier 3 with sensitivity fields
    payload_bad = {
        "doc_type": "GENERIC_MEMO",
        "tier": 3,
        "sensitivity_fields": [
            {"field_name": "memo_text", "sensitive": False},
        ],
    }
    res_bad = client.post("/admin/document-schemas", headers=headers, json=payload_bad)
    assert res_bad.status_code == 400
    assert "Tier 3 schemas must have null sensitivity_fields" in res_bad.json()["detail"]

    # Reject tier 1/2 with empty or null sensitivity fields
    res_bad_tier1 = client.post(
        "/admin/document-schemas",
        headers=headers,
        json={"doc_type": "ARREST_MEMO", "tier": 1, "sensitivity_fields": None},
    )
    assert res_bad_tier1.status_code == 400
    assert "Tier 1 and Tier 2 schemas must specify non-empty sensitivity_fields" in res_bad_tier1.json()["detail"]

    # Accept tier 3 with null fields
    payload_good = {
        "doc_type": "GENERIC_MEMO",
        "tier": 3,
        "sensitivity_fields": None,
    }
    res_good = client.post("/admin/document-schemas", headers=headers, json=payload_good)
    assert res_good.status_code == 201
    assert res_good.json()["tier"] == 3
    assert res_good.json()["sensitivity_fields"] is None


def test_admin_update_document_schema(client, db_session):
    res = client.post("/auth/login", json={"email": "admin.sharma@legadoc.gov.in", "password": DEFAULT_TEST_PASSWORD})
    token = res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Create schema
    client.post(
        "/admin/document-schemas",
        headers=headers,
        json={
            "doc_type": "MLC",
            "tier": 2,
            "sensitivity_fields": [{"field_name": "doctor_name", "sensitive": False}],
        },
    )

    # Update schema
    update_res = client.put(
        "/admin/document-schemas/MLC",
        headers=headers,
        json={
            "tier": 1,
            "sensitivity_fields": [
                {"field_name": "doctor_name", "sensitive": False},
                {"field_name": "injuries", "sensitive": True},
            ],
        },
    )
    assert update_res.status_code == 200
    updated = update_res.json()
    assert updated["tier"] == 1
    assert len(updated["sensitivity_fields"]) == 2

    # Check audit log diff
    audit = (
        db_session.query(models.AuditLog)
        .filter(models.AuditLog.action == "document_schema_updated")
        .order_by(models.AuditLog.created_at.desc())
        .first()
    )
    assert audit is not None
    assert audit.action_metadata["doc_type"] == "MLC"
    assert audit.action_metadata["previous_tier"] == 2
    assert audit.action_metadata["new_tier"] == 1
    assert len(audit.action_metadata["previous_sensitivity_fields"]) == 1
    assert len(audit.action_metadata["new_sensitivity_fields"]) == 2

    # Verify updating to tier 3 without clearing sensitivity_fields fails
    res_invalid_tier3 = client.put(
        "/admin/document-schemas/MLC",
        headers=headers,
        json={"tier": 3},
    )
    assert res_invalid_tier3.status_code == 400


def test_admin_set_recognizer_mappings(client):
    res = client.post("/auth/login", json={"email": "admin.sharma@legadoc.gov.in", "password": DEFAULT_TEST_PASSWORD})
    token = res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    client.post(
        "/admin/document-schemas",
        headers=headers,
        json={
            "doc_type": "CHARGE_SHEET",
            "tier": 1,
            "sensitivity_fields": [
                {"field_name": "accused_name", "sensitive": True},
                {"field_name": "police_station", "sensitive": False},
            ],
        },
    )

    rec_res = client.post(
        "/admin/document-schemas/CHARGE_SHEET/recognizers",
        headers=headers,
        json={
            "mappings": [
                {"entity_type": "PERSON", "field_name": "accused_name"},
                {"entity_type": "LOCATION", "field_name": "police_station"},
            ]
        },
    )
    assert rec_res.status_code == 200
    mappings = rec_res.json()
    assert len(mappings) == 2
    assert {m["entity_type"] for m in mappings} == {"PERSON", "LOCATION"}
    assert {m["field_name"] for m in mappings} == {"accused_name", "police_station"}


def test_admin_set_recognizer_mappings_unknown_field_rejected(client):
    res = client.post("/auth/login", json={"email": "admin.sharma@legadoc.gov.in", "password": DEFAULT_TEST_PASSWORD})
    token = res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    client.post(
        "/admin/document-schemas",
        headers=headers,
        json={
            "doc_type": "SEIZURE_MEMO",
            "tier": 2,
            "sensitivity_fields": [{"field_name": "item_description", "sensitive": False}],
        },
    )

    bad_res = client.post(
        "/admin/document-schemas/SEIZURE_MEMO/recognizers",
        headers=headers,
        json={"mappings": [{"entity_type": "PERSON", "field_name": "victim_name"}]},
    )
    assert bad_res.status_code == 400
    assert "victim_name" in bad_res.json()["detail"]


def test_admin_set_recognizer_mappings_no_schema_404(client):
    res = client.post("/auth/login", json={"email": "admin.sharma@legadoc.gov.in", "password": DEFAULT_TEST_PASSWORD})
    token = res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    res_404 = client.post(
        "/admin/document-schemas/NON_EXISTENT_DOC/recognizers",
        headers=headers,
        json={"mappings": [{"entity_type": "PERSON", "field_name": "victim_name"}]},
    )
    assert res_404.status_code == 404


def test_admin_set_recognizer_mappings_replaces_not_appends(client):
    res = client.post("/auth/login", json={"email": "admin.sharma@legadoc.gov.in", "password": DEFAULT_TEST_PASSWORD})
    token = res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    client.post(
        "/admin/document-schemas",
        headers=headers,
        json={
            "doc_type": "INQUEST_REPORT",
            "tier": 1,
            "sensitivity_fields": [
                {"field_name": "deceased_name", "sensitive": True},
                {"field_name": "cause_of_death", "sensitive": True},
            ],
        },
    )

    # First set
    res1 = client.post(
        "/admin/document-schemas/INQUEST_REPORT/recognizers",
        headers=headers,
        json={"mappings": [{"entity_type": "PERSON", "field_name": "deceased_name"}]},
    )
    assert res1.status_code == 200

    # Second set
    res2 = client.post(
        "/admin/document-schemas/INQUEST_REPORT/recognizers",
        headers=headers,
        json={"mappings": [{"entity_type": "MEDICAL_CONDITION", "field_name": "cause_of_death"}]},
    )
    assert res2.status_code == 200

    # Verify GET returns only second set, not union
    get_res = client.get("/admin/document-schemas", headers=headers)
    assert get_res.status_code == 200
    schemas_list = get_res.json()
    inquest_schema = next(s for s in schemas_list if s["doc_type"] == "INQUEST_REPORT")
    assert len(inquest_schema["recognizer_mappings"]) == 1
    assert inquest_schema["recognizer_mappings"][0]["entity_type"] == "MEDICAL_CONDITION"
    assert inquest_schema["recognizer_mappings"][0]["field_name"] == "cause_of_death"


def test_document_schema_changes_appear_in_audit_log(client):
    res = client.post("/auth/login", json={"email": "admin.sharma@legadoc.gov.in", "password": DEFAULT_TEST_PASSWORD})
    token = res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Create schema
    client.post(
        "/admin/document-schemas",
        headers=headers,
        json={
            "doc_type": "FORENSIC_REPORT",
            "tier": 1,
            "sensitivity_fields": [{"field_name": "expert_name", "sensitive": False}],
        },
    )

    # 2. Update schema
    client.put(
        "/admin/document-schemas/FORENSIC_REPORT",
        headers=headers,
        json={
            "tier": 2,
            "sensitivity_fields": [{"field_name": "expert_name", "sensitive": True}],
        },
    )

    # 3. Set recognizer mappings
    client.post(
        "/admin/document-schemas/FORENSIC_REPORT/recognizers",
        headers=headers,
        json={"mappings": [{"entity_type": "PERSON", "field_name": "expert_name"}]},
    )

    # Check audit logs via GET /admin/audit-logs
    audit_res = client.get("/admin/audit-logs?target_type=document_schema", headers=headers)
    assert audit_res.status_code == 200
    logs = audit_res.json()
    actions = [l["action"] for l in logs]
    assert "document_schema_created" in actions
    assert "document_schema_updated" in actions
    assert "recognizer_mapping_updated" in actions

    # Check update log metadata diff
    update_log = next(l for l in logs if l["action"] == "document_schema_updated")
    assert update_log["action_metadata"]["doc_type"] == "FORENSIC_REPORT"
    assert update_log["action_metadata"]["previous_tier"] == 1
    assert update_log["action_metadata"]["new_tier"] == 2

    # Check recognizer mapping log metadata diff
    rec_log = next(l for l in logs if l["action"] == "recognizer_mapping_updated")
    assert rec_log["action_metadata"]["doc_type"] == "FORENSIC_REPORT"
    assert rec_log["action_metadata"]["previous_mappings"] == []
    assert len(rec_log["action_metadata"]["new_mappings"]) == 1
    assert rec_log["action_metadata"]["new_mappings"][0]["entity_type"] == "PERSON"


