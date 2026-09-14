"""The startup guard in app/config.py: a deployment must not run with the
credentials that are published in this repository."""

import pytest
from pydantic import ValidationError

from app.config import Settings

STRONG = {
    "JWT_SECRET": "a" * 64,
    "OBJECT_STORAGE_SECRET_KEY": "a-real-minio-secret",
    "DATABASE_URL": "postgresql://postgres:a-real-password@db:5432/legadoc",
}


@pytest.mark.parametrize("env", ["local", "dev", "test", "TEST"])
def test_dev_environments_accept_the_defaults(env):
    Settings(ENV=env)  # must not raise — local setup works with zero configuration


def test_production_with_every_default_is_refused_and_names_each_problem():
    with pytest.raises(ValidationError) as exc:
        Settings(ENV="production")
    message = str(exc.value)
    assert "JWT_SECRET" in message
    assert "OBJECT_STORAGE_SECRET_KEY" in message
    assert "DATABASE_URL" in message


@pytest.mark.parametrize("field,bad", [
    ("JWT_SECRET", "change-me-in-every-env-except-local"),
    ("JWT_SECRET", "too-short"),
    ("OBJECT_STORAGE_SECRET_KEY", "minioadmin"),
    ("DATABASE_URL", "postgresql://postgres:postgres@db:5432/legadoc"),
])
def test_any_single_public_default_is_refused(field, bad):
    with pytest.raises(ValidationError):
        Settings(ENV="staging", **{**STRONG, field: bad})


def test_production_with_real_secrets_starts():
    s = Settings(ENV="production", **STRONG)
    assert s.ENV == "production"
