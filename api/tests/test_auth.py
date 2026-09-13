"""Auth tests — see SYSTEM_DESIGN.md's testing priority: "Auth/RBAC tests
first" is stated as exactly what judges (and, more importantly, real
attackers) will probe hardest."""

from tests.conftest import login


def test_login_success_returns_access_and_refresh_tokens(client, make_user):
    make_user("duty_officer", email="duty@example.com", password="hunter2000")

    resp = login(client, "duty@example.com", "hunter2000")

    assert resp.status_code == 200
    body = resp.json()
    assert body["access_token"]
    assert body["refresh_token"]
    assert body["token_type"] == "bearer"


def test_login_wrong_password_rejected(client, make_user):
    make_user("duty_officer", email="duty@example.com", password="hunter2000")

    resp = login(client, "duty@example.com", "wrong-password")

    assert resp.status_code == 401
    assert "invalid" in resp.json()["detail"].lower()


def test_login_unknown_email_gets_same_generic_error_as_wrong_password(client, make_user):
    make_user("duty_officer", email="duty@example.com", password="hunter2000")

    known_wrong = login(client, "duty@example.com", "wrong-password")
    unknown = login(client, "nobody-like-this-exists@example.com", "whatever")

    assert unknown.status_code == known_wrong.status_code == 401
    # Same message either way — the response body must not leak which case it was.
    assert unknown.json()["detail"] == known_wrong.json()["detail"]


def test_refresh_token_issues_a_new_access_token(client, make_user):
    make_user("duty_officer", email="duty@example.com", password="hunter2000")
    tokens = login(client, "duty@example.com", "hunter2000").json()

    resp = client.post("/auth/refresh", json={"refresh_token": tokens["refresh_token"]})

    assert resp.status_code == 200
    assert resp.json()["access_token"]
    assert resp.json()["access_token"] != tokens["access_token"]


def test_refresh_rejects_an_access_token_used_as_a_refresh_token(client, make_user):
    """An access token must not double as a refresh token — they're issued
    with different `type` claims specifically to prevent this."""
    make_user("duty_officer", email="duty@example.com", password="hunter2000")
    tokens = login(client, "duty@example.com", "hunter2000").json()

    resp = client.post("/auth/refresh", json={"refresh_token": tokens["access_token"]})

    assert resp.status_code == 401


def test_protected_endpoint_rejects_missing_token(client):
    resp = client.get("/cases")
    assert resp.status_code == 401


def test_protected_endpoint_rejects_garbage_token(client):
    resp = client.get("/cases", headers={"Authorization": "Bearer not-a-real-token"})
    assert resp.status_code == 401


def test_login_rate_limiter_blocks_11th_attempt(client, make_user):
    """Ten FAILED attempts per account per minute; the 11th returns 429 with a
    Retry-After header. Was "per IP", which behind the Vite proxy meant one
    shared bucket for every user — see
    test_failed_attempts_are_scoped_per_account_not_globally."""
    from app.rate_limit import login_rate_limiter
    login_rate_limiter.reset()

    make_user("duty_officer", email="rate_test@example.com", password="hunter2000")

    try:
        # First 10 attempts allowed
        for _ in range(10):
            resp = login(client, "rate_test@example.com", "wrong-password")
            assert resp.status_code == 401

        # 11th attempt must be blocked by rate limiter
        resp11 = login(client, "rate_test@example.com", "wrong-password")
        assert resp11.status_code == 429
        assert "too many failed sign-in attempts" in resp11.json()["detail"].lower()
        assert "Retry-After" in resp11.headers
    finally:
        login_rate_limiter.reset()


def test_mfa_challenge_when_mfa_enabled(client, db_session, make_user):
    """Verify that an officer with mfa_enabled=True receives a 401 challenge
    if mfa_code is omitted from the login request."""
    user = make_user("config_admin", email="mfa_admin@legadoc.gov", password="Password123!")
    user.mfa_enabled = True
    db_session.commit()

    # Login without mfa_code should be challenged
    resp = login(client, "mfa_admin@legadoc.gov", "Password123!")
    assert resp.status_code == 401
    assert "mfa code required" in resp.json()["detail"].lower()


def test_mfa_invalid_code_rejected(client, db_session, make_user):
    """Verify that an incorrect MFA code is rejected with 401."""
    user = make_user("court", email="mfa_judge@court.gov", password="Password123!")
    user.mfa_enabled = True
    db_session.commit()

    resp = login(client, "mfa_judge@court.gov", "Password123!", mfa_code="000000")
    assert resp.status_code == 401
    assert "invalid mfa code" in resp.json()["detail"].lower()


def test_mfa_valid_totp_code_succeeds(client, db_session, make_user):
    """Verify that providing the correct 6-digit TOTP code authenticates successfully."""
    from app.config import settings
    from app import security

    user = make_user("security_auditor", email="mfa_auditor@legadoc.gov", password="Password123!")
    user.mfa_enabled = True
    db_session.commit()

    secret = security.get_user_mfa_secret(str(user.id), user.email, settings.JWT_SECRET)
    valid_code = security.generate_totp_code(secret)

    resp = login(client, "mfa_auditor@legadoc.gov", "Password123!", mfa_code=valid_code)
    assert resp.status_code == 200
    body = resp.json()
    assert body["access_token"]
    assert body["refresh_token"]


def test_mfa_setup_enable_and_disable_lifecycle(client, make_user):
    """Verify authenticated officer can set up, enable with TOTP, and disable MFA."""
    from app import security
    from tests.conftest import auth_headers

    make_user("io", email="io_mfa@police.gov", password="Password123!")
    tokens = login(client, "io_mfa@police.gov", "Password123!").json()
    headers = auth_headers(tokens["access_token"])

    # 1. Setup endpoint returns base32 secret and provisioning URI
    setup_resp = client.post("/auth/mfa/setup", headers=headers)
    assert setup_resp.status_code == 200
    data = setup_resp.json()
    secret = data["secret"]
    assert len(secret) == 32
    assert "otpauth://totp/" in data["provisioning_uri"]
    assert data["mfa_enabled"] is False

    # 2. Invalid code rejected on enable
    bad_enable = client.post("/auth/mfa/enable", json={"code": "000000"}, headers=headers)
    assert bad_enable.status_code == 400

    # 3. Valid TOTP code enables MFA
    valid_code = security.generate_totp_code(secret)
    good_enable = client.post("/auth/mfa/enable", json={"code": valid_code}, headers=headers)
    assert good_enable.status_code == 200
    assert good_enable.json()["status"] == "mfa enabled"

    # 4. Subsequent login now requires MFA
    no_mfa = login(client, "io_mfa@police.gov", "Password123!")
    assert no_mfa.status_code == 401
    assert "mfa code required" in no_mfa.json()["detail"].lower()

    # 5. Disable MFA requires password confirmation
    bad_pwd_disable = client.post("/auth/mfa/disable", json={"password": "wrong"}, headers=headers)
    assert bad_pwd_disable.status_code == 400

    good_disable = client.post("/auth/mfa/disable", json={"password": "Password123!"}, headers=headers)
    assert good_disable.status_code == 200
    assert good_disable.json()["status"] == "mfa disabled"


def test_change_password_enforces_complexity(client, make_user):
    """Verify change-password validates current password and enforces NIST complexity."""
    from tests.conftest import auth_headers

    make_user("duty_officer", email="officer_pwd@police.gov", password="OldPassword123!")
    tokens = login(client, "officer_pwd@police.gov", "OldPassword123!").json()
    headers = auth_headers(tokens["access_token"])

    # Wrong current password rejected
    wrong_curr = client.post(
        "/auth/change-password",
        json={"current_password": "WrongPassword!", "new_password": "NewPassword123!"},
        headers=headers,
    )
    assert wrong_curr.status_code == 400

    # Weak password (< 8 chars) rejected
    too_short = client.post(
        "/auth/change-password",
        json={"current_password": "OldPassword123!", "new_password": "Short1!"},
        headers=headers,
    )
    assert too_short.status_code == 422
    assert "at least 8 characters" in too_short.json()["detail"].lower()

    # Common password rejected
    common_pwd = client.post(
        "/auth/change-password",
        json={"current_password": "OldPassword123!", "new_password": "password123"},
        headers=headers,
    )
    assert common_pwd.status_code == 422
    assert "too common" in common_pwd.json()["detail"].lower()

    # Valid strong password succeeds
    valid_change = client.post(
        "/auth/change-password",
        json={"current_password": "OldPassword123!", "new_password": "SecurePassword2026!"},
        headers=headers,
    )
    assert valid_change.status_code == 200
    assert valid_change.json()["status"] == "password updated successfully"

    # Login with new password works
    new_login = login(client, "officer_pwd@police.gov", "SecurePassword2026!")
    assert new_login.status_code == 200



def test_successful_logins_do_not_consume_rate_limit_quota(client, make_user):
    """The reported blocker. The limiter counted every attempt, including
    successful ones, and keyed on request.client.host — which is the Vite
    proxy container's address for every browser request, since uvicorn runs
    without --proxy-headers. That made it one shared bucket of ten for the
    whole application: walking the nine seeded personas nearly exhausted it,
    and the next sign-in anywhere returned 429.
    """
    from app.rate_limit import login_rate_limiter, login_ip_limiter
    login_rate_limiter.reset()
    login_ip_limiter.reset()

    make_user("duty_officer", email="quota@example.com", password="hunter2000")

    # Well past the old limit of 10 — none of these should be charged.
    for i in range(15):
        resp = login(client, "quota@example.com", "hunter2000")
        assert resp.status_code == 200, f"attempt {i + 1} returned {resp.status_code}: {resp.text}"


def test_failed_attempts_are_scoped_per_account_not_globally(client, make_user):
    """One account being attacked must not lock everyone else out. With a
    single per-IP bucket behind the proxy, it did exactly that."""
    from app.rate_limit import login_rate_limiter, login_ip_limiter
    login_rate_limiter.reset()
    login_ip_limiter.reset()

    make_user("duty_officer", email="victim@example.com", password="hunter2000")
    make_user("io", email="bystander@example.com", password="hunter2000")

    for _ in range(10):
        assert login(client, "victim@example.com", "wrong-password").status_code == 401

    # That account is now locked...
    assert login(client, "victim@example.com", "wrong-password").status_code == 429
    # ...but an unrelated account signs in normally.
    assert login(client, "bystander@example.com", "hunter2000").status_code == 200


def test_a_successful_login_clears_earlier_failures(client, make_user):
    """A few mistyped passwords followed by the right one should not leave the
    account one attempt from lockout."""
    from app.rate_limit import login_rate_limiter, login_ip_limiter
    login_rate_limiter.reset()
    login_ip_limiter.reset()

    make_user("duty_officer", email="typo@example.com", password="hunter2000")

    for _ in range(9):
        assert login(client, "typo@example.com", "wrong-password").status_code == 401
    assert login(client, "typo@example.com", "hunter2000").status_code == 200

    # Budget reset: nine more failures are available before the block.
    for _ in range(9):
        assert login(client, "typo@example.com", "wrong-password").status_code == 401


def test_seeded_personas_match_the_frontend_login_picker():
    """CLAUDE.md, seed_data.py and the DevLogin picker describe the same set of
    accounts, and nothing kept them in step — the SHO persona was in the picker
    and absent from the documented table. A persona offered by the UI that the
    seeder never creates is indistinguishable, to whoever clicks it, from a
    broken login.
    """
    import re
    from pathlib import Path
    from app.seed_data import OFFICIAL_TEST_USERS

    picker = Path(__file__).resolve().parents[2] / "web" / "src" / "dev" / "seededAccounts.js"
    listed = set(re.findall(r"email:\s*'([^']+)'", picker.read_text(encoding="utf-8")))
    seeded = {u["email"] for u in OFFICIAL_TEST_USERS}

    assert listed == seeded, (
        f"offered by the picker but never seeded: {sorted(listed - seeded)}; "
        f"seeded but not offered: {sorted(seeded - listed)}"
    )


def test_every_seeded_persona_can_authenticate(db_session):
    """Pins the seeder end to end: each documented persona exists, carries the
    documented role, and its password verifies. Until scripts/setup.sh called
    the seeder, a fresh stack had none of them and every sign-in failed."""
    from app import models, security
    from app.seed_data import DEFAULT_TEST_PASSWORD, OFFICIAL_TEST_USERS, seed_all

    seed_all(db_session)

    for u in OFFICIAL_TEST_USERS:
        row = db_session.query(models.User).filter(models.User.email == u["email"]).first()
        assert row is not None, f"{u['email']} was not created by seed_all"
        assert row.role == u["role"], f"{u['email']}: role {row.role} != {u['role']}"
        assert security.verify_password(DEFAULT_TEST_PASSWORD, row.hashed_password), (
            f"{u['email']} does not accept the documented password"
        )
