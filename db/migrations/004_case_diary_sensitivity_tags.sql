-- Apply once to existing PostgreSQL environments before deploying case-diary
-- redaction. New databases receive this table from models.
--
-- Stores the sensitive spans the AI Parser finds in a case-diary entry. Before
-- this, the parser computed the spans and discarded them, and diary text was
-- returned unredacted to every role that could open the case (issue #92).
-- Coordinates and entity type only — never the text.
CREATE TABLE IF NOT EXISTS case_diary_sensitivity_tags (
    id UUID PRIMARY KEY,
    case_diary_entry_id UUID NOT NULL REFERENCES case_diary_entries(id),
    entity_type VARCHAR NOT NULL,
    span_start INTEGER NOT NULL,
    span_end INTEGER NOT NULL,
    confidence INTEGER,
    source VARCHAR NOT NULL DEFAULT 'ai_parser',
    created_at TIMESTAMPTZ DEFAULT now() NOT NULL
);

-- Every read of a diary list looks tags up by entry.
CREATE INDEX IF NOT EXISTS ix_case_diary_tags_entry ON case_diary_sensitivity_tags(case_diary_entry_id);
