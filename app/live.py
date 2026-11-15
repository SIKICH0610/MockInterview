"""Live updates: when anyone saves a change, every open page of that session
refreshes the affected parts by itself.

- SQLAlchemy events notice committed changes to the tracked tables and bump the
  session's counter (live_versions).
- The change is broadcast: PostgreSQL LISTEN/NOTIFY reaches every server process
  (we run 2); on SQLite (local dev, one process) it is delivered in-process.
- /wb/live/{sid} streams the changes to the browser (Server-Sent Events);
  /wb/live/{sid}/version is the fallback the page polls when the stream is down.
"""

import asyncio
import datetime as dt
import json
import logging
import threading
import time

from sqlalchemy import bindparam, event, text

from .db import SessionLocal, engine, side_engine

log = logging.getLogger("mockinterview.live")
CHANNEL = "mi_live"
IS_PG = engine.dialect.name == "postgresql"

_subs = set()  # {(loop, queue)}
_subs_lock = threading.Lock()


# ---------- in-process fan-out ----------

def subscribe():
    entry = (asyncio.get_running_loop(), asyncio.Queue(maxsize=500))
    with _subs_lock:
        _subs.add(entry)
    return entry


def unsubscribe(entry):
    with _subs_lock:
        _subs.discard(entry)


def _put(q, msg):
    try:
        q.put_nowait(msg)
    except asyncio.QueueFull:
        pass


def _dispatch(msg):
    with _subs_lock:
        entries = list(_subs)
    for loop, q in entries:
        try:
            loop.call_soon_threadsafe(_put, q, msg)
        except RuntimeError:  # loop closed
            unsubscribe((loop, q))


# ---------- noticing changes ----------

def _tracked():
    from .models import Event, Group, ItemRecord, ReportPdf, Review, StageObs, Student, Summary

    return Student, Group, (ItemRecord, StageObs, Event, Review, Summary, ReportPdf)


def _collect(session, _ctx):
    Student, Group, per_student = _tracked()
    bag = session.info.setdefault("live", set())
    for obj in list(session.new) + list(session.dirty) + list(session.deleted):
        if isinstance(obj, Student):
            bag.add((obj.id, obj.session_id))
        elif isinstance(obj, Group):
            bag.add((None, obj.session_id))
        elif isinstance(obj, per_student):
            bag.add((obj.student_id, None))


def _forget(session):
    session.info.pop("live", None)


def _after_commit(session):
    bag = session.info.pop("live", None)
    if not bag:
        return
    try:
        _publish(bag)
    except Exception:  # noqa: BLE001 - live updates must never break a save
        log.exception("live publish failed")


def _publish(bag):
    need = sorted({st for st, sid in bag if sid is None and st})
    by_session = {}
    with side_engine.connect() as c:  # not the request pool (see db.py)
        if need:
            rows = c.execute(
                text("SELECT id, session_id FROM students WHERE id IN :ids").bindparams(bindparam("ids", expanding=True)),
                {"ids": need},
            ).all()
            sid_of = {r[0]: r[1] for r in rows}
        else:
            sid_of = {}
        for st, sid in bag:
            sid = sid if sid is not None else sid_of.get(st)
            if sid is None:
                continue
            by_session.setdefault(sid, set())
            if st:
                by_session[sid].add(st)
        now = dt.datetime.now()
        msgs = []
        for sid, students in by_session.items():
            c.execute(
                text(
                    "INSERT INTO live_versions (session_id, v, updated_at) VALUES (:sid, 1, :now) "
                    "ON CONFLICT (session_id) DO UPDATE SET v = live_versions.v + 1, updated_at = :now"
                ),
                {"sid": sid, "now": now},
            )
            v = c.execute(text("SELECT v FROM live_versions WHERE session_id = :sid"), {"sid": sid}).scalar()
            msgs.append({"sid": sid, "v": v, "st": sorted(students)[:50]})
        if IS_PG:
            for m in msgs:
                c.execute(text("SELECT pg_notify(:ch, :p)"), {"ch": CHANNEL, "p": json.dumps(m)})
        c.commit()
    if not IS_PG:
        for m in msgs:
            _dispatch(m)


def version(db, sid):
    from .models import LiveVersion

    row = db.get(LiveVersion, sid)
    return row.v if row else 0


# ---------- PostgreSQL listener (one thread per server process) ----------

def _listen_forever():
    import psycopg

    dsn = engine.url.set(drivername="postgresql").render_as_string(hide_password=False)
    while True:
        try:
            with psycopg.connect(dsn, autocommit=True) as conn:
                conn.execute(f"LISTEN {CHANNEL}")
                log.info("live: listening for changes")
                while True:
                    for n in conn.notifies(timeout=30):
                        try:
                            _dispatch(json.loads(n.payload))
                        except ValueError:
                            pass
                    conn.execute("SELECT 1")  # keep the connection honest
        except Exception:  # noqa: BLE001
            log.warning("live: listener lost the database, retrying in 3 s", exc_info=True)
            time.sleep(3)


_started = False


def start():
    """Hook the change tracking into every DB session; start the listener on PostgreSQL."""
    global _started
    if _started:
        return
    _started = True
    event.listen(SessionLocal, "after_flush", _collect)
    event.listen(SessionLocal, "after_commit", _after_commit)
    event.listen(SessionLocal, "after_rollback", _forget)
    if IS_PG:
        threading.Thread(target=_listen_forever, name="live-listener", daemon=True).start()
