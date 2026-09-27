-- Apply once to existing PostgreSQL environments. New databases receive this
-- table from models.
--
-- The redaction blueprint: per role, per document type, per entity type,
-- what a restricted reader sees. With no rows present every tagged span is
-- masked, which is exactly how redaction behaved before this table existed —
-- so an environment that never configures a policy is unchanged.
CREATE TABLE IF NOT EXISTS redaction_policies (
    id UUID PRIMARY KEY,
    role VARCHAR NOT NULL,
    doc_type VARCHAR NOT NULL DEFAULT '*',
    entity_type VARCHAR NOT NULL,
    action VARCHAR NOT NULL DEFAULT 'mask',
    min_confidence INTEGER NOT NULL DEFAULT 0,
    updated_by_user_id UUID REFERENCES users(id),
    updated_at TIMESTAMPTZ DEFAULT now(),
    CONSTRAINT uq_redaction_policy_scope UNIQUE (role, doc_type, entity_type)
);
