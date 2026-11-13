"""Daily database backup, keeping the last 14 days (run by deploy/mockinterview-backup.*).

- MI_DATABASE_URL set to PostgreSQL -> `pg_dump -Fc` to mi_YYYY-MM-DD.dump
  (needs the postgresql client, same major version as the server or newer;
  the password is passed through the environment, never on the command line)
- otherwise -> SQLite online backup of data/app.db to app_YYYY-MM-DD.db

    python scripts/backup_db.py [--dest DIR] [--keep 14] [--source data/app.db]

Restore a PostgreSQL dump (overwrites the current data, confirm first):
    pg_restore --clean --no-owner -d <database> mi_YYYY-MM-DD.dump
"""

import argparse
import datetime
import os
import sqlite3
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

parser = argparse.ArgumentParser()
parser.add_argument("--source", default=os.path.join(ROOT, "data", "app.db"), help="SQLite file")
parser.add_argument("--dest", default="/var/lib/mockinterview/backup")
parser.add_argument("--keep", type=int, default=14, help="days to keep")
args = parser.parse_args()

os.makedirs(args.dest, exist_ok=True)
today = f"{datetime.date.today():%Y-%m-%d}"
url = os.environ.get("MI_DATABASE_URL", "")

if url.startswith("postgresql"):
    from sqlalchemy.engine import make_url

    u = make_url(url)
    prefix, ext = "mi_", ".dump"
    target = os.path.join(args.dest, f"{prefix}{today}{ext}")
    tmp = target + ".part"
    env = dict(os.environ, PGHOST=u.host or "", PGPORT=str(u.port or 5432),
               PGUSER=u.username or "", PGPASSWORD=u.password or "", PGDATABASE=u.database or "")
    r = subprocess.run(["pg_dump", "-Fc", "--no-owner", "-f", tmp], env=env)
    if r.returncode:
        if os.path.exists(tmp):
            os.remove(tmp)
        sys.exit(f"pg_dump failed (exit {r.returncode})")
else:
    prefix, ext = "app_", ".db"
    target = os.path.join(args.dest, f"{prefix}{today}{ext}")
    tmp = target + ".part"
    src = sqlite3.connect(args.source)
    dst = sqlite3.connect(tmp)
    src.backup(dst)
    dst.close()
    src.close()

os.replace(tmp, target)
print("backup:", target, os.path.getsize(target), "bytes")

cutoff = time.time() - args.keep * 86400
for name in os.listdir(args.dest):
    path = os.path.join(args.dest, name)
    if name.startswith(prefix) and name.endswith(ext) and os.path.getmtime(path) < cutoff:
        os.remove(path)
        print("removed old backup:", path)
