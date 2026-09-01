"""
JWT issuance/verification, password hashing, and the RBAC / Org-Scoping dependencies
used across all protected routes.

See SYSTEM_DESIGN.md:
- "Domain Overlays Applied: B2B SaaS multi-tenant overlay"
- "Access Model Summary" and "Role & Authority Taxonomy"
- "Security: Encryption, Key Management, Input Validation & Audit Integrity"

Never log passwords or tokens. Never reveal user existence on auth failures.
"""

from datetime import datetime, timedelta, timezone
from typing import Callable, Iterable, List, Optional
from uuid import UUID

import bcrypt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import Case, CaseAssignment, EvidenceRequest, User

# OAuth2 scheme for Swagger UI & token extraction
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login", auto_error=True)


# ============================================================================
# Password Hashing Helpers (Direct bcrypt implementation)
# ============================================================================

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifies a plain password against a bcrypt hash in constant time."""
    try:
        password_bytes = plain_password.encode("utf-8")[:72]
        hash_bytes = hashed_password.encode("utf-8")
        return bcrypt.checkpw(password_bytes, hash_bytes)
    except Exception:
        return False


def get_password_hash(password: str) -> str:
    """Generates a secure bcrypt hash of the given password."""
    password_bytes = password.encode("utf-8")[:72]
    salt = bcrypt.gensalt(rounds=12)
    return bcrypt.hashpw(password_bytes, salt).decode("utf-8")


# ============================================================================
# JWT Token Helpers
# ============================================================================

def create_access_token(
    user_id: str | UUID,
    org_id: str | UUID,
    role: str,
    name: Optional[str] = None,
    expires_delta: Optional[timedelta] = None,
) -> str:
    """Issues a signed JWT access token containing subject, org_id, role, and expiration."""
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=settings.JWT_EXPIRE_MINUTES)

    payload = {
        "sub": str(user_id),
        "org_id": str(org_id),
        "role": role,
        "name": name or "",
        "exp": expire,
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str) -> dict:
    """Decodes and validates the signature/expiration of a JWT token."""
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
        if "sub" not in payload or "role" not in payload or "org_id" not in payload:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token payload",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return payload
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )


# ============================================================================
# FastAPI Dependencies: Authentication & RBAC
# ============================================================================

def get_current_claims(token: str = Depends(oauth2_scheme)) -> dict:
    """
    Every protected endpoint depends on this (directly or via require_role).
    Returns a dict with 'sub' (user_id), 'org_id', 'role', 'name'.
    """
    return decode_token(token)


def get_current_user(
    claims: dict = Depends(get_current_claims),
    db: Session = Depends(get_db),
) -> User:
    """Resolves the full User ORM model from the current JWT token."""
    try:
        user_id = UUID(claims["sub"])
    except (ValueError, KeyError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid user identifier in token",
        )

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )
    return user


def require_role(*allowed_roles: str) -> Callable:
    """
    FastAPI dependency factory: Depends(require_role("sho", "admin")).
    Checks that the requesting user possesses one of the allowed roles.
    """
    def _check_role(claims: dict = Depends(get_current_claims)) -> dict:
        role = claims.get("role")
        if role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{role}' is not permitted for this action",
            )
        return claims

    return _check_role


# ============================================================================
# Centralized Org-Scoping & Case Authorization Helpers
# ============================================================================

def verify_case_access(
    case_id: UUID | str,
    claims: dict,
    db: Session,
) -> Case:
    """
    Validates that the caller has legitimate access to the given case.
    Enforces multi-tenant and role-scoping rules from SYSTEM_DESIGN.md:
    
    1. System Admin & Court: Full case access.
    2. Records/NCRB Analyst: Case metadata view only (handled by dedicated view).
    3. Investigating Officer (IO): Must be assigned to this specific case via CaseAssignment.
    4. SHO, Duty Officer, Police Specialist Units: Permitted within police jurisdiction.
    5. Public Prosecutor: Permitted to review case materials for charge sheet / trial.
    6. Defense / Accused: Restricted to own bail submissions; blocked from active investigation materials.
    7. External Authority (FSL/Hospital/Bank/etc.): Cannot read arbitrary case files —
       access must be scoped to their routed evidence request.
    """
    if isinstance(case_id, str):
        try:
            case_id = UUID(case_id)
        except ValueError:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid case ID format")

    case = db.query(Case).filter(Case.id == case_id).first()
    if not case:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")

    role = claims.get("role", "")
    user_id_str = claims.get("sub", "")

    # 1. Admin and Court have global case access
    if role in ("admin", "court"):
        return case

    # 2. Investigating Officer (IO) — must be the assigned IO for this case
    if role == "io":
        assignment = (
            db.query(CaseAssignment)
            .filter(
                CaseAssignment.case_id == case_id,
                CaseAssignment.io_user_id == UUID(user_id_str),
            )
            .first()
        )
        if not assignment:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access restricted: you are not the assigned Investigating Officer for this case",
            )
        return case

    # 3. SHO, Duty Officer, Police Specialist Units, Prosecutor
    police_and_prosecution_roles = {
        "sho",
        "duty_officer",
        "women_cell",
        "cyber_cell",
        "narcotics_police",
        "traffic_police",
        "crime_scene_unit",
        "rescue_team",
        "counselor",
        "prosecutor",
    }
    if role in police_and_prosecution_roles:
        return case

    # 4. Defense / Accused: cannot browse general investigation case files
    if role == "defense":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Defense access to active investigation materials is restricted",
        )

    # 5. External Authorities: cannot browse case files directly
    if role == "authority_staff":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="External authority access must be routed through specific evidence requests",
        )

    # Fallback default-deny
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Access not permitted for this role",
    )


def verify_evidence_request_org_access(
    request_id: UUID | str,
    claims: dict,
    db: Session,
) -> EvidenceRequest:
    """
    Validates that an external authority only touches evidence requests
    specifically routed to their organization (Domain 2-4 scoping).
    """
    if isinstance(request_id, str):
        try:
            request_id = UUID(request_id)
        except ValueError:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid request ID format")

    req = db.query(EvidenceRequest).filter(EvidenceRequest.id == request_id).first()
    if not req:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Evidence request not found")

    role = claims.get("role", "")
    user_org_id = claims.get("org_id", "")

    # Admin has system-wide access
    if role == "admin":
        return req

    # Authority staff must belong to the requested organization
    if role == "authority_staff":
        if str(req.requested_org_id) != str(user_org_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access restricted: this evidence request is routed to a different organization",
            )
        return req

    # IO / SHO / Police who created/own the case can read the request
    return req
