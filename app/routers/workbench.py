from fastapi import APIRouter, Body, Depends, Request
from fastapi.responses import RedirectResponse, Response, StreamingResponse
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import (
    AssessSession,
    Event,
    Group,
    ItemRecord,
    Paper,
    Question,
    QuestionMedia,
    Review,
    SessionArchive,
    StageMaterial,
    StageObs,
    Student,
    Teacher,
)
from ..seed import STAGES
from ..templating import templates

router = APIRouter(prefix="/wb")


def _paper_id_for(db, s):
    if s.paper_id:
        return s.paper_id
    p = db.query(Paper).order_by(Paper.id).first()
    return p.id if p else None


def _paper_questions(db, paper_id):
    """Returns ({version: {code: q}}, [codes in order], {versions})."""
    out = {}
    codes, seen = [], set()
    for q in db.query(Question).filter_by(paper_id=paper_id).order_by(Question.sort).all():
        out.setdefault(q.version, {})[q.code] = q
        if q.code not in seen:
            seen.add(q.code)
            codes.append(q.code)
    return out, codes, set(out.keys())


def _event_stages(db, s):
    """Where an SEL / classroom event can be logged: the interview's team parts + the general ones."""
    from ..stage_defs import paper_stages

    return [p["key"] for p in paper_stages(db, _paper_id_for(db, s))] + [x for x in STAGES if x in ("Station", "Other")]


def _changed_after_review(db, reviews):
    """{student_id: (count, last time)} of result changes made after the child was confirmed."""
    from ..models import ChangeLog

    out = {}
    for stid, rv in reviews.items():
        rows = (
            db.query(ChangeLog.at)
            .filter(ChangeLog.student_id == stid, ChangeLog.at > rv.created_at,
                    ChangeLog.kind.in_(("score", "stage", "event", "comment")))
            .all()
        )
        if rows:
            out[stid] = (len(rows), max(r[0] for r in rows))
    return out


def _stage_guide(stage):
    from ..guides import stage_guide
    from ..i18n import cur_lang

    return stage_guide(stage, zh=cur_lang() == "zh")


def _may_open(db, teacher, s):
    """Teachers may open only sessions in which a group is assigned to them (admins: all)."""
    from ..perm import can_open_session

    return can_open_session(db, teacher, s.id)


def _allowed_groups(db, session_id, teacher):
    groups = db.query(Group).filter_by(session_id=session_id).order_by(Group.id).all()
    if teacher and teacher.role == "admin":
        return groups
    return [g for g in groups if teacher and g.teacher_id == teacher.id]


def _grouping_ready(db, s):
    """Scoring opens only after every student is grouped and has a level
    that exists in the session's paper."""
    students = db.query(Student).filter_by(session_id=s.id).all()
    if not students:
        return False
    if not db.query(Group).filter_by(session_id=s.id).count():
        return False
    _, _, versions = _paper_questions(db, _paper_id_for(db, s))
    return all(st.group_id and st.level in versions for st in students)


def _gate_redirect(session_id, teacher):
    if teacher and teacher.role == "admin":
        return RedirectResponse(f"/admin/sessions/{session_id}/grouping?msg=gate", status_code=303)
    return RedirectResponse(f"/wb?msg=gate&session_id={session_id}", status_code=303)


def _records_map(db, student_ids):
    recs = {}
    if student_ids:
        for r in db.query(ItemRecord).filter(ItemRecord.student_id.in_(student_ids)).all():
            recs[(r.student_id, r.code)] = r
    return recs


@router.get("")
def select_page(request: Request, msg: str = "", session_id: int = 0, db: Session = Depends(get_db)):
    from ..perm import visible_sessions

    sessions = visible_sessions(db, request.state.teacher)  # teachers: only sessions they are assigned to
    return templates.TemplateResponse(
        request,
        "wb_select.html",
        {"sessions": sessions, "selected": session_id, "teacher": request.state.teacher, "msg": msg, "active": "wb"},
    )


@router.get("/group")
def group_redirect(session_id: int = 0):
    """The by-question group-scoring mode was merged into Group activities;
    old links land on the stage page."""
    if session_id:
        return RedirectResponse(f"/wb/stage?session_id={session_id}", status_code=303)
    return RedirectResponse("/wb", status_code=303)


OBS_STAGES = ["Separation", "Self Introduction", "Story Time", "Cutting & Drawing"]


@router.get("/stage")
def stage_mode(
    request: Request,
    session_id: int,
    group_id: int = 0,
    stage: str = "Separation",
    db: Session = Depends(get_db),
):
    s = db.get(AssessSession, session_id)
    teacher = request.state.teacher
    if not s:
        return RedirectResponse("/wb", status_code=303)
    if not _may_open(db, teacher, s):
        return RedirectResponse("/wb?msg=not_assigned", status_code=303)
    if not _grouping_ready(db, s):
        return _gate_redirect(session_id, teacher)
    from ..stage_defs import paper_prompts as _prompts_of, paper_stages

    parts = paper_stages(db, _paper_id_for(db, s))
    if stage not in [p["key"] for p in parts]:
        stage = parts[0]["key"]
    stage_kind = next(p["kind"] for p in parts if p["key"] == stage)
    if stage_kind == "prompts" and not _prompts_of(db, _paper_id_for(db, s), stage):
        stage_kind = "rubric"  # no questions written yet: rate on the rating items only

    groups = _allowed_groups(db, session_id, teacher)
    group = None
    if group_id:
        cand = db.get(Group, group_id)
        if cand and any(g.id == cand.id for g in groups):
            group = cand
    if group is None and groups:
        group = next((g for g in groups if g.teacher_id == teacher.id), groups[0])
    students = sorted(group.students, key=lambda x: (x.level, x.name)) if group else []

    ids = [st.id for st in students]
    obs_rows = []
    if ids:
        obs_rows = (
            db.query(StageObs)
            .filter(StageObs.student_id.in_(ids), StageObs.stage == stage)
            .order_by(StageObs.created_at.desc())
            .all()
        )
    obs_by_student = {}
    dimvals = {}
    for o in obs_rows:
        if o.dim:
            dimvals[(o.student_id, o.dim)] = o.response
        else:
            obs_by_student.setdefault(o.student_id, []).append(o)

    from ..stage_defs import paper_dims, paper_prompts

    pid = _paper_id_for(db, s)
    teacher_names = {t.id: t.name for t in db.query(Teacher).all()}
    return templates.TemplateResponse(
        request,
        "wb_stage.html",
        {
            "s": s,
            "teacher": teacher,
            "groups": groups,
            "my_groups": [g for g in groups if g.teacher_id == teacher.id],
            "other_groups": [g for g in groups if g.teacher_id != teacher.id],
            "viewing_other": bool(group and group.teacher_id != teacher.id),
            "guide": _stage_guide(stage),
            "group": group,
            "students": students,
            "stage": stage,
            "obs_stages": [p["key"] for p in parts],
            "stage_kind": stage_kind,
            "obs_by_student": obs_by_student,
            "dimvals": dimvals,
            "stage_dims": paper_dims(db, pid).get(stage, []),
            "prompts": paper_prompts(db, pid, stage) if stage_kind == "prompts" else [],
            "material": db.query(StageMaterial).filter_by(paper_id=pid, stage=stage).first(),
            "stage_media": db.query(QuestionMedia)
            .filter_by(paper_id=pid, stage=stage)
            .order_by(QuestionMedia.sort, QuestionMedia.id)
            .all(),
            "teacher_names": teacher_names,
            "active": "wb",
        },
    )


@router.get("/live/{sid}")
async def live_stream(sid: int, request: Request):
    """Server-Sent Events: one line per saved change in this session."""
    import asyncio
    import json

    from .. import live
    from ..db import SessionLocal
    from ..perm import can_open_session

    _db = SessionLocal()
    try:
        allowed = can_open_session(_db, request.state.teacher, sid)
    finally:
        _db.close()
    if not allowed:
        return Response(status_code=403)

    entry = live.subscribe()

    async def gen():
        try:
            yield "retry: 3000\n\n"
            yield 'event: hello\ndata: {}\n\n'
            while True:
                if await request.is_disconnected():
                    break
                try:
                    msg = await asyncio.wait_for(entry[1].get(), timeout=20)
                except asyncio.TimeoutError:
                    yield ": ping\n\n"  # keeps nginx / Cloudflare from closing an idle stream
                    continue
                if msg.get("sid") == sid:
                    yield f"data: {json.dumps(msg)}\n\n"
        finally:
            live.unsubscribe(entry)

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"},
    )


@router.get("/live/{sid}/version")
def live_version(sid: int, request: Request, db: Session = Depends(get_db)):
    """Fallback when the stream is unavailable: the page polls this number."""
    from .. import live
    from ..perm import can_open_session

    if not can_open_session(db, request.state.teacher, sid):
        return Response(status_code=403)

    v, rv = live.versions(db, sid)
    return {"v": v, "rv": rv}


PRESENCE_PAGES = ("stage", "student", "list", "review", "grouping")


@router.post("/live/{sid}/beat")
def live_beat(sid: int, request: Request, payload: dict = Body(...), db: Session = Depends(get_db)):
    """An open page says "still here" (about every 20 s): which page, and which version of the
    groups it shows. The grouping board reads this to show who is online (admin.session_presence)."""
    import re
    from datetime import datetime

    from sqlalchemy.exc import IntegrityError

    from ..models import Presence
    from ..perm import can_open_session

    me = request.state.teacher
    if not can_open_session(db, me, sid):
        return Response(status_code=403)
    if getattr(request.state, "admin_return", False):
        return {"ok": True}  # an admin looking through a teacher's account is not that teacher being online
    cid = re.sub(r"[^A-Za-z0-9]", "", str(payload.get("cid") or ""))[:24]
    page = str(payload.get("page") or "")
    if len(cid) < 8 or page not in PRESENCE_PAGES:
        return Response(status_code=400)

    def _int(v):
        try:
            return int(v) if v not in (None, "") else None
        except (TypeError, ValueError):
            return None

    try:
        row = db.get(Presence, cid)
        if row is None:
            row = Presence(client_id=cid)
            db.add(row)
        row.teacher_id, row.session_id, row.page = me.id, sid, page
        row.stage = str(payload.get("stage") or "")[:80]
        row.group_id, row.student_id = _int(payload.get("group_id")), _int(payload.get("student_id"))
        row.rv = _int(payload.get("rv")) or 0
        row.seen_at = datetime.now()
        db.commit()
    except IntegrityError:  # the same tab sent two first beats at once
        db.rollback()
    return {"ok": True}


@router.get("/live/{sid}/where")
def live_where(sid: int, request: Request, ids: str = "", db: Session = Depends(get_db)):
    """Where children are now (name, group, teacher): for the notice a page shows after the groups changed."""
    from ..perm import can_open_session

    if not can_open_session(db, request.state.teacher, sid):
        return Response(status_code=403)
    want = [int(x) for x in ids.split(",") if x.strip().isdigit()][:40]
    if not want:
        return {"items": []}
    names = {x.id: x.name for x in db.query(Teacher).all()}
    items = []
    for st in db.query(Student).filter(Student.session_id == sid, Student.id.in_(want)).all():
        g = st.group
        items.append({"id": st.id, "name": st.name, "group": g.name if g else "",
                      "teacher": names.get(g.teacher_id, "") if g and g.teacher_id else ""})
    return {"items": items}


@router.get("/history")
def history_fragment(request: Request, student_id: int, kind: str = "", ref: str = "", ref_prefix: str = "",
                     db: Session = Depends(get_db)):
    """The change history of one child (optionally one question / activity), as HTML for the popover."""
    from .. import audit

    st = db.get(Student, student_id)
    if not audit.can_view(request.state.teacher, st):
        return Response(status_code=403)
    entries = audit.query(db, student_id=student_id, kind=kind or None, ref=ref or None,
                          ref_prefix=ref_prefix or None, limit=100)
    return templates.TemplateResponse(request, "_history_list.html",
                                      {"entries": audit.describe(db, entries), "show_child": False})


@router.get("/dragasset/{aid}")
def drag_asset(aid: int, db: Session = Depends(get_db)):
    """A picture of a drag-on-tablet task. Never changes once stored, so tablets may keep it."""
    from ..models import DragAsset

    a = db.get(DragAsset, aid)
    if not a:
        return Response(status_code=404)
    return Response(content=a.data, media_type=a.mime,
                    headers={"Cache-Control": "private, max-age=604800, immutable", "X-Content-Type-Options": "nosniff"})


@router.get("/media/{mid}")
def media_file(mid: int, db: Session = Depends(get_db)):
    """A question picture / PDF, for any signed-in teacher (shown on scoring pages)."""
    m = db.get(QuestionMedia, mid)
    if not m:
        return Response(status_code=404)
    safe = "".join(c for c in m.filename if c.isascii() and (c.isalnum() or c in "._- ")) or "file"
    return Response(
        content=m.data,
        media_type=m.mime,
        headers={
            "Content-Disposition": f'inline; filename="{safe}"',
            "Cache-Control": "private, max-age=86400",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/list")
def student_list(request: Request, session_id: int, db: Session = Depends(get_db)):
    s = db.get(AssessSession, session_id)
    teacher = request.state.teacher
    if not s:
        return RedirectResponse("/wb", status_code=303)
    if not _may_open(db, teacher, s):
        return RedirectResponse("/wb?msg=not_assigned", status_code=303)
    if not _grouping_ready(db, s):
        return _gate_redirect(session_id, teacher)
    others = []
    if teacher.role == "admin":
        # an admin's own group(s) first; everyone else's children are kept behind "other teachers' students"
        everyone = db.query(Student).filter_by(session_id=session_id).order_by(Student.level, Student.name).all()
        mine = {g.id for g in _allowed_groups(db, session_id, teacher) if g.teacher_id == teacher.id}
        if mine:
            students = [st for st in everyone if st.group_id in mine]
            others = sorted((st for st in everyone if st.group_id not in mine),
                            key=lambda x: ((x.group.name if x.group else "~"), x.level, x.name))
        else:
            students = everyone
    else:
        allowed = _allowed_groups(db, session_id, teacher)
        students = sorted(
            [st for g in allowed for st in g.students], key=lambda x: (x.level, x.name)
        )
    _, codes, _ = _paper_questions(db, _paper_id_for(db, s))
    records = _records_map(db, [st.id for st in students + others])
    progress = {}
    for st in students + others:
        done = sum(1 for c in codes if (st.id, c) in records and records[(st.id, c)].status)
        progress[st.id] = done
    return templates.TemplateResponse(
        request,
        "wb_list.html",
        {
            "s": s,
            "teacher": teacher,
            "students": students,
            "others": others,
            "teacher_names": {x.id: x.name for x in db.query(Teacher).all()},
            "progress": progress,
            "total": len(codes),
            "active": "wb",
        },
    )


@router.get("/review")
def review_mode(request: Request, session_id: int, view: str = "", db: Session = Depends(get_db)):
    s = db.get(AssessSession, session_id)
    teacher = request.state.teacher
    if not s:
        return RedirectResponse("/wb", status_code=303)
    if not _may_open(db, teacher, s):
        return RedirectResponse("/wb?msg=not_assigned", status_code=303)
    if not _grouping_ready(db, s):
        return _gate_redirect(session_id, teacher)

    allowed = _allowed_groups(db, session_id, teacher)
    counts = None  # admins who also teach a group: (mine, everyone) for the "My group / Everyone" switch
    if teacher.role == "admin":
        students = db.query(Student).filter_by(session_id=session_id).all()
        mine = [g for g in allowed if g.teacher_id == teacher.id]
        if mine:
            mine_ids = {g.id for g in mine}
            counts = (sum(1 for st in students if st.group_id in mine_ids), len(students))
            if view != "all":  # their own children first: that is who they talk to parents about
                view, allowed = "mine", mine
                students = [st for st in students if st.group_id in mine_ids]
    else:
        students = [st for g in allowed for st in g.students]
    ids = [st.id for st in students]
    questions, codes, _ = _paper_questions(db, _paper_id_for(db, s))
    records = _records_map(db, ids)

    from ..stage_defs import paper_stages

    parts = paper_stages(db, _paper_id_for(db, s))  # one review column per team part
    sep_keys = {p["key"] for p in parts if p["kind"] == "separation"}
    sep = {}  # (student, part) -> the single separation-type record
    ct_counts = {}
    obs_counts = {}
    obs_stage = {}
    stage_counts = {}  # (student, part) -> records
    team_any = set()
    if ids:
        for o in db.query(StageObs).filter(StageObs.student_id.in_(ids)).all():
            stage_counts[(o.student_id, o.stage)] = stage_counts.get((o.student_id, o.stage), 0) + 1
            team_any.add(o.student_id)
            if o.stage in sep_keys and not o.dim:
                sep[(o.student_id, o.stage)] = o

    ev_counts = {}
    if ids:
        for ev in db.query(Event).filter(Event.student_id.in_(ids)).all():
            ev_counts[ev.student_id] = ev_counts.get(ev.student_id, 0) + (ev.count or 1)  # times distracted, not records

    reviews = {}
    if ids:
        for r in db.query(Review).filter(Review.student_id.in_(ids)).all():
            reviews[r.student_id] = r

    progress = {}
    status = {}
    for st in students:
        done = sum(1 for c in codes if (st.id, c) in records and records[(st.id, c)].status)
        progress[st.id] = done
        if st.id in reviews:
            status[st.id] = "reviewed"
        elif done == len(codes):
            status[st.id] = "ready"
        elif done > 0 or st.id in team_any or st.id in ev_counts:
            status[st.id] = "in_progress"
        else:
            status[st.id] = "not_started"

    roster = []
    for g in allowed:
        members = sorted([m for m in students if m.group_id == g.id], key=lambda m: (m.level, m.name))
        if members:
            roster.append((g.name, members))
    if teacher.role == "admin" and view != "mine":
        ungrouped = sorted([m for m in students if not m.group_id], key=lambda m: (m.level, m.name))
        if ungrouped:
            roster.append((None, ungrouped))

    archives = (
        db.query(SessionArchive)
        .filter_by(session_id=session_id)
        .order_by(SessionArchive.created_at.desc())
        .limit(5)
        .all()
    )
    teacher_names = {t.id: t.name for t in db.query(Teacher).all()}
    return templates.TemplateResponse(
        request,
        "wb_review.html",
        {
            "s": s,
            "teacher": teacher,
            "roster": roster,
            "view": view,
            "view_counts": counts,
            "codes": codes,
            "questions": questions,
            "records": records,
            "sep": sep,
            "parts": parts,
            "ct_counts": ct_counts,
            "changed_after": _changed_after_review(db, reviews),
            "stage_counts": stage_counts,
            "obs_counts": obs_counts,
            "obs_stage": obs_stage,
            "ev_counts": ev_counts,
            "reviews": reviews,
            "progress": progress,
            "status": status,
            "archives": archives,
            "total": len(codes),
            "teacher_names": teacher_names,
            "active": "wb",
        },
    )


@router.get("/student/{stid}")
def student_mode(request: Request, stid: int, db: Session = Depends(get_db)):
    st = db.get(Student, stid)
    teacher = request.state.teacher
    if not st:
        return RedirectResponse("/wb", status_code=303)
    s = st.session
    if not _grouping_ready(db, s):
        return _gate_redirect(s.id, teacher)
    if teacher.role != "admin" and not (st.group and st.group.teacher_id == teacher.id):
        return RedirectResponse(f"/wb/list?session_id={s.id}", status_code=303)
    questions, codes, _ = _paper_questions(db, _paper_id_for(db, s))
    qs = questions.get(st.level, {})

    if teacher.role == "admin":
        all_students = db.query(Student).filter_by(session_id=s.id).all()
    else:
        all_students = [m for g in _allowed_groups(db, s.id, teacher) for m in g.students]
    records = _records_map(db, [x.id for x in all_students])
    progress = {
        x.id: sum(1 for c in codes if (x.id, c) in records and records[(x.id, c)].status)
        for x in all_students
    }
    roster = []
    for g in _allowed_groups(db, s.id, teacher):
        members = sorted([m for m in all_students if m.group_id == g.id], key=lambda m: (m.level, m.name))
        if members:
            roster.append((g.name, members))
    if teacher.role == "admin":
        ungrouped = sorted([m for m in all_students if not m.group_id], key=lambda m: (m.level, m.name))
        if ungrouped:
            roster.append((None, ungrouped))

    events = (
        db.query(Event).filter_by(student_id=st.id).order_by(Event.created_at.desc()).all()
    )
    teacher_names = {t.id: t.name for t in db.query(Teacher).all()}
    from .. import audit

    history = audit.describe(db, audit.query(db, student_id=st.id, limit=300))
    return templates.TemplateResponse(
        request,
        "wb_student.html",
        {
            "history": history,
            "s": s,
            "st": st,
            "teacher": teacher,
            "qs": qs,
            "records": records,
            "codes": codes,
            "events": events,
            "stages": _event_stages(db, s),
            "teacher_names": teacher_names,
            "roster": roster,
            "progress": progress,
            "total": len(codes),
            "active": "wb",
        },
    )
