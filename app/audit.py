"""Change history: who changed what about a child's results, and what it was before.

A before_flush hook on every DB session compares tracked rows with their stored
values and adds ChangeLog rows to the same transaction, so a save and its history
entry are written together or not at all. New save routes are covered automatically.
Bulk deletes (Query.delete) bypass the ORM; callers log those with log_bulk().
"""

import contextvars
import datetime as dt
import json

from sqlalchemy import event, inspect

from .db import SessionLocal

# (teacher_id, teacher_name, via_admin_name, request_path) of the current request
ACTOR = contextvars.ContextVar("audit_actor", default=None)
MERGE_SECONDS = 60


def _spec():
    from .models import Event, ItemRecord, Review, StageObs, Student, Summary

    def stage_ref(o):
        if o.dim:
            return f"{o.stage}|dim:{o.dim}"
        if o.prompt_index:
            return f"{o.stage}|{o.prompt_index}"
        return o.stage or ""

    return {
        ItemRecord: ("score", ("status", "academic", "expression", "trial", "note"), lambda o: o.code),
        StageObs: ("stage", ("response", "note"), stage_ref),
        Event: ("event", ("category", "stage", "points", "reason"), lambda o: o.category or ""),
        Review: ("review", (), lambda o: ""),
        Summary: ("comment", ("text", "text_zh"), lambda o: ""),
        Student: ("roster", ("name", "level", "group_id", "parent_email", "external_id"), lambda o: ""),
    }


def _plain(v):
    if isinstance(v, (dt.date, dt.datetime)):
        return v.isoformat()
    return v


def _old_new(obj, field, state):
    hist = state.attrs[field].history
    if hist.has_changes():
        old = hist.deleted[0] if hist.deleted else None
        new = hist.added[0] if hist.added else None
        return _plain(old), _plain(new)
    cur = getattr(obj, field)
    return _plain(cur), _plain(cur)


def _student_info(session, obj):
    from .models import Student

    if isinstance(obj, Student):
        return obj.id, obj.session_id, obj.name
    st = session.get(Student, obj.student_id) if obj.student_id else None
    return (obj.student_id, st.session_id if st else None, st.name if st else "")


def _before_flush(session, _ctx, _instances):
    from .models import ChangeLog

    spec = _spec()
    actor = ACTOR.get() or (None, "system", "", "")
    now = dt.datetime.now()
    with session.no_autoflush:
        for bucket, action in ((session.new, "create"), (session.dirty, "update"), (session.deleted, "delete")):
            for obj in list(bucket):
                cfg = spec.get(type(obj))
                if cfg is None:
                    continue
                kind, fields, ref_fn = cfg
                state = inspect(obj)
                if action == "update" and not session.is_modified(obj, include_collections=False):
                    continue
                changes = {}
                for f in fields:
                    old, new = _old_new(obj, f, state)
                    if action == "create":
                        old = None
                    elif action == "delete":
                        new = None
                    if old != new and not (old in (None, "") and new in (None, "")):
                        changes[f] = [old, new]
                if action == "update" and not changes:
                    continue
                if action == "create" and kind not in ("review", "event") and not changes:
                    continue
                student_id, session_id, student_name = _student_info(session, obj)
                ref = ref_fn(obj) or ""
                if _merge(session, ChangeLog, actor, student_id, kind, ref, action, changes, now):
                    continue
                session.add(ChangeLog(
                    at=now, actor_id=actor[0], actor_name=actor[1] or "", via_name=actor[2] or "",
                    session_id=session_id, student_id=student_id, student_name=student_name,
                    kind=kind, ref=ref[:120], action=action,
                    changes=json.dumps(changes, ensure_ascii=False, default=str), source=(actor[3] or "")[:120],
                ))


def _merge(session, ChangeLog, actor, student_id, kind, ref, action, changes, now):
    """Fold quick successive edits (autosave) into the previous entry by the same person."""
    if actor[0] is None or student_id is None:
        return False
    prev = (
        session.query(ChangeLog)
        .filter(ChangeLog.actor_id == actor[0], ChangeLog.student_id == student_id,
                ChangeLog.kind == kind, ChangeLog.ref == ref,
                ChangeLog.at >= now - dt.timedelta(seconds=MERGE_SECONDS))
        .order_by(ChangeLog.id.desc())
        .first()
    )
    if prev is None or prev.action not in ("create", "update"):
        return False
    if action == "delete":
        if prev.action == "create":  # added and removed again within a minute: nothing happened
            session.delete(prev)
            return True
        return False
    if action == "create":
        return False
    merged = json.loads(prev.changes or "{}")
    for f, (old, new) in changes.items():
        merged[f] = [merged[f][0] if f in merged else old, new]
    merged = {f: v for f, v in merged.items() if v[0] != v[1]}
    if not merged and prev.action == "update":
        session.delete(prev)  # changed and changed back
        return True
    prev.changes = json.dumps(merged, ensure_ascii=False, default=str)
    prev.at = now
    return True


def log_bulk(db, session_id, ref, changes):
    """For deletes that bypass the ORM (e.g. admin 'clear session results')."""
    from .models import ChangeLog

    actor = ACTOR.get() or (None, "system", "", "")
    db.add(ChangeLog(at=dt.datetime.now(), actor_id=actor[0], actor_name=actor[1] or "", via_name=actor[2] or "",
                     session_id=session_id, kind="bulk", ref=ref, action="clear",
                     changes=json.dumps(changes, ensure_ascii=False), source=(actor[3] or "")[:120]))


_started = False


def start():
    global _started
    if not _started:
        _started = True
        event.listen(SessionLocal, "before_flush", _before_flush)


# ---------- reading the history back ----------

def can_view(teacher, student):
    """Admins see everything; teachers see the children in their own groups."""
    if not teacher:
        return False
    if teacher.role == "admin":
        return True
    return bool(student and student.group and student.group.teacher_id == teacher.id)


def query(db, session_id=None, student_id=None, kind=None, ref=None, actor_id=None, ref_prefix=None, limit=500):
    from .models import ChangeLog

    q = db.query(ChangeLog)
    if session_id is not None:
        q = q.filter(ChangeLog.session_id == session_id)
    if student_id is not None:
        q = q.filter(ChangeLog.student_id == student_id)
    if kind:
        q = q.filter(ChangeLog.kind == kind)
    if ref is not None:
        q = q.filter(ChangeLog.ref == ref)
    if ref_prefix:
        q = q.filter(ChangeLog.ref.like(ref_prefix + "%"))
    if actor_id:
        q = q.filter(ChangeLog.actor_id == actor_id)
    return q.order_by(ChangeLog.at.desc(), ChangeLog.id.desc()).limit(limit).all()


class _Ctx:
    """Lookups to turn codes and ids into names, cached per page."""

    def __init__(self, db, session_ids, student_ids=()):
        from .models import AssessSession, Group, Paper, Question, Student
        from .stage_defs import paper_dims

        self.titles, self.dims, self.groups, self.levels = {}, {}, {}, {}
        for sid, lv in db.query(Student.id, Student.level).filter(Student.id.in_(list(student_ids) or [-1])):
            self.levels[sid] = lv
        papers = set()
        default = db.query(Paper.id).order_by(Paper.id).first()
        for s in db.query(AssessSession).filter(AssessSession.id.in_(list(session_ids) or [-1])):
            papers.add(s.paper_id or (default[0] if default else None))
        for q in db.query(Question).filter(Question.paper_id.in_([p for p in papers if p] or [-1])):
            self.titles.setdefault((q.version, q.code), q.title)  # TK and K have different questions per code
            self.titles.setdefault((None, q.code), q.title)
        for pid in papers:
            for stage, dl in paper_dims(db, pid).items():
                for d in dl:
                    self.dims[(stage, d["key"])] = d
        for g in db.query(Group).filter(Group.session_id.in_(list(session_ids) or [-1])):
            self.groups[g.id] = g.name


def _short(v, n=80):
    s = str(v)
    return s if len(s) <= n else s[: n - 1] + "…"


def describe(db, entries):
    """[{at, who, child, what, lines: [(label, old, new, full_old, full_new)], action, kind}]"""
    from .i18n import cur_lang, t
    from .report_i18n import DIM_LABEL_ZH, DIM_VALUE_ZH

    zh = cur_lang() == "zh"
    ctx = _Ctx(db, {e.session_id for e in entries if e.session_id}, {e.student_id for e in entries if e.student_id})
    status_lbl = {"scored": t("hist.v.scored"), "not_observed": t("hist.v.not_observed"),
                  "not_completed": t("hist.v.not_completed")}

    def val(e, field, v):
        if v is None or v == "":
            return t("hist.empty")
        if field == "status":
            return status_lbl.get(v, v)
        if field == "response":
            stage = e.ref.split("|", 1)[0]
            if "|dim:" in e.ref:
                return DIM_VALUE_ZH.get(v, v) if zh else v
            if stage == "Separation" or v in ("brief", "support", "not_observed"):  # separation-type parts
                return t("sep.cell." + v) if v in ("independent", "brief", "support", "not_observed") else v
            return t("resp." + v) if v in ("independent", "prompted", "none") else v
        if field == "group_id":
            return ctx.groups.get(v, f"#{v}")
        if field == "category":
            return "SEL" if v == "SEL" else t("events.cat.cs")
        if field == "stage":
            return t("stage." + v) if v else v
        return v

    def what(e):
        if e.kind == "score":
            lv = ctx.levels.get(e.student_id)
            title = ctx.titles.get((lv, e.ref)) or ctx.titles.get((None, e.ref), "")
            return f"{e.ref} · {title}" if title else e.ref
        if e.kind == "stage":
            stage, _, rest = e.ref.partition("|")
            name = t("stage." + stage) if stage else ""
            if rest.startswith("dim:"):
                d = ctx.dims.get((stage, rest[4:]))
                label = (d["label_zh"] or d["label"]) if (d and zh) else (d["label"] if d else rest[4:])
                if zh and not (d and d["label_zh"]):
                    label = DIM_LABEL_ZH.get(label, label)
                return f"{name} · {label}"
            if rest:
                return f"{name} · P{rest}"
            return name
        return t("hist.kind." + e.kind)

    out = []
    for e in entries:
        try:
            changes = json.loads(e.changes or "{}")
        except ValueError:
            changes = {}
        lines = []
        if e.kind == "bulk":
            n = (changes.get("records") or [0])[0]
            lines.append((t("hist.bulk_cleared").format(n=n), "", "", "", ""))
        elif e.kind == "review":
            lines.append((t("hist.reviewed") if e.action == "create" else t("hist.unreviewed"), "", "", "", ""))
        else:
            for f, (old, new) in changes.items():
                o, n = val(e, f, old), val(e, f, new)
                lines.append((t("hist.f." + f), _short(o), _short(n), str(o), str(n)))
            if e.action == "delete" and not lines:
                lines.append((t("hist.deleted"), "", "", "", ""))
        who = e.actor_name or t("hist.system")
        if e.via_name:
            who += " " + t("hist.via").format(name=e.via_name)
        out.append({"id": e.id, "at": e.at, "who": who, "child": e.student_name, "student_id": e.student_id,
                    "what": what(e), "lines": lines, "action": e.action, "kind": e.kind})
    return out
