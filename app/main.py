import os
from urllib.parse import quote

from fastapi import Depends, FastAPI, Form, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from .auth import AUTH_COOKIE, TOKEN_TTL, hash_password, make_token, parse_token, verify_password
from .db import Base, engine, get_db, SessionLocal
from .i18n import cur_lang, current_lang, t
from .models import AssessSession, Teacher
from .routers import admin, api, report, workbench
from .schema import upgrade_schema
from .seed import seed_questions
from .templating import templates

app = FastAPI(title="Think Academy SV Assessment Workbench")

templates.env.globals["t"] = t
templates.env.globals["cur_lang"] = cur_lang


@app.middleware("http")
async def lang_middleware(request: Request, call_next):
    lang = request.cookies.get("lang", "en")
    token = current_lang.set(lang if lang in ("en", "zh") else "en")
    try:
        return await call_next(request)
    finally:
        current_lang.reset(token)


PUBLIC_PREFIXES = ("/static/", "/lang/", "/favicon.ico")


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    path = request.url.path
    teacher = None
    token = request.cookies.get("auth")
    if token:
        tid = parse_token(token)
        if tid:
            db = SessionLocal()
            try:
                tt = db.get(Teacher, tid)
                if tt and tt.active:
                    teacher = tt
            finally:
                db.close()
    request.state.teacher = teacher

    # admin impersonating a teacher keeps their own token in admin_auth
    request.state.admin_return = False
    admin_token = request.cookies.get("admin_auth")
    if admin_token and teacher is not None:
        atid = parse_token(admin_token)
        if atid and atid != teacher.id:
            db = SessionLocal()
            try:
                at = db.get(Teacher, atid)
                if at and at.active and at.role == "admin":
                    request.state.admin_return = True
            finally:
                db.close()

    if path == "/login" or any(path.startswith(p) for p in PUBLIC_PREFIXES):
        return await call_next(request)
    if teacher is None:
        if path.startswith("/api/"):
            return JSONResponse(status_code=401, content={"ok": False, "error": "login required"})
        nxt = path + ("?" + str(request.url.query) if request.url.query else "")
        return RedirectResponse(f"/login?next={quote(nxt)}", status_code=303)
    if path.startswith("/admin") and teacher.role != "admin":
        return RedirectResponse("/wb?msg=admin_only", status_code=303)
    return await call_next(request)


@app.get("/lang/{code}")
def set_lang(code: str, next: str = "/"):
    if not next.startswith("/"):
        next = "/"
    resp = RedirectResponse(next, status_code=303)
    resp.set_cookie("lang", code if code in ("en", "zh") else "en", max_age=31536000, path="/")
    return resp

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

app.include_router(admin.router)
app.include_router(workbench.router)
app.include_router(api.router)
app.include_router(report.router)


@app.on_event("startup")
def startup():
    # Several workers start at once: on PostgreSQL, one at a time runs the schema
    # upgrade + seeding (otherwise two can ALTER the same table and one crashes).
    lock = None
    if engine.dialect.name == "postgresql":
        lock = engine.connect()
        lock.exec_driver_sql("SELECT pg_advisory_lock(7240311)")
    try:
        _startup_setup()
    finally:
        if lock is not None:
            lock.exec_driver_sql("SELECT pg_advisory_unlock(7240311)")
            lock.close()


def _startup_setup():
    upgrade_schema(engine)
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        seed_questions(db)
        from .models import Paper
        from .stage_defs import ensure_paper_defaults

        for p in db.query(Paper).all():
            ensure_paper_defaults(db, p.id)
        from .bank import ensure_bank

        ensure_bank(db)
        db.commit()
        admins = db.query(Teacher).filter_by(role="admin").all()
        if not any(a.password_hash for a in admins):
            admin_user = db.query(Teacher).filter_by(name="Admin").first()
            if admin_user is None:
                admin_user = Teacher(name="Admin")
                db.add(admin_user)
            admin_user.role = "admin"
            admin_user.active = True
            # Only for a brand-new, empty database. On a server set
            # MI_INITIAL_ADMIN_PASSWORD so the public README default is never live.
            admin_user.password_hash = hash_password(
                os.environ.get("MI_INITIAL_ADMIN_PASSWORD") or "admin123"
            )
            db.commit()
    finally:
        db.close()


@app.get("/")
def home(request: Request, db: Session = Depends(get_db)):
    sessions = db.query(AssessSession).order_by(AssessSession.date.desc()).all()
    teachers = db.query(Teacher).filter_by(active=True).all()
    return templates.TemplateResponse(
        request,
        "home.html",
        {"sessions": sessions, "teachers": teachers, "active": "home"},
    )


@app.get("/login")
def login_page(request: Request, next: str = "/"):
    if request.state.teacher:
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse(
        request, "login.html", {"next": next, "error": "", "active": ""}
    )


@app.post("/login")
def login_post(
    request: Request,
    name: str = Form(...),
    password: str = Form(...),
    next: str = Form("/"),
    db: Session = Depends(get_db),
):
    teacher = db.query(Teacher).filter(Teacher.name == name.strip()).first()
    if teacher and teacher.active and verify_password(password, teacher.password_hash or ""):
        target = next if next.startswith("/") else "/"
        resp = RedirectResponse(target, status_code=303)
        resp.set_cookie(
            "auth", make_token(teacher.id), max_age=TOKEN_TTL, **AUTH_COOKIE
        )
        return resp
    return templates.TemplateResponse(
        request,
        "login.html",
        {"next": next, "error": t("login.error"), "active": ""},
        status_code=401,
    )


@app.get("/logout")
def logout():
    resp = RedirectResponse("/login", status_code=303)
    resp.delete_cookie("auth")
    resp.delete_cookie("admin_auth")
    return resp


@app.post("/switch/{tid}")
def switch_account(tid: int, request: Request, db: Session = Depends(get_db)):
    """Admin (or an admin currently impersonating) switches straight into
    another account from the header menu, no password needed."""
    me = request.state.teacher
    target = db.get(Teacher, tid)
    is_admin = bool(me and me.role == "admin")

    keep_token = None
    admin_token = request.cookies.get("admin_auth")
    if admin_token:
        atid = parse_token(admin_token)
        at = db.get(Teacher, atid) if atid else None
        if at and at.active and at.role == "admin":
            keep_token = admin_token

    if not target or not target.active or not (is_admin or keep_token):
        return RedirectResponse("/", status_code=303)

    resp = RedirectResponse("/" if target.role == "admin" else "/wb", status_code=303)
    resp.set_cookie("auth", make_token(target.id), max_age=TOKEN_TTL, **AUTH_COOKIE)
    if target.role == "admin":
        resp.delete_cookie("admin_auth")
    else:
        token = keep_token or request.cookies.get("auth", "")
        resp.set_cookie("admin_auth", token, max_age=TOKEN_TTL, **AUTH_COOKIE)
    return resp


@app.get("/impersonate/stop")
def impersonate_stop(request: Request, db: Session = Depends(get_db)):
    admin_token = request.cookies.get("admin_auth")
    resp = RedirectResponse("/admin/teachers", status_code=303)
    tid = parse_token(admin_token) if admin_token else None
    teacher = db.get(Teacher, tid) if tid else None
    if teacher and teacher.active and teacher.role == "admin":
        resp.set_cookie("auth", admin_token, max_age=TOKEN_TTL, **AUTH_COOKIE)
    else:
        resp = RedirectResponse("/login", status_code=303)
        resp.delete_cookie("auth")
    resp.delete_cookie("admin_auth")
    return resp
