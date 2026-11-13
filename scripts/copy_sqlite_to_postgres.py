"""Copy every table from the SQLite file (data/app.db) into an empty PostgreSQL database.

Run from the project root, BEFORE the app is started against PostgreSQL for the
first time (the app seeds questions and an Admin into an empty database, and
this script refuses to copy into a database that already has rows):

    python scripts/copy_sqlite_to_postgres.py --source data/app.db \
        --target "postgresql+psycopg://USER:PASSWORD@HOST:5432/DBNAME"

--target can be left out when MI_DATABASE_URL is set.

What it does
  1. brings the SQLite file's schema up to date (same upgrade the app runs on start)
  2. checks the data for things PostgreSQL rejects but SQLite allowed:
     text longer than its column (stops), and rows pointing at a parent that no
     longer exists — an optional link (e.g. "recorded by" a deleted teacher) is
     cleared and the row kept; a required one stops the copy
  3. creates the tables on the target and copies all rows in ONE transaction,
     so a failure leaves the target untouched
  4. moves each id sequence past the copied ids, then compares row counts
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import String, create_engine, func, inspect, select, text  # noqa: E402

from app import models  # noqa: E402,F401  (registers the tables)
from app.db import Base  # noqa: E402
from app.schema import upgrade_schema  # noqa: E402

BATCH = 500


def fail(msg):
    print(f"\nSTOPPED: {msg}\nNo rows were copied to the target.")
    sys.exit(1)


def check_source(src, tables):
    """Returns (problems that stop the copy, {table: [(column, parent_column)]} links to clear)."""
    problems, clear = [], {}
    with src.connect() as c:
        for t in tables:
            for col in t.columns:
                if isinstance(col.type, String) and col.type.length:
                    n = c.execute(
                        select(func.count()).select_from(t).where(func.length(col) > col.type.length)
                    ).scalar()
                    if n:
                        problems.append(f"{t.name}.{col.name}: {n} value(s) longer than {col.type.length} characters")
            for fk in t.foreign_keys:
                parent = fk.column
                orphans = c.execute(
                    select(func.count()).select_from(t).where(
                        fk.parent.is_not(None),
                        fk.parent.not_in(select(parent)),
                    )
                ).scalar()
                if not orphans:
                    continue
                msg = f"{t.name}.{fk.parent.name}: {orphans} row(s) point to a missing {parent.table.name}.{parent.name}"
                if fk.parent.nullable:
                    # e.g. "recorded by" a teacher account that was deleted: keep the
                    # row, clear only the dangling link (the app shows it as blank).
                    clear.setdefault(t.name, []).append((fk.parent.name, parent))
                    print(f"  keeping rows, clearing dangling link -> {msg}")
                else:
                    problems.append(msg)
    return problems, clear


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", default="data/app.db", help="SQLite file (default: data/app.db)")
    ap.add_argument("--target", default=os.environ.get("MI_DATABASE_URL", ""), help="PostgreSQL URL")
    args = ap.parse_args()

    if not os.path.exists(args.source):
        fail(f"source file not found: {args.source}")
    if not args.target.startswith("postgresql"):
        fail("--target (or MI_DATABASE_URL) must be a postgresql+psycopg://... URL")

    src = create_engine(f"sqlite:///{os.path.abspath(args.source)}")
    dst = create_engine(args.target)
    print(f"source: {args.source}")
    print(f"target: {dst.url.render_as_string(hide_password=True)}")

    upgrade_schema(src)
    src_tables = set(inspect(src).get_table_names())
    tables = [t for t in Base.metadata.sorted_tables if t.name in src_tables]
    skipped = sorted(src_tables - {t.name for t in Base.metadata.sorted_tables})
    if skipped:
        print(f"not copied (no longer used by the app): {', '.join(skipped)}")

    problems, clear = check_source(src, tables)
    if problems:
        fail("the source data has rows PostgreSQL would reject:\n  - " + "\n  - ".join(problems))

    Base.metadata.create_all(dst)
    with dst.connect() as c:
        busy = [t.name for t in Base.metadata.sorted_tables if c.execute(select(func.count()).select_from(t)).scalar()]
    if busy:
        fail(
            "the target already has data in: " + ", ".join(busy) + "\n"
            "Copy into an empty database (was the app started against it first?)."
        )

    counts = {}
    with src.connect() as s, dst.begin() as d:
        for t in tables:
            rows = [dict(r._mapping) for r in s.execute(select(t))]
            for col_name, parent in clear.get(t.name, []):
                valid = set(s.execute(select(parent)).scalars())
                for r in rows:
                    if r[col_name] is not None and r[col_name] not in valid:
                        r[col_name] = None
            for i in range(0, len(rows), BATCH):
                d.execute(t.insert(), rows[i : i + BATCH])
            counts[t.name] = len(rows)
            pk = list(t.primary_key.columns)
            if len(pk) == 1 and pk[0].autoincrement in (True, "auto") and rows:
                d.execute(
                    text(
                        f"SELECT setval(pg_get_serial_sequence(:t, :c), "
                        f"(SELECT MAX({pk[0].name}) FROM {t.name}))"
                    ),
                    {"t": t.name, "c": pk[0].name},
                )
            print(f"  {t.name:24s} {len(rows):6d} rows")

    with dst.connect() as c:
        wrong = [
            f"{name}: copied {n}, target has {c.execute(select(func.count()).select_from(Base.metadata.tables[name])).scalar()}"
            for name, n in counts.items()
            if c.execute(select(func.count()).select_from(Base.metadata.tables[name])).scalar() != n
        ]
    if wrong:
        print("\nWARNING: row counts differ:\n  - " + "\n  - ".join(wrong))
        sys.exit(1)
    print(f"\nDone: {sum(counts.values())} rows in {len(counts)} tables copied; row counts match.")


if __name__ == "__main__":
    main()
