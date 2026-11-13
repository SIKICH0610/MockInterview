"""Question bank + interview (paper) building.

- A question TYPE fixes how it is scored (the buttons on the scoring card):
    single  academic 0/1/2
    expr    academic 0/1/2 + expression 0/1/2
    count   academic 0/1/2 + a "correct x / N" counter
- The bank holds reusable questions. Citing one into an interview COPIES it
  (fields + pictures) and remembers where it came from, so editing the bank never
  changes an interview that sessions already used.
- An interview's question list can only be restructured (add / remove / reorder /
  change type) while no child has been scored on it; codes are renumbered
  M01.., E01.. per level so they stay tidy.
"""

from .models import (
    AssessSession,
    BankQuestion,
    ItemRecord,
    Paper,
    Question,
    QuestionMedia,
    Student,
)

QTYPES = ["single", "expr", "count"]
DOMAINS = ["Mathematics", "English"]
LEVELS = ["TK", "K"]
PREFIX = {"Mathematics": "M", "English": "E"}

# default rubric wording per type (the card text stays English, like the existing papers)
DEFAULT_RUBRIC = {
    "r": ("Independent correct answer", "Correct after guidance", "No correct answer after guidance"),
    "count_r": (
        "Independently gets all {n}",
        "Independently gets some, or more after a cue",
        "None established after support",
    ),
    "e": ("Relevant complete sentence", "Relevant word / short phrase", "No relevant oral response"),
}

FIELDS = ["domain", "ability", "title", "prompt", "target", "setup", "r2", "r1", "r0", "e2", "e1", "e0", "trial_max"]

ALLOWED_MEDIA = {
    "application/pdf": (b"%PDF",),
    "image/png": (b"\x89PNG",),
    "image/jpeg": (b"\xff\xd8\xff",),
    "image/gif": (b"GIF87a", b"GIF89a"),
    "image/webp": (b"RIFF",),
}
MAX_MEDIA_BYTES = 15 * 1024 * 1024


def qtype_of(q):
    if getattr(q, "qtype", "") in QTYPES:
        return q.qtype
    if q.has_expression:
        return "expr"
    if q.trial_max:
        return "count"
    return "single"


def apply_qtype(q, qtype, trial_max):
    """Sets the type and the scoring flags it implies (Question only has the flags)."""
    qtype = qtype if qtype in QTYPES else "single"
    q.qtype = qtype
    if isinstance(q, Question):
        q.has_expression = qtype == "expr"
    q.trial_max = (trial_max or 6) if qtype == "count" else None
    if qtype != "expr":
        q.e2 = q.e1 = q.e0 = None


def default_rubric(qtype, n=6):
    r = DEFAULT_RUBRIC["count_r"] if qtype == "count" else DEFAULT_RUBRIC["r"]
    return {
        "r2": r[0].format(n=n), "r1": r[1], "r0": r[2],
        "e2": DEFAULT_RUBRIC["e"][0], "e1": DEFAULT_RUBRIC["e"][1], "e0": DEFAULT_RUBRIC["e"][2],
    }


def sniff_media(filename, data):
    """-> mime or None (only PDFs and common pictures; SVG is refused on purpose)."""
    for mime, magics in ALLOWED_MEDIA.items():
        if any(data.startswith(m) for m in magics):
            if mime == "image/webp" and data[8:12] != b"WEBP":
                continue
            return mime
    return None


def copy_media(db, src_list, **owner):
    for i, m in enumerate(src_list):
        db.add(QuestionMedia(filename=m.filename, caption=m.caption or "", mime=m.mime, data=m.data, size=m.size,
                             sort=i, **owner))


# ---------- interview structure ----------

def default_paper_id(db):
    p = db.query(Paper).order_by(Paper.id).first()
    return p.id if p else None


def paper_locked(db, pid):
    """True once any child in a session using this interview has a score."""
    q = (
        db.query(ItemRecord.id)
        .join(Student, ItemRecord.student_id == Student.id)
        .join(AssessSession, Student.session_id == AssessSession.id)
    )
    if pid == default_paper_id(db):
        q = q.filter((AssessSession.paper_id == pid) | (AssessSession.paper_id.is_(None)))
    else:
        q = q.filter(AssessSession.paper_id == pid)
    return q.first() is not None


def renumber(db, pid, version):
    """Codes M01.. / E01.. in display order; Mathematics first."""
    qs = db.query(Question).filter_by(paper_id=pid, version=version).order_by(Question.sort, Question.id).all()
    n = 0
    for dom in DOMAINS:
        part = [q for q in qs if q.domain == dom]
        for i, q in enumerate(part, 1):
            q.code = f"{PREFIX[dom]}{i:02d}"
            q.sort = n
            n += 1
    others = [q for q in qs if q.domain not in DOMAINS]
    for i, q in enumerate(others, 1):
        q.code = f"X{i:02d}"
        q.sort = n
        n += 1
    db.flush()


def _park_codes(db, pid, version):
    """Give every question a temporary unique code so renumbering never collides
    with the (paper, version, code) unique constraint mid-way."""
    for q in db.query(Question).filter_by(paper_id=pid, version=version).all():
        q.code = f"~{q.id}"[:8]
    db.flush()


def cite(db, bank, pid, version):
    """Copy a bank question into an interview level; returns the new Question."""
    last = (
        db.query(Question)
        .filter_by(paper_id=pid, version=version, domain=bank.domain)
        .order_by(Question.sort.desc())
        .first()
    )
    q = Question(
        paper_id=pid,
        version=version,
        code=f"~new{bank.id}"[:8],
        sort=(last.sort + 1) if last else (0 if bank.domain == "Mathematics" else 1000),
        bank_id=bank.id,
        **{f: getattr(bank, f) for f in FIELDS},
    )
    apply_qtype(q, bank.qtype, bank.trial_max)
    if bank.qtype == "expr":
        q.e2, q.e1, q.e0 = bank.e2, bank.e1, bank.e0
    db.add(q)
    db.flush()
    copy_media(db, bank.media, question_id=q.id)
    _park_codes(db, pid, version)
    renumber(db, pid, version)
    return q


def remove_question(db, q):
    pid, version = q.paper_id, q.version
    db.delete(q)
    db.flush()
    _park_codes(db, pid, version)
    renumber(db, pid, version)


def move_question(db, q, step):
    pid, version = q.paper_id, q.version
    same = (
        db.query(Question)
        .filter_by(paper_id=pid, version=version, domain=q.domain)
        .order_by(Question.sort, Question.id)
        .all()
    )
    i = same.index(q)
    j = i + step
    if 0 <= j < len(same):
        same[i].sort, same[j].sort = same[j].sort, same[i].sort
        if same[i].sort == same[j].sort:
            same[i].sort += step
        db.flush()
        _park_codes(db, pid, version)
        renumber(db, pid, version)


def save_to_bank(db, q):
    """Write an interview question back to its bank entry (fields + pictures)."""
    b = db.get(BankQuestion, q.bank_id) if q.bank_id else None
    if b is None:
        b = BankQuestion(level=q.version, qtype=qtype_of(q))
        db.add(b)
    for f in FIELDS:
        setattr(b, f, getattr(q, f))
    b.qtype = qtype_of(q)
    db.flush()
    for m in list(b.media):
        db.delete(m)
    db.flush()
    copy_media(db, q.media, bank_id=b.id)
    q.bank_id = b.id
    return b


def known_abilities(db):
    """Core-content labels already in use, per domain (for the picker)."""
    out = {d: [] for d in DOMAINS}
    seen = set()
    rows = list(db.query(Question.domain, Question.ability)) + list(db.query(BankQuestion.domain, BankQuestion.ability))
    for dom, ab in rows:
        if ab and (dom, ab) not in seen:
            seen.add((dom, ab))
            out.setdefault(dom, []).append(ab)
    return out


# ---------- one-time migration ----------

def ensure_bank(db):
    """Give every question a type, and seed the bank from the existing interviews
    the first time (one bank entry per distinct question; interview copies link to it)."""
    for q in db.query(Question).filter((Question.qtype.is_(None)) | (Question.qtype == "")).all():
        q.qtype = qtype_of(q)
    if db.query(BankQuestion.id).first() is not None:
        db.flush()
        return
    made = {}
    for q in db.query(Question).order_by(Question.paper_id, Question.version, Question.sort).all():
        key = (q.domain, q.version, q.title.strip(), (q.prompt or "").strip())
        b = made.get(key)
        if b is None:
            b = BankQuestion(level=q.version, qtype=qtype_of(q), **{f: getattr(q, f) for f in FIELDS})
            db.add(b)
            db.flush()
            made[key] = b
        q.bank_id = b.id
    db.flush()
