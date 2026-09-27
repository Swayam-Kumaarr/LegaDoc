"""The redaction blueprint: per role, per document type, per entity type,
what a restricted reader sees.

Before it, masking was all-or-nothing — a role either held full-text access
in code or saw every tagged span masked. These tests pin the two properties
that matter: the default is still to mask everything, and a rule can never
turn into a way of revealing a detection nobody is confident about.
"""

from uuid import uuid4

from app import models
from app.redaction import apply_redaction
from tests.conftest import auth_headers, login

TEXT = "Complainant Rajesh Kumar of Karol Bagh, phone 9876543210, attended."


def _tag(entity_type, fragment, confidence=90):
    start = TEXT.index(fragment)
    return type("Tag", (), {
        "entity_type": entity_type,
        "span_start": start,
        "span_end": start + len(fragment),
        "confidence": confidence,
    })()


def _policy(role, entity_type, action, min_confidence=0, doc_type="*"):
    return models.RedactionPolicy(
        role=role, doc_type=doc_type, entity_type=entity_type,
        action=action, min_confidence=min_confidence,
    )


def test_with_no_policy_every_tagged_span_is_masked():
    """The behaviour before this feature existed, and the behaviour of any
    environment that never configures a rule."""
    out = apply_redaction(TEXT, [_tag("PERSON", "Rajesh Kumar"), _tag("PHONE_NUMBER", "9876543210")])

    assert "Rajesh Kumar" not in out
    assert "9876543210" not in out
    assert out.count("[REDACTED") == 2


def test_a_show_rule_reveals_only_that_entity_type_for_that_role():
    policies = [_policy("duty_officer", "LOCATION", "show")]
    tags = [_tag("PERSON", "Rajesh Kumar"), _tag("LOCATION", "Karol Bagh")]

    duty = apply_redaction(TEXT, tags, policies=policies, role="duty_officer", doc_type="FIR")
    assert "Karol Bagh" in duty          # allowed by the rule
    assert "Rajesh Kumar" not in duty    # no rule, so still masked

    # Another restricted role is unaffected by a rule written for duty_officer.
    other = apply_redaction(TEXT, tags, policies=policies, role="records_ncrb_analyst", doc_type="FIR")
    assert "Karol Bagh" not in other


def test_a_weak_detection_is_not_revealed_by_a_rule_written_for_confident_ones():
    """The floor is the point of the feature: "show LOCATION" is written with
    real place names in mind, not with the OCR debris the parser sometimes
    labels LOCATION at low confidence."""
    policies = [_policy("duty_officer", "LOCATION", "show", min_confidence=70)]

    confident = apply_redaction(TEXT, [_tag("LOCATION", "Karol Bagh", confidence=90)],
                                policies=policies, role="duty_officer", doc_type="FIR")
    weak = apply_redaction(TEXT, [_tag("LOCATION", "Karol Bagh", confidence=55)],
                           policies=policies, role="duty_officer", doc_type="FIR")

    assert "Karol Bagh" in confident
    assert "Karol Bagh" not in weak
    assert "[REDACTED:LOCATION]" in weak


def test_flag_leaves_the_text_visible_but_marked_unconfirmed():
    policies = [_policy("duty_officer", "PERSON", "flag")]
    out = apply_redaction(TEXT, [_tag("PERSON", "Rajesh Kumar")],
                          policies=policies, role="duty_officer", doc_type="FIR")

    assert "Rajesh Kumar [UNCONFIRMED:PERSON]" in out


def test_the_most_specific_rule_wins():
    """A blanket rule stays in force while one document type is carved out of
    it, so an administrator does not have to restate the whole matrix."""
    policies = [
        _policy("duty_officer", "PERSON", "show"),                      # blanket
        _policy("duty_officer", "PERSON", "mask", doc_type="Case Diary"),  # carve-out
    ]
    tags = [_tag("PERSON", "Rajesh Kumar")]

    assert "Rajesh Kumar" in apply_redaction(TEXT, tags, policies=policies, role="duty_officer", doc_type="FIR")
    assert "Rajesh Kumar" not in apply_redaction(TEXT, tags, policies=policies, role="duty_officer", doc_type="Case Diary")


def test_only_the_config_admin_may_change_the_blueprint(client, make_user):
    """Reading it is an audit question; changing it decides who sees a
    witness's phone number."""
    make_user("config_admin", email="cfg@legadoc.gov.in", password="pw")
    make_user("security_auditor", email="aud@legadoc.gov.in", password="pw")
    make_user("io", email="io_policy@police.gov.in", password="pw")

    admin = login(client, "cfg@legadoc.gov.in", "pw").json()["access_token"]
    auditor = login(client, "aud@legadoc.gov.in", "pw").json()["access_token"]
    io_token = login(client, "io_policy@police.gov.in", "pw").json()["access_token"]

    body = {"rules": [{"role": "duty_officer", "entity_type": "LOCATION", "action": "show", "min_confidence": 70}]}

    assert client.put("/admin/redaction-policy", json=body, headers=auth_headers(io_token)).status_code == 403
    assert client.put("/admin/redaction-policy", json=body, headers=auth_headers(auditor)).status_code == 403
    assert client.put("/admin/redaction-policy", json=body, headers=auth_headers(admin)).status_code == 200

    assert client.get("/admin/redaction-policy", headers=auth_headers(auditor)).status_code == 200
    assert client.get("/admin/redaction-policy", headers=auth_headers(io_token)).status_code == 403


def test_widening_access_is_named_in_the_audit_row(client, db_session, make_user):
    """A rule that reveals an entity type to a role is a widening of access,
    and the audit trail has to say which one."""
    make_user("config_admin", email="cfg2@legadoc.gov.in", password="pw")
    admin = login(client, "cfg2@legadoc.gov.in", "pw").json()["access_token"]

    client.put(
        "/admin/redaction-policy",
        json={"rules": [
            {"role": "duty_officer", "entity_type": "LOCATION", "action": "show", "min_confidence": 70},
            {"role": "duty_officer", "entity_type": "PERSON", "action": "mask"},
        ]},
        headers=auth_headers(admin),
    )

    row = (
        db_session.query(models.AuditLog)
        .filter(models.AuditLog.action == "redaction_policy_updated")
        .order_by(models.AuditLog.seq.desc())
        .first()
    )
    assert row is not None
    widened = row.action_metadata["widened"]
    assert any("duty_officer/*/LOCATION" in w and "-> show" in w for w in widened), widened
    assert not any("PERSON" in w for w in widened), widened


def test_an_invalid_action_is_refused(client, make_user):
    make_user("config_admin", email="cfg3@legadoc.gov.in", password="pw")
    admin = login(client, "cfg3@legadoc.gov.in", "pw").json()["access_token"]

    resp = client.put(
        "/admin/redaction-policy",
        json={"rules": [{"role": "duty_officer", "entity_type": "PERSON", "action": "unmask_everything"}]},
        headers=auth_headers(admin),
    )
    assert resp.status_code == 422
