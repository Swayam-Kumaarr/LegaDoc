"""Tests for Flow 3 — Parallel Evidence Requests & Charge Sheet AND-Join Gate."""

import io
from app import models
from tests.conftest import auth_headers, login


def _register_and_assign_case(client, make_user, crime_type="Cyber Crime"):
    police_station = make_user("duty_officer", email="duty@police.gov.in", password="pw").organization
    sho = make_user("sho", email="sho@police.gov.in", password="pw", org=police_station)
    io_user = make_user("io", email="io@police.gov.in", password="pw", org=police_station)

    duty_token = login(client, "duty@police.gov.in", "pw").json()["access_token"]
    case = client.post(
        "/cases",
        json={"crime_type": crime_type, "complaint_text": "Cyber security breach"},
        headers=auth_headers(duty_token),
    ).json()

    sho_token = login(client, "sho@police.gov.in", "pw").json()["access_token"]
    client.post(
        f"/cases/{case['id']}/assign-io",
        json={"io_user_id": str(io_user.id)},
        headers=auth_headers(sho_token),
    )

    io_token = login(client, "io@police.gov.in", "pw").json()["access_token"]
    return case, io_user, io_token


def test_io_can_create_evidence_request_to_external_org(client, make_user, make_org):
    case, io_user, io_token = _register_and_assign_case(client, make_user)
    fsl_org = make_org(name="Digital Forensics Lab", org_type="fsl")

    resp = client.post(
        f"/cases/{case['id']}/evidence-requests",
        json={
            "requested_org_id": str(fsl_org.id),
            "doc_type_expected": "Digital Forensic Report",
            "notes": "Extract hard drive images",
        },
        headers=auth_headers(io_token),
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["case_id"] == case["id"]
    assert data["requested_org_id"] == str(fsl_org.id)
    assert data["doc_type_expected"] == "Digital Forensic Report"
    assert data["status"] == "requested"


def test_unassigned_io_cannot_create_evidence_request(client, make_user, make_org):
    case, io_user, io_token = _register_and_assign_case(client, make_user)
    fsl_org = make_org(name="Digital Forensics Lab", org_type="fsl")

    other_io = make_user("io", email="other_io@police.gov.in", password="pw")
    other_token = login(client, "other_io@police.gov.in", "pw").json()["access_token"]

    resp = client.post(
        f"/cases/{case['id']}/evidence-requests",
        json={
            "requested_org_id": str(fsl_org.id),
            "doc_type_expected": "Digital Forensic Report",
        },
        headers=auth_headers(other_token),
    )
    assert resp.status_code == 403
    assert "Not assigned" in resp.text


def test_authority_staff_scoping_and_cross_tenant_block(client, make_user, make_org):
    case, io_user, io_token = _register_and_assign_case(client, make_user)
    fsl_org = make_org(name="Digital Forensics Lab", org_type="fsl")
    bank_org = make_org(name="State Bank", org_type="bank")

    # Create evidence request for FSL
    ev_resp = client.post(
        f"/cases/{case['id']}/evidence-requests",
        json={"requested_org_id": str(fsl_org.id), "doc_type_expected": "FSL Report"},
        headers=auth_headers(io_token),
    ).json()
    req_id = ev_resp["id"]

    fsl_user = make_user("authority_staff", email="fsl_analyst@fsl.gov.in", password="pw", org=fsl_org)
    bank_user = make_user("authority_staff", email="bank_mgr@bank.com", password="pw", org=bank_org)

    fsl_token = login(client, "fsl_analyst@fsl.gov.in", "pw").json()["access_token"]
    bank_token = login(client, "bank_mgr@bank.com", "pw").json()["access_token"]

    # FSL can see request
    fsl_list = client.get(f"/cases/{case['id']}/evidence-requests", headers=auth_headers(fsl_token))
    assert fsl_list.status_code == 200
    assert len(fsl_list.json()) == 1

    # Bank cannot see FSL's request
    bank_list = client.get(f"/cases/{case['id']}/evidence-requests", headers=auth_headers(bank_token))
    assert bank_list.status_code == 200
    assert len(bank_list.json()) == 0

    # Bank tries to submit to FSL's request -> 403 Forbidden
    fake_pdf = b"%PDF-1.4 test forensic report content"
    bank_submit = client.post(
        f"/evidence-requests/{req_id}/submit",
        files={"file": ("fsl_report.pdf", io.BytesIO(fake_pdf), "application/pdf")},
        headers=auth_headers(bank_token),
    )
    assert bank_submit.status_code == 403
    assert "routed to a different organization" in bank_submit.text


def test_authority_fulfillment_and_double_submit_prevention(client, make_user, make_org):
    case, io_user, io_token = _register_and_assign_case(client, make_user)
    fsl_org = make_org(name="Digital Forensics Lab", org_type="fsl")

    ev_resp = client.post(
        f"/cases/{case['id']}/evidence-requests",
        json={"requested_org_id": str(fsl_org.id), "doc_type_expected": "FSL Report"},
        headers=auth_headers(io_token),
    ).json()
    req_id = ev_resp["id"]

    fsl_user = make_user("authority_staff", email="fsl_analyst@fsl.gov.in", password="pw", org=fsl_org)
    fsl_token = login(client, "fsl_analyst@fsl.gov.in", "pw").json()["access_token"]

    fake_pdf = b"%PDF-1.4 verified digital forensic analysis"
    submit_resp = client.post(
        f"/evidence-requests/{req_id}/submit",
        files={"file": ("report.pdf", io.BytesIO(fake_pdf), "application/pdf")},
        headers=auth_headers(fsl_token),
    )
    assert submit_resp.status_code == 200
    res_data = submit_resp.json()
    assert res_data["status"] == "completed"
    assert res_data["completed_at"] is not None

    # Re-submitting to the completed request must return 409 Conflict
    re_submit = client.post(
        f"/evidence-requests/{req_id}/submit",
        files={"file": ("report.pdf", io.BytesIO(fake_pdf), "application/pdf")},
        headers=auth_headers(fsl_token),
    )
    assert re_submit.status_code == 409
    assert "already been fulfilled" in re_submit.text


def test_unauthorized_roles_cannot_fulfill_evidence_request(client, make_user, make_org):
    """Asserts that roles outside matching authority_staff/admin (e.g. defense) are rejected with 403."""
    case, io_user, io_token = _register_and_assign_case(client, make_user)
    fsl_org = make_org(name="Digital Forensics Lab", org_type="fsl")

    ev_resp = client.post(
        f"/cases/{case['id']}/evidence-requests",
        json={"requested_org_id": str(fsl_org.id), "doc_type_expected": "FSL Report"},
        headers=auth_headers(io_token),
    ).json()
    req_id = ev_resp["id"]

    # Defense intruder attempting to submit fake forensic report
    defense_user = make_user("defense", email="defense@evil.com", password="pw")
    defense_token = login(client, "defense@evil.com", "pw").json()["access_token"]

    fake_pdf = b"%PDF-1.4 fabricated defense analysis"
    intruder_resp = client.post(
        f"/evidence-requests/{req_id}/submit",
        files={"file": ("report.pdf", io.BytesIO(fake_pdf), "application/pdf")},
        headers=auth_headers(defense_token),
    )
    assert intruder_resp.status_code == 403
    assert "Role not permitted" in intruder_resp.json()["detail"]



def test_charge_sheet_and_join_gate(client, make_user, make_org, db_session):
    case, io_user, io_token = _register_and_assign_case(client, make_user, crime_type="Financial Fraud")
    prosecutor = make_user("prosecutor", email="prosecutor@court.gov.in", password="pw")
    pros_token = login(client, "prosecutor@court.gov.in", "pw").json()["access_token"]

    bank_org = make_org(name="Bank", org_type="bank")

    # Seed mandatory stage requirement for Financial Fraud
    sr1 = models.StageRequirement(
        crime_type="Financial Fraud",
        requirement_type="document",
        requirement_key="FIR",
        mandatory=True,
    )
    sr2 = models.StageRequirement(
        crime_type="Financial Fraud",
        requirement_type="evidence_request",
        requirement_key="Bank Statement",
        mandatory=True,
    )
    db_session.add_all([sr1, sr2])
    db_session.commit()

    # Attempt to file charge sheet without satisfying requirements -> 409
    cs_fail = client.post(
        f"/cases/{case['id']}/file-charge-sheet",
        headers=auth_headers(pros_token),
    )
    assert cs_fail.status_code == 409
    detail = cs_fail.json()["detail"]
    assert "missing_items" in detail
    assert any("FIR" in item for item in detail["missing_items"])
    assert any("Bank Statement" in item for item in detail["missing_items"])

    # 1. Upload FIR document
    fake_pdf = b"%PDF-1.4 official complaint document"
    client.post(
        "/documents",
        data={"case_id": case["id"], "doc_type": "FIR"},
        files={"file": ("fir.pdf", io.BytesIO(fake_pdf), "application/pdf")},
        headers=auth_headers(io_token),
    )

    # Attempt again — still missing Bank Statement
    cs_fail2 = client.post(
        f"/cases/{case['id']}/file-charge-sheet",
        headers=auth_headers(pros_token),
    )
    assert cs_fail2.status_code == 409
    detail2 = cs_fail2.json()["detail"]
    assert len(detail2["missing_items"]) == 1
    assert "Bank Statement" in detail2["missing_items"][0]

    # 2. Fulfill evidence request for Bank Statement
    ev_req = client.post(
        f"/cases/{case['id']}/evidence-requests",
        json={"requested_org_id": str(bank_org.id), "doc_type_expected": "Bank Statement"},
        headers=auth_headers(io_token),
    ).json()

    bank_user = make_user("authority_staff", email="banker@bank.com", password="pw", org=bank_org)
    bank_token = login(client, "banker@bank.com", "pw").json()["access_token"]
    client.post(
        f"/evidence-requests/{ev_req['id']}/submit",
        files={"file": ("stmt.pdf", io.BytesIO(fake_pdf), "application/pdf")},
        headers=auth_headers(bank_token),
    )

    # 3. Both requirements now satisfied -> Charge Sheet successfully filed!
    cs_success = client.post(
        f"/cases/{case['id']}/file-charge-sheet",
        headers=auth_headers(pros_token),
    )
    assert cs_success.status_code == 200
    assert cs_success.json()["investigation_status"] == "Charge_Sheet_Filed"
