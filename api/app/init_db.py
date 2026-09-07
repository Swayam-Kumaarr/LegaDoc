"""
Creates every table from app.models against DATABASE_URL. Run once after
`docker compose up`:

    docker compose exec api python -m app.init_db

Replace with real Alembic migrations once the schema stabilizes — this is
intentionally the simplest thing that works for a baseline.

create_all() only creates tables that don't exist yet — it never alters an
existing table to add a new column. Fine for a genuinely fresh `docker
compose up` (empty Postgres volume, first-ever run), but if your local DB
volume predates a model change that added a column to an EXISTING table
(e.g. User.must_change_password, added alongside UserApplication/
CredentialDocument), running this again silently does nothing for that
column and you'll hit real errors the first time code tries to read/write
it. Either wipe the volume (`docker compose down -v && docker compose up
-d --build && python -m app.init_db`) or hand-run the matching `ALTER
TABLE ... ADD COLUMN` yourself — there's no migration tool here to do it
for you yet.
"""

from app.database import Base, engine
from app import models  # noqa: F401 — import registers every model on Base.metadata

if __name__ == "__main__":
    Base.metadata.create_all(bind=engine)
    print("Tables created.")
