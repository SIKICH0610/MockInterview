from datetime import datetime

from fastapi import APIRouter, Body, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import AssessSession, Event, Group, ItemRecord, Review, StageObs, Student, Summary, Teacher

router = APIRouter(prefix="/api")


def _me(request: Request):
    return getattr(request.state, "teacher", None)


def _require_admin(request: Request):
    me = _me(request)
    if not me or me.role != "admin":
        return JSONResponse(status_code=403, content={"ok": False, "error": "admin only"})
    return None


def _can_touch(me, st):
    """Teachers may only write records for students in their own groups."""
    if me is None:
        return False
    if me.role == "admin":
        return True
    g = st.group
    return bool(g and g.teacher_id == me.id)


FORBIDDEN = {"ok": False, "error": "not your group"}


def _lock_student(db, student_id):
    """One save at a time per child. On PostgreSQL the second writer waits until the first has
    committed and then works from what was saved - so two people saving the same score at the same
    instant cannot silently overwrite each other (the later one gets the usual "someone else changed
    this" answer), and no duplicate rows are created. Released automatically at commit / rollback."""
    if db.get_bind().dialect.name == "postgresql":
        from sqlalchemy import text

        db.execute(text("SELECT pg_advisory_xact_lock(7240, :k)"), {"k": int(student_id)})


@router.post("/summary/ai")
def ai_summary(request: Request, payload: dict = Body(...), db: Session = Depends(get_db)):
    """Draft / polish the Teacher's View with Claude. Returns a draft only;
    the teacher edits and saves it explicitly."""
    student_id = int(payload["student_id"])
    student = db.get(Student, student_id)
    if not student:
        return JSONResponse(status_code=404, content={"ok": False, "error": "student not found"})
    me = _me(request)
    if not _can_touch(me, student):
        return JSONResponse(status_code=403, content=FORBIDDEN)

    from ..routers.report import collect_report_facts
    from ..services import ai

    facts = collect_report_facts(db, student)
    ok, result = ai.draft_teacher_view(facts, str(payload.get("draft") or ""))
    if not ok:
        return JSONResponse(status_code=200, content={"ok": False, "error": result})
    # The Chinese comment is adapted from the English draft so both PDFs say the
    # same thing. If only this step fails, still return the English draft.
    zh_ok, zh = ai.translate_teacher_view_zh(result)
    out = {"ok": True, "text": result}
    if zh_ok:
        out["text_zh"] = zh
    else:
        out["zh_error"] = zh
    return out


@router.post("/summary/translate")
def ai_translate(request: Request, payload: dict = Body(...), db: Session = Depends(get_db)):
    """Re-create the Chinese comment from the (teacher-edited) English one.
    Returns a draft only; the teacher saves it explicitly."""
    student_id = int(payload["student_id"])
    student = db.get(Student, student_id)
    if not student:
        return JSONResponse(status_code=404, content={"ok": False, "error": "student not found"})
    me = _me(request)
    if not _can_touch(me, student):
        return JSONResponse(status_code=403, content=FORBIDDEN)

    from ..services import ai

    ok, result = ai.translate_teacher_view_zh(str(payload.get("text") or ""))
    if not ok:
        return JSONResponse(status_code=200, content={"ok": False, "error": result})
    return {"ok": True, "text_zh": result}


@router.post("/summary/save")
def save_summary(request: Request, payload: dict = Body(...), db: Session = Depends(get_db)):
    student_id = int(payload["student_id"])
    student = db.get(Student, student_id)
    if not student:
        return JSONResponse(status_code=404, content={"ok": False, "error": "student not found"})
    me = _me(request)
    if not _can_touch(me, student):
        return JSONResponse(status_code=403, content=FORBIDDEN)
    _lock_student(db, student_id)
    row = db.query(Summary).filter_by(student_id=student_id).first()
    if row is None:
        row = Summary(student_id=student_id)
        db.add(row)
    # Only touch the languages the client sent, so an older page that posts
    # just `text` never wipes the Chinese comment.
    if "text" in payload:
        row.text = str(payload.get("text") or "")
    if "text_zh" in payload:
        row.text_zh = str(payload.get("text_zh") or "")
    row.teacher_id = me.id if me else None
    db.commit()
    return {
        "ok": True,
        "by": me.name if me else "",
        "time": row.updated_at.strftime("%m-%d %H:%M"),
    }


def _serialize_record(rec, db):
    tname = ""
    if rec.teacher_id:
        t = db.get(Teacher, rec.teacher_id)
        tname = t.name if t else ""
    return {
        "student_id": rec.student_id,
        "code": rec.code,
        "status": rec.status,
        "academic": rec.academic,
        "expression": rec.expression,
        "trial": rec.trial,
        "note": rec.note or "",
        "rev": rec.rev,
        "by": tname,
    }


def _coerce_int(v):
    if v is None or v == "":
        return None
    return int(v)


@router.get("/teachers/switchable")
def switchable_teachers(request: Request, db: Session = Depends(get_db)):
    me = _me(request)
    if not me or not (me.role == "admin" or getattr(request.state, "admin_return", False)):
        return JSONResponse(status_code=403, content={"ok": False})
    from .. import perm
    from ..auth import parse_token

    # the admin really behind this request (when impersonating a teacher: the one to return to)
    real = me if me.role == "admin" else db.get(Teacher, parse_token(request.cookies.get("admin_auth") or "") or 0)
    teachers = db.query(Teacher).filter_by(active=True).order_by(Teacher.name).all()
    return {
        "ok": True,
        "teachers": [
            {"id": te.id, "name": te.name, "role": te.role}
            for te in teachers
            if te.id != me.id and (perm.can_switch_into(real, te) or (real is not None and te.id == real.id))
        ],
    }


@router.post("/record/upsert")
def upsert_record(request: Request, payload: dict = Body(...), db: Session = Depends(get_db)):
    student_id = int(payload["student_id"])
    code = str(payload["code"])
    client_rev = int(payload.get("rev") or 0)

    student = db.get(Student, student_id)
    if not student:
        return JSONResponse(status_code=404, content={"ok": False, "error": "student not found"})
    if not _can_touch(_me(request), student):
        return JSONResponse(status_code=403, content=FORBIDDEN)
    _lock_student(db, student_id)

    rec = db.query(ItemRecord).filter_by(student_id=student_id, code=code).first()

    me = _me(request)
    teacher_id = me.id if me else _coerce_int(payload.get("teacher_id"))
    tname = ""
    if teacher_id:
        t = db.get(Teacher, teacher_id)
        tname = t.name if t else ""

    if rec is not None and client_rev != rec.rev:
        return JSONResponse(
            status_code=409,
            content={"ok": False, "conflict": True, "current": _serialize_record(rec, db)},
        )

    if rec is None:
        rec = ItemRecord(student_id=student_id, code=code, rev=0)
        db.add(rec)

    rec.academic = _coerce_int(payload.get("academic"))
    rec.expression = _coerce_int(payload.get("expression"))
    rec.trial = _coerce_int(payload.get("trial"))
    status = payload.get("status") or None
    if status not in (None, "scored", "not_observed", "not_completed"):
        status = None
    rec.status = status
    rec.note = str(payload.get("note") or "")
    rec.teacher_id = teacher_id
    rec.rev += 1
    rec.updated_at = datetime.now()
    db.commit()
    return {"ok": True, "rev": rec.rev, "by": tname}


@router.post("/event/add")
def add_event(request: Request, payload: dict = Body(...), db: Session = Depends(get_db)):
    student_id = int(payload["student_id"])
    student = db.get(Student, student_id)
    if not student:
        return JSONResponse(status_code=404, content={"ok": False, "error": "student not found"})
    if not _can_touch(_me(request), student):
        return JSONResponse(status_code=403, content=FORBIDDEN)
    _lock_student(db, student_id)
    ev = Event(
        student_id=student_id,
        category=str(payload.get("category") or "SEL"),
        stage=str(payload.get("stage") or ""),
        code=(payload.get("code") or None),
        points=_coerce_int(payload.get("points")) or 1,
        reason=str(payload.get("reason") or ""),
        support=str(payload.get("support") or ""),
        teacher_id=(_me(request).id if _me(request) else _coerce_int(payload.get("teacher_id"))),
    )
    db.add(ev)
    db.commit()
    tname = ""
    if ev.teacher_id:
        t = db.get(Teacher, ev.teacher_id)
        tname = t.name if t else ""
    return {
        "ok": True,
        "id": ev.id,
        "category": ev.category,
        "stage": ev.stage,
        "points": ev.points,
        "reason": ev.reason,
        "support": ev.support,
        "by": tname,
        "time": ev.created_at.strftime("%H:%M"),
    }


@router.post("/event/delete")
def delete_event(request: Request, payload: dict = Body(...), db: Session = Depends(get_db)):
    ev = db.get(Event, int(payload["id"]))
    if ev:
        if not _can_touch(_me(request), ev.student):
            return JSONResponse(status_code=403, content=FORBIDDEN)
        _lock_student(db, ev.student_id)
        if db.query(Event.id).filter_by(id=ev.id).first():  # not already removed by someone else
            db.delete(ev)
            db.commit()
    return {"ok": True}


@router.post("/stage/add")
def add_stage_obs(request: Request, payload: dict = Body(...), db: Session = Depends(get_db)):
    student_id = int(payload["student_id"])
    student = db.get(Student, student_id)
    if not student:
        return JSONResponse(status_code=404, content={"ok": False, "error": "student not found"})
    if not _can_touch(_me(request), student):
        return JSONResponse(status_code=403, content=FORBIDDEN)
    _lock_student(db, student_id)
    response = str(payload.get("response") or "")
    if response not in ("independent", "prompted", "none"):
        return JSONResponse(status_code=400, content={"ok": False, "error": "bad response"})
    stage = str(payload.get("stage") or "")
    prompt_index = _coerce_int(payload.get("prompt_index"))

    matches = db.query(StageObs).filter_by(student_id=student_id, stage=stage).filter(
        StageObs.dim.is_(None)
    )
    if prompt_index is None:
        matches = matches.filter(StageObs.prompt_index.is_(None))
    else:
        matches = matches.filter(StageObs.prompt_index == prompt_index)
    rows = matches.order_by(StageObs.id).all()
    obs = rows[0] if rows else None
    for extra in rows[1:]:
        db.delete(extra)
    if obs is None:
        obs = StageObs(student_id=student_id, stage=stage, prompt_index=prompt_index, response=response)
        db.add(obs)
    obs.response = response
    note = str(payload.get("note") or "")
    if note:
        obs.note = note
    me = _me(request)
    obs.teacher_id = me.id if me else _coerce_int(payload.get("teacher_id"))
    db.commit()
    tname = ""
    if obs.teacher_id:
        te = db.get(Teacher, obs.teacher_id)
        tname = te.name if te else ""
    return {
        "ok": True,
        "id": obs.id,
        "prompt_index": obs.prompt_index,
        "response": obs.response,
        "note": obs.note,
        "by": tname,
        "time": obs.created_at.strftime("%H:%M"),
    }


@router.post("/stage/delete")
def delete_stage_obs(request: Request, payload: dict = Body(...), db: Session = Depends(get_db)):
    obs = db.get(StageObs, int(payload["id"]))
    if obs:
        if not _can_touch(_me(request), obs.student):
            return JSONResponse(status_code=403, content=FORBIDDEN)
        _lock_student(db, obs.student_id)
        # someone else may have removed it a moment ago: that is fine, it is gone either way
        if db.query(StageObs.id).filter_by(id=obs.id).first():
            db.delete(obs)
            db.commit()
    return {"ok": True}


@router.post("/stage/single")
def upsert_stage_single(request: Request, payload: dict = Body(...), db: Session = Depends(get_db)):
    """Single-state stages: Separation and the general activity stages."""
    student_id = int(payload["student_id"])
    student = db.get(Student, student_id)
    if not student:
        return JSONResponse(status_code=404, content={"ok": False, "error": "student not found"})
    if not _can_touch(_me(request), student):
        return JSONResponse(status_code=403, content=FORBIDDEN)
    _lock_student(db, student_id)
    stage = str(payload.get("stage") or "Separation")
    from ..stage_defs import stage_kind

    pid = student.session.paper_id if student.session else None
    if not pid:
        from ..models import Paper

        first = db.query(Paper.id).order_by(Paper.id).first()
        pid = first[0] if first else None
    allowed = (
        ("independent", "brief", "support", "not_observed", "")
        if stage == "Separation" or stage_kind(db, pid, stage) == "separation"
        else ("independent", "prompted", "none", "")
    )
    rows = (
        db.query(StageObs)
        .filter(
            StageObs.student_id == student_id,
            StageObs.stage == stage,
            StageObs.prompt_index.is_(None),
            StageObs.dim.is_(None),
        )
        .order_by(StageObs.id)
        .all()
    )
    obs = rows[0] if rows else None
    for extra in rows[1:]:
        db.delete(extra)
    if obs is None:
        obs = StageObs(student_id=student_id, stage=stage, response="")
        db.add(obs)
    response = payload.get("response")
    if response is not None:
        if response not in allowed:
            return JSONResponse(status_code=400, content={"ok": False, "error": "bad response"})
        obs.response = response
    if payload.get("note") is not None:
        obs.note = str(payload.get("note") or "")
    me = _me(request)
    obs.teacher_id = (me.id if me else _coerce_int(payload.get("teacher_id"))) or obs.teacher_id
    db.commit()
    tname = ""
    if obs.teacher_id:
        te = db.get(Teacher, obs.teacher_id)
        tname = te.name if te else ""
    return {"ok": True, "id": obs.id, "response": obs.response, "by": tname}


@router.post("/stage/dim")
def upsert_stage_dim(request: Request, payload: dict = Body(...), db: Session = Depends(get_db)):
    """One value per (student, stage, dimension) from the group rubric."""
    from ..stage_defs import paper_dims

    student_id = int(payload["student_id"])
    student = db.get(Student, student_id)
    if not student:
        return JSONResponse(status_code=404, content={"ok": False, "error": "student not found"})
    if not _can_touch(_me(request), student):
        return JSONResponse(status_code=403, content=FORBIDDEN)
    _lock_student(db, student_id)

    stage = str(payload.get("stage") or "")
    dim = str(payload.get("dim") or "")
    value = str(payload.get("value") or "")
    dims = paper_dims(db, student.session.paper_id).get(stage, [])
    entry = next((d for d in dims if d["key"] == dim), None)
    if entry is None:
        return JSONResponse(status_code=400, content={"ok": False, "error": "bad dim"})
    if value and value not in [en for en, _ in entry["options"]]:
        return JSONResponse(status_code=400, content={"ok": False, "error": "bad value"})

    rows = (
        db.query(StageObs)
        .filter(
            StageObs.student_id == student_id,
            StageObs.stage == stage,
            StageObs.dim == dim,
        )
        .order_by(StageObs.id)
        .all()
    )
    obs = rows[0] if rows else None
    for extra in rows[1:]:
        db.delete(extra)
    if obs is None:
        obs = StageObs(student_id=student_id, stage=stage, dim=dim, response="")
        db.add(obs)
    obs.response = value
    me = _me(request)
    obs.teacher_id = (me.id if me else None) or obs.teacher_id
    db.commit()
    return {"ok": True}


@router.post("/review/toggle")
def toggle_review(request: Request, payload: dict = Body(...), db: Session = Depends(get_db)):
    student_id = int(payload["student_id"])
    student = db.get(Student, student_id)
    if not student:
        return JSONResponse(status_code=404, content={"ok": False, "error": "student not found"})
    if not _can_touch(_me(request), student):
        return JSONResponse(status_code=403, content=FORBIDDEN)
    _lock_student(db, student_id)
    row = db.query(Review).filter_by(student_id=student_id).first()
    if row:
        db.delete(row)
        db.commit()
        return {"ok": True, "confirmed": False}
    me = _me(request)
    row = Review(student_id=student_id, teacher_id=(me.id if me else _coerce_int(payload.get("teacher_id"))))
    db.add(row)
    db.commit()
    tname = ""
    if row.teacher_id:
        te = db.get(Teacher, row.teacher_id)
        tname = te.name if te else ""
    return {
        "ok": True,
        "confirmed": True,
        "by": tname,
        "time": row.created_at.strftime("%m-%d %H:%M"),
    }


@router.post("/student/group")
def set_student_group(request: Request, payload: dict = Body(...), db: Session = Depends(get_db)):
    denied = _require_admin(request)
    if denied:
        return denied
    st = db.get(Student, int(payload["student_id"]))
    if not st:
        return JSONResponse(status_code=404, content={"ok": False})
    gid = payload.get("group_id")
    if gid:
        # a group holds one grade only
        other = (db.query(Student.level).filter(Student.group_id == int(gid), Student.id != st.id, Student.level != st.level).first())
        if other:
            from ..i18n import t

            g = db.get(Group, int(gid))
            return JSONResponse(status_code=409, content={"ok": False, "error": "mixed grades", "message": t("gb.mixed").format(
                name=st.name, level=st.level, group=g.name if g else "", other=other[0])})
    st.group_id = int(gid) if gid else None
    db.commit()
    return {"ok": True}


@router.post("/groups/randomize")
def randomize_groups(request: Request, payload: dict = Body(...), db: Session = Depends(get_db)):
    denied = _require_admin(request)
    if denied:
        return denied
    import random

    from .. import bank as qbank
    from ..i18n import t

    sid = int(payload["session_id"])
    s = db.get(AssessSession, sid)
    groups = db.query(Group).filter_by(session_id=sid).order_by(Group.id).all()
    if not s or not groups:
        return JSONResponse(status_code=400, content={"ok": False, "error": "no groups"})
    students = db.query(Student).filter_by(session_id=sid).all()
    plan, unknown = plan_groups(students, groups, qbank.paper_levels(db, s.paper_id or qbank.default_paper_id(db)))
    if plan is None:
        grades = sorted({st.level for st in students if st not in unknown})
        return JSONResponse(status_code=400, content={"ok": False, "error": "too few groups", "message": t("gb.rand_few").format(
            grades=len(grades), names=" / ".join(grades), groups=len(groups))})
    parts = []
    for level, gs, sts in plan:
        random.shuffle(sts)
        for i, st in enumerate(sts):
            st.group_id = gs[i % len(gs)].id
        parts.append(t("gb.rand_part").format(level=level, groups=", ".join(g.name for g in gs), n=len(sts)))
    used = {g.id for _, gs, _ in plan for g in gs}
    for st in unknown:
        st.group_id = None
    db.commit()
    message = t("gb.rand_done") + " " + "; ".join(parts)
    if unknown:
        message += " " + t("gb.rand_unknown").format(n=len(unknown))
    empty = [g.name for g in groups if g.id not in used]
    if empty:
        message += " " + t("gb.rand_empty").format(names=", ".join(empty))
    return {"ok": True, "message": message}


def plan_groups(students, groups, levels):
    """Which groups each grade gets, so that no group mixes grades.

    Returns ([(level, [groups], [students])], [students whose grade is not in the interview]);
    the plan is None when there are fewer groups than grades. Every grade gets at least one group;
    the remaining groups go, one at a time, to the grade with the most children per group, so group
    sizes stay as even as the grades allow (a small grade simply ends up with a smaller group).
    Groups are handed out in list order: the first groups to the first grade, and so on."""
    by_level, unknown = {}, []
    for st in students:
        if st.level in levels:
            by_level.setdefault(st.level, []).append(st)
        else:
            unknown.append(st)
    order = [lv for lv in levels if lv in by_level]
    if not order:
        return [], unknown
    if len(groups) < len(order):
        return None, unknown
    share = {lv: 1 for lv in order}
    for _ in range(len(groups) - len(order)):
        lv = max(order, key=lambda x: (len(by_level[x]) / share[x], -order.index(x)))
        if len(by_level[lv]) <= share[lv]:  # every group of every grade would have at most one child: leave the rest empty
            break
        share[lv] += 1
    plan, i = [], 0
    for lv in order:
        plan.append((lv, groups[i:i + share[lv]], by_level[lv]))
        i += share[lv]
    return plan, unknown


@router.post("/student/level")
def set_student_level(request: Request, payload: dict = Body(...), db: Session = Depends(get_db)):
    denied = _require_admin(request)
    if denied:
        return denied
    st = db.get(Student, int(payload["student_id"]))
    if not st:
        return JSONResponse(status_code=404, content={"ok": False})
    from .. import bank as qbank

    level = str(payload.get("level") or "")
    if level not in qbank.paper_levels(db, st.session.paper_id or qbank.default_paper_id(db)):
        return JSONResponse(status_code=400, content={"ok": False, "error": "bad level"})
    st.level = level
    moved_out = False
    if st.group_id and db.query(Student.id).filter(Student.group_id == st.group_id, Student.id != st.id, Student.level != level).first():
        st.group_id, moved_out = None, True  # its group belongs to another grade now: back to "not grouped"
    db.commit()
    return {"ok": True, "ungrouped": moved_out}


@router.post("/student/email")
def set_student_email(request: Request, payload: dict = Body(...), db: Session = Depends(get_db)):
    from ..i18n import t
    from ..services.mailer import split_emails

    denied = _require_admin(request)
    if denied:
        return denied
    st = db.get(Student, int(payload["student_id"]))
    if not st:
        return JSONResponse(status_code=404, content={"ok": False})
    good, bad = split_emails(str(payload.get("email") or ""))
    if bad:
        return JSONResponse(status_code=400, content={"ok": False, "error": t("msg.email_bad").format(bad=", ".join(bad))})
    value = ", ".join(good)
    if len(value) > 255:
        return JSONResponse(status_code=400, content={"ok": False, "error": "too long"})
    st.parent_email = value
    db.commit()
    return {"ok": True, "email": value}


@router.post("/group/teacher")
def set_group_teacher(request: Request, payload: dict = Body(...), db: Session = Depends(get_db)):
    denied = _require_admin(request)
    if denied:
        return denied
    g = db.get(Group, int(payload["group_id"]))
    if not g:
        return JSONResponse(status_code=404, content={"ok": False})
    tid = payload.get("teacher_id")
    g.teacher_id = int(tid) if tid else None
    db.commit()
    return {"ok": True}
