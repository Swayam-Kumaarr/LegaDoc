-- Apply once to existing PostgreSQL environments. New databases receive these
-- columns from models.
--
-- The instruction an investigating officer writes when raising a Section 91
-- requisition ("Examine the broken lock for tool marks") was accepted by the
-- API and written only into the audit log. The organisation receiving the
-- requisition — FSL, a bank, a telecom — saw a document type and a case
-- number, and never the request itself.
--
-- Nullable: requisitions raised before this change have no stored note, and
-- the audit row is the only record of what was asked. Nothing backfills them,
-- because the audit log's action_metadata is not a place to read application
-- state back out of — it is the tamper-evident record of what happened.
ALTER TABLE evidence_requests ADD COLUMN IF NOT EXISTS notes VARCHAR;
ALTER TABLE evidence_requests ADD COLUMN IF NOT EXISTS requested_by_user_id UUID REFERENCES users(id);
