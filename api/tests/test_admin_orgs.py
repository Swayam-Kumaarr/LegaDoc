"""Tests for admin endpoints (document-schemas, recognizers, stage-requirements)
and org endpoints."""

from app import models
from tests.conftest import auth_headers, login


def test_list_document_schemas(client, make_user, db_session):
    make_user("config_admin", email="admin@example.com", password="pw")
    admin_token = login(client, "admin@example.com", "pw").json()["access_token"]

    schema = models.DocumentSchemaConfig(doc_type="FIR", tier=1, sensitivity_fields={"name": "PERSON"})
    db_session.add(schema)
    db_session.commit()

    resp = client.get("/admin/document-schemas", headers=auth_headers(admin_token))

    assert resp.status_code == 200
    assert len(resp.json()) == 1
    assert resp.json()[0]["doc_type"] == "FIR"
    assert resp.json()[0]["tier"] == 1


def test_non_admin_cannot_list_schemas(client, make_user, db_session):
    make_user("duty_officer", email="duty@example.com", password="pw")
    duty_token = login(client, "duty@example.com", "pw").json()["access_token"]

    resp = client.get("/admin/document-schemas", headers=auth_headers(duty_token))

    assert resp.status_code == 403


def test_set_recognizer_mapping(client, make_user, db_session):
    make_user("config_admin", email="admin@example.com", password="pw")
    admin_token = login(client, "admin@example.com", "pw").json()["access_token"]

    schema = models.DocumentSchemaConfig(doc_type="FIR", tier=1, sensitivity_fields={})
    db_session.add(schema)
    db_session.commit()

    resp = client.post(
        "/admin/document-schemas/FIR/recognizers",
        json=[{"entity_type": "PERSON", "field_name": "name"}],
        headers=auth_headers(admin_token),
    )

    assert resp.status_code == 200
    mappings = resp.json()
    assert len(mappings) == 1
    assert mappings[0]["entity_type"] == "PERSON"
    assert mappings[0]["field_name"] == "name"


def test_recognizer_mapping_replaces_existing(client, make_user, db_session):
    make_user("config_admin", email="admin@example.com", password="pw")
    admin_token = login(client, "admin@example.com", "pw").json()["access_token"]

    schema = models.DocumentSchemaConfig(doc_type="FIR", tier=1, sensitivity_fields={})
    db_session.add(schema)
    db_session.commit()

    db_session.add(models.RecognizerMapping(document_schema_id=schema.id, entity_type="OLD", field_name="old_field"))
    db_session.commit()

    resp = client.post(
        "/admin/document-schemas/FIR/recognizers",
        json=[{"entity_type": "NEW", "field_name": "new_field"}],
        headers=auth_headers(admin_token),
    )

    assert resp.status_code == 200
    mappings = db_session.query(models.RecognizerMapping).filter_by(document_schema_id=schema.id).all()
    assert len(mappings) == 1
    assert mappings[0].entity_type == "NEW"


def test_recognizer_mapping_creates_audit_log(client, make_user, db_session):
    make_user("config_admin", email="admin@example.com", password="pw")
    admin_token = login(client, "admin@example.com", "pw").json()["access_token"]

    schema = models.DocumentSchemaConfig(doc_type="FIR", tier=1, sensitivity_fields={})
    db_session.add(schema)
    db_session.commit()

    client.post(
        "/admin/document-schemas/FIR/recognizers",
        json=[{"entity_type": "PERSON", "field_name": "name"}],
        headers=auth_headers(admin_token),
    )

    entries = db_session.query(models.AuditLog).filter_by(action="recognizer_mapping_updated").all()
    assert len(entries) == 1
    assert entries[0].action_metadata["old_mappings"] == []
    assert entries[0].action_metadata["new_mappings"] == [{"entity_type": "PERSON", "field_name": "name"}]


def test_recognizer_mapping_nonexistent_schema_returns_404(client, make_user, db_session):
    make_user("config_admin", email="admin@example.com", password="pw")
    admin_token = login(client, "admin@example.com", "pw").json()["access_token"]

    resp = client.post(
        "/admin/document-schemas/NONEXISTENT/recognizers",
        json=[{"entity_type": "PERSON", "field_name": "name"}],
        headers=auth_headers(admin_token),
    )

    assert resp.status_code == 404


def test_list_stage_requirements(client, make_user, db_session):
    make_user("config_admin", email="admin@example.com", password="pw")
    admin_token = login(client, "admin@example.com", "pw").json()["access_token"]

    req = models.StageRequirement(
        crime_type="Theft", requirement_type="document", requirement_key="Witness Statement", mandatory=True
    )
    db_session.add(req)
    db_session.commit()

    resp = client.get("/admin/stage-requirements", headers=auth_headers(admin_token))

    assert resp.status_code == 200
    assert len(resp.json()) == 1
    assert resp.json()[0]["crime_type"] == "Theft"
    assert resp.json()[0]["mandatory"] is True


def test_list_org_users(client, make_user, db_session):
    org = make_user("duty_officer", email="duty@example.com", password="pw").organization
    make_user("io", email="io@example.com", password="pw", org=org)

    make_user("config_admin", email="admin@example.com", password="pw")
    admin_token = login(client, "admin@example.com", "pw").json()["access_token"]

    resp = client.get(f"/orgs/{org.id}/users", headers=auth_headers(admin_token))

    assert resp.status_code == 200
    assert len(resp.json()) == 2
    for user in resp.json():
        assert "hashed_password" not in user


def test_onboard_org(client, make_user, db_session):
    make_user("config_admin", email="admin@example.com", password="pw")
    admin_token = login(client, "admin@example.com", "pw").json()["access_token"]

    resp = client.post(
        "/orgs",
        json={"name": "Central FSL", "org_type": "fsl"},
        headers=auth_headers(admin_token),
    )

    assert resp.status_code == 201, resp.text

    org = db_session.query(models.Organization).filter_by(name="Central FSL").first()
    assert org is not None
    assert org.org_type == "fsl"


def test_onboard_org_creates_audit_log(client, make_user, db_session):
    make_user("config_admin", email="admin@example.com", password="pw")
    admin_token = login(client, "admin@example.com", "pw").json()["access_token"]

    client.post(
        "/orgs",
        json={"name": "Test FSL", "org_type": "fsl"},
        headers=auth_headers(admin_token),
    )

    entries = db_session.query(models.AuditLog).filter_by(action="org_onboarded").all()
    assert len(entries) == 1
    assert entries[0].action_metadata["name"] == "Test FSL"


def test_onboard_duplicate_org_returns_409(client, make_user, db_session):
    make_user("config_admin", email="admin@example.com", password="pw")
    admin_token = login(client, "admin@example.com", "pw").json()["access_token"]

    client.post(
        "/orgs",
        json={"name": "Duplicate Org", "org_type": "fsl"},
        headers=auth_headers(admin_token),
    )

    resp = client.post(
        "/orgs",
        json={"name": "Duplicate Org", "org_type": "fsl"},
        headers=auth_headers(admin_token),
    )

    assert resp.status_code == 409


def test_list_users_nonexistent_org_returns_404(client, make_user, db_session):
    make_user("config_admin", email="admin@example.com", password="pw")
    admin_token = login(client, "admin@example.com", "pw").json()["access_token"]

    resp = client.get(
        "/orgs/00000000-0000-0000-0000-000000000000/users",
        headers=auth_headers(admin_token),
    )

    assert resp.status_code == 404
