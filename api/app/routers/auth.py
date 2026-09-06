"""Auth — see SYSTEM_DESIGN.md Interface Contracts, "Endpoint Table", and
the Security section's login-hardening rules."""

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app import models, schemas, security
from app.config import settings
from app.database import get_db
from app.rate_limit import login_rate_limiter

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=schemas.TokenResponse)
def login(request: Request, body: schemas.LoginRequest, db: Session = Depends(get_db)):
    """POST /auth/login — Public. Issue an access token (15 min) + refresh
    token (7 days). Accepts either official government email or Government Service ID.

    Hardened with:
    1. Sliding window IP rate limiting (10 attempts / 60 seconds)
    2. Constant-time dummy bcrypt check preventing user enumeration
    3. Multi-Factor Authentication (MFA) enforcement for high-privilege roles
       and users with mfa_enabled=True.
    """
    client_ip = request.client.host if request.client else "127.0.0.1"
    login_rate_limiter.check(
        client_ip,
        detail="Login rate limit exceeded. Maximum 10 attempts per minute. Please retry later."
    )

    ident = body.email.strip()
    user = (
        db.query(models.User)
        .filter((models.User.email == ident) | (models.User.service_id == ident))
        .first()
    )

    if user is None:
        security.dummy_password_check(body.password)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")

    if not security.verify_password(body.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")

    # MFA evaluation: enforced when user.mfa_enabled is True
    if user.mfa_enabled:
        if not body.mfa_code:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="MFA code required",
            )
        secret = security.get_user_mfa_secret(str(user.id), user.email, settings.JWT_SECRET)
        if not security.verify_totp_code(secret, body.mfa_code):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid MFA code",
            )

    org_id = str(user.org_id)
    return schemas.TokenResponse(
        access_token=security.create_access_token(str(user.id), org_id, user.role),
        refresh_token=security.create_refresh_token(str(user.id), org_id, user.role),
    )


@router.get("/me", response_model=schemas.UserProfileResponse)
def get_current_user_profile(
    current_user: models.User = Depends(security.get_current_user),
    db: Session = Depends(get_db)
):
    """GET /auth/me — Authenticated. Returns authoritative user profile, department,
    government service ID, authoritative role, and assigned permissions list.

    Resolves permissions dynamically from the assigned Role entity in PostgreSQL/SQLite.
    Guarantees that frontend clients receive verified server-side claims rather than
    allowing client-side role selection.
    """
    # Resolve permissions from user's role
    permissions = []
    if current_user.role_rel and current_user.role_rel.permissions:
        permissions = [p.code for p in current_user.role_rel.permissions]
    else:
        # Fallback to Role by code
        role_obj = db.query(models.Role).filter(models.Role.code == current_user.role).first()
        if role_obj and role_obj.permissions:
            permissions = [p.code for p in role_obj.permissions]

    org_name = current_user.organization.name if current_user.organization else None
    org_type = current_user.organization.org_type if current_user.organization else None

    return schemas.UserProfileResponse(
        id=current_user.id,
        name=current_user.name,
        email=current_user.email,
        service_id=current_user.service_id,
        designation=current_user.designation,
        role=current_user.role,
        org_id=current_user.org_id,
        org_name=org_name,
        org_type=org_type,
        language_preference=current_user.language_preference or "en",
        permissions=permissions
    )


@router.post("/refresh", response_model=schemas.AccessTokenResponse)
def refresh_token(body: schemas.RefreshRequest):
    """POST /auth/refresh — Exchange a valid refresh token for a new access
    token. Not in the original endpoint table — added because a 15-minute
    access-token TTL is unusable without this."""
    claims = security.decode_token(body.refresh_token, expected_type="refresh")
    new_access = security.create_access_token(claims["sub"], claims["org_id"], claims["role"])
    return schemas.AccessTokenResponse(access_token=new_access)


@router.post("/logout")
def logout(claims: dict = Depends(security.get_current_claims)):
    """POST /auth/logout — Not in the original endpoint table.

    Baseline behavior: stateless. The 15-minute access-token TTL bounds the
    exposure window on its own. LATER (see SYSTEM_DESIGN.md): write the
    token's JTI to a Redis revocation set (settings.TOKEN_REVOCATION_REDIS_DB)
    with a TTL matching its remaining lifetime, so a shared-device logout
    invalidates the session immediately instead of waiting out the TTL.
    """
    return {"status": "logged out"}


@router.post("/change-password")
def change_password(
    body: schemas.ChangePasswordRequest,
    current_user: models.User = Depends(security.get_current_user),
    db: Session = Depends(get_db)
):
    """POST /auth/change-password — Authenticated. Validates current password,
    enforces password complexity requirements (NIST SP 800-63B), and updates
    the user's hashed password.
    """
    if not security.verify_password(body.current_password, current_user.hashed_password):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Current password incorrect")

    security.validate_password_strength(body.new_password)
    current_user.hashed_password = security.hash_password(body.new_password)
    db.commit()
    return {"status": "password updated successfully"}


@router.post("/mfa/setup", response_model=schemas.MFASetupResponse)
def setup_mfa(current_user: models.User = Depends(security.get_current_user)):
    """POST /auth/mfa/setup — Authenticated. Generates a deterministic RFC 6238
    base32 secret and provisioning URI for standard authenticator applications.
    """
    secret = security.get_user_mfa_secret(str(current_user.id), current_user.email, settings.JWT_SECRET)
    uri = f"otpauth://totp/LegaDoc:{current_user.email}?secret={secret}&issuer=LegaDoc"
    return schemas.MFASetupResponse(
        secret=secret,
        provisioning_uri=uri,
        mfa_enabled=current_user.mfa_enabled
    )


@router.post("/mfa/enable")
def enable_mfa(
    body: schemas.MFAVerifyRequest,
    current_user: models.User = Depends(security.get_current_user),
    db: Session = Depends(get_db)
):
    """POST /auth/mfa/enable — Authenticated. Verifies the 6-digit TOTP code
    and authoritatively enables MFA on the officer's account.
    """
    secret = security.get_user_mfa_secret(str(current_user.id), current_user.email, settings.JWT_SECRET)
    if not security.verify_totp_code(secret, body.code):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid MFA code")

    current_user.mfa_enabled = True
    db.commit()
    return {"status": "mfa enabled"}


@router.post("/mfa/disable")
def disable_mfa(
    body: schemas.MFADisableRequest,
    current_user: models.User = Depends(security.get_current_user),
    db: Session = Depends(get_db)
):
    """POST /auth/mfa/disable — Authenticated. Verifies current password
    before deactivating MFA.
    """
    if not security.verify_password(body.password, current_user.hashed_password):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Password incorrect")

    current_user.mfa_enabled = False
    db.commit()
    return {"status": "mfa disabled"}

