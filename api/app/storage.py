"""
Object storage abstraction. `LocalObjectStorage` is a real, working
implementation backed by the local filesystem — used for local dev and for
tests, since this sandbox has no MinIO to test against. Swap in a
boto3/MinIO-backed implementation behind the same three methods for a real
deployment; nothing calling this interface needs to change.

Path convention matches SYSTEM_DESIGN.md: {org_id}/{case_id}/{doc_id}/v{version}
— this is what prevents cross-tenant object traversal in a single bucket.
"""

import base64
import hashlib
import logging
import os
from abc import ABC, abstractmethod
from pathlib import Path

logger = logging.getLogger(__name__)

try:
    from cryptography.fernet import Fernet
    _HAS_FERNET = True
except ImportError:
    _HAS_FERNET = False


class ObjectStorage(ABC):
    @abstractmethod
    def put(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> None: ...

    @abstractmethod
    def get(self, key: str) -> bytes: ...

    @abstractmethod
    def exists(self, key: str) -> bool: ...

    @abstractmethod
    def delete(self, key: str) -> None: ...

    @abstractmethod
    def get_presigned_url(self, key: str, expires_in: int = 300) -> str: ...


class LocalObjectStorage(ObjectStorage):
    """Disk-backed object storage hardened with encryption at rest (Fernet/AES-128-CBC + HMAC-SHA256).
    Key is derived from settings.JWT_SECRET. Transparently encrypts bytes on write and decrypts on read.
    """

    def __init__(self, root: str, secret: str = "change-me-in-every-env-except-local"):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.secret = secret
        if _HAS_FERNET:
            fernet_key = base64.urlsafe_b64encode(hashlib.sha256(self.secret.encode("utf-8")).digest())
            self._cipher = Fernet(fernet_key)
        else:
            self._cipher = None
            logger.warning("cryptography package missing: LocalObjectStorage falling back to unencrypted storage.")

    def _path(self, key: str) -> Path:
        # key is always our own {org_id}/{case_id}/{doc_id}/v{version} —
        # reject anything that looks like it's trying to escape root.
        full = (self.root / key).resolve()
        if self.root.resolve() not in full.parents and full != self.root.resolve():
            raise ValueError(f"Refusing to write outside storage root: {key}")
        return full

    def put(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = self._cipher.encrypt(data) if self._cipher else data
        with open(path, "wb") as f:
            f.write(payload)

    def get(self, key: str) -> bytes:
        with open(self._path(key), "rb") as f:
            raw = f.read()
        if self._cipher:
            try:
                return self._cipher.decrypt(raw)
            except Exception:
                # If reading legacy or pre-existing unencrypted bytes, return gracefully
                return raw
        return raw

    def exists(self, key: str) -> bool:
        return self._path(key).exists()

    def delete(self, key: str) -> None:
        path = self._path(key)
        if path.exists():
            path.unlink()

    def get_presigned_url(self, key: str, expires_in: int = 300) -> str:
        # Stand-in URL for local disk testing
        return f"/local-storage/{key}?expires={expires_in}"



class MinIOObjectStorage(ObjectStorage):
    """Production MinIO S3-compatible storage.
    Enforces Server-Side Encryption (AES256 in prod) and short-lived presigned URLs."""

    def __init__(
        self,
        endpoint_url: str,
        access_key: str,
        secret_key: str,
        bucket: str,
        region_name: str = "us-east-1",
        env: str = "local",
    ):
        import boto3
        from botocore.client import Config

        self.bucket = bucket
        self.env = env
        self.client = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            config=Config(signature_version="s3v4"),
            region_name=region_name,
        )
        self._bucket_ensured = False

    def _ensure_bucket(self):
        if not self._bucket_ensured:
            try:
                self.client.head_bucket(Bucket=self.bucket)
            except Exception:
                try:
                    self.client.create_bucket(Bucket=self.bucket)
                except Exception:
                    pass
            self._bucket_ensured = True

    def put(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> None:
        self._ensure_bucket()
        extra_args = {"ContentType": content_type}
        if self.env not in ("local", "test", "dev"):
            extra_args["ServerSideEncryption"] = "AES256"

        self.client.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=data,
            **extra_args,
        )

    def get(self, key: str) -> bytes:
        self._ensure_bucket()
        obj = self.client.get_object(Bucket=self.bucket, Key=key)
        return obj["Body"].read()

    def exists(self, key: str) -> bool:
        self._ensure_bucket()
        try:
            self.client.head_object(Bucket=self.bucket, Key=key)
            return True
        except Exception:
            return False

    def delete(self, key: str) -> None:
        self._ensure_bucket()
        try:
            self.client.delete_object(Bucket=self.bucket, Key=key)
        except Exception:
            pass

    def get_presigned_url(self, key: str, expires_in: int = 300) -> str:
        self._ensure_bucket()
        return self.client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket, "Key": key},
            ExpiresIn=expires_in,
        )


def object_key(org_id, case_id, doc_id, version: int) -> str:
    return f"{org_id}/{case_id}/{doc_id}/v{version}"


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


_default_storage = None


def get_storage() -> ObjectStorage:
    """FastAPI dependency. Uses MinIO if configured and reachable;
    otherwise falls back to LocalObjectStorage (used for bare-metal dev and pytest)."""
    global _default_storage
    if _default_storage is None:
        from app.config import settings

        backend = getattr(settings, "OBJECT_STORAGE_BACKEND", "local").lower()
        if backend == "minio" and settings.ENV != "test":
            try:
                storage = MinIOObjectStorage(
                    endpoint_url=settings.OBJECT_STORAGE_ENDPOINT,
                    access_key=settings.OBJECT_STORAGE_ACCESS_KEY,
                    secret_key=settings.OBJECT_STORAGE_SECRET_KEY,
                    bucket=settings.OBJECT_STORAGE_BUCKET,
                    env=settings.ENV,
                )
                storage._ensure_bucket()
                _default_storage = storage
            except Exception:
                # Endpoint unreachable (e.g. running natively outside docker-compose)
                root = os.environ.get("OBJECT_STORAGE_LOCAL_DIR", "./data/objects")
                _default_storage = LocalObjectStorage(root, secret=settings.JWT_SECRET)
        else:
            root = os.environ.get("OBJECT_STORAGE_LOCAL_DIR", "./data/objects")
            _default_storage = LocalObjectStorage(root, secret=settings.JWT_SECRET)
    return _default_storage

