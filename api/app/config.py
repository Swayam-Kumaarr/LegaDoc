"""
Central config, read from environment variables. See .env.example at the repo root
for every variable this expects. Nothing here should ever hold a real secret —
production values come from a secrets manager (see SYSTEM_DESIGN.md, "Key management").
"""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Core service
    ENV: str = "local"
    # Must be a 256-bit high-entropy value in every real env — never reuse
    # the local default. A short access-token TTL is the actual revocation
    # mechanism here; pair it with a longer-lived refresh token rather than
    # extending this.
    JWT_SECRET: str = "change-me-in-every-env-except-local"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    # A compromised access token still works until it expires unless you
    # check it against a denylist. TODO once real auth is built: on
    # logout/suspected-compromise, write the token's JTI to this Redis set
    # with a TTL matching its remaining lifetime; reject any token whose JTI
    # is present. Skipped for the baseline since a 15-min TTL alone already
    # bounds the damage window.
    TOKEN_REVOCATION_REDIS_DB: int = 2
    LOGIN_RATE_LIMIT: str = "10/minute"  # per IP, on /auth/login specifically
    AUDIT_LOG_AI_PARSER_RATE_LIMIT: str = "20/minute"  # per user — the most sensitive read path in the system

    # Database
    DATABASE_URL: str = "postgresql://postgres:postgres@db:5432/legadoc"

    # Object storage (MinIO / S3-compatible, or disk-backed local for bare-metal dev)
    OBJECT_STORAGE_BACKEND: str = "local"
    OBJECT_STORAGE_ENDPOINT: str = "http://minio:9000"
    OBJECT_STORAGE_ACCESS_KEY: str = "minioadmin"
    OBJECT_STORAGE_SECRET_KEY: str = "minioadmin"
    OBJECT_STORAGE_BUCKET: str = "legadoc-documents"

    # Upload & Ingestion Controls
    MAX_UPLOAD_SIZE_MB: int = 50
    UPLOAD_ALLOWED_ROLES: str = "io,sho,duty_officer,authority_staff,config_admin"

    # CORS configuration (Issue #43)
    # Comma-separated or list of allowed frontend origins. Never allows wildcard (*).
    CORS_ORIGINS: str = "http://localhost:5173,http://127.0.0.1:5173"

    @property
    def cors_origins_list(self) -> list[str]:
        """Parsed list of allowed origins. Rejects wildcards to prevent credential leak."""
        raw = [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]
        if "*" in raw:
            raise ValueError(
                "Wildcard origin ('*') is strictly forbidden when allow_credentials=True. "
                "Specify exact origins in CORS_ORIGINS."
            )
        return raw or ["http://localhost:5173", "http://127.0.0.1:5173"]


    # Queue
    CELERY_BROKER_URL: str = "redis://redis:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://redis:6379/1"

    # Hyperledger Fabric (Chain Worker reads these, not the API directly)
    FABRIC_CONNECTION_PROFILE: str = "/fabric-network/connection-profile.json"
    FABRIC_MSP_ID: str = "PoliceMSP"

    class Config:
        env_file = ".env"


settings = Settings()
