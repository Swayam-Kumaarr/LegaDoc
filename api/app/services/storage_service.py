"""
Storage Service — MinIO / S3-compatible object storage operations.
See SYSTEM_DESIGN.md:
- Flow 2 (Document Upload → MinIO)
- Container Diagram connection #4 (API -> Object Storage)
- Org-scoped paths: {org_id}/{case_id}/{document_id}/v{version}
- Server-Side Encryption (AES256) at rest
"""

from typing import Any, BinaryIO, Dict, Optional
from uuid import UUID
import boto3
from botocore.client import Config
from botocore.exceptions import ClientError

from app.config import settings


class StorageService:
    """Handles object storage uploads, downloads, and presigned URLs."""

    def __init__(self):
        self._client = None
        self._bucket_verified = False

    @property
    def client(self):
        """Lazy initialization of boto3 S3 client."""
        if self._client is None:
            self._client = boto3.client(
                "s3",
                endpoint_url=settings.OBJECT_STORAGE_ENDPOINT,
                aws_access_key_id=settings.OBJECT_STORAGE_ACCESS_KEY,
                aws_secret_access_key=settings.OBJECT_STORAGE_SECRET_KEY,
                config=Config(signature_version="s3v4"),
                region_name="us-east-1",
            )
        return self._client

    def ensure_bucket(self) -> None:
        """Ensures the storage bucket exists with private ACL."""
        if self._bucket_verified:
            return

        try:
            self.client.head_bucket(Bucket=settings.OBJECT_STORAGE_BUCKET)
            self._bucket_verified = True
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code")
            if error_code in ("404", "NoSuchBucket"):
                self.client.create_bucket(Bucket=settings.OBJECT_STORAGE_BUCKET)
                self._bucket_verified = True
            else:
                raise

    @staticmethod
    def build_storage_path(
        org_id: str | UUID,
        case_id: str | UUID,
        document_id: str | UUID,
        version: int = 1,
    ) -> str:
        """
        Builds org-scoped storage path:
        {org_id}/{case_id}/{document_id}/v{version}
        """
        return f"{str(org_id)}/{str(case_id)}/{str(document_id)}/v{version}"

    def upload_file(
        self,
        file_obj: BinaryIO,
        storage_path: str,
        content_type: str = "application/octet-stream",
    ) -> Dict[str, Any]:
        """
        Uploads a seekable binary file object to MinIO.
        Enforces Server-Side Encryption (AES256).
        """
        self.ensure_bucket()
        extra_args = {"ContentType": content_type}

        # Server-side encryption (AES256) is enforced in production/staging environments
        # where KMS is configured. Local MinIO runs in dev mode without KMS.
        if settings.ENV not in ("local", "test", "dev"):
            extra_args["ServerSideEncryption"] = "AES256"

        self.client.upload_fileobj(
            file_obj,
            settings.OBJECT_STORAGE_BUCKET,
            storage_path,
            ExtraArgs=extra_args,
        )

        return {
            "bucket": settings.OBJECT_STORAGE_BUCKET,
            "storage_path": storage_path,
        }

    def get_presigned_url(self, storage_path: str, expires_in: int = 300) -> str:
        """Generates a short-lived presigned GET URL for secure document download."""
        self.ensure_bucket()
        return self.client.generate_presigned_url(
            "get_object",
            Params={
                "Bucket": settings.OBJECT_STORAGE_BUCKET,
                "Key": storage_path,
            },
            ExpiresIn=expires_in,
        )

    def delete_file(self, storage_path: str) -> bool:
        """Deletes an object from MinIO."""
        try:
            self.client.delete_object(
                Bucket=settings.OBJECT_STORAGE_BUCKET,
                Key=storage_path,
            )
            return True
        except ClientError:
            return False


# Singleton instance
storage_service = StorageService()
