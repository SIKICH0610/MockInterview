import io
import re
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from ..db import get_db
from ..i18n import t
from ..models import (
    AssessSession,
    Group,
    ItemRecord,
    Paper,
    Question,
    StageDimDef,
    StoryPromptDef,
    Student,
    Teacher,
)
from ..stage_defs import (
    clone_paper_defs,
    ensure_paper_defaults,
    paper_dims,
    paper_prompts,
    slug_key,
)
from ..templating import templates

router = APIRouter(prefix="/admin")


def _redirect(url, msg=None):
    if msg:
        url = f"{url}?msg={quote(msg)}"
    return RedirectResponse(url, status_code=303)


# ---------- sessions ----------

@router.get("/sessions")
def sessions_page(request: Request, msg: str = "", db: Session = Depends(get_db)):
    sessions = db.query(AssessSession).order_by(AssessSession.date.desc()).all()
    counts = {s.id: len(s.students) for s in sessions}
    papers = db.query(Paper).order_by(Paper.id).all()
    paper_names = {p.id: p.name for p in papers}
    return templates.TemplateResponse(
        request,
        "admin_sessions.html",
        {
            "sessions": sessions,
            "counts": counts,
            "papers": papers,
            "paper_names": paper_names,
            "msg": msg,
            "active": "admin",
        },
    )


@router.post("/sessions/create")
def create_session(
    date: str = Form(...),
    label: str = Form(...),
    paper_id: str = Form(""),
    db: Session = Depends(get_db),
):
    pid = int(paper_id) if paper_id else None
    if pid is None:
        p = db.query(Paper).order_by(Paper.id).first()
        pid = p.id if p else None
    s = AssessSession(date=date.strip(), label=label.strip(), paper_id=pid)
    db.add(s)
    db.commit()
    return _redirect(f"/admin/sessions/{s.id}")


@router.post("/sessions/{sid}/delete")
def delete_session(sid: int, db: Session = Depends(get_db)):
    s = db.get(AssessSession, sid)
    if s:
        db.delete(s)
        db.commit()
    return _redirect("/admin/sessions", t("msg.session_deleted"))


@router.get("/sessions/{sid}")
def session_detail(sid: int, request: Request, msg: str = "", db: Session = Depends(get_db)):
    s = db.get(AssessSession, sid)
    if not s:
        return _redirect("/admin/sessions", t("msg.session_not_found"))
    teachers = db.query(Teacher).filter_by(active=True).order_by(Teacher.name).all()
    groups = db.query(Group).filter_by(session_id=sid).order_by(Group.id).all()
    students = db.query(Student).filter_by(session_id=sid).order_by(Student.level, Student.name).all()
    return templates.TemplateResponse(
        request,
        "admin_session_detail.html",
        {
            "s": s,
            "teachers": teachers,
            "groups": groups,
            "students": students,
            "msg": msg,
            "active": "admin",
        },
    )


# ---------- student import ----------

def _detect_level(grade, course):
    text = f"{grade} {course}".upper()
    if "PRE-K" in text or "PREK" in text or re.search(r"\bTK\b", text):
        return "TK"
    if re.search(r"\bK\b", text) or "KINDER" in text:
        return "K"
    return "?"


def _parse_ta_rows(rows):
    """Think Academy class export: userName / 学员id / gradeName / className."""
    header = [h.strip() for h in rows[0]]
    idx = {h: i for i, h in enumerate(header)}

    def col(r, *names):
        for n in names:
            i = idx.get(n)
            if i is not None and i < len(r):
                return str(r[i]).strip()
        return ""

    out, errors = [], []
    skipped_unenrolled = 0
    for rn, r in enumerate(rows[1:], 2):
        name = col(r, "userName") or (col(r, "firstName") + " " + col(r, "lastName")).strip()
        if not name:
            continue
        if col(r, "是否入班") == "否":
            skipped_unenrolled += 1
            continue
        grade = col(r, "gradeName")
        course = col(r, "className")
        out.append(
            {
                "name": name,
                "external_id": col(r, "学员id"),
                "grade": grade,
                "course": course,
                "level": _detect_level(grade, course),
            }
        )
    return out, errors, skipped_unenrolled


def _parse_rows(rows):
    """rows: list of list of str -> (students, errors)."""
    if not rows:
        return [], ["No rows found"]
    header = [c.lower().strip() for c in rows[0]]

    def find(keys):
        for i, h in enumerate(header):
            if any(k in h for k in keys):
                return i
        return None

    ni = find(["name", "姓名"])
    li = find(["level", "grade", "档", "年级"])
    ei = find(["id", "编号", "学号"])
    start = 1 if ni is not None else 0
    if ni is None:
        ni, li, ei = 0, 1, 2

    out, errors = [], []
    for idx, r in enumerate(rows[start:], start + 1):
        name = r[ni].strip() if ni < len(r) else ""
        level = (r[li].strip().upper() if li is not None and li < len(r) else "")
        ext = r[ei].strip() if ei is not None and ei < len(r) else ""
        if not name:
            continue
        if level not in ("TK", "K"):
            errors.append(f"Row {idx} ({name}): level must be TK or K")
            continue
        out.append({"name": name, "level": level, "external_id": ext})
    return out, errors


def _insert_students(db, sid, parsed):
    current = db.query(Student).filter_by(session_id=sid).all()
    existing_ids = {st.external_id for st in current if st.external_id}
    existing_names = {st.name.lower() for st in current}
    added = skipped = 0
    for p in parsed:
        ext = p.get("external_id", "")
        if ext and ext in existing_ids:
            skipped += 1
            continue
        if not ext and p["name"].lower() in existing_names:
            skipped += 1
            continue
        db.add(Student(session_id=sid, **p))
        if ext:
            existing_ids.add(ext)
        existing_names.add(p["name"].lower())
        added += 1
    db.commit()
    return added, skipped


@router.post("/sessions/{sid}/students/upload")
async def upload_students(sid: int, file: UploadFile = File(...), db: Session = Depends(get_db)):
    import csv

    data = await file.read()
    name = (file.filename or "").lower()
    rows = []
    try:
        if name.endswith(".xlsx"):
            import openpyxl

            wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True)
            ws = wb.active
            for r in ws.iter_rows(values_only=True):
                rows.append(["" if c is None else str(c).strip() for c in r])
        else:
            text = None
            for enc in ("utf-8-sig", "gb18030"):
                try:
                    text = data.decode(enc)
                    break
                except UnicodeDecodeError:
                    continue
            if text is None:
                return _redirect(f"/admin/sessions/{sid}", t("msg.decode_err"))
            dialect = csv.excel_tab if "\t" in text.splitlines()[0] else csv.excel
            for r in csv.reader(io.StringIO(text), dialect):
                if any(str(c).strip() for c in r):
                    rows.append([str(c).strip() for c in r])
    except Exception as e:  # noqa: BLE001
        return _redirect(f"/admin/sessions/{sid}", f"{t('msg.import_failed')}: {e}")

    if not rows:
        return _redirect(f"/admin/sessions/{sid}", t("msg.import_failed"))

    header = [str(h).strip() for h in rows[0]]
    unenrolled = 0
    if "userName" in header or "学员id" in header:
        parsed, errors, unenrolled = _parse_ta_rows(rows)
    else:
        parsed, errors = _parse_rows(rows)

    added, skipped = _insert_students(db, sid, parsed)
    unknown = sum(1 for p in parsed if p.get("level") == "?")
    msg = t("msg.imported").format(added=added, skipped=skipped)
    if unenrolled:
        msg += "; " + t("msg.unenrolled").format(n=unenrolled)
    if unknown:
        msg += "; " + t("msg.unknown_level").format(n=unknown)
    if errors:
        msg += f"; {len(errors)} {t('msg.rows_problem')}: " + " | ".join(errors[:3])
    return _redirect(f"/admin/sessions/{sid}", msg)


@router.post("/sessions/{sid}/students/paste")
def paste_students(sid: int, text: str = Form(...), db: Session = Depends(get_db)):
    rows = []
    for line in text.splitlines():
        if line.strip():
            sep = "\t" if "\t" in line else ","
            rows.append([c.strip() for c in line.split(sep)])
    parsed, errors = _parse_rows(rows)
    added, skipped = _insert_students(db, sid, parsed)
    msg = t("msg.imported").format(added=added, skipped=skipped)
    if errors:
        msg += f"; {len(errors)} {t('msg.rows_problem')}: " + " | ".join(errors[:3])
    return _redirect(f"/admin/sessions/{sid}", msg)


@router.post("/sessions/{sid}/students/add")
def add_student(
    sid: int,
    name: str = Form(...),
    level: str = Form(...),
    external_id: str = Form(""),
    db: Session = Depends(get_db),
):
    level = level.strip().upper()
    if level not in ("TK", "K"):
        return _redirect(f"/admin/sessions/{sid}", t("msg.level_err"))
    added, skipped = _insert_students(
        db, sid, [{"name": name.strip(), "level": level, "external_id": external_id.strip()}]
    )
    return _redirect(f"/admin/sessions/{sid}", t("msg.student_added") if added else t("msg.duplicate_skipped"))


@router.post("/students/{stid}/delete")
def delete_student(stid: int, db: Session = Depends(get_db)):
    st = db.get(Student, stid)
    if not st:
        return _redirect("/admin/sessions")
    sid = st.session_id
    db.delete(st)
    db.commit()
    return _redirect(f"/admin/sessions/{sid}", t("msg.student_removed"))


# ---------- groups ----------

@router.get("/sessions/{sid}/grouping")
def grouping_board(sid: int, request: Request, msg: str = "", db: Session = Depends(get_db)):
    s = db.get(AssessSession, sid)
    if not s:
        return _redirect("/admin/sessions", t("msg.session_not_found"))
    teachers = db.query(Teacher).filter_by(active=True).order_by(Teacher.name).all()
    groups = db.query(Group).filter_by(session_id=sid).order_by(Group.id).all()
    students = db.query(Student).filter_by(session_id=sid).order_by(Student.level, Student.name).all()
    pool = [st for st in students if not st.group_id]
    return templates.TemplateResponse(
        request,
        "admin_grouping.html",
        {
            "s": s,
            "teachers": teachers,
            "groups": groups,
            "students": students,
            "pool": pool,
            "msg": msg,
            "active": "admin",
        },
    )


@router.post("/sessions/{sid}/groups/add")
def add_group(
    sid: int,
    name: str = Form(...),
    teacher_id: str = Form(""),
    back: str = Form(""),
    db: Session = Depends(get_db),
):
    g = Group(session_id=sid, name=name.strip(), teacher_id=int(teacher_id) if teacher_id else None)
    db.add(g)
    db.commit()
    target = f"/admin/sessions/{sid}/grouping" if back == "grouping" else f"/admin/sessions/{sid}"
    return _redirect(target)


@router.post("/groups/{gid}/delete")
def delete_group(gid: int, back: str = Form(""), db: Session = Depends(get_db)):
    g = db.get(Group, gid)
    if not g:
        return _redirect("/admin/sessions")
    sid = g.session_id
    for st in g.students:
        st.group_id = None
    db.delete(g)
    db.commit()
    target = f"/admin/sessions/{sid}/grouping" if back == "grouping" else f"/admin/sessions/{sid}"
    return _redirect(target, t("msg.group_deleted"))


# ---------- statistics ----------

@router.get("/stats")
def stats_page(
    request: Request,
    scope: str = "",
    session_id: int = 0,
    stats_paper_id: int = 0,
    date_from: str = "",
    date_to: str = "",
    db: Session = Depends(get_db),
):
    sessions_all = db.query(AssessSession).order_by(AssessSession.date.desc()).all()
    papers = db.query(Paper).order_by(Paper.id).all()
    paper_names = {p.id: p.name for p in papers}

    targets = []
    if scope == "session" and session_id:
        s = db.get(AssessSession, session_id)
        targets = [s] if s else []
    elif scope == "paper" and stats_paper_id:
        targets = db.query(AssessSession).filter_by(paper_id=stats_paper_id).all()
    elif scope == "range" and date_from and date_to:
        q = db.query(AssessSession).filter(
            AssessSession.date >= date_from, AssessSession.date <= date_to
        )
        if stats_paper_id:
            q = q.filter(AssessSession.paper_id == stats_paper_id)
        targets = q.all()

    blocks = []
    if targets:
        from ..models import Event as Ev
        from ..models import ItemRecord as IR

        by_paper = {}
        for s in targets:
            pid = s.paper_id
            if pid:
                by_paper.setdefault(pid, []).append(s.id)

        for pid, sids in by_paper.items():
            qs_all = (
                db.query(Question).filter_by(paper_id=pid).order_by(Question.sort).all()
            )
            by_level = {}
            for q in qs_all:
                by_level.setdefault(q.version, []).append(q)

            for level, qs in by_level.items():
                students = (
                    db.query(Student)
                    .filter(Student.session_id.in_(sids), Student.level == level)
                    .all()
                )
                ids = [st.id for st in students]
                if not ids:
                    continue
                recs = {}
                for r in db.query(IR).filter(IR.student_id.in_(ids)).all():
                    recs[(r.student_id, r.code)] = r
                ev_sums = {}
                for ev in db.query(Ev).filter(Ev.student_id.in_(ids)).all():
                    ev_sums[(ev.student_id, ev.category)] = (
                        ev_sums.get((ev.student_id, ev.category), 0) + ev.points
                    )

                codes = [q.code for q in qs]
                per_student = []
                for st in students:
                    done = sum(1 for c in codes if (st.id, c) in recs and recs[(st.id, c)].status)
                    if done == 0:
                        continue
                    math = eng = expr = 0
                    for q in qs:
                        r = recs.get((st.id, q.code))
                        ok = r and r.status == "scored" and r.academic is not None
                        if ok:
                            if q.domain == "Mathematics":
                                math += r.academic
                            else:
                                eng += r.academic
                        if q.has_expression and r and r.status == "scored" and r.expression is not None:
                            expr += r.expression
                    per_student.append(
                        {
                            "done": done,
                            "math": math,
                            "eng": eng,
                            "expr": expr,
                            "sel": max(0, 50 - ev_sums.get((st.id, "SEL"), 0)),
                            "cs": max(0, 50 - ev_sums.get((st.id, "CS"), 0)),
                        }
                    )
                if not per_student:
                    continue

                n = len(per_student)

                def agg(key):
                    vals = [p[key] for p in per_student]
                    return {
                        "mean": round(sum(vals) / n, 1),
                        "min": min(vals),
                        "max": max(vals),
                    }

                math_max = 2 * sum(1 for q in qs if q.domain == "Mathematics")
                eng_max = 2 * sum(1 for q in qs if q.domain == "English")
                expr_max = 2 * sum(1 for q in qs if q.has_expression)
                complete = sum(1 for p in per_student if p["done"] == len(codes))

                q_stats = []
                for q in qs:
                    rows = [recs.get((sid, q.code)) for sid in ids]
                    scored = [
                        r.academic
                        for r in rows
                        if r and r.status == "scored" and r.academic is not None
                    ]
                    no_n = sum(1 for r in rows if r and r.status == "not_observed")
                    blank = sum(1 for r in rows if not r or not r.status)
                    q_stats.append(
                        {
                            "code": q.code,
                            "title": q.title,
                            "ability": q.ability,
                            "scored_n": len(scored),
                            "mean": round(sum(scored) / len(scored), 2) if scored else None,
                            "indep_pct": round(100 * sum(1 for v in scored if v == 2) / len(scored)) if scored else None,
                            "guided_n": sum(1 for v in scored if v == 1),
                            "no_n": no_n,
                            "blank_n": blank,
                        }
                    )

                blocks.append(
                    {
                        "paper": paper_names.get(pid, ""),
                        "level": level,
                        "sessions_n": len(sids),
                        "n": n,
                        "complete_pct": round(100 * complete / n),
                        "math": agg("math"),
                        "eng": agg("eng"),
                        "expr": agg("expr"),
                        "sel": agg("sel"),
                        "cs": agg("cs"),
                        "math_max": math_max,
                        "eng_max": eng_max,
                        "expr_max": expr_max,
                        "q_stats": q_stats,
                    }
                )

    return templates.TemplateResponse(
        request,
        "admin_stats.html",
        {
            "sessions": sessions_all,
            "papers": papers,
            "scope": scope,
            "sel_session": session_id,
            "sel_paper": stats_paper_id,
            "date_from": date_from,
            "date_to": date_to,
            "blocks": blocks,
            "searched": bool(scope),
            "active": "admin",
        },
    )


# ---------- question papers ----------

@router.get("/papers")
def papers_page(request: Request, msg: str = "", db: Session = Depends(get_db)):
    papers = db.query(Paper).order_by(Paper.id).all()
    stats = {}
    for p in papers:
        versions = sorted({q.version for q in p.questions})
        sessions_using = db.query(AssessSession).filter_by(paper_id=p.id).count()
        stats[p.id] = {"count": len(p.questions), "versions": versions, "sessions": sessions_using}
    return templates.TemplateResponse(
        request,
        "admin_papers.html",
        {"papers": papers, "stats": stats, "msg": msg, "active": "admin"},
    )


@router.post("/papers/create")
def create_paper(name: str = Form(...), clone_from: str = Form(""), db: Session = Depends(get_db)):
    name = name.strip()
    if not name or db.query(Paper).filter_by(name=name).first():
        return _redirect("/admin/papers", t("papers.name_taken"))
    p = Paper(name=name)
    db.add(p)
    db.flush()
    if clone_from:
        src = db.get(Paper, int(clone_from))
        if src:
            for q in src.questions:
                db.add(
                    Question(
                        paper_id=p.id,
                        version=q.version,
                        code=q.code,
                        sort=q.sort,
                        domain=q.domain,
                        ability=q.ability,
                        title=q.title,
                        prompt=q.prompt,
                        target=q.target,
                        setup=q.setup,
                        r2=q.r2,
                        r1=q.r1,
                        r0=q.r0,
                        e2=q.e2,
                        e1=q.e1,
                        e0=q.e0,
                        has_expression=q.has_expression,
                        trial_max=q.trial_max,
                    )
                )
            clone_paper_defs(db, src.id, p.id)
    if not clone_from:
        ensure_paper_defaults(db, p.id)
    db.commit()
    return _redirect(f"/admin/papers/{p.id}")


@router.get("/papers/{pid}")
def paper_detail(pid: int, request: Request, msg: str = "", db: Session = Depends(get_db)):
    p = db.get(Paper, pid)
    if not p:
        return _redirect("/admin/papers")
    questions = (
        db.query(Question).filter_by(paper_id=pid).order_by(Question.version, Question.sort).all()
    )
    by_version = {}
    for q in questions:
        by_version.setdefault(q.version, []).append(q)
    ensure_paper_defaults(db, pid)
    db.commit()
    return templates.TemplateResponse(
        request,
        "admin_paper_detail.html",
        {
            "p": p,
            "by_version": by_version,
            "dims": paper_dims(db, pid),
            "prompts": paper_prompts(db, pid),
            "msg": msg,
            "active": "admin",
        },
    )


@router.post("/papers/{pid}/delete")
def delete_paper(pid: int, db: Session = Depends(get_db)):
    p = db.get(Paper, pid)
    if not p:
        return _redirect("/admin/papers")
    if db.query(AssessSession).filter_by(paper_id=pid).count():
        return _redirect("/admin/papers", t("papers.in_use"))
    for q in list(p.questions):
        db.delete(q)
    db.query(StageDimDef).filter_by(paper_id=pid).delete()
    db.query(StoryPromptDef).filter_by(paper_id=pid).delete()
    db.delete(p)
    db.commit()
    return _redirect("/admin/papers", t("papers.deleted"))


@router.get("/questions/{qid}/edit")
def question_edit(qid: int, request: Request, db: Session = Depends(get_db)):
    q = db.get(Question, qid)
    if not q:
        return _redirect("/admin/papers")
    return templates.TemplateResponse(
        request, "admin_question_edit.html", {"q": q, "active": "admin"}
    )


@router.post("/questions/{qid}/edit")
def question_save(
    qid: int,
    title: str = Form(...),
    prompt: str = Form(""),
    target: str = Form(""),
    setup: str = Form(""),
    domain: str = Form(""),
    ability: str = Form(""),
    r2: str = Form(""),
    r1: str = Form(""),
    r0: str = Form(""),
    e2: str = Form(""),
    e1: str = Form(""),
    e0: str = Form(""),
    has_expression: str = Form(""),
    trial_max: str = Form(""),
    db: Session = Depends(get_db),
):
    q = db.get(Question, qid)
    if not q:
        return _redirect("/admin/papers")
    q.title = title.strip()
    q.prompt = prompt.strip()
    q.target = target.strip()
    q.setup = setup.strip()
    q.domain = domain.strip()
    q.ability = ability.strip()
    q.r2, q.r1, q.r0 = r2.strip(), r1.strip(), r0.strip()
    q.has_expression = bool(has_expression)
    q.e2 = e2.strip() or None
    q.e1 = e1.strip() or None
    q.e0 = e0.strip() or None
    q.trial_max = int(trial_max) if trial_max.strip().isdigit() else None
    db.commit()
    return _redirect(f"/admin/papers/{q.paper_id}", t("q.saved"))


# ---------- group-activity evaluation content (per paper) ----------

def _parse_option_lines(text):
    """One option per line, 'English | 中文' (zh optional), best first."""
    out = []
    for line in (text or "").splitlines():
        line = line.strip()
        if not line:
            continue
        if "|" in line:
            en, _, zh = line.partition("|")
        elif "｜" in line:
            en, _, zh = line.partition("｜")
        else:
            en, zh = line, ""
        en = en.strip()
        if en:
            out.append([en, zh.strip()])
    return out


@router.post("/papers/{pid}/dims")
async def save_paper_dims(pid: int, request: Request, db: Session = Depends(get_db)):
    import json

    p = db.get(Paper, pid)
    if not p:
        return _redirect("/admin/papers")
    form = await request.form()
    stage = str(form.get("stage") or "")
    existing = {
        d.key: d
        for d in db.query(StageDimDef).filter_by(paper_id=pid, stage=stage).all()
    }
    keys = form.getlist("key")
    labels = form.getlist("label")
    labels_zh = form.getlist("label_zh")
    options_texts = form.getlist("options")

    sort = 0
    for key, label, label_zh, opts_text in zip(keys, labels, labels_zh, options_texts):
        label = label.strip()
        row = existing.get(key)
        if row is None:
            continue
        if form.get(f"del_{key}"):
            db.delete(row)
            del existing[key]
            continue
        opts = _parse_option_lines(opts_text)
        if label:
            row.label = label
        row.label_zh = label_zh.strip()
        if len(opts) >= 2:
            row.options = json.dumps(opts, ensure_ascii=False)
        row.sort = sort
        sort += 1

    new_label = str(form.get("new_label") or "").strip()
    new_opts = _parse_option_lines(str(form.get("new_options") or ""))
    if new_label and len(new_opts) >= 2:
        db.add(
            StageDimDef(
                paper_id=pid,
                stage=stage,
                key=slug_key(new_label, set(existing.keys())),
                label=new_label,
                label_zh=str(form.get("new_label_zh") or "").strip(),
                options=json.dumps(new_opts, ensure_ascii=False),
                sort=sort,
            )
        )
    db.commit()
    return _redirect(f"/admin/papers/{pid}", t("papers.dims_saved"))


@router.post("/papers/{pid}/prompts")
def save_paper_prompts(pid: int, text: str = Form(...), db: Session = Depends(get_db)):
    p = db.get(Paper, pid)
    if not p:
        return _redirect("/admin/papers")
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return _redirect(f"/admin/papers/{pid}", t("papers.prompts_empty"))
    db.query(StoryPromptDef).filter_by(paper_id=pid).delete()
    for i, line in enumerate(lines, 1):
        db.add(StoryPromptDef(paper_id=pid, idx=i, text=line))
    db.commit()
    return _redirect(f"/admin/papers/{pid}", t("papers.prompts_saved"))


# ---------- teachers ----------

@router.get("/teachers")
def teachers_page(request: Request, msg: str = "", db: Session = Depends(get_db)):
    teachers = db.query(Teacher).order_by(Teacher.name).all()
    return templates.TemplateResponse(
        request,
        "admin_teachers.html",
        {"teachers": teachers, "msg": msg, "active": "admin"},
    )


@router.post("/teachers/add")
def add_teacher(name: str = Form(...), role: str = Form("teacher"), db: Session = Depends(get_db)):
    name = name.strip()
    if name and not db.query(Teacher).filter_by(name=name).first():
        db.add(Teacher(name=name, role=role))
        db.commit()
    return _redirect("/admin/teachers")


@router.post("/teachers/{tid}/role")
def toggle_teacher_role(tid: int, request: Request, db: Session = Depends(get_db)):
    te = db.get(Teacher, tid)
    me = request.state.teacher
    if not te:
        return _redirect("/admin/teachers")
    if me and te.id == me.id:
        return _redirect("/admin/teachers", t("teachers.cant_self"))
    te.role = "teacher" if te.role == "admin" else "admin"
    db.commit()
    return _redirect("/admin/teachers")


@router.post("/teachers/{tid}/password")
def set_teacher_password(tid: int, password: str = Form(...), db: Session = Depends(get_db)):
    from ..auth import hash_password

    teacher = db.get(Teacher, tid)
    if teacher and password.strip():
        teacher.password_hash = hash_password(password.strip())
        db.commit()
    return _redirect("/admin/teachers", t("teachers.pw_set"))


@router.post("/teachers/{tid}/toggle")
def toggle_teacher(tid: int, db: Session = Depends(get_db)):
    t = db.get(Teacher, tid)
    if t:
        t.active = not t.active
        db.commit()
    return _redirect("/admin/teachers")
