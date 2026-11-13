"""Schema upgrades for an existing database (SQLite or PostgreSQL; no Alembic yet).

Runs at startup, before create_all():
- Any database: columns that exist in the models but not yet in the table are
  added (nullable, with the model's plain default filled in for existing rows).
  This covers the usual change — a new field on an existing table.
- SQLite only: one legacy fix for very old demo files.

Not handled automatically: renaming or dropping columns, changing a column's
type, new constraints/indexes on existing tables. Do those by hand (or bring
in Alembic) and note them in the deploy log.
"""

import logging

from sqlalchemy import inspect, literal

from .db import Base

log = logging.getLogger("mockinterview.schema")


def _default_sql(col, dialect):
    d = col.default
    if d is None or not getattr(d, "is_scalar", False) or d.arg is None:
        return None
    return str(
        literal(d.arg, type_=col.type).compile(dialect=dialect, compile_kwargs={"literal_binds": True})
    )


def upgrade_schema(engine_):
    from . import models  # noqa: F401  (registers every table on Base.metadata)

    with engine_.begin() as conn:
        dialect = conn.dialect
        q = dialect.identifier_preparer.quote
        insp = inspect(conn)
        existing = set(insp.get_table_names())

        if dialect.name == "sqlite" and "questions" in existing:
            # questions gained paper_id + a new unique constraint; the table is
            # pure seed data, so rebuild it from scratch.
            if "paper_id" not in {c["name"] for c in insp.get_columns("questions")}:
                conn.exec_driver_sql("DROP TABLE questions")
                existing.discard("questions")

        for table in Base.metadata.sorted_tables:
            if table.name not in existing:
                continue  # create_all() builds new tables in full
            have = {c["name"] for c in insp.get_columns(table.name)}
            for col in table.columns:
                if col.name in have:
                    continue
                sql = f"ALTER TABLE {q(table.name)} ADD COLUMN {q(col.name)} {col.type.compile(dialect=dialect)}"
                default = _default_sql(col, dialect)
                if default is not None:
                    sql += f" DEFAULT {default}"
                conn.exec_driver_sql(sql)
                log.warning("schema upgrade: added %s.%s", table.name, col.name)
