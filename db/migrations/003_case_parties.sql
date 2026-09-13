-- Apply once to existing PostgreSQL environments before deploying the
-- defence-engagement scoping. New databases receive this table from models.
--
-- Links a non-police participant (today: a defence advocate) to a case.
-- Deliberately NOT CaseAssignment, which means "the current IO" and is
-- deleted wholesale by reassign_io — an engagement must survive a police
-- reassignment. See issue #70.
CREATE TABLE IF NOT EXISTS case_parties (
    id UUID PRIMARY KEY,
    case_id UUID NOT NULL REFERENCES cases(id),
    user_id UUID NOT NULL REFERENCES users(id),
    party_role VARCHAR NOT NULL,
    recorded_by_user_id UUID NOT NULL REFERENCES users(id),
    created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
    CONSTRAINT uq_case_party UNIQUE (case_id, user_id, party_role)
);

-- Scoping reads this on every GET /cases for a defence account, and on
-- every assert_case_access for that role.
CREATE INDEX IF NOT EXISTS ix_case_parties_user_role ON case_parties(user_id, party_role);
CREATE INDEX IF NOT EXISTS ix_case_parties_case ON case_parties(case_id);
