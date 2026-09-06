"""Tests for Flow 5 — Trial & Court Disposition (Terminal Transition)."""

from tests.conftest import auth_headers, login


def _setup_case_with_prosecutor_and_court(client, make_user):
    duty = make_user("duty_officer", email="duty_trial@police.gov.in", password="pw")
    pros = make_user("prosecutor", email="pros_trial@court.gov.in", password="pw")
    court = make_user("court", email="judge_trial@court.gov.in", password="pw")

    duty_token = login(client, "duty_trial@police.gov.in", "pw").json()["access_token"]
    case = client.post(
        "/cases",
        json={"crime_type": "Theft", "complaint_text": "Store theft"},
        headers=auth_headers(duty_token),
    ).json()

    tokens = {
        "pros": login(client, "pros_trial@court.gov.in", "pw").json()["access_token"],
        "court": login(client, "judge_trial@court.gov.in", "pw").json()["access_token"],
        "duty": duty_token,
    }
    return case, tokens


def test_trial_lifecycle_and_terminal_judgment(client, make_user):
    case, tokens = _setup_case_with_prosecutor_and_court(client, make_user)

    # 1. Cannot schedule trial hearing while still FIR_Registered
    premature_trial = client.post(
        f"/cases/{case['id']}/trial/hearing-notice",
        headers=auth_headers(tokens["court"]),
    )
    assert premature_trial.status_code == 409
    assert "Charge_Sheet_Filed" in premature_trial.text

    # 2. File charge sheet (no mandatory stage requirements configured for Theft, so passes)
    cs_resp = client.post(
        f"/cases/{case['id']}/file-charge-sheet",
        headers=auth_headers(tokens["pros"]),
    )
    assert cs_resp.status_code == 200
    assert cs_resp.json()["investigation_status"] == "Charge_Sheet_Filed"

    # 3. Schedule trial hearing -> status = Trial
    trial_resp = client.post(
        f"/cases/{case['id']}/trial/hearing-notice",
        headers=auth_headers(tokens["court"]),
    )
    assert trial_resp.status_code == 200
    assert trial_resp.json()["investigation_status"] == "Trial"

    # 4. Invalid verdict validation
    bad_verdict = client.post(
        f"/cases/{case['id']}/judgment",
        json={"verdict": "guilty_ish"},
        headers=auth_headers(tokens["court"]),
    )
    assert bad_verdict.status_code == 400
    assert "acquitted" in bad_verdict.text

    # 5. Record final judgment -> status = Judgment (Terminal)
    jdg_resp = client.post(
        f"/cases/{case['id']}/judgment",
        json={"verdict": "convicted", "summary": "Sentenced to 2 years under IPC 379"},
        headers=auth_headers(tokens["court"]),
    )
    assert jdg_resp.status_code == 200
    assert jdg_resp.json()["investigation_status"] == "Judgment"

    # 6. Post-judgment cannot schedule trial or file new charge sheet
    post_hearing = client.post(
        f"/cases/{case['id']}/trial/hearing-notice",
        headers=auth_headers(tokens["court"]),
    )
    assert post_hearing.status_code == 409


def test_trial_role_authorizations(client, make_user):
    case, tokens = _setup_case_with_prosecutor_and_court(client, make_user)

    # Duty officer cannot schedule trial hearing or record judgment
    duty_hearing = client.post(
        f"/cases/{case['id']}/trial/hearing-notice",
        headers=auth_headers(tokens["duty"]),
    )
    assert duty_hearing.status_code == 403

    duty_jdg = client.post(
        f"/cases/{case['id']}/judgment",
        json={"verdict": "acquitted"},
        headers=auth_headers(tokens["duty"]),
    )
    assert duty_jdg.status_code == 403
