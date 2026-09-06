"""
JWT issuance/verification, password hashing, and the RBAC dependencies every
protected route uses. This is the ONE place role/org/case-assignment checks
happen — per SYSTEM_DESIGN.md's B2B multi-tenant overlay, don't reinvent
this per-endpoint.
"""

import base64
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import struct
import time
from typing import Optional
from uuid import UUID, uuid4

import bcrypt
from fastapi import Depends, HTTPException, status
from fastapi.security import APIKeyHeader, OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app import models

# auto_error=False on both schemes: get_current_claims branches on whichever
# credential is actually present (Bearer JWT for humans in the browser, an
# X-API-Key header for programmatic clients) instead of letting the OAuth2
# scheme shortcut past the API-key branch with its own 401.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login", auto_error=False)
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

# Plain `bcrypt`, not passlib's CryptContext — passlib's bcrypt backend
# detection has a real, live incompatibility with recent bcrypt releases
# (its own internal self-test trips bcrypt's 72-byte limit check and raises).
# This system only ever needs bcrypt, never passlib's multi-scheme support,
# so calling bcrypt directly removes the dependency conflict entirely rather
# than pinning around it.
_BCRYPT_MAX_BYTES = 72  # bcrypt's own hard limit — truncate rather than error

DISALLOWED_WEAK_PASSWORDS = {
    "password", "password123", "admin123", "12345678", "qwerty123", "letmein123"
}


def validate_password_strength(password: str) -> None:
    """Validates that a password satisfies minimum complexity requirements (NIST SP 800-63B).
    Raises HTTPException(422) if the password is too weak.
    """
    if not password or len(password) < 8:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Password must be at least 8 characters long."
        )
    if len(password) > 128:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Password must not exceed 128 characters."
        )
    if password.lower() in DISALLOWED_WEAK_PASSWORDS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Password is too common and easily guessable."
        )
    has_letter = any(c.isalpha() for c in password)
    has_digit_or_special = any(c.isdigit() or not c.isalnum() for c in password)
    if not (has_letter and has_digit_or_special):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Password must contain at least one letter and at least one number or special character."
        )


def get_user_mfa_secret(user_id: str, email: str, jwt_secret: str = settings.JWT_SECRET) -> str:
    """Derives a deterministic, high-entropy 160-bit base32 TOTP secret for a user
    using HMAC-SHA256, eliminating the need for a separate database secret column.
    """
    secret_bytes = hmac.new(
        jwt_secret.encode("utf-8"),
        f"legadoc:mfa:{user_id}:{email}".encode("utf-8"),
        hashlib.sha256
    ).digest()[:20]
    return base64.b32encode(secret_bytes).decode("utf-8")


def generate_totp_code(secret: str, interval: int = 30) -> str:
    """Generates a standard 6-digit TOTP code per RFC 6238."""
    secret_bytes = base64.b32decode(secret.upper() + "=" * ((8 - len(secret) % 8) % 8))
    counter = int(time.time() // interval)
    msg = struct.pack(">Q", counter)
    digest = hmac.new(secret_bytes, msg, hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    code_int = struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF
    return f"{code_int % 1000000:06d}"


def verify_totp_code(secret: str, code: str, interval: int = 30, window: int = 1) -> bool:
    """Verifies a 6-digit TOTP code against a secret with +/- window steps."""
    if not code or not secret:
        return False
    clean_code = code.strip()
    try:
        secret_bytes = base64.b32decode(secret.upper() + "=" * ((8 - len(secret) % 8) % 8))
    except Exception:
        secret_bytes = secret.encode("utf-8")

    current_step = int(time.time() // interval)
    for step in range(current_step - window, current_step + window + 1):
        msg = struct.pack(">Q", step)
        digest = hmac.new(secret_bytes, msg, hashlib.sha1).digest()
        offset = digest[-1] & 0x0F
        code_int = struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF
        expected = f"{code_int % 1000000:06d}"
        if hmac.compare_digest(expected, clean_code):
            return True
    return False


def _prepare(plain: str) -> bytes:
    return plain.encode("utf-8")[:_BCRYPT_MAX_BYTES]


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(_prepare(plain), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(_prepare(plain), hashed.encode("utf-8"))
    except ValueError:
        return False


# Computed once at import time, not hand-typed — a hand-typed "fake bcrypt
# string" is exactly the kind of fabricated-looking constant that's either
# invalid or silently wrong. Checking an unknown email against this (instead
# of skipping the check entirely) makes "no such officer" and "wrong
# password" take the same amount of time — see SYSTEM_DESIGN.md,
# "Constant-time login". No real password corresponds to it.
DUMMY_HASH = hash_password("no-such-user-timing-placeholder")


def dummy_password_check(plain: str) -> None:
    """Burns the same time a real bcrypt check would, for an email that
    doesn't exist. The result is discarded — this call exists only for its
    timing, not its answer."""
    verify_password(plain, DUMMY_HASH)


def hash_api_key(plain: str) -> str:
    """SHA-256 of the raw key — the only form ever persisted. The keys are
    256-bit random values (see admin.create_api_key), so SHA-256 is the right
    tool here: fast, collision-resistant, and not subject to bcrypt's 72-byte
    input truncation. bcrypt stays for passwords, where attackers reuse weak
    passphrases and need the salt+work-factor."""
    return hashlib.sha256(plain.encode("utf-8")).hexdigest()


def _create_token(user_id: str, org_id: str, role: str, expires_delta: timedelta, token_type: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "org_id": org_id,
        "role": role,
        "type": token_type,
        "iat": now,
        "exp": now + expires_delta,
        # Unique per issuance — this is the identifier the planned Redis JTI
        # denylist (see SYSTEM_DESIGN.md, token revocation LATER item) would
        # key off. Also means two tokens issued in the same second are never
        # byte-identical, which matters for e.g. an audit trail distinguishing them.
        "jti": uuid4().hex,
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def create_access_token(user_id: str, org_id: str, role: str) -> str:
    return _create_token(user_id, org_id, role, timedelta(minutes=settings.JWT_EXPIRE_MINUTES), "access")


def create_refresh_token(user_id: str, org_id: str, role: str) -> str:
    return _create_token(user_id, org_id, role, timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS), "refresh")


def decode_token(token: str, expected_type: str = "access") -> dict:
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")
    if payload.get("type") != expected_type:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"Expected a {expected_type} token")
    return payload


def _as_utc(dt: datetime) -> datetime:
    """Normalize a possibly-naive stored datetime to a tz-aware UTC datetime.
    Both SQLite and Postgres round-trip naive datetimes; timestamps are always
    written as UTC (see audit.py), so attaching UTC is always correct."""
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def _api_key_claims(raw_key: str, db: Session) -> dict:
    """Resolves an X-API-Key header to the same claims dict a JWT would carry.
    The key acts as its owning user: {sub, org_id, role, type} feed straight
    into require_role, get_current_user, and the org/case scoping checks with
    zero router changes. Every failure mode is a generic 401 — never reveal
    whether the key was unknown, revoked, expired, or its owner vanished."""
    row = db.query(models.ApiKey).filter(models.ApiKey.key_hash == hash_api_key(raw_key)).first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")

    now = datetime.now(timezone.utc)
    if row.revoked_at is not None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")
    if row.expires_at is not None and _as_utc(row.expires_at) < now:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")

    user = db.get(models.User, row.user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")

    row.last_used_at = now
    db.commit()

    return {
        "sub": str(user.id),
        "org_id": str(user.org_id),
        "role": user.role,
        "type": "api-key",
    }


def get_current_claims(
    token: Optional[str] = Depends(oauth2_scheme),
    api_key: Optional[str] = Depends(api_key_header),
    db: Session = Depends(get_db),
) -> dict:
    """Every protected endpoint depends on this (directly or via require_role).

    Two credentials are accepted, both resolving to the same claims shape:
    - Authorization: Bearer <JWT>  — human sessions from the auth routers
    - X-API-Key: <key>            — user-bound programmatic keys (see ApiKey)
    An X-API-Key takes precedence if both are sent."""
    if api_key:
        return _api_key_claims(api_key, db)
    if token:
        return decode_token(token, expected_type="access")
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")


def get_current_user(claims: dict = Depends(get_current_claims), db: Session = Depends(get_db)) -> models.User:
    """Loads the actual User row — needed for anything that checks case
    assignment or other DB-backed relationships, not just the role string."""
    user = db.get(models.User, UUID(claims["sub"]))
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User no longer exists")
    return user


def require_role(*allowed_roles: str):
    """FastAPI dependency factory: Depends(require_role("sho", "config_admin")).
    Org-scoping (does this claim's org_id match the resource being touched) is
    each router's own responsibility on top of this — role alone isn't enough
    for anything that reads/writes a specific case or org's data.
    """

    def _check(claims: dict = Depends(get_current_claims)) -> dict:
        if claims.get("role") not in allowed_roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Role not permitted for this action")
        return claims

    return _check


# Roles that see every case regardless of assignment — see SYSTEM_DESIGN.md's
# Access Model. Everyone else (IO, specifically) must have a CaseAssignment
# row for this exact case, or a Court order that touches it.
_UNRESTRICTED_CASE_ROLES = {"config_admin", "security_auditor", "court", "prosecutor", "sho"}

_POLICE_SPECIALIST_ROLES = {
    "duty_officer",
    "women_cell",
    "cyber_cell",
    "narcotics_police",
    "traffic_police",
    "crime_scene_unit",
    "rescue_team",
    "counselor",
}

# Roles that see a document's full, unredacted text once they already have
# case access — everyone else gets the AI-Parser-tagged spans masked. This
# is a baseline simplification of the Access Model's real nuance (Duty
# Officer is actually restricted to FIR-registration fields only; External
# Authority is restricted to their own routed request) — full per-role,
# per-doc-type scoping is real future work, not built in this slice.
FULL_TEXT_ACCESS_ROLES = _UNRESTRICTED_CASE_ROLES | {"io"}


def assert_case_access(case_id, claims: dict, db: Session) -> None:
    """The plain (non-Depends) version — call this directly from a route
    that doesn't have case_id as a path parameter (e.g. a multipart upload
    where case_id arrives as a form field). Raises HTTPException; returns
    nothing on success.

    Closes the CRITICAL finding: role-only authorization let any IO browse
    any case, including sensitive ones with no connection to their actual
    assignment. An IO must have a CaseAssignment row for this case_id, or
    this raises 403 — cross-case reads must never silently succeed.
    """
    role = claims.get("role")
    if role in _UNRESTRICTED_CASE_ROLES:
        return
    if role in (_POLICE_SPECIALIST_ROLES | {"io"}):
        user_id = UUID(claims["sub"])
        try:
            case_uuid = case_id if isinstance(case_id, UUID) else UUID(str(case_id))
        except ValueError:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")
        assigned = (
            db.query(models.CaseAssignment)
            .filter(models.CaseAssignment.case_id == case_uuid, models.CaseAssignment.io_user_id == user_id)
            .first()
        )
        if assigned is None:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not assigned to this case")
        return
    # Every other role (Defense, external authorities, etc.) reaches this
    # check only from endpoints that shouldn't be granting general case
    # access in the first place — deny by default rather than silently allow.
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Role not permitted to read case files directly")


def verify_case_access(case_id: str, claims: dict = Depends(get_current_claims), db: Session = Depends(get_db)) -> dict:
    """FastAPI dependency wrapper for routes where case_id IS a path
    parameter, e.g. GET /cases/:id. See assert_case_access for the logic and
    for routes that need this check but don't have case_id in the path."""
    assert_case_access(case_id, claims, db)
    return claims


def verify_evidence_request_org_access(
    request_id,
    claims: dict,
    db: Session,
) -> models.EvidenceRequest:
    """Validates that external authorities (FSL, Hospital, Bank, etc.) only touch
    evidence requests specifically routed to their organization (Domain 2-4 scoping).
    Ready for wiring into api/app/routers/evidence_requests.py as endpoints are
    implemented from their current 501 stubs."""
    try:
        req_uuid = request_id if isinstance(request_id, UUID) else UUID(str(request_id))
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Evidence request not found")

    req = db.get(models.EvidenceRequest, req_uuid)
    if req is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Evidence request not found")

    role = claims.get("role", "")
    user_org_id = claims.get("org_id", "")

    if role in ("config_admin", "security_auditor"):
        return req

    if role == "authority_staff":
        if str(req.requested_org_id) != str(user_org_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access restricted: this evidence request is routed to a different organization",
            )
        return req

    # Default-deny: only the target authority organization (or oversight roles) can fulfill/touch evidence requests
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Role not permitted to fulfill or access external evidence requests",
    )

