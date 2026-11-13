from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse, Response
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
    sessions = db.query(AssessSession).order_by(AssessSession.date.desc()).all()
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
    if not _grouping_ready(db, s):
        return _gate_redirect(session_id, teacher)
    if stage not in OBS_STAGES:
        stage = "Separation"

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
            "group": group,
            "students": students,
            "stage": stage,
            "obs_stages": OBS_STAGES,
            "obs_by_student": obs_by_student,
            "dimvals": dimvals,
            "stage_dims": paper_dims(db, pid).get(stage, []),
            "prompts": paper_prompts(db, pid),
            "material": db.query(StageMaterial).filter_by(paper_id=pid, stage=stage).first(),
            "stage_media": db.query(QuestionMedia)
            .filter_by(paper_id=pid, stage=stage)
            .order_by(QuestionMedia.sort, QuestionMedia.id)
            .all(),
            "teacher_names": teacher_names,
            "active": "wb",
        },
    )


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
    if not _grouping_ready(db, s):
        return _gate_redirect(session_id, teacher)
    if teacher.role == "admin":
        students = (
            db.query(Student).filter_by(session_id=session_id).order_by(Student.level, Student.name).all()
        )
    else:
        allowed = _allowed_groups(db, session_id, teacher)
        students = sorted(
            [st for g in allowed for st in g.students], key=lambda x: (x.level, x.name)
        )
    _, codes, _ = _paper_questions(db, _paper_id_for(db, s))
    records = _records_map(db, [st.id for st in students])
    progress = {}
    for st in students:
        done = sum(1 for c in codes if (st.id, c) in records and records[(st.id, c)].status)
        progress[st.id] = done
    return templates.TemplateResponse(
        request,
        "wb_list.html",
        {
            "s": s,
            "teacher": teacher,
            "students": students,
            "progress": progress,
            "total": len(codes),
            "active": "wb",
        },
    )


@router.get("/review")
def review_mode(request: Request, session_id: int, db: Session = Depends(get_db)):
    s = db.get(AssessSession, session_id)
    teacher = request.state.teacher
    if not s:
        return RedirectResponse("/wb", status_code=303)
    if not _grouping_ready(db, s):
        return _gate_redirect(session_id, teacher)

    allowed = _allowed_groups(db, session_id, teacher)
    if teacher.role == "admin":
        students = db.query(Student).filter_by(session_id=session_id).all()
    else:
        students = [st for g in allowed for st in g.students]
    ids = [st.id for st in students]
    questions, codes, _ = _paper_questions(db, _paper_id_for(db, s))
    records = _records_map(db, ids)

    sep = {}
    ct_counts = {}
    obs_counts = {}
    obs_stage = {}
    stage_counts = {}  # (student, stage) -> records, one review column per team activity
    if ids:
        for o in db.query(StageObs).filter(StageObs.student_id.in_(ids)).all():
            stage_counts[(o.student_id, o.stage)] = stage_counts.get((o.student_id, o.stage), 0) + 1
            if o.stage == "Separation":
                sep[o.student_id] = o
            elif o.stage == "Story Time":
                ct_counts[o.student_id] = ct_counts.get(o.student_id, 0) + 1
            else:
                obs_counts[o.student_id] = obs_counts.get(o.student_id, 0) + 1
                # "Stages" column links to the first other stage with records
                prev = obs_stage.get(o.student_id)
                if o.stage in OBS_STAGES and (
                    prev is None or OBS_STAGES.index(o.stage) < OBS_STAGES.index(prev)
                ):
                    obs_stage[o.student_id] = o.stage

    ev_counts = {}
    if ids:
        for ev in db.query(Event).filter(Event.student_id.in_(ids)).all():
            ev_counts[ev.student_id] = ev_counts.get(ev.student_id, 0) + 1

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
        elif done > 0 or st.id in sep or st.id in ct_counts or st.id in obs_counts or st.id in ev_counts:
            status[st.id] = "in_progress"
        else:
            status[st.id] = "not_started"

    roster = []
    for g in allowed:
        members = sorted([m for m in students if m.group_id == g.id], key=lambda m: (m.level, m.name))
        if members:
            roster.append((g.name, members))
    if teacher.role == "admin":
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
            "codes": codes,
            "questions": questions,
            "records": records,
            "sep": sep,
            "ct_counts": ct_counts,
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
    return templates.TemplateResponse(
        request,
        "wb_student.html",
        {
            "s": s,
            "st": st,
            "teacher": teacher,
            "qs": qs,
            "records": records,
            "codes": codes,
            "events": events,
            "stages": STAGES,
            "teacher_names": teacher_names,
            "roster": roster,
            "progress": progress,
            "total": len(codes),
            "active": "wb",
        },
    )
