import io
import re
from urllib.parse import quote

from fastapi import APIRouter, Body, Depends, File, Form, Request, UploadFile
from fastapi.responses import JSONResponse, RedirectResponse, Response
from sqlalchemy.orm import Session

from ..db import get_db
from ..i18n import t
from .. import bank as qbank
from ..models import (
    AssessSession,
    AudioNote,
    BankActivity,
    BankQuestion,
    EmailLog,
    Event,
    Group,
    ItemRecord,
    Paper,
    PaperStage,
    Question,
    QuestionMedia,
    ReportPdf,
    Review,
    SessionArchive,
    SourcePdf,
    StageMaterial,
    StageDimDef,
    StageObs,
    StoryPromptDef,
    Student,
    Summary,
    Teacher,
)
from ..stage_defs import (
    clone_paper_defs,
    ensure_paper_defaults,
    paper_dims,
    paper_prompts,
    slug_key,
)
from ..services import mailer, pdfsrc
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


@router.post("/sessions/{sid}/rename")
def rename_session(sid: int, label: str = Form(...), date: str = Form(""), back: str = Form(""), db: Session = Depends(get_db)):
    """Change a session's name and / or date. Nothing else about the session changes."""
    s = db.get(AssessSession, sid)
    dest = f"/admin/sessions/{sid}" if back == "detail" else "/admin/sessions"
    if not s:
        return _redirect("/admin/sessions", t("msg.session_not_found"))
    label = " ".join(label.split())[:120]
    if not label:
        return _redirect(dest, t("sessions.rename_empty"))
    date = date.strip()
    if date and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
        return _redirect(dest, t("sessions.rename_bad_date"))
    s.label = label
    if date:
        s.date = date
    db.commit()
    return _redirect(dest, t("sessions.renamed").format(label=label))


@router.post("/sessions/{sid}/delete")
def delete_session(sid: int, db: Session = Depends(get_db)):
    """Delete a whole session: its students, groups and everything recorded for them."""
    s = db.get(AssessSession, sid)
    if s:
        ids = [x for (x,) in db.query(Student.id).filter_by(session_id=sid)]
        if ids:  # email history is not removed with the student automatically
            db.query(EmailLog).filter(EmailLog.student_id.in_(ids)).delete(synchronize_session=False)
        db.delete(s)
        db.commit()
    return _redirect("/admin/sessions", t("msg.session_deleted"))


@router.post("/sessions/{sid}/clear")
def clear_session_results(sid: int, confirm_label: str = Form(""), db: Session = Depends(get_db)):
    """Testing aid: wipe every result recorded in ONE session (scores, observations,
    events, comments, reviews, PDFs, archives, email history). Students, groups and
    teacher assignments stay. The admin must type the session name to confirm."""
    s = db.get(AssessSession, sid)
    if not s:
        return _redirect("/admin/sessions", t("msg.session_not_found"))
    if confirm_label.strip() != s.label.strip():
        return _redirect("/admin/sessions", t("msg.clear_mismatch"))
    ids = [st.id for st in db.query(Student.id).filter_by(session_id=sid)]
    n = 0
    if ids:
        for model in (ItemRecord, StageObs, Event, Summary, Review, ReportPdf, AudioNote, EmailLog):
            n += db.query(model).filter(model.student_id.in_(ids)).delete(synchronize_session=False)
    n += db.query(SessionArchive).filter_by(session_id=sid).delete(synchronize_session=False)
    from ..audit import log_bulk

    log_bulk(db, sid, "clear_results", {"records": [n, 0]})
    db.commit()
    return _redirect("/admin/sessions", t("msg.cleared").format(label=s.label, n=n))


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
            "levels": _session_levels(db, s),
            "s": s,
            "teachers": teachers,
            "groups": groups,
            "students": students,
            "msg": msg,
            "active": "admin",
        },
    )


# ---------- student import ----------

def _session_levels(db, s):
    """Grades of the interview this session uses."""
    return qbank.paper_levels(db, (s.paper_id if s else None) or qbank.default_paper_id(db))


def _detect_level(grade, course, levels=()):
    """Grade from the export's grade / course text: the interview's own grades first, then TK / K."""
    text = f"{grade} {course}".upper()
    for lv in sorted((x for x in levels if x not in ("TK", "K")), key=len, reverse=True):
        if re.search(r"(?<![A-Z0-9])" + re.escape(lv) + r"(?![A-Z0-9])", text):
            return lv
    if "PRE-K" in text or "PREK" in text or re.search(r"\bTK\b", text):
        return "TK"
    if re.search(r"\bK\b", text) or "KINDER" in text:
        return "K"
    return "?"


def _parse_ta_rows(rows, levels=()):
    """Think Academy class export: userName / 学员id / gradeName / className."""
    header = [h.strip() for h in rows[0]]
    idx = {h: i for i, h in enumerate(header)}

    def col(r, *names):
        for n in names:
            i = idx.get(n)
            if i is not None and i < len(r):
                return str(r[i]).strip()
        return ""

    email_cols = [h for h in header if "email" in h.lower() or "邮箱" in h]
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
                "level": _detect_level(grade, course, levels),
                "parent_email": _join_emails(col(r, h) for h in email_cols),
            }
        )
    return out, errors, skipped_unenrolled


def _is_order_export(header):
    """Mall order export: one row per paid registration, with the parent's
    registration-form answers ("Child's Full Name", grade applying for)."""
    low = [h.lower() for h in header]
    return any("child" in h and "full name" in h for h in low)


def _join_emails(values):
    """Valid, de-duplicated addresses from several cells -> 'a@x.com, b@y.com'."""
    good, _bad = mailer.split_emails(", ".join(v for v in values if v))
    return ", ".join(good)[:255]


def _clean_name(name):
    """Collapse spaces and capitalise each word's first letter ("zoey li" -> "Zoey Li");
    the rest of each word is kept as typed (McKenzie, RyanHou)."""
    words = name.split()
    return " ".join(w[:1].upper() + w[1:] for w in words)


def _parse_order_rows(rows, levels=()):
    """Order export. 学生姓名 there is the *account* name (often a parent's name,
    email or phone number), so the child's name comes from the form answer
    "Child's Full Name"; level from "Which grade is your child applying for";
    the student uid is the id (one child can hold several orders)."""
    header = [h.strip() for h in rows[0]]
    low = [h.lower() for h in header]

    def find(pred):
        return next((i for i, h in enumerate(low) if pred(h)), None)

    ci = find(lambda h: "child" in h and "full name" in h)
    gi = find(lambda h: "grade" in h)
    ui = find(lambda h: h in ("学生uid", "学员id"))
    ai = find(lambda h: h == "学生姓名")
    si = find(lambda h: h == "订单状态")
    # parent email typed in the registration form first, then the account email
    fi = find(lambda h: "email" in h and ("parent" in h or "guardian" in h))
    mi = find(lambda h: h == "邮箱")

    def col(r, i):
        return str(r[i]).strip() if i is not None and i < len(r) else ""

    out, errors = [], []
    for rn, r in enumerate(rows[1:], 2):
        name = _clean_name(col(r, ci) or col(r, ai))
        if not name:
            continue
        status = col(r, si)
        if any(k in status for k in ("退", "取消", "关闭")):
            errors.append(f"Row {rn} ({name}): order {status}")
            continue
        grade = col(r, gi)
        out.append(
            {
                "name": name,
                "external_id": col(r, ui),
                "grade": grade,
                "level": _detect_level(grade, "", levels),
                "parent_email": _join_emails([col(r, fi), col(r, mi)]),
            }
        )
    return out, errors


def _parse_rows(rows, levels=("TK", "K")):
    """rows: list of list of str -> (students, errors). levels = grades of the session's interview."""
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
    mi = find(["email", "邮箱", "mail"])
    start = 1 if ni is not None else 0
    if ni is None:
        # no header: name, level, id, email
        ni, li, ei, mi = 0, 1, 2, 3

    out, errors = [], []
    for idx, r in enumerate(rows[start:], start + 1):
        name = r[ni].strip() if ni < len(r) else ""
        level = (r[li].strip().upper() if li is not None and li < len(r) else "")
        ext = r[ei].strip() if ei is not None and ei < len(r) else ""
        email = _join_emails([r[mi]]) if mi is not None and mi < len(r) else ""
        if not name:
            continue
        if level not in levels:
            errors.append(f"Row {idx} ({name}): level must be {' / '.join(levels)}")
            continue
        out.append({"name": name, "level": level, "external_id": ext, "parent_email": email})
    return out, errors


def _insert_students(db, sid, parsed):
    """Adds new students; a duplicate (same id, or same name when there is no id)
    is skipped, but fills in the parent email if that student has none yet.
    Returns (added, skipped, emails_filled)."""
    current = db.query(Student).filter_by(session_id=sid).all()
    by_id = {st.external_id: st for st in current if st.external_id}
    by_name = {st.name.lower(): st for st in current}
    added = skipped = filled = 0
    for p in parsed:
        ext = p.get("external_id", "")
        dup = by_id.get(ext) if ext else by_name.get(p["name"].lower())
        if dup is not None:
            skipped += 1
            if p.get("parent_email") and not (dup.parent_email or "").strip():
                dup.parent_email = p["parent_email"]
                filled += 1
            continue
        st = Student(session_id=sid, **p)
        db.add(st)
        if ext:
            by_id[ext] = st
        by_name[p["name"].lower()] = st
        added += 1
    db.commit()
    return added, skipped, filled


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
    levels = _session_levels(db, db.get(AssessSession, sid))
    if _is_order_export(header):
        parsed, errors = _parse_order_rows(rows, levels)
    elif "userName" in header or "学员id" in header:
        parsed, errors, unenrolled = _parse_ta_rows(rows, levels)
    else:
        parsed, errors = _parse_rows(rows, levels)

    added, skipped, filled = _insert_students(db, sid, parsed)
    unknown = sum(1 for p in parsed if p.get("level") == "?")
    msg = t("msg.imported").format(added=added, skipped=skipped)
    if filled:
        msg += "; " + t("msg.emails_filled").format(n=filled)
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
    parsed, errors = _parse_rows(rows, _session_levels(db, db.get(AssessSession, sid)))
    added, skipped, filled = _insert_students(db, sid, parsed)
    msg = t("msg.imported").format(added=added, skipped=skipped)
    if filled:
        msg += "; " + t("msg.emails_filled").format(n=filled)
    if errors:
        msg += f"; {len(errors)} {t('msg.rows_problem')}: " + " | ".join(errors[:3])
    return _redirect(f"/admin/sessions/{sid}", msg)


@router.post("/sessions/{sid}/students/add")
def add_student(
    sid: int,
    name: str = Form(...),
    level: str = Form(...),
    external_id: str = Form(""),
    parent_email: str = Form(""),
    db: Session = Depends(get_db),
):
    level = level.strip().upper()
    levels = _session_levels(db, db.get(AssessSession, sid))
    if level not in levels:
        return _redirect(f"/admin/sessions/{sid}", t("msg.level_err").format(levels=" / ".join(levels)))
    good, bad = mailer.split_emails(parent_email)
    if bad:
        return _redirect(f"/admin/sessions/{sid}", t("msg.email_bad").format(bad=", ".join(bad)))
    added, skipped, _filled = _insert_students(
        db, sid,
        [{"name": name.strip(), "level": level, "external_id": external_id.strip(),
          "parent_email": ", ".join(good)}],
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
            "levels": _session_levels(db, s),
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


def _next_group_names(existing, n):
    """n new letter names that continue the session's own style: "A" -> "B", "Group A" -> "Group B"."""
    prefix = "Group "
    for name in existing:
        m = re.fullmatch(r"(.*?)([A-Z])", name.strip())
        if m and (m.group(1) == "" or m.group(1).endswith(" ")):
            prefix = m.group(1)
            break
    taken, out = {x.strip().lower() for x in existing}, []
    letters = [chr(c) for c in range(ord("A"), ord("Z") + 1)]
    pool = letters + [a + b for a in letters for b in letters]
    for x in pool:
        if len(out) >= n:
            break
        if (prefix + x).lower() not in taken:
            out.append(prefix + x)
    return out


@router.post("/sessions/{sid}/groups/bulk")
async def add_groups_for_teachers(sid: int, request: Request, db: Session = Depends(get_db)):
    """One new group per ticked teacher (teachers who already have a group in this session are skipped)."""
    s = db.get(AssessSession, sid)
    if not s:
        return _redirect("/admin/sessions", t("msg.session_not_found"))
    form = await request.form()
    ids = []
    for x in form.getlist("teacher_id"):
        if str(x).isdigit() and int(x) not in ids:
            ids.append(int(x))
    groups = db.query(Group).filter_by(session_id=sid).all()
    have = {g.teacher_id for g in groups if g.teacher_id}
    picked = [te for te in (db.get(Teacher, i) for i in ids) if te and te.active and te.id not in have]
    if not picked:
        return _redirect(f"/admin/sessions/{sid}", t("groups.bulk_none"))
    existing = [g.name for g in groups]
    if form.get("naming") == "teacher":
        names, taken = [], {x.strip().lower() for x in existing}
        for te in picked:
            name, k = te.name.strip()[:60], 2
            while name.lower() in taken:
                name, k = f"{te.name.strip()[:56]} {k}", k + 1
            taken.add(name.lower())
            names.append(name)
    else:
        names = _next_group_names(existing, len(picked))
    for te, name in zip(picked, names):
        db.add(Group(session_id=sid, name=name, teacher_id=te.id))
    db.commit()
    return _redirect(f"/admin/sessions/{sid}", t("groups.bulk_done").format(n=len(names), names=", ".join(names)))


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
        versions = qbank.paper_levels(db, p.id)  # the interview's grades, in its own order
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
    p = Paper(name=name, levels=",".join(qbank.LEVELS))
    db.add(p)
    db.flush()
    if clone_from:
        src = db.get(Paper, int(clone_from))
        if src:
            p.levels = ",".join(qbank.paper_levels(db, src.id))
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
                        qtype=qbank.qtype_of(q),
                        bank_id=q.bank_id,
                        **{f: getattr(q, f) for f in qbank.EXTRA_FIELDS},
                        media=[
                            QuestionMedia(filename=m.filename, caption=m.caption or "", mime=m.mime, data=m.data,
                                          size=m.size, sort=m.sort)
                            for m in q.media
                        ],
                    )
                )
            clone_paper_defs(db, src.id, p.id)
            for m in db.query(StageMaterial).filter_by(paper_id=src.id):
                db.add(StageMaterial(paper_id=p.id, stage=m.stage, title=m.title, text=m.text, activity_id=m.activity_id))
            for m in db.query(QuestionMedia).filter_by(paper_id=src.id):
                db.add(QuestionMedia(paper_id=p.id, stage=m.stage, filename=m.filename, caption=m.caption or "", mime=m.mime,
                                     data=m.data, size=m.size, sort=m.sort))
    if not clone_from:
        ensure_paper_defaults(db, p.id)
    db.commit()
    return _redirect(f"/admin/papers/{p.id}/build")


def _paper_ctx(db, p):
    """Everything the interview pages show: sections, team stems, rubric, lock state."""
    pid = p.id
    questions = (
        db.query(Question).filter_by(paper_id=pid).order_by(Question.version, Question.sort).all()
    )
    levels = qbank.paper_levels(db, pid)
    sections = {lv: {dom: [] for dom in qbank.DOMAINS} for lv in levels}
    for q in questions:
        sections.setdefault(q.version, {}).setdefault(q.domain, []).append(q)
    ensure_paper_defaults(db, pid)
    db.commit()
    from ..stage_defs import STAGE_KINDS, paper_stages

    parts = paper_stages(db, pid)
    materials = {m.stage: m for m in db.query(StageMaterial).filter_by(paper_id=pid)}
    stage_media = {}
    for m in db.query(QuestionMedia).filter_by(paper_id=pid).order_by(QuestionMedia.sort, QuestionMedia.id):
        stage_media.setdefault(m.stage, []).append(m)
    return {
        "p": p,
        "sections": sections,
        "locked": qbank.paper_locked(db, pid),
        "dims": paper_dims(db, pid),
        "prompts": paper_prompts(db, pid),
        "prompts_by": {x["key"]: paper_prompts(db, pid, x["key"]) for x in parts if x["kind"] == "prompts"},
        "obs_stages": [x["key"] for x in parts],
        "parts": parts,
        "stage_kinds": STAGE_KINDS,
        "levels": levels,
        "more_levels": [x for x in qbank.all_levels(db) if x not in levels],
        "level_scored": {lv: qbank.level_scored(db, pid, lv) for lv in levels},
        "materials": materials,
        "stage_media": stage_media,
        "active": "admin",
    }


@router.get("/papers/{pid}")
def paper_detail(pid: int, request: Request, msg: str = "", db: Session = Depends(get_db)):
    p = db.get(Paper, pid)
    if not p:
        return _redirect("/admin/papers")
    ctx = _paper_ctx(db, p)
    ctx.update(other_papers=db.query(Paper).filter(Paper.id != pid).order_by(Paper.id).all(), msg=msg)
    return templates.TemplateResponse(request, "admin_paper_detail.html", ctx)


# ---------- drag-and-drop builder ----------

@router.get("/papers/{pid}/build")
def paper_builder(pid: int, request: Request, msg: str = "", db: Session = Depends(get_db)):
    p = db.get(Paper, pid)
    if not p:
        return _redirect("/admin/papers")
    from sqlalchemy import func

    ctx = _paper_ctx(db, p)
    media_q = dict(db.query(QuestionMedia.bank_id, func.count()).filter(QuestionMedia.bank_id.isnot(None)).group_by(QuestionMedia.bank_id).all())
    media_a = dict(db.query(QuestionMedia.activity_id, func.count()).filter(QuestionMedia.activity_id.isnot(None)).group_by(QuestionMedia.activity_id).all())
    ctx.update(
        bank_questions=db.query(BankQuestion).order_by(BankQuestion.domain.desc(), BankQuestion.level, BankQuestion.title).all(),
        bank_activities=db.query(BankActivity).order_by(BankActivity.stage, BankActivity.title).all(),
        media_q=media_q, media_a=media_a, qtypes=qbank.QTYPES, domains=qbank.DOMAINS, all_levels=qbank.all_levels(db), msg=msg,
    )
    return templates.TemplateResponse(request, "admin_builder.html", ctx)


@router.get("/papers/{pid}/build/outline")
def builder_outline(pid: int, request: Request, db: Session = Depends(get_db)):
    p = db.get(Paper, pid)
    if not p:
        return Response(status_code=404)
    return templates.TemplateResponse(request, "_builder_outline.html", _paper_ctx(db, p))


@router.get("/papers/{pid}/preview")
def paper_preview(pid: int, request: Request, fragment: int = 0, db: Session = Depends(get_db)):
    p = db.get(Paper, pid)
    if not p:
        return _redirect("/admin/papers")
    ctx = _paper_ctx(db, p)
    ctx["fragment"] = bool(fragment)
    return templates.TemplateResponse(request, "_paper_preview.html" if fragment else "admin_paper_preview.html", ctx)


def _build_err(code, key):
    return JSONResponse(status_code=code, content={"ok": False, "error": t(key)})


@router.post("/papers/{pid}/build/add")
def builder_add(pid: int, payload: dict = Body(...), db: Session = Depends(get_db)):
    """Drop a bank question into a section (optionally at a position)."""
    b = db.get(BankQuestion, int(payload.get("bank_id") or 0))
    version = str(payload.get("version") or "")
    if not db.get(Paper, pid) or not b or version not in qbank.paper_levels(db, pid):
        return _build_err(404, "build.err_missing")
    if qbank.paper_locked(db, pid):
        return _build_err(409, "papers.locked_msg")
    idx = payload.get("index")
    q = qbank.add_at(db, b, pid, version, int(idx) if isinstance(idx, int) or str(idx).isdigit() else None)
    db.commit()
    return {"ok": True, "id": q.id, "code": q.code}


@router.post("/papers/{pid}/build/reorder")
def builder_reorder(pid: int, payload: dict = Body(...), db: Session = Depends(get_db)):
    version, domain = str(payload.get("version") or ""), str(payload.get("domain") or "")
    if not db.get(Paper, pid) or version not in qbank.paper_levels(db, pid) or domain not in qbank.DOMAINS:
        return _build_err(404, "build.err_missing")
    if qbank.paper_locked(db, pid):
        return _build_err(409, "papers.locked_msg")
    ids = [int(i) for i in (payload.get("ids") or []) if str(i).isdigit()]
    qbank.reorder(db, pid, version, domain, ids)
    db.commit()
    return {"ok": True}


@router.post("/papers/{pid}/build/remove")
def builder_remove(pid: int, payload: dict = Body(...), db: Session = Depends(get_db)):
    q = db.get(Question, int(payload.get("question_id") or 0))
    if not q or q.paper_id != pid:
        return _build_err(404, "build.err_missing")
    if qbank.paper_locked(db, pid):
        return _build_err(409, "papers.locked_msg")
    qbank.remove_question(db, q)
    db.commit()
    return {"ok": True}


@router.post("/papers/{pid}/build/stage")
def builder_stage(pid: int, payload: dict = Body(...), db: Session = Depends(get_db)):
    """Drop a team stem onto its activity, or clear the activity's stem."""
    if not db.get(Paper, pid):
        return _build_err(404, "build.err_missing")
    keys = _paper_stage_keys(db, pid)
    stage = str(payload.get("stage") or "")
    if payload.get("clear"):
        if stage not in keys:
            return _build_err(404, "build.err_missing")
        qbank.clear_stage_stem(db, pid, stage)
    else:
        a = db.get(BankActivity, int(payload.get("activity_id") or 0))
        if not a:
            return _build_err(404, "build.err_missing")
        stage = stage or a.stage
        if stage not in keys:
            return _build_err(404, "build.err_no_part")
        qbank.set_stage_stem(db, pid, a, stage)
    db.commit()
    return {"ok": True}


@router.post("/papers/{pid}/levels/add")
async def level_add(pid: int, request: Request, db: Session = Depends(get_db)):
    """Add a grade (TK, K, G1 …) to this interview, optionally copying another grade's questions."""
    if not db.get(Paper, pid):
        return _redirect("/admin/papers")
    form = await request.form()
    back, copy_from = str(form.get("back") or ""), str(form.get("copy_from") or "")
    # the typed name and a quick "＋ TK" button share the field name: a clicked button wins
    names = [str(x) for x in form.getlist("level") if str(x).strip()]
    lv = qbank.norm_level(names[-1] if names else "")
    if not lv:
        return _redirect(_part_back(pid, back), t("grades.bad_name"))
    if not qbank.add_level(db, pid, lv, copy_from):
        return _redirect(_part_back(pid, back), t("grades.exists").format(level=lv))
    db.commit()
    return _redirect(_part_back(pid, back), t("grades.added").format(level=lv))


@router.post("/papers/{pid}/levels/remove")
def level_remove(pid: int, level: str = Form(...), back: str = Form(""), db: Session = Depends(get_db)):
    """Take a grade out of this interview. Refused once children of that grade have scores."""
    if not db.get(Paper, pid):
        return _redirect("/admin/papers")
    levels = qbank.paper_levels(db, pid)
    if level not in levels:
        return _redirect(_part_back(pid, back))
    if len(levels) <= 1:
        return _redirect(_part_back(pid, back), t("grades.last"))
    if qbank.level_scored(db, pid, level):
        return _redirect(_part_back(pid, back), t("grades.in_use").format(level=level))
    qbank.remove_level(db, pid, level)
    db.commit()
    return _redirect(_part_back(pid, back), t("grades.removed").format(level=level))


def _forget_labels():
    from ..i18n import forget_stage_labels

    forget_stage_labels()


def _part_back(pid, back):
    return back if back.startswith(f"/admin/papers/{pid}") else f"/admin/papers/{pid}/build"


def _part_records(db, pid, key):
    """How many saved observations / events use this part in sessions of this interview."""
    from ..models import Event, StageObs

    sess = db.query(AssessSession.id)
    if pid == qbank.default_paper_id(db):
        sess = sess.filter((AssessSession.paper_id == pid) | (AssessSession.paper_id.is_(None)))
    else:
        sess = sess.filter(AssessSession.paper_id == pid)
    studs = db.query(Student.id).filter(Student.session_id.in_(sess))
    return (db.query(StageObs).filter(StageObs.stage == key, StageObs.student_id.in_(studs)).count()
            + db.query(Event).filter(Event.stage == key, Event.student_id.in_(studs)).count())


@router.post("/papers/{pid}/parts/add")
def part_add(pid: int, label: str = Form(...), label_zh: str = Form(""), kind: str = Form("rubric"),
             back: str = Form(""), db: Session = Depends(get_db)):
    from ..stage_defs import add_stage

    if not db.get(Paper, pid) or not label.strip():
        return _redirect(_part_back(pid, back))
    row = add_stage(db, pid, label, label_zh, kind)
    db.commit()
    _forget_labels()
    return _redirect(_part_back(pid, back), t("parts.added").format(name=row.label))


@router.post("/papers/{pid}/parts/{sid}/rename")
def part_rename(pid: int, sid: int, label: str = Form(...), label_zh: str = Form(""), back: str = Form(""),
                db: Session = Depends(get_db)):
    row = db.get(PaperStage, sid)
    if row and row.paper_id == pid and label.strip():
        row.label, row.label_zh = label.strip()[:80], label_zh.strip()[:80]
        db.commit()
    _forget_labels()
    return _redirect(_part_back(pid, back))


@router.post("/papers/{pid}/parts/{sid}/move")
def part_move(pid: int, sid: int, step: int = Form(...), back: str = Form(""), db: Session = Depends(get_db)):
    rows = db.query(PaperStage).filter_by(paper_id=pid).order_by(PaperStage.sort, PaperStage.id).all()
    i = next((n for n, r in enumerate(rows) if r.id == sid), None)
    if i is not None:
        j = i + (-1 if step < 0 else 1)
        if 0 <= j < len(rows):
            rows[i], rows[j] = rows[j], rows[i]
            for n, r in enumerate(rows):
                r.sort = n
            db.commit()
    return _redirect(_part_back(pid, back))


@router.post("/papers/{pid}/parts/{sid}/delete")
def part_delete(pid: int, sid: int, back: str = Form(""), db: Session = Depends(get_db)):
    """Remove a team part from this interview. Refused while children have records in it."""
    row = db.get(PaperStage, sid)
    if not row or row.paper_id != pid:
        return _redirect(_part_back(pid, back))
    if db.query(PaperStage).filter_by(paper_id=pid).count() <= 1:
        return _redirect(_part_back(pid, back), t("parts.last"))
    n = _part_records(db, pid, row.key)
    if n:
        return _redirect(_part_back(pid, back), t("parts.in_use").format(n=n))
    key = row.key
    db.query(StageDimDef).filter_by(paper_id=pid, stage=key).delete()
    db.query(StageMaterial).filter_by(paper_id=pid, stage=key).delete()
    db.query(QuestionMedia).filter_by(paper_id=pid, stage=key).delete()
    for sp in db.query(StoryPromptDef).filter_by(paper_id=pid).all():
        if (sp.stage or "Story Time") == key:
            db.delete(sp)
    db.delete(row)
    db.commit()
    _forget_labels()
    return _redirect(_part_back(pid, back), t("parts.removed"))


@router.post("/papers/{pid}/rename")
def paper_rename(pid: int, name: str = Form(...), back: str = Form(""), db: Session = Depends(get_db)):
    p = db.get(Paper, pid)
    name = " ".join(name.split())[:120]
    dest = back if back.startswith("/admin/papers") else f"/admin/papers/{pid}"
    if not p or not name:
        return _redirect(dest)
    if db.query(Paper).filter(Paper.name == name, Paper.id != pid).first():
        return _redirect(dest, t("papers.name_taken"))
    p.name = name
    db.commit()
    return _redirect(dest)


@router.post("/papers/{pid}/delete")
def delete_paper(pid: int, db: Session = Depends(get_db)):
    p = db.get(Paper, pid)
    if not p:
        return _redirect("/admin/papers")
    using = db.query(AssessSession).filter_by(paper_id=pid).order_by(AssessSession.date).all()
    if pid == qbank.default_paper_id(db):  # sessions saved before interviews existed fall back to the first one
        using += db.query(AssessSession).filter(AssessSession.paper_id.is_(None)).all()
    if using:
        names = ", ".join(f"{x.date} · {x.label}" for x in using[:5]) + (" …" if len(using) > 5 else "")
        return _redirect("/admin/papers", t("papers.in_use_by").format(name=p.name, n=len(using), sessions=names))
    if db.query(Paper).count() <= 1:
        return _redirect("/admin/papers", t("papers.last"))
    for q in list(p.questions):
        db.delete(q)
    db.query(StageDimDef).filter_by(paper_id=pid).delete()
    db.query(StoryPromptDef).filter_by(paper_id=pid).delete()
    db.query(PaperStage).filter_by(paper_id=pid).delete()
    db.query(StageMaterial).filter_by(paper_id=pid).delete()
    db.query(QuestionMedia).filter_by(paper_id=pid).delete()
    db.delete(p)
    db.commit()
    return _redirect("/admin/papers", t("papers.deleted"))


# ---------- question form helpers (bank entries and interview questions share one form) ----------

def _read_uploads(files):
    """[(filename, mime, bytes)] for the valid uploads, plus a list of rejected names."""
    good, bad = [], []
    for f in files or []:
        if not f or not f.filename:
            continue
        data = f.file.read(qbank.MAX_MEDIA_BYTES + 1)
        mime = qbank.sniff_media(f.filename, data)
        if not data or mime is None or len(data) > qbank.MAX_MEDIA_BYTES:
            bad.append(f.filename)
            continue
        good.append((f.filename[-200:], mime, data))
    return good, bad


def _add_uploads(db, uploads, **owner):
    start = db.query(QuestionMedia).filter_by(**owner).count()
    for i, (name, mime, data) in enumerate(uploads):
        db.add(QuestionMedia(filename=name, mime=mime, data=data, size=len(data), sort=start + i, **owner))


def _fill_question(obj, form, qtype_allowed=True):
    """Copy the shared form fields onto a Question or BankQuestion."""
    obj.title = (form.get("title") or "").strip()[:160]
    obj.domain = form.get("domain") if form.get("domain") in qbank.DOMAINS else obj.domain or "Mathematics"
    obj.ability = (form.get("ability") or "").strip()[:48]
    for f in ("prompt", "target", "setup", "r2", "r1", "r0"):
        setattr(obj, f, (form.get(f) or "").strip())
    for f in qbank.EXTRA_FIELDS:
        if f in form:  # older forms without these fields leave them untouched
            v = (form.get(f) or "").strip()
            setattr(obj, f, v[:255] if f in ("ta_lesson", "ccss_module", "ccss_codes") else v)
    if qtype_allowed:
        tm = str(form.get("trial_max") or "").strip()
        qbank.apply_qtype(obj, form.get("qtype"), int(tm) if tm.isdigit() and 0 < int(tm) <= 30 else None)
    if qbank.qtype_of(obj) == "expr":
        obj.e2 = (form.get("e2") or "").strip() or None
        obj.e1 = (form.get("e1") or "").strip() or None
        obj.e0 = (form.get("e0") or "").strip() or None


def _qform(request, ctx):
    from ..i18n import t as _t  # noqa: F401

    base = {
        "qtypes": qbank.QTYPES,
        "domains": qbank.DOMAINS,
        "levels": ctx.pop("_levels"),
        "abilities": ctx.pop("_db_abilities"),
        "defaults": {qt: qbank.default_rubric(qt) for qt in qbank.QTYPES},
        "active": "admin",
    }
    base.update(ctx)
    return templates.TemplateResponse(request, "admin_qform.html", base)


def _upload_msg(bad):
    return ("; " + t("bank.bad_files").format(names=", ".join(bad))) if bad else ""


# ---------- question bank ----------

@router.get("/bank")
def bank_page(
    request: Request,
    domain: str = "",
    level: str = "",
    qtype: str = "",
    ability: str = "",
    q: str = "",
    pick: int = 0,
    version: str = "",
    msg: str = "",
    db: Session = Depends(get_db),
):
    from sqlalchemy import func, or_

    query = db.query(BankQuestion)
    if domain in qbank.DOMAINS:
        query = query.filter(BankQuestion.domain == domain)
    if level in qbank.all_levels(db):
        query = query.filter(or_(BankQuestion.level == level, BankQuestion.level == ""))
    if qtype in qbank.QTYPES:
        query = query.filter(BankQuestion.qtype == qtype)
    if ability:
        query = query.filter(BankQuestion.ability == ability)
    if q.strip():
        like = f"%{q.strip().lower()}%"
        query = query.filter(
            or_(
                func.lower(BankQuestion.title).like(like),
                func.lower(BankQuestion.prompt).like(like),
                func.lower(BankQuestion.tags).like(like),
                func.lower(BankQuestion.ability).like(like),
            )
        )
    items = query.order_by(BankQuestion.domain.desc(), BankQuestion.ability, BankQuestion.title).all()
    ids = [b.id for b in items]
    used, media_n = {}, {}
    if ids:
        for bid, n in db.query(Question.bank_id, func.count(func.distinct(Question.paper_id))).filter(
            Question.bank_id.in_(ids)
        ).group_by(Question.bank_id):
            used[bid] = n
        for bid, n in db.query(QuestionMedia.bank_id, func.count()).filter(QuestionMedia.bank_id.in_(ids)).group_by(
            QuestionMedia.bank_id
        ):
            media_n[bid] = n
    pick_paper = db.get(Paper, pick) if pick else None
    return templates.TemplateResponse(
        request,
        "admin_bank.html",
        {
            "items": items,
            "used": used,
            "media_n": media_n,
            "f": {"domain": domain, "level": level, "qtype": qtype, "ability": ability, "q": q},
            "abilities": qbank.known_abilities(db),
            "qtypes": qbank.QTYPES,
            "domains": qbank.DOMAINS,
            "levels": qbank.all_levels(db),
            "pick_paper": pick_paper,
            "pick_version": version if pick_paper and version in qbank.paper_levels(db, pick_paper.id) else "",
            "msg": msg,
            "active": "admin",
        },
    )


def _new_with_type(obj, qtype):
    """Preselect a question type (and its default rubric) on a new-question form."""
    qtype = qtype if qtype in qbank.QTYPES else "single"
    for k, v in qbank.default_rubric(qtype).items():
        setattr(obj, k, v)
    obj.qtype = qtype
    obj.trial_max = 6 if qtype == "count" else None
    if qtype != "expr":
        obj.e2 = obj.e1 = obj.e0 = None
    return obj


@router.get("/bank/new")
def bank_new(request: Request, domain: str = "Mathematics", qtype: str = "single", db: Session = Depends(get_db)):
    b = _new_with_type(BankQuestion(domain=domain if domain in qbank.DOMAINS else "Mathematics", level=""), qtype)
    crop = _crop_prefill(db, request.query_params)
    if crop:
        b.prompt = crop["text"]
    return _qform(request, {"_db_abilities": qbank.known_abilities(db), "_levels": qbank.all_levels(db), "obj": b, "mode": "bank_new",
                            "action": "/admin/bank/new", "back": "/admin/bank", "media": [], "crop": crop})


@router.post("/bank/new")
async def bank_create(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    b = BankQuestion(domain="Mathematics", qtype="single", level="", created_by=request.state.teacher.id)
    _fill_question(b, form)
    b.level = qbank.norm_level(form.get("level"))
    b.tags = (form.get("tags") or "").strip()[:255]
    if not b.title or not b.ability:
        return _redirect("/admin/bank", t("bank.need_title"))
    db.add(b)
    db.flush()
    ups, bad = _read_uploads(form.getlist("files"))
    ups += _crop_upload(db, form)
    _add_uploads(db, ups, bank_id=b.id)
    db.commit()
    return _redirect(f"/admin/bank/{b.id}", t("q.saved") + _upload_msg(bad))


@router.get("/bank/{bid}")
def bank_edit(bid: int, request: Request, msg: str = "", db: Session = Depends(get_db)):
    b = db.get(BankQuestion, bid)
    if not b:
        return _redirect("/admin/bank")
    used_in = (
        db.query(Paper.name).join(Question, Question.paper_id == Paper.id).filter(Question.bank_id == bid).distinct().all()
    )
    return _qform(request, {"_db_abilities": qbank.known_abilities(db), "_levels": qbank.all_levels(db), "obj": b, "mode": "bank_edit",
                            "action": f"/admin/bank/{bid}", "back": "/admin/bank", "media": b.media,
                            "used_in": [n for (n,) in used_in], "msg": msg})


@router.post("/bank/{bid}")
async def bank_save(bid: int, request: Request, db: Session = Depends(get_db)):
    b = db.get(BankQuestion, bid)
    if not b:
        return _redirect("/admin/bank")
    form = await request.form()
    _fill_question(b, form)
    b.level = qbank.norm_level(form.get("level"))
    b.tags = (form.get("tags") or "").strip()[:255]
    ups, bad = _read_uploads(form.getlist("files"))
    _add_uploads(db, ups, bank_id=b.id)
    db.commit()
    return _redirect(f"/admin/bank/{bid}", t("q.saved") + _upload_msg(bad))


@router.post("/bank/{bid}/delete")
def bank_delete(bid: int, db: Session = Depends(get_db)):
    b = db.get(BankQuestion, bid)
    if b:
        db.query(Question).filter_by(bank_id=bid).update({"bank_id": None})
        db.delete(b)
        db.commit()
    return _redirect("/admin/bank", t("bank.deleted"))


# ---------- interview builder ----------

def _locked_redirect(pid):
    return _redirect(f"/admin/papers/{pid}", t("papers.locked_msg"))


@router.post("/papers/{pid}/import_sheet")
async def paper_import_sheet(pid: int, file: UploadFile = File(...), db: Session = Depends(get_db)):
    """Key abilities, curriculum links and home practice from the curriculum spreadsheet
    (one row per question id such as "TK M01"). Text only: allowed on scored interviews too."""
    if not db.get(Paper, pid):
        return _redirect("/admin/papers")
    data = await file.read()
    try:
        rows, problems = qbank.parse_ability_sheet(data)
    except Exception:  # noqa: BLE001
        return _redirect(f"/admin/papers/{pid}", t("sheet.bad_file"))
    if not rows:
        return _redirect(f"/admin/papers/{pid}", t("sheet.no_rows"))
    updated, missing, mismatched = qbank.apply_ability_sheet(db, pid, rows)
    db.commit()
    msg = t("sheet.done").format(n=len(updated))
    if missing:
        msg += " " + t("sheet.missing").format(ids=", ".join(missing))
    if mismatched:
        msg += " " + t("sheet.mismatch").format(
            items="; ".join(f"{i}: “{sheet}” ≠ “{site}”" for i, sheet, site in mismatched))
    return _redirect(f"/admin/papers/{pid}", msg)


@router.post("/papers/{pid}/cite")
def paper_cite(pid: int, bank_id: int = Form(...), version: str = Form(...), db: Session = Depends(get_db)):
    p, b = db.get(Paper, pid), db.get(BankQuestion, bank_id)
    if not p or not b or version not in qbank.paper_levels(db, pid):
        return _redirect("/admin/papers")
    if qbank.paper_locked(db, pid):
        return _locked_redirect(pid)
    q = qbank.cite(db, b, pid, version)
    db.commit()
    return _redirect(f"/admin/papers/{pid}", t("papers.cited").format(code=f"{version} {q.code}", title=q.title))


@router.get("/papers/{pid}/new")
def paper_new_question(pid: int, request: Request, version: str = "K", domain: str = "Mathematics",
                       qtype: str = "single", db: Session = Depends(get_db)):
    p = db.get(Paper, pid)
    if not p:
        return _redirect("/admin/papers")
    if qbank.paper_locked(db, pid):
        return _locked_redirect(pid)
    q = _new_with_type(Question(paper_id=pid, version=version if version in qbank.paper_levels(db, pid) else qbank.paper_levels(db, pid)[-1],
                                domain=domain if domain in qbank.DOMAINS else "Mathematics"), qtype)
    crop = _crop_prefill(db, request.query_params)
    if crop:
        q.prompt = crop["text"]
    return _qform(request, {"_db_abilities": qbank.known_abilities(db), "_levels": qbank.all_levels(db), "obj": q, "mode": "paper_new", "paper": p,
                            "action": f"/admin/papers/{pid}/new", "back": f"/admin/papers/{pid}", "media": [],
                            "crop": crop})


@router.post("/papers/{pid}/new")
async def paper_create_question(pid: int, request: Request, db: Session = Depends(get_db)):
    """A new question written inside an interview is saved to the bank too, then cited."""
    p = db.get(Paper, pid)
    if not p:
        return _redirect("/admin/papers")
    if qbank.paper_locked(db, pid):
        return _locked_redirect(pid)
    form = await request.form()
    version = form.get("version") if form.get("version") in qbank.paper_levels(db, pid) else qbank.paper_levels(db, pid)[-1]
    b = BankQuestion(domain="Mathematics", qtype="single", level=version, created_by=request.state.teacher.id)
    _fill_question(b, form)
    b.tags = (form.get("tags") or "").strip()[:255]
    if not b.title or not b.ability:
        return _redirect(f"/admin/papers/{pid}", t("bank.need_title"))
    db.add(b)
    db.flush()
    ups, bad = _read_uploads(form.getlist("files"))
    ups += _crop_upload(db, form)
    _add_uploads(db, ups, bank_id=b.id)
    db.flush()
    db.refresh(b)
    q = qbank.cite(db, b, pid, version)
    db.commit()
    return _redirect(f"/admin/papers/{pid}", t("papers.cited").format(code=f"{version} {q.code}", title=q.title) + _upload_msg(bad))


@router.get("/questions/{qid}/edit")
def question_edit(qid: int, request: Request, msg: str = "", db: Session = Depends(get_db)):
    q = db.get(Question, qid)
    if not q:
        return _redirect("/admin/papers")
    return _qform(request, {"_db_abilities": qbank.known_abilities(db), "_levels": qbank.all_levels(db), "obj": q, "mode": "paper_edit",
                            "paper": q.paper, "action": f"/admin/questions/{qid}/edit",
                            "back": f"/admin/papers/{q.paper_id}", "media": q.media,
                            "locked": qbank.paper_locked(db, q.paper_id), "msg": msg})


@router.post("/questions/{qid}/edit")
async def question_save(qid: int, request: Request, db: Session = Depends(get_db)):
    q = db.get(Question, qid)
    if not q:
        return _redirect("/admin/papers")
    form = await request.form()
    locked = qbank.paper_locked(db, q.paper_id)
    old_domain = q.domain
    _fill_question(q, form, qtype_allowed=not locked)
    if locked:
        q.domain = old_domain  # scored interviews keep their structure
    ups, bad = _read_uploads(form.getlist("files"))
    _add_uploads(db, ups, question_id=q.id)
    db.flush()
    if q.domain != old_domain:
        qbank._park_codes(db, q.paper_id, q.version)
        qbank.renumber(db, q.paper_id, q.version)
    msg = t("q.saved")
    if form.get("save_bank"):
        db.refresh(q)
        qbank.save_to_bank(db, q)
        msg = t("bank.saved_back")
    db.commit()
    return _redirect(f"/admin/papers/{q.paper_id}", msg + _upload_msg(bad))


@router.post("/questions/{qid}/delete")
def question_delete(qid: int, db: Session = Depends(get_db)):
    q = db.get(Question, qid)
    if not q:
        return _redirect("/admin/papers")
    pid = q.paper_id
    if qbank.paper_locked(db, pid):
        return _locked_redirect(pid)
    qbank.remove_question(db, q)
    db.commit()
    return _redirect(f"/admin/papers/{pid}", t("papers.removed"))


@router.post("/questions/{qid}/move")
def question_move(qid: int, step: int = Form(...), db: Session = Depends(get_db)):
    q = db.get(Question, qid)
    if not q:
        return _redirect("/admin/papers")
    pid = q.paper_id
    if qbank.paper_locked(db, pid):
        return _locked_redirect(pid)
    qbank.move_question(db, q, -1 if step < 0 else 1)
    db.commit()
    return _redirect(f"/admin/papers/{pid}")


@router.post("/media/update")
async def media_update(request: Request, db: Session = Depends(get_db)):
    """Save picture captions and their order (one form for a question's / stem's pictures)."""
    form = await request.form()
    back = str(form.get("back") or "/admin/papers")
    rows = []
    for raw in form.getlist("ids"):
        try:
            m = db.get(QuestionMedia, int(raw))
        except ValueError:
            m = None
        if m is None:
            continue
        m.caption = str(form.get(f"caption_{m.id}") or "").strip()[:2000]
        try:
            want = int(form.get(f"sort_{m.id}") or 0)
        except ValueError:
            want = 0
        rows.append((want, m.sort or 0, m.id, m))
    for i, (_w, _s, _id, m) in enumerate(sorted(rows, key=lambda x: (x[0], x[1], x[2]))):
        m.sort = i
    db.commit()
    return _redirect(back if back.startswith("/admin/") else "/admin/papers", t("media.saved"))


@router.post("/media/{mid}/delete")
def media_delete(mid: int, back: str = Form("/admin/papers"), db: Session = Depends(get_db)):
    m = db.get(QuestionMedia, mid)
    if m:
        db.delete(m)
        db.commit()
    return _redirect(back if back.startswith("/admin/") else "/admin/papers", t("bank.media_removed"))


@router.post("/papers/{pid}/stage_material")
async def stage_material_save(pid: int, request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    stage = str(form.get("stage") or "")
    if not db.get(Paper, pid) or stage not in _paper_stage_keys(db, pid):
        return _redirect("/admin/papers")
    back = str(form.get("back") or "")
    dest = back if back.startswith(f"/admin/papers/{pid}") else f"/admin/papers/{pid}"
    m = db.query(StageMaterial).filter_by(paper_id=pid, stage=stage).first()
    if m is None:
        m = StageMaterial(paper_id=pid, stage=stage)
        db.add(m)
    m.title = (form.get("title") or "").strip()[:160]
    m.text = (form.get("text") or "").strip()
    ups, bad = _read_uploads(form.getlist("files"))
    _add_uploads(db, ups, paper_id=pid, stage=stage)
    db.commit()
    return _redirect(dest, t("papers.material_saved") + _upload_msg(bad))


@router.post("/papers/{pid}/stage_copy")
def stage_copy(pid: int, stage: str = Form(...), from_pid: int = Form(...), db: Session = Depends(get_db)):
    """Cite a team activity from an earlier interview: its material, pictures,
    rubric dimensions (and Story Time prompts) replace this interview's."""
    if not db.get(Paper, pid) or not db.get(Paper, from_pid) or pid == from_pid:
        return _redirect(f"/admin/papers/{pid}")
    db.query(StageMaterial).filter_by(paper_id=pid, stage=stage).delete()
    db.query(QuestionMedia).filter_by(paper_id=pid, stage=stage).delete()
    src = db.query(StageMaterial).filter_by(paper_id=from_pid, stage=stage).first()
    if src:
        db.add(StageMaterial(paper_id=pid, stage=stage, title=src.title, text=src.text, activity_id=src.activity_id))
    for m in db.query(QuestionMedia).filter_by(paper_id=from_pid, stage=stage).order_by(QuestionMedia.sort):
        db.add(QuestionMedia(paper_id=pid, stage=stage, filename=m.filename, caption=m.caption or "", mime=m.mime, data=m.data,
                             size=m.size, sort=m.sort))
    src_dims = db.query(StageDimDef).filter_by(paper_id=from_pid, stage=stage).all()
    if src_dims:
        db.query(StageDimDef).filter_by(paper_id=pid, stage=stage).delete()
        for d in src_dims:
            db.add(StageDimDef(paper_id=pid, stage=stage, key=d.key, label=d.label, label_zh=d.label_zh,
                               options=d.options, sort=d.sort))
    src_prompts = [sp for sp in db.query(StoryPromptDef).filter_by(paper_id=from_pid).all() if (sp.stage or "Story Time") == stage]
    if src_prompts:
        for old in db.query(StoryPromptDef).filter_by(paper_id=pid).all():
            if (old.stage or "Story Time") == stage:
                db.delete(old)
        for sp in src_prompts:
            db.add(StoryPromptDef(paper_id=pid, idx=sp.idx, text=sp.text, stage=stage))
    db.commit()
    return _redirect(f"/admin/papers/{pid}", t("papers.stage_copied"))


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
def save_paper_prompts(pid: int, text: str = Form(...), stage: str = Form("Story Time"), db: Session = Depends(get_db)):
    p = db.get(Paper, pid)
    if not p:
        return _redirect("/admin/papers")
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return _redirect(f"/admin/papers/{pid}", t("papers.prompts_empty"))
    for old in db.query(StoryPromptDef).filter_by(paper_id=pid).all():
        if (old.stage or "Story Time") == stage:
            db.delete(old)
    for i, line in enumerate(lines, 1):
        db.add(StoryPromptDef(paper_id=pid, idx=i, text=line, stage=stage))
    db.commit()
    return _redirect(f"/admin/papers/{pid}", t("papers.prompts_saved"))


# ---------- teachers ----------

@router.get("/teachers")
def teachers_page(request: Request, msg: str = "", db: Session = Depends(get_db)):
    from .. import perm

    teachers = db.query(Teacher).order_by(Teacher.name).all()
    me = request.state.teacher
    return templates.TemplateResponse(
        request,
        "admin_teachers.html",
        {"teachers": teachers, "msg": msg, "active": "admin", "me": me, "i_am_owner": perm.is_owner(me),
         "manageable": {te.id for te in teachers if perm.can_manage(me, te)},
         "switchable": {te.id for te in teachers if perm.can_switch_into(me, te)}},
    )


def _deny_account(me, target, owner_only=False):
    """A redirect with the reason when `me` may not change `target`'s account, else None."""
    from .. import perm

    if owner_only and not perm.is_owner(me):
        return _redirect("/admin/teachers", t("teachers.owner_only"))
    if not perm.can_manage(me, target):
        return _redirect("/admin/teachers", t("teachers.no_manage_admin"))
    return None


def _teacher_name_taken(db, name, except_id=None):
    from sqlalchemy import func

    q = db.query(Teacher).filter(func.lower(Teacher.name) == name.lower())
    if except_id:
        q = q.filter(Teacher.id != except_id)
    return q.first() is not None


@router.post("/teachers/add")
def add_teacher(request: Request, name: str = Form(...), role: str = Form("teacher"), db: Session = Depends(get_db)):
    from .. import perm

    name = " ".join(name.split())[:80]
    role = "admin" if role == "admin" else "teacher"
    if role == "admin" and not perm.is_owner(request.state.teacher):  # only the owner creates admins
        return _redirect("/admin/teachers", t("teachers.owner_only"))
    if name and not _teacher_name_taken(db, name):
        db.add(Teacher(name=name, role=role))
        db.commit()
    return _redirect("/admin/teachers")


@router.post("/teachers/{tid}/rename")
def rename_teacher(tid: int, request: Request, name: str = Form(...), db: Session = Depends(get_db)):
    """The name is what the teacher types to sign in; past records keep pointing at the same account."""
    te = db.get(Teacher, tid)
    name = " ".join(name.split())[:80]
    if not te or not name:
        return _redirect("/admin/teachers")
    denied = _deny_account(request.state.teacher, te)
    if denied:
        return denied
    if _teacher_name_taken(db, name, except_id=tid):
        return _redirect("/admin/teachers", t("teachers.name_taken"))
    te.name = name
    db.commit()
    return _redirect("/admin/teachers", t("teachers.renamed").format(name=name))


@router.post("/teachers/{tid}/role")
def toggle_teacher_role(tid: int, request: Request, db: Session = Depends(get_db)):
    te = db.get(Teacher, tid)
    me = request.state.teacher
    if not te:
        return _redirect("/admin/teachers")
    # who is an admin is decided by the owner account only
    denied = _deny_account(me, te, owner_only=True)
    if denied:
        return denied
    if te.id == me.id or te.is_owner:
        return _redirect("/admin/teachers", t("teachers.owner_protected"))
    te.role = "teacher" if te.role == "admin" else "admin"
    db.commit()
    return _redirect("/admin/teachers", t("teachers.role_set").format(name=te.name, role=t("role." + te.role)))


@router.post("/teachers/{tid}/password")
def set_teacher_password(tid: int, request: Request, password: str = Form(...), db: Session = Depends(get_db)):
    from ..auth import hash_password

    teacher = db.get(Teacher, tid)
    if teacher:
        denied = _deny_account(request.state.teacher, teacher)
        if denied:
            return denied
    if teacher and password.strip():
        teacher.password_hash = hash_password(password.strip())
        db.commit()
    return _redirect("/admin/teachers", t("teachers.pw_set"))


@router.post("/teachers/{tid}/delete")
def delete_teacher(tid: int, request: Request, db: Session = Depends(get_db)):
    """Delete an account. Children's results stay; their "recorded by" becomes blank
    (change history keeps the name), and groups the teacher led become unassigned."""
    from ..models import (AudioNote, BankActivity, BankQuestion, EmailLog, Event, Group, ItemRecord,
                          MailAccount, ReportPdf, Review, SessionArchive, SourcePdf, StageObs, Summary)

    te = db.get(Teacher, tid)
    me = request.state.teacher
    if not te:
        return _redirect("/admin/teachers")
    if me and te.id == me.id:
        return _redirect("/admin/teachers", t("teachers.cannot_delete_self"))
    denied = _deny_account(me, te)
    if denied:
        return denied
    if te.is_owner:
        return _redirect("/admin/teachers", t("teachers.owner_protected"))
    if te.role == "admin" and db.query(Teacher).filter(Teacher.role == "admin", Teacher.id != tid).count() == 0:
        return _redirect("/admin/teachers", t("teachers.cannot_delete_last_admin"))
    refs = [
        (Group, Group.teacher_id), (ItemRecord, ItemRecord.teacher_id), (Event, Event.teacher_id),
        (StageObs, StageObs.teacher_id), (Summary, Summary.teacher_id), (Review, Review.teacher_id),
        (ReportPdf, ReportPdf.teacher_id), (SessionArchive, SessionArchive.teacher_id),
        (AudioNote, AudioNote.teacher_id), (EmailLog, EmailLog.teacher_id), (MailAccount, MailAccount.connected_by),
        (BankQuestion, BankQuestion.created_by), (BankActivity, BankActivity.created_by), (SourcePdf, SourcePdf.uploaded_by),
    ]
    kept = 0
    for model, col in refs:
        kept += db.query(model).filter(col == tid).update({col: None}, synchronize_session=False)
    name = te.name
    db.delete(te)
    db.commit()
    return _redirect("/admin/teachers", t("teachers.deleted").format(name=name, n=kept))


@router.post("/teachers/{tid}/toggle")
def toggle_teacher(tid: int, request: Request, db: Session = Depends(get_db)):
    te = db.get(Teacher, tid)
    if te:
        denied = _deny_account(request.state.teacher, te)
        if denied:
            return denied
        if te.is_owner:
            return _redirect("/admin/teachers", t("teachers.owner_protected"))
        te.active = not te.active
        db.commit()
    return _redirect("/admin/teachers")


# ---------- report emails ----------

def _pdf_lang(filename):
    return "zh" if "_Report_CN_" in filename else "en"


def _latest_pdfs(db, student_ids):
    """{student_id: {'en': ReportPdf, 'zh': ReportPdf}} — newest of each language
    (loads only id/filename/time, not the PDF bytes)."""
    out = {}
    if not student_ids:
        return out
    rows = (
        db.query(ReportPdf.id, ReportPdf.student_id, ReportPdf.filename, ReportPdf.created_at)
        .filter(ReportPdf.student_id.in_(student_ids))
        .order_by(ReportPdf.id)
        .all()
    )
    for r in rows:
        out.setdefault(r.student_id, {})[_pdf_lang(r.filename)] = r
    return out


@router.get("/sessions/{sid}/email")
def email_page(sid: int, request: Request, db: Session = Depends(get_db)):
    s = db.get(AssessSession, sid)
    if not s:
        return _redirect("/admin/sessions", t("msg.session_not_found"))
    students = (
        db.query(Student).filter_by(session_id=sid).order_by(Student.level, Student.name).all()
    )
    ids = [st.id for st in students]
    reviewed = {r.student_id for r in db.query(Review.student_id).filter(Review.student_id.in_(ids))} if ids else set()
    last_sent, last_fail = {}, {}
    if ids:
        for lg in db.query(EmailLog).filter(EmailLog.student_id.in_(ids)).order_by(EmailLog.id):
            if lg.status == "sent":
                last_sent[lg.student_id] = lg
                last_fail.pop(lg.student_id, None)  # a later success clears an earlier failure
            elif lg.status == "failed":
                last_fail[lg.student_id] = lg
    mail = mailer.status(db)
    db.commit()
    return templates.TemplateResponse(
        request,
        "admin_email.html",
        {
            "s": s,
            "students": students,
            "pdfs": _latest_pdfs(db, ids),
            "reviewed": reviewed,
            "last_sent": last_sent,
            "last_fail": last_fail,
            "emails": {st.id: mailer.split_emails(st.parent_email)[0] for st in students},
            "configured": mail["connected"],
            "from_addr": mail["from_addr"],
            "default_bcc": mailer.default_bcc(),
            "active": "admin",
        },
    )


@router.post("/sessions/{sid}/email/send")
def email_send_one(sid: int, request: Request, payload: dict = Body(...), db: Session = Depends(get_db)):
    """Sends ONE student's report email (the page calls this once per student,
    so a long list never hits a request timeout). test_to: send the same email
    only to that address (no parent, no BCC) to check it first."""
    me = request.state.teacher
    if not mailer.status(db)["connected"]:
        db.commit()
        return JSONResponse(status_code=400, content={"ok": False, "error": t("email.err_config")})
    st = db.get(Student, int(payload.get("student_id") or 0))
    if not st or st.session_id != sid:
        return JSONResponse(status_code=404, content={"ok": False, "error": "student not found"})
    subject_t = str(payload.get("subject") or "").strip()
    body_t = str(payload.get("body") or "").strip()
    if not subject_t or not body_t:
        return JSONResponse(status_code=400, content={"ok": False, "error": t("email.err_text")})
    langs = [x for x in (payload.get("langs") or []) if x in ("en", "zh")]
    if not langs:
        return JSONResponse(status_code=400, content={"ok": False, "error": t("email.err_lang")})

    test_to = str(payload.get("test_to") or "").strip()
    if test_to:
        to, bad = mailer.split_emails(test_to)
        bcc = []
    else:
        to, bad = mailer.split_emails(st.parent_email)
        bcc, bad_bcc = mailer.split_emails(str(payload.get("bcc") or ""))
        bad += bad_bcc
    if bad:
        return JSONResponse(status_code=400, content={"ok": False, "error": t("msg.email_bad").format(bad=", ".join(bad))})
    if not to:
        return JSONResponse(status_code=400, content={"ok": False, "error": t("email.err_no_email")})

    latest = _latest_pdfs(db, [st.id]).get(st.id, {})
    missing = [x for x in langs if x not in latest]
    if missing:
        names = {"en": "EN", "zh": "中文"}
        return JSONResponse(
            status_code=400,
            content={"ok": False, "error": t("email.err_no_pdf").format(lang="/".join(names[x] for x in missing))},
        )
    attachments = []
    for x in langs:
        row = db.get(ReportPdf, latest[x].id)
        attachments.append((row.filename, row.data))

    values = {
        "name": st.name,
        "first_name": st.name.split()[0] if st.name.split() else st.name,
        "level": st.level,
        "date": st.session.date if st.session else "",
    }
    subject = mailer.fill(subject_t, values)[:250]
    body = mailer.fill(body_t, values)
    log = EmailLog(
        student_id=st.id,
        to_addr=", ".join(to)[:255],
        bcc=", ".join(bcc)[:255],
        subject=subject,
        attachments=", ".join(n for n, _ in attachments)[:255],
        status="test" if test_to else "sent",
        teacher_id=me.id if me else None,
    )
    try:
        mailer.send(db, to, bcc, subject, body, attachments)
    except mailer.NeedsReconnect as e:
        log.status = "failed"
        log.error = f"{t('mailbox.reconnect_needed')} ({e})"[:1000]
        db.add(log)
        db.commit()
        return JSONResponse(status_code=502, content={"ok": False, "error": log.error})
    except Exception as e:  # noqa: BLE001
        log.status = "failed"
        log.error = (str(e) if isinstance(e, mailer.MailError) else f"{type(e).__name__}: {e}")[:1000]
        db.add(log)
        db.commit()
        return JSONResponse(status_code=502, content={"ok": False, "error": log.error})
    db.add(log)
    db.commit()
    return {
        "ok": True,
        "to": log.to_addr,
        "attachments": log.attachments,
        "test": bool(test_to),
        "time": log.created_at.strftime("%m-%d %H:%M"),
    }


# ---------- sender mailbox (admin only: the whole /admin prefix is admin-only) ----------

@router.get("/mailbox")
def mailbox_page(request: Request, msg: str = "", db: Session = Depends(get_db)):
    st = mailer.status(db)
    db.commit()
    return templates.TemplateResponse(
        request, "admin_mailbox.html", {"m": st, "msg": msg, "active": "admin"}
    )


@router.post("/mailbox/start")
def mailbox_start(payload: dict = Body(...), db: Session = Depends(get_db)):
    sender = str(payload.get("sender") or "").strip()
    if sender:
        good, bad = mailer.split_emails(sender)
        if bad or len(good) != 1:
            return JSONResponse(status_code=400, content={"ok": False, "error": t("msg.email_bad").format(bad=sender)})
        sender = good[0]
    try:
        info = mailer.start_sign_in(db, sender)
    except mailer.MailError as e:
        return JSONResponse(status_code=502, content={"ok": False, "error": str(e)})
    return {"ok": True, **info}


@router.post("/mailbox/poll")
def mailbox_poll(request: Request, db: Session = Depends(get_db)):
    me = request.state.teacher
    try:
        state, err = mailer.poll_sign_in(db, me.id if me else None)
    except mailer.MailError as e:
        return {"ok": False, "state": "error", "error": str(e)}
    return {"ok": state == "ok", "state": state, "error": err}


@router.post("/mailbox/disconnect")
def mailbox_disconnect(db: Session = Depends(get_db)):
    mailer.disconnect(db)
    return _redirect("/admin/mailbox", t("mailbox.disconnected"))


@router.post("/mailbox/test")
def mailbox_test(to: str = Form(...), db: Session = Depends(get_db)):
    good, bad = mailer.split_emails(to)
    if bad or not good:
        return _redirect("/admin/mailbox", t("msg.email_bad").format(bad=to))
    try:
        mailer.send(db, good, [], t("mailbox.test_subject"), t("mailbox.test_body"), [])
    except mailer.NeedsReconnect:
        return _redirect("/admin/mailbox", t("mailbox.reconnect_needed"))
    except mailer.MailError as e:
        return _redirect("/admin/mailbox", f"{t('mailbox.test_failed')}: {e}")
    return _redirect("/admin/mailbox", t("mailbox.test_sent").format(to=", ".join(good)))


# ---------- question bank: team-activity stems ----------
# (own URL prefix: /admin/bank/{bid} already takes every /admin/bank/<x> path)

def _team_stages():
    """Every team part name in use (the four built-in ones first), for bank stems."""
    from ..db import SessionLocal
    from ..stage_defs import DEFAULT_STAGES

    out = [k for k, _ in DEFAULT_STAGES]
    db = SessionLocal()
    try:
        for (k,) in db.query(PaperStage.key).distinct().order_by(PaperStage.key):
            if k not in out:
                out.append(k)
    finally:
        db.close()
    return out


def _paper_stage_keys(db, pid):
    from ..stage_defs import paper_stages

    return [x["key"] for x in paper_stages(db, pid)]


@router.get("/teambank")
def teambank_page(request: Request, stage: str = "", q: str = "", pick: int = 0, msg: str = "",
                  db: Session = Depends(get_db)):
    from sqlalchemy import func, or_

    query = db.query(BankActivity)
    if stage in _team_stages():
        query = query.filter(BankActivity.stage == stage)
    if q.strip():
        like = f"%{q.strip().lower()}%"
        query = query.filter(or_(func.lower(BankActivity.title).like(like), func.lower(BankActivity.prompt).like(like),
                                 func.lower(BankActivity.tags).like(like)))
    items = query.order_by(BankActivity.stage, BankActivity.title).all()
    ids = [a.id for a in items]
    used, media_n = {}, {}
    if ids:
        for aid, n in db.query(StageMaterial.activity_id, func.count()).filter(StageMaterial.activity_id.in_(ids)).group_by(
            StageMaterial.activity_id
        ):
            used[aid] = n
        for aid, n in db.query(QuestionMedia.activity_id, func.count()).filter(QuestionMedia.activity_id.in_(ids)).group_by(
            QuestionMedia.activity_id
        ):
            media_n[aid] = n
    return templates.TemplateResponse(
        request,
        "admin_teambank.html",
        {
            "items": items, "used": used, "media_n": media_n, "stages": _team_stages(),
            "f": {"stage": stage, "q": q}, "pick_paper": db.get(Paper, pick) if pick else None,
            "msg": msg, "active": "admin",
        },
    )


def _activity_form(request, a, action, media, msg="", used_in=None, crop=None):
    return templates.TemplateResponse(
        request,
        "admin_activity_form.html",
        {"a": a, "action": action, "media": media, "stages": _team_stages(), "msg": msg,
         "used_in": used_in or [], "crop": crop, "active": "admin"},
    )


@router.get("/teambank/new")
def teambank_new(request: Request, stage: str = "", db: Session = Depends(get_db)):
    a = BankActivity(stage=stage if stage in _team_stages() else _team_stages()[0], title="", prompt="", tags="")
    crop = _crop_prefill(db, request.query_params)
    if crop:
        a.prompt = crop["text"]
    return _activity_form(request, a, "/admin/teambank/new", [], crop=crop)


def _fill_activity(a, form):
    a.stage = form.get("stage") if form.get("stage") in _team_stages() else a.stage
    a.title = (form.get("title") or "").strip()[:160]
    a.prompt = (form.get("prompt") or "").strip()
    a.tags = (form.get("tags") or "").strip()[:255]


@router.post("/teambank/new")
async def teambank_create(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    a = BankActivity(stage=_team_stages()[0], created_by=request.state.teacher.id)
    _fill_activity(a, form)
    if not a.title:
        return _redirect("/admin/teambank", t("bank.need_title_only"))
    db.add(a)
    db.flush()
    ups, bad = _read_uploads(form.getlist("files"))
    ups += _crop_upload(db, form)
    _add_uploads(db, ups, activity_id=a.id)
    db.commit()
    return _redirect(f"/admin/teambank/{a.id}", t("q.saved") + _upload_msg(bad))


@router.get("/teambank/{aid}")
def teambank_edit(aid: int, request: Request, msg: str = "", db: Session = Depends(get_db)):
    a = db.get(BankActivity, aid)
    if not a:
        return _redirect("/admin/teambank")
    used_in = db.query(Paper.name).join(StageMaterial, StageMaterial.paper_id == Paper.id).filter(
        StageMaterial.activity_id == aid).distinct().all()
    return _activity_form(request, a, f"/admin/teambank/{aid}", a.media, msg, [n for (n,) in used_in])


@router.post("/teambank/{aid}")
async def teambank_save(aid: int, request: Request, db: Session = Depends(get_db)):
    a = db.get(BankActivity, aid)
    if not a:
        return _redirect("/admin/teambank")
    form = await request.form()
    _fill_activity(a, form)
    ups, bad = _read_uploads(form.getlist("files"))
    _add_uploads(db, ups, activity_id=a.id)
    db.commit()
    return _redirect(f"/admin/teambank/{aid}", t("q.saved") + _upload_msg(bad))


@router.post("/teambank/{aid}/delete")
def teambank_delete(aid: int, db: Session = Depends(get_db)):
    a = db.get(BankActivity, aid)
    if a:
        db.query(StageMaterial).filter_by(activity_id=aid).update({"activity_id": None})
        db.delete(a)
        db.commit()
    return _redirect("/admin/teambank", t("bank.deleted"))


@router.post("/papers/{pid}/stage_cite")
def stage_cite(pid: int, activity_id: int = Form(...), db: Session = Depends(get_db)):
    """Use a team-activity stem from the bank in this interview (copy of text + files)."""
    a = db.get(BankActivity, activity_id)
    if not db.get(Paper, pid) or not a:
        return _redirect("/admin/papers")
    if a.stage not in _paper_stage_keys(db, pid):
        return _redirect(f"/admin/papers/{pid}", t("build.err_no_part"))
    qbank.set_stage_stem(db, pid, a)
    db.commit()
    return _redirect(f"/admin/papers/{pid}", t("papers.stage_cited").format(stage=t("stage." + a.stage), title=a.title))


@router.post("/papers/{pid}/stage_to_bank")
def stage_to_bank(pid: int, stage: str = Form(...), db: Session = Depends(get_db)):
    """Save this interview's stem for a team activity into the bank (updates the
    entry it was cited from, or creates one)."""
    m = db.query(StageMaterial).filter_by(paper_id=pid, stage=stage).first()
    if not m or not (m.title or m.text):
        return _redirect(f"/admin/papers/{pid}", t("papers.stage_empty"))
    a = db.get(BankActivity, m.activity_id) if m.activity_id else None
    if a is None:
        a = BankActivity(stage=stage)
        db.add(a)
    a.title = m.title or t("stage." + stage)
    a.prompt = m.text
    db.flush()
    for old in list(a.media):
        db.delete(old)
    db.flush()
    qbank.copy_media(db, db.query(QuestionMedia).filter_by(paper_id=pid, stage=stage).order_by(QuestionMedia.sort).all(),
                     activity_id=a.id)
    m.activity_id = a.id
    db.commit()
    return _redirect(f"/admin/papers/{pid}", t("papers.stage_saved_bank"))


# ---------- question PDFs: view pages, cut pictures, read text ----------

def _pdf_bytes(db, pdf_id):
    data = pdfsrc.cached(pdf_id)
    if data is None:
        src = db.get(SourcePdf, pdf_id)
        if src is None:
            return None
        data = bytes(src.data)
        pdfsrc.remember(pdf_id, data)
    return data


def _pdf_target(db, target):
    """'bank:12' | 'q:34' | 'act:5' | 'stage:3:Story Time' -> (owner kwargs, back url, label) or None."""
    kind, _, rest = (target or "").partition(":")
    try:
        if kind == "bank":
            o = db.get(BankQuestion, int(rest))
            return ({"bank_id": o.id}, f"/admin/bank/{o.id}", o.title) if o else None
        if kind == "q":
            o = db.get(Question, int(rest))
            return ({"question_id": o.id}, f"/admin/questions/{o.id}/edit", f"{o.version} {o.code} · {o.title}") if o else None
        if kind == "act":
            o = db.get(BankActivity, int(rest))
            return ({"activity_id": o.id}, f"/admin/teambank/{o.id}", o.title) if o else None
        if kind == "stage":
            pid, _, stage = rest.partition(":")
            p = db.get(Paper, int(pid))
            if p and stage in _paper_stage_keys(db, p.id):
                return ({"paper_id": p.id, "stage": stage}, f"/admin/papers/{p.id}", f"{p.name} · {t('stage.' + stage)}")
    except ValueError:
        return None
    return None


def _pdf_new_links(db, new):
    """Buttons that start a new question from the selection, one per question type
    (the page adds pdf/page/rect). -> (heading, [(label, url)])"""
    kind, _, rest = (new or "").partition(":")
    per_type = lambda base: [(t("qtype." + qt), f"{base}&qtype={qt}") for qt in qbank.QTYPES]  # noqa: E731
    if kind == "paper":
        try:
            pid, lv, dom = rest.split(":", 2)
            p = db.get(Paper, int(pid))
        except ValueError:
            p = None
        if p and lv in qbank.paper_levels(db, p.id) and dom in qbank.DOMAINS:
            return [(t("pdf.new_in_paper").format(paper=p.name, lv=lv, dom=t("domain." + dom)),
                     per_type(f"/admin/papers/{p.id}/new?version={lv}&domain={quote(dom)}"))]
    # from the bank (either tab) every category is offered: pick it per question
    team = [(t("stage." + st), f"/admin/teambank/new?stage={quote(st)}") for st in _team_stages()]
    return [(t("pdf.new_as_individual"), per_type("/admin/bank/new?domain=Mathematics")),
            (t("pdf.new_as_team"), team)]


def _crop_prefill(db, params):
    """?pdf=&page=&rect= on a new-question form -> {text, hidden fields, preview url}."""
    try:
        pdf_id, page = int(params.get("pdf") or 0), int(params.get("page") or 0)
    except ValueError:
        return None
    rect = pdfsrc.parse_rect(params.get("rect") or "")
    data = _pdf_bytes(db, pdf_id) if pdf_id else None
    if not data or not rect or page < 1:
        return None
    rs = ",".join(f"{v:.4f}" for v in rect)
    return {"pdf": pdf_id, "page": page, "rect": rs, "text": pdfsrc.text_in(data, page, rect),
            "url": f"/admin/pdfs/{pdf_id}/crop?page={page}&rect={rs}"}


def _crop_upload(db, form):
    """The PDF selection carried by a new-question form -> [(filename, mime, bytes)]."""
    try:
        pdf_id, page = int(form.get("pdf_id") or 0), int(form.get("pdf_page") or 0)
    except ValueError:
        return []
    rect = pdfsrc.parse_rect(form.get("pdf_rect") or "")
    src = db.get(SourcePdf, pdf_id) if pdf_id else None
    if not src or not rect:
        return []
    img, mime = pdfsrc.crop_image(_pdf_bytes(db, pdf_id), page, rect)
    stem = src.filename.rsplit(".", 1)[0][:60]
    return [(f"{stem}_p{page}.{'png' if mime == 'image/png' else 'jpg'}", mime, img)]


@router.get("/pdfs")
def pdfs_page(request: Request, target: str = "", new: str = "", msg: str = "", db: Session = Depends(get_db)):
    rows = db.query(SourcePdf.id, SourcePdf.filename, SourcePdf.pages, SourcePdf.size, SourcePdf.created_at).order_by(
        SourcePdf.id.desc()).all()
    tgt = _pdf_target(db, target) if target else None
    return templates.TemplateResponse(
        request,
        "admin_pdfs.html",
        {"rows": rows, "target": target if tgt else "", "target_label": tgt[2] if tgt else "",
         "target_back": tgt[1] if tgt else "", "new": new, "msg": msg, "active": "admin"},
    )


@router.post("/pdfs/upload")
async def pdfs_upload(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    f = form.get("file")
    keep = "&".join(f"{k}={quote(str(form.get(k)))}" for k in ("target", "new") if form.get(k))
    if not f or not getattr(f, "filename", ""):
        return _redirect("/admin/pdfs" + (f"?{keep}" if keep else ""))
    data = await f.read()
    if not pdfsrc.is_pdf(data) or len(data) > pdfsrc.MAX_PDF_BYTES:
        return RedirectResponse(f"/admin/pdfs?msg={quote(t('pdf.bad_file'))}" + (f"&{keep}" if keep else ""), status_code=303)
    try:
        pages = pdfsrc.page_count(data)
    except Exception:  # noqa: BLE001
        return RedirectResponse(f"/admin/pdfs?msg={quote(t('pdf.bad_file'))}" + (f"&{keep}" if keep else ""), status_code=303)
    src = SourcePdf(filename=f.filename[-200:], data=data, size=len(data), pages=pages, uploaded_by=request.state.teacher.id)
    db.add(src)
    db.commit()
    return RedirectResponse(f"/admin/pdfs/{src.id}?page=1" + (f"&{keep}" if keep else ""), status_code=303)


@router.post("/pdfs/{pdf_id}/delete")
def pdfs_delete(pdf_id: int, db: Session = Depends(get_db)):
    src = db.get(SourcePdf, pdf_id)
    if src:
        db.delete(src)
        db.commit()
        pdfsrc._cache.pop(pdf_id, None)
    return _redirect("/admin/pdfs", t("pdf.deleted"))


@router.get("/pdfs/{pdf_id}")
def pdf_view(pdf_id: int, request: Request, page: int = 1, target: str = "", new: str = "", msg: str = "",
             db: Session = Depends(get_db)):
    src = db.query(SourcePdf.id, SourcePdf.filename, SourcePdf.pages).filter_by(id=pdf_id).first()
    if not src:
        return _redirect("/admin/pdfs")
    page = min(max(1, page), max(1, src.pages))
    tgt = _pdf_target(db, target) if target else None
    data = _pdf_bytes(db, pdf_id)
    return templates.TemplateResponse(
        request,
        "admin_pdf_view.html",
        {
            "src": src, "page": page, "has_text": bool(pdfsrc.text_in(data, page).strip()),
            "target": target if tgt else "", "target_label": tgt[2] if tgt else "", "target_back": tgt[1] if tgt else "",
            "new": new, "new_links": [] if tgt else _pdf_new_links(db, new), "msg": msg, "active": "admin",
        },
    )


@router.get("/pdfs/{pdf_id}/page/{page}")
def pdf_page_image(pdf_id: int, page: int, db: Session = Depends(get_db)):
    data = _pdf_bytes(db, pdf_id)
    if not data:
        return Response(status_code=404)
    try:
        img = pdfsrc.page_jpeg(data, page)
    except ValueError:
        return Response(status_code=404)
    return Response(content=img, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=3600"})


@router.get("/pdfs/{pdf_id}/crop")
def pdf_crop_image(pdf_id: int, page: int, rect: str, db: Session = Depends(get_db)):
    data, r = _pdf_bytes(db, pdf_id), pdfsrc.parse_rect(rect)
    if not data or not r:
        return Response(status_code=404)
    try:
        img, mime = pdfsrc.crop_image(data, page, r)
    except ValueError:
        return Response(status_code=404)
    return Response(content=img, media_type=mime, headers={"Cache-Control": "private, max-age=3600"})


@router.get("/pdfs/{pdf_id}/text")
def pdf_text(pdf_id: int, page: int, rect: str = "", db: Session = Depends(get_db)):
    data = _pdf_bytes(db, pdf_id)
    if not data:
        return JSONResponse(status_code=404, content={"ok": False})
    return {"ok": True, "text": pdfsrc.text_in(data, page, pdfsrc.parse_rect(rect) if rect else None)}


@router.post("/pdfs/{pdf_id}/attach")
def pdf_attach(pdf_id: int, page: int = Form(...), rect: str = Form(...), target: str = Form(...),
               db: Session = Depends(get_db)):
    """Cut the selection out as a picture and add it to a question / stem."""
    tgt = _pdf_target(db, target)
    src = db.get(SourcePdf, pdf_id)
    r = pdfsrc.parse_rect(rect)
    if not tgt or not src or not r:
        return _redirect(f"/admin/pdfs/{pdf_id}", t("pdf.no_selection"))
    ups = _crop_upload(db, {"pdf_id": pdf_id, "pdf_page": page, "pdf_rect": rect})
    _add_uploads(db, ups, **tgt[0])
    db.commit()
    return RedirectResponse(
        f"/admin/pdfs/{pdf_id}?page={page}&target={quote(target)}&msg={quote(t('pdf.attached').format(label=tgt[2]))}",
        status_code=303,
    )


# ---------- change history ----------

HIST_KINDS = ["score", "stage", "event", "review", "comment", "roster", "bulk"]
HIST_LIMIT = 1000


def _history_rows(db, sid, actor, student, kind):
    from .. import audit

    return audit.query(db, session_id=sid, student_id=student or None, kind=kind if kind in HIST_KINDS else None,
                       actor_id=actor or None, limit=HIST_LIMIT)


@router.get("/sessions/{sid}/history")
def session_history(sid: int, request: Request, actor: int = 0, student: int = 0, kind: str = "",
                    db: Session = Depends(get_db)):
    from .. import audit
    from ..models import ChangeLog

    s = db.get(AssessSession, sid)
    if not s:
        return _redirect("/admin/sessions")
    actors = (
        db.query(ChangeLog.actor_id, ChangeLog.actor_name).filter(ChangeLog.session_id == sid, ChangeLog.actor_id.isnot(None))
        .distinct().order_by(ChangeLog.actor_name).all()
    )
    entries = audit.describe(db, _history_rows(db, sid, actor, student, kind))
    return templates.TemplateResponse(
        request,
        "admin_history.html",
        {
            "s": s, "entries": entries, "limit": HIST_LIMIT,
            "actors": [(a, n) for a, n in actors], "kinds": HIST_KINDS,
            "students": db.query(Student).filter_by(session_id=sid).order_by(Student.name).all(),
            "f": {"actor": actor, "student": student, "kind": kind}, "active": "admin",
        },
    )


@router.get("/sessions/{sid}/history.csv")
def session_history_csv(sid: int, actor: int = 0, student: int = 0, kind: str = "", db: Session = Depends(get_db)):
    import csv
    import io

    from .. import audit

    s = db.get(AssessSession, sid)
    if not s:
        return _redirect("/admin/sessions")
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Time", "Who", "Child", "Item", "Field", "Before", "After"])
    for e in audit.describe(db, _history_rows(db, sid, actor, student, kind)):
        for label, _o, _n, full_old, full_new in e["lines"] or [("", "", "", "", "")]:
            w.writerow([e["at"].strftime("%Y-%m-%d %H:%M:%S"), e["who"], e["child"], e["what"], label, full_old, full_new])
    name = f"{s.date}_{s.label.replace(' ', '_')}_history.csv"
    safe = "".join(c for c in name if c.isascii() and (c.isalnum() or c in "._-")) or "history.csv"
    return Response(content=("﻿" + buf.getvalue()).encode("utf-8"), media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="{safe}"'})
