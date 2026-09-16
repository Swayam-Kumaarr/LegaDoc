"""
Seeds the canonical permissions, roles, organisations and personas.

    docker compose exec api python -m app.seed_db

Run after `python -m app.init_db`, which creates the tables this fills.
scripts/setup.sh does both, in that order.

This existed as seed_all() in app.seed_data for a long time with no caller
outside the test suite, so a fresh `docker compose up` produced a working
stack containing **zero users**. Every persona documented in CLAUDE.md and
offered by the DevLogin picker returned "Invalid email or password", which
reads as a broken login rather than an empty database.

Idempotent: seed_all only creates what is missing, so re-running it after
adding a persona (e.g. security_auditor) backfills just that one and leaves
existing accounts, including any changed passwords, untouched.
"""

from app.database import SessionLocal
from app.seed_data import DEFAULT_TEST_PASSWORD, OFFICIAL_TEST_USERS, seed_all
from app import models


def main() -> None:
    db = SessionLocal()
    try:
        before = db.query(models.User).count()
        seed_all(db)
        after = db.query(models.User).count()

        seeded_emails = {u["email"] for u in OFFICIAL_TEST_USERS}
        present = (
            db.query(models.User)
            .filter(models.User.email.in_(seeded_emails))
            .count()
        )

        print(f"Seeded. Users: {before} -> {after}.")
        print(f"{present}/{len(seeded_emails)} canonical personas present.")
        print(f"Password for all seeded personas: {DEFAULT_TEST_PASSWORD}")

        missing = seeded_emails - {
            e for (e,) in db.query(models.User.email)
            .filter(models.User.email.in_(seeded_emails))
            .all()
        }
        if missing:
            # Not an exception: the stack is still usable, but say so loudly
            # rather than let it surface later as a login failure.
            print("WARNING — these personas were not created: " + ", ".join(sorted(missing)))
    finally:
        db.close()


if __name__ == "__main__":
    main()
