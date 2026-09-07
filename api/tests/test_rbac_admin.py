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

