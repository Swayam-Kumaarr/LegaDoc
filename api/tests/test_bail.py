"""Tests for Flow 4 — Independent Bail Track Finite State Machine."""

from tests.conftest import auth_headers, login


def _setup_case_and_users(client, make_user):
    station = make_user("duty_officer", email="duty_bail@police.gov.in", password="pw").organization
    sho = make_user("sho", email="sho_bail@police.gov.in", password="pw", org=station)
    io = make_user("io", email="io_bail@police.gov.in", password="pw", org=station)
    court = make_user("court", email="judge@court.gov.in", password="pw")
    defense = make_user("defense", email="advocate@bar.in", password="pw")

    duty_token = login(client, "duty_bail@police.gov.in", "pw").json()["access_token"]
    case = client.post(
        "/cases",
        json={"crime_type": "Domestic Violence", "complaint_text": "DV complaint"},
        headers=auth_headers(duty_token),
    ).json()

    sho_token = login(client, "sho_bail@police.gov.in", "pw").json()["access_token"]
    client.post(
        f"/cases/{case['id']}/assign-io",
        json={"io_user_id": str(io.id)},
        headers=auth_headers(sho_token),
    )

    tokens = {
        "io": login(client, "io_bail@police.gov.in", "pw").json()["access_token"],
        "court": login(client, "judge@court.gov.in", "pw").json()["access_token"],
        "defense": login(client, "advocate@bar.in", "pw").json()["access_token"],
    }
    return case, tokens


def test_bail_full_lifecycle(client, make_user):
    case, tokens = _setup_case_and_users(client, make_user)

    # 1. Arrest
    arr_resp = client.post(f"/cases/{case['id']}/bail/arrest", headers=auth_headers(tokens["io"]))
    assert arr_resp.status_code == 201
    assert arr_resp.json()["stage"] == "Arrested"

    # Verify investigation_status did not change (independent tracks!)
    case_check = client.get(f"/cases/{case['id']}", headers=auth_headers(tokens["io"])).json()
    assert case_check["bail_status"] == "Arrested"
    assert case_check["investigation_status"] == "FIR_Registered"

    # 2. Bail Application
    app_resp = client.post(f"/cases/{case['id']}/bail/application", headers=auth_headers(tokens["defense"]))
    assert app_resp.status_code == 201
    assert app_resp.json()["stage"] == "Application_Filed"

    # 3. Hearing Notice
    hr_resp = client.post(f"/cases/{case['id']}/bail/hearing-notice", headers=auth_headers(tokens["court"]))
    assert hr_resp.status_code == 201
    assert hr_resp.json()["stage"] == "Hearing_Scheduled"

    # 4. Bail Order (Granted)
    ord_resp = client.post(
        f"/cases/{case['id']}/bail/order",
        json={"granted": True, "conditions": "Surrender passport, reporting every Monday"},
        headers=auth_headers(tokens["court"]),
    )
    assert ord_resp.status_code == 201
    assert ord_resp.json()["stage"] == "Order_Issued"

    # 5. Surety Registration
    sur_resp = client.post(
        f"/cases/{case['id']}/bail/surety",
        json={"surety_name": "Ramesh Kumar", "bond_amount": 50000.0},
        headers=auth_headers(tokens["defense"]),
    )
    assert sur_resp.status_code == 201
    assert sur_resp.json()["stage"] == "Surety_Registered"

    # 6. List history
    history = client.get(f"/cases/{case['id']}/bail", headers=auth_headers(tokens["court"])).json()
    stages = [r["stage"] for r in history]
    assert stages == ["Arrested", "Application_Filed", "Hearing_Scheduled", "Order_Issued", "Surety_Registered"]


def test_bail_denial_path(client, make_user):
    case, tokens = _setup_case_and_users(client, make_user)

    client.post(f"/cases/{case['id']}/bail/arrest", headers=auth_headers(tokens["io"]))
    client.post(f"/cases/{case['id']}/bail/application", headers=auth_headers(tokens["defense"]))
    client.post(f"/cases/{case['id']}/bail/hearing-notice", headers=auth_headers(tokens["court"]))

    ord_resp = client.post(
        f"/cases/{case['id']}/bail/order",
        json={"granted": False, "conditions": "Risk of witness tampering"},
        headers=auth_headers(tokens["court"]),
    )
    assert ord_resp.status_code == 201
    assert ord_resp.json()["stage"] == "Denied_Final"

    case_check = client.get(f"/cases/{case['id']}", headers=auth_headers(tokens["court"])).json()
    assert case_check["bail_status"] == "Denied_Final"


def test_bail_fsm_rejects_out_of_order_transitions(client, make_user):
    case, tokens = _setup_case_and_users(client, make_user)

    # Cannot file application before arrest
    app_fail = client.post(f"/cases/{case['id']}/bail/application", headers=auth_headers(tokens["defense"]))
    assert app_fail.status_code == 400
    assert "must be arrested first" in app_fail.text

    # Arrest
    client.post(f"/cases/{case['id']}/bail/arrest", headers=auth_headers(tokens["io"]))

    # Cannot register surety right after arrest
    sur_fail = client.post(
        f"/cases/{case['id']}/bail/surety",
        json={"surety_name": "Test", "bond_amount": 1000},
        headers=auth_headers(tokens["defense"]),
    )
    assert sur_fail.status_code == 400
    assert "bail has not been granted" in sur_fail.text

    # Cannot schedule hearing before application
    hr_fail = client.post(f"/cases/{case['id']}/bail/hearing-notice", headers=auth_headers(tokens["court"]))
    assert hr_fail.status_code == 400
    assert "application must be filed first" in hr_fail.text


def test_bail_role_authorizations(client, make_user):
    case, tokens = _setup_case_and_users(client, make_user)

    # Defense cannot record arrest
    arr_defense = client.post(f"/cases/{case['id']}/bail/arrest", headers=auth_headers(tokens["defense"]))
    assert arr_defense.status_code == 403

    # IO cannot issue court order
    client.post(f"/cases/{case['id']}/bail/arrest", headers=auth_headers(tokens["io"]))
    client.post(f"/cases/{case['id']}/bail/application", headers=auth_headers(tokens["defense"]))
    client.post(f"/cases/{case['id']}/bail/hearing-notice", headers=auth_headers(tokens["court"]))

    io_order = client.post(
        f"/cases/{case['id']}/bail/order",
        json={"granted": True},
        headers=auth_headers(tokens["io"]),
    )
    assert io_order.status_code == 403


def test_bail_pathway_taxonomy_coverage(client, make_user):
    """Verifies statutory bail pathway resolution for NDPS and standard cases."""
    case, tokens = _setup_case_and_users(client, make_user)

    # 1. Domestic Violence pathway check
    resp = client.get(f"/cases/{case['id']}/bail/pathway", headers=auth_headers(tokens["court"]))
    assert resp.status_code == 200
    data = resp.json()
    assert data["statutory_pathway"]["bailable_status"] == "Non-Bailable"
    assert "Domestic Violence" in data["statutory_pathway"]["crime_type"]
    assert len(data["statutory_pathway"]["statutory_pathway"]) > 0

    # 2. NDPS statutory bar pathway check
    duty_token = login(client, "duty_bail@police.gov.in", "pw").json()["access_token"]
    ndps_case = client.post(
        "/cases",
        json={"crime_type": "NDPS", "complaint_text": "Commercial contraband seizure"},
        headers=auth_headers(duty_token),
    ).json()

    ndps_resp = client.get(f"/cases/{ndps_case['id']}/bail/pathway", headers=auth_headers(tokens["defense"]))
    assert ndps_resp.status_code == 200
    ndps_data = ndps_resp.json()
    assert "Twin Conditions" in ndps_data["statutory_pathway"]["applicable_sections"]
    assert "Strictly Non-Bailable" in ndps_data["statutory_pathway"]["bailable_status"]

