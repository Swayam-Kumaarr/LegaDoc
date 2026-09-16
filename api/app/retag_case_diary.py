"""
Re-tags case-diary entries that were marked "ready" before their sensitive
spans were being stored (issue #92).

    docker compose exec api python -m app.retag_case_diary

Run once after applying db/migrations/004_case_diary_sensitivity_tags.sql.

Why this is needed: before the fix, the AI parser computed spans for a diary
entry and discarded them. Any entry tagged in that window is "ready" with no
rows in case_diary_sensitivity_tags, so the redacted read path has nothing to
mask with and would return the raw text to roles that must only see it
redacted.

Fail-closed by construction: each such entry is first moved back to
"processing", which GET /cases/:id/case-diary already hides from every role
outside IO/SHO. It only becomes visible to them again once the worker has
re-tagged it and stored its spans. An entry that genuinely contains nothing
sensitive is simply re-tagged to "ready" with no spans — harmless.

Idempotent: an entry that already has stored spans is left alone.
"""

from app import models
from app.database import SessionLocal
from app.queue import get_queue


def main() -> None:
    db = SessionLocal()
    try:
        tagged_ids = {
            row[0]
            for row in db.query(models.CaseDiarySensitivityTag.case_diary_entry_id)
            .filter(models.CaseDiarySensitivityTag.source == "ai_parser")
            .distinct()
            .all()
        }
        untagged = [
            e
            for e in db.query(models.CaseDiaryEntry)
            .filter(models.CaseDiaryEntry.status == "ready")
            .all()
            if e.id not in tagged_ids
        ]

        if not untagged:
            print("No ready case-diary entries without stored spans. Nothing to do.")
            return

        # Hide first, then enqueue — never the reverse. If enqueueing fails
        # partway, the remaining entries stay hidden rather than exposed.
        for entry in untagged:
            entry.status = "processing"
        db.commit()

        queue = get_queue()
        for entry in untagged:
            queue.enqueue("ai_parser_worker.tag_case_diary_entry", case_diary_entry_id=str(entry.id))

        print(f"Re-queued {len(untagged)} case-diary entr{'y' if len(untagged) == 1 else 'ies'} for tagging.")
        print("They are hidden from roles outside IO/SHO until the worker stores their spans.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
