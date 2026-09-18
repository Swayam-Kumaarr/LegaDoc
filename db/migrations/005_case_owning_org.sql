-- Apply once to existing PostgreSQL environments. New databases receive
-- these columns from models. See issue #74.
--
-- Records which station owns a case and which officer registered it.
-- Both nullable: a case with no fir_registered audit row cannot be
-- attributed, and is left NULL rather than guessed.
ALTER TABLE cases ADD COLUMN IF NOT EXISTS org_id UUID REFERENCES organizations(id);
ALTER TABLE cases ADD COLUMN IF NOT EXISTS registered_by_user_id UUID REFERENCES users(id);
CREATE INDEX IF NOT EXISTS ix_cases_org_id ON cases(org_id);

-- Backfill from the audit trail. Only fills rows still NULL, so re-running
-- is harmless. If a case somehow has several fir_registered rows, the
-- earliest one is the registration.
UPDATE cases c
SET registered_by_user_id = src.actor_user_id,
    org_id = u.org_id
FROM (
    SELECT DISTINCT ON (case_id) case_id, actor_user_id
    FROM audit_log
    WHERE action = 'fir_registered' AND case_id IS NOT NULL AND actor_user_id IS NOT NULL
    ORDER BY case_id, seq
) src
JOIN users u ON u.id = src.actor_user_id
WHERE c.id = src.case_id
  AND c.registered_by_user_id IS NULL;
