ADR-0002 — Store plans in SQLite
================================

.. adr:: Use SQLite as the single-user persistence layer
   :id: ADR-0002
   :status: approved
   :links: REQ-002, SPEC-002

   **Context.** This is a personal travel-planning tool used by one person at a
   time on a single machine. We need persistence beyond the browser session.

   **Decision.** Use a local SQLite file (``travel_hub.db``) accessed through
   the standard ``sqlite3`` module via parameterised queries in
   ``database.py``. Defer ORM adoption (e.g. SQLAlchemy) until the schema gets
   non-trivial.

   **Consequences.** Zero external dependencies, easy backups (copy a file).
   Migrations are manual for now; if the schema grows we will revisit and
   record an ADR-0003 introducing Alembic.
