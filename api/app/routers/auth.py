"""
Auth Router — login, session/JWT issuance, and profile resolution.
See SYSTEM_DESIGN.md Interface Contracts, "Endpoint Table" (POST /auth/login).
"""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.schemas.auth import LoginRequest, TokenResponse, UserResponse
from app.security import (
    create_access_token,
    get_current_user,
    verify_password,
)

router = APIRouter(prefix="/auth", tags=["auth"])

# Dummy hash for constant-time comparison when email is not found (prevents user enumeration via timing)
DUMMY_HASH = "$2b$12$e80MvQk6d1r1mF9h31zE4u7nI/YpYIuHkW/Q0WnB0XkK.qH1w3e.e"


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="User Login",
    description="Authenticates with email and password, returning a signed JWT with role and org claims.",
)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    """
    POST /auth/login — Public. Authenticates user and issues JWT.
    
    Security controls:
    - Timing attack safe: constant-time password verification even if user does not exist.
    - Information leakage safe: generic 401 error message regardless of whether email was found.
    - Password is never logged or included in response.
    """
    user = db.query(User).filter(User.email == payload.email).first()

    if not user:
        # Perform dummy verify to simulate constant-time execution
        verify_password(payload.password, DUMMY_HASH)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not verify_password(payload.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token = create_access_token(
        user_id=user.id,
        org_id=user.org_id,
        role=user.role,
        name=user.name,
    )

    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        user_id=user.id,
        org_id=user.org_id,
        role=user.role,
        name=user.name,
    )


@router.get(
    "/me",
    response_model=UserResponse,
    summary="Current User Profile",
    description="Returns the authenticated user's profile details.",
)
def get_me(current_user: User = Depends(get_current_user)):
    """GET /auth/me — Returns the profile of the currently authenticated user."""
    return current_user
