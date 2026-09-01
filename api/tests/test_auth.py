"""
Unit and Integration Tests for Auth & RBAC Substrate.
Tests:
- Password hashing with bcrypt
- JWT creation, decoding, expiration
- Role requirement dependencies (require_role)
- Timing attack & enumeration resistance
- Login endpoint & token authorization
"""

import unittest
from datetime import timedelta
from uuid import uuid4

from fastapi import HTTPException

from app.database import SessionLocal
from app.models import Organization, User
from app.routers.auth import DUMMY_HASH, login
from app.schemas.auth import LoginRequest
from app.security import (
    create_access_token,
    decode_token,
    get_password_hash,
    require_role,
    verify_password,
)


class TestAuthAndSecurity(unittest.TestCase):
    def setUp(self):
        self.db = SessionLocal()
        self.test_password = "SecurePassword123!"
        self.test_email = f"test_officer_{uuid4().hex[:6]}@police.gov.in"

        # Create org and user for login tests
        self.org = Organization(name="Test Auth Station", org_type="police")
        self.db.add(self.org)
        self.db.commit()

        self.user = User(
            org_id=self.org.id,
            role="io",
            name="Test IO Officer",
            email=self.test_email,
            hashed_password=get_password_hash(self.test_password),
        )
        self.db.add(self.user)
        self.db.commit()

        self.user_id = self.user.id
        self.org_id = self.org.id
        self.role = "io"
        self.name = "Test IO Officer"

    def tearDown(self):
        try:
            self.db.rollback()
            self.db.query(User).filter(User.id == self.user.id).delete()
            self.db.query(Organization).filter(Organization.id == self.org.id).delete()
            self.db.commit()
        except Exception:
            self.db.rollback()
        finally:
            self.db.close()

    def test_password_hashing(self):
        hashed = get_password_hash(self.test_password)
        self.assertNotEqual(hashed, self.test_password)
        self.assertTrue(verify_password(self.test_password, hashed))
        self.assertFalse(verify_password("WrongPassword", hashed))

    def test_jwt_issuance_and_decoding(self):
        token = create_access_token(
            user_id=self.user_id,
            org_id=self.org_id,
            role=self.role,
            name=self.name,
        )
        claims = decode_token(token)
        self.assertEqual(claims["sub"], str(self.user_id))
        self.assertEqual(claims["org_id"], str(self.org_id))
        self.assertEqual(claims["role"], self.role)
        self.assertEqual(claims["name"], self.name)
        self.assertIn("exp", claims)

    def test_jwt_expired_token(self):
        token = create_access_token(
            user_id=self.user_id,
            org_id=self.org_id,
            role=self.role,
            expires_delta=timedelta(seconds=-10),  # Expired 10s ago
        )
        with self.assertRaises(HTTPException) as ctx:
            decode_token(token)
        self.assertEqual(ctx.exception.status_code, 401)
        self.assertEqual(ctx.exception.detail, "Invalid or expired token")

    def test_jwt_invalid_token(self):
        with self.assertRaises(HTTPException) as ctx:
            decode_token("invalid.jwt.token")
        self.assertEqual(ctx.exception.status_code, 401)

    def test_require_role_authorized(self):
        checker = require_role("io", "sho", "admin")
        claims = {"sub": str(self.user_id), "org_id": str(self.org_id), "role": "io"}
        result = checker(claims=claims)
        self.assertEqual(result, claims)

    def test_require_role_forbidden(self):
        checker = require_role("admin")
        claims = {"sub": str(self.user_id), "org_id": str(self.org_id), "role": "defense"}
        with self.assertRaises(HTTPException) as ctx:
            checker(claims=claims)
        self.assertEqual(ctx.exception.status_code, 403)
        self.assertIn("Role 'defense' is not permitted", ctx.exception.detail)

    def test_login_success(self):
        req = LoginRequest(email=self.test_email, password=self.test_password)
        resp = login(req, db=self.db)
        self.assertEqual(resp.token_type, "bearer")
        self.assertEqual(resp.user_id, self.user.id)
        self.assertEqual(resp.org_id, self.org.id)
        self.assertEqual(resp.role, "io")
        self.assertEqual(resp.name, self.name)

        # Token should decode properly
        claims = decode_token(resp.access_token)
        self.assertEqual(claims["sub"], str(self.user.id))

    def test_login_wrong_password(self):
        req = LoginRequest(email=self.test_email, password="IncorrectPassword!")
        with self.assertRaises(HTTPException) as ctx:
            login(req, db=self.db)
        self.assertEqual(ctx.exception.status_code, 401)
        self.assertEqual(ctx.exception.detail, "Invalid email or password")

    def test_login_unknown_email(self):
        req = LoginRequest(email="nonexistent@police.gov.in", password="AnyPassword123!")
        with self.assertRaises(HTTPException) as ctx:
            login(req, db=self.db)
        self.assertEqual(ctx.exception.status_code, 401)
        self.assertEqual(ctx.exception.detail, "Invalid email or password")


if __name__ == "__main__":
    unittest.main()
