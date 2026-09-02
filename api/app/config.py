"""
Central config, read from environment variables. See .env.example at the repo root
for every variable this expects. Nothing here should ever hold a real secret —
production values come from a secrets manager (see SYSTEM_DESIGN.md, "Key management").
"""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Core service
    ENV: str = "local"
    JWT_SECRET: str = "change-me-in-every-env-except-local"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 30

    # Database
    DATABASE_URL: str = "postgresql://postgres:postgres@db:5432/legadoc"

    # Object storage (MinIO / S3-compatible)
    OBJECT_STORAGE_ENDPOINT: str = "http://minio:9000"
    OBJECT_STORAGE_ACCESS_KEY: str = "minioadmin"
    OBJECT_STORAGE_SECRET_KEY: str = "minioadmin"
    OBJECT_STORAGE_BUCKET: str = "legadoc-documents"

    # Upload & Ingestion Controls
    MAX_UPLOAD_SIZE_MB: int = 50
    UPLOAD_ALLOWED_ROLES: str = "io,sho,duty_officer,authority_staff,admin"

    # Queue
    CELERY_BROKER_URL: str = "redis://redis:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://redis:6379/1"

    # Hyperledger Fabric (Chain Worker reads these, not the API directly)
    FABRIC_CONNECTION_PROFILE: str = "/fabric-network/connection-profile.json"
    FABRIC_MSP_ID: str = "PoliceMSP"

    class Config:
        env_file = ".env"


settings = Settings()
