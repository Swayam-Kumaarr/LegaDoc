"""
Auth & User Pydantic schemas.
"""

from datetime import datetime
from typing import Optional
from uuid import UUID
from pydantic import BaseModel


class LoginRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: UUID
    org_id: UUID
    role: str
    name: str


class UserClaims(BaseModel):
    sub: str  # user_id
    org_id: str
    role: str
    name: Optional[str] = None
    exp: Optional[int] = None


class UserResponse(BaseModel):
    id: UUID
    org_id: UUID
    role: str
    name: str
    email: str
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True
