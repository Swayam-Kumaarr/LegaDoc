"""
Shared test fixtures. Uses an in-memory SQLite DB (via the GUID cross-dialect
type in app/db_types.py) so this suite runs with no Postgres, no Docker, no
external services at all — exactly what makes it runnable anywhere, including
before the rest of the infra exists.
"""

import os
import sys

_api_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _api_dir not in sys.path:
    sys.path.insert(0, _api_dir)

os.environ["ENV"] = "test"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import settings
settings.ENV = "test"

from app.database import Base, get_db
from app.main import app
from app import models, security
from app.queue import InMemoryQueueClient, get_queue
from app.storage import LocalObjectStorage, get_storage

TEST_ENGINE = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=TEST_ENGINE)


@pytest.fixture(autouse=True)
def _fresh_schema():
    """Recreate every table before each test — cheap at this data size, and
    it means no test can leak state into another."""
    Base.metadata.create_all(bind=TEST_ENGINE)
    yield
    Base.metadata.drop_all(bind=TEST_ENGINE)


@pytest.fixture(autouse=True)
def _reset_rate_limiters():
    """Reset singleton sliding-window rate limiters before and after each test."""
    from app.rate_limit import login_rate_limiter, ai_parser_limiter
    login_rate_limiter.reset()
    ai_parser_limiter.reset()
    yield
    login_rate_limiter.reset()
    ai_parser_limiter.reset()


@pytest.fixture
def db_session():
    session = TestSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def fake_queue():
    return InMemoryQueueClient()


@pytest.fixture
def client(db_session, fake_queue, tmp_path):
    def _override_get_db():
        yield db_session

    test_storage = LocalObjectStorage(str(tmp_path / "objects"))

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_queue] = lambda: fake_queue
    app.dependency_overrides[get_storage] = lambda: test_storage
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def make_org(db_session):
    def _make(name="Test Police Station", org_type="police"):
        org = models.Organization(name=name, org_type=org_type)
        db_session.add(org)
        db_session.commit()
        db_session.refresh(org)
        return org

    return _make


@pytest.fixture
def make_user(db_session, make_org):
    def _make(role, email=None, password="correct-horse-battery-staple", org=None):
        org = org or make_org()
        email = email or f"{role}@example.com"
        user = models.User(
            org_id=org.id,
            role=role,
            name=role.replace("_", " ").title(),
            email=email,
            hashed_password=security.hash_password(password),
        )
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)
        return user

    return _make


def login(client, email, password="correct-horse-battery-staple", mfa_code=None):
    payload = {"email": email, "password": password}
    if mfa_code is not None:
        payload["mfa_code"] = mfa_code
    resp = client.post("/auth/login", json=payload)
    return resp


def auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}
