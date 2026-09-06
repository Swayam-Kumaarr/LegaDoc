-- Apply once to existing PostgreSQL environments before deploying the
-- API-key management feature. New databases receive this table from models.
CREATE TABLE IF NOT EXISTS api_keys (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users(id),
    name VARCHAR NOT NULL,
    key_hash VARCHAR NOT NULL UNIQUE,
    key_prefix VARCHAR NOT NULL,
    created_by_user_id UUID NOT NULL REFERENCES users(id),
    created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
    last_used_at TIMESTAMPTZ,
    expires_at TIMESTAMPTZ,
    revoked_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS ix_api_keys_user_id ON api_keys(user_id);
