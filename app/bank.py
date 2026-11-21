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

QTYPES = ["single", "expr", "count", "drag"]  # drag = one score, worked out from a drag-on-tablet task
DOMAINS = ["Mathematics", "English"]
LEVELS = ["TK", "K"]  # the grades every new interview starts with; each interview can add or remove grades


def norm_level(text):
    """A grade name as stored: upper case, at most 8 characters ("TK", "K", "G1", "PRE-K"). "" if not usable."""
    import re as _re

    s = " ".join(str(text or "").split()).upper()
    return s if _re.fullmatch(r"[A-Z0-9][A-Z0-9+\- ]{0,7}", s) else ""


def paper_levels(db, pid):
    """Grades of one interview, in order."""
    p = db.get(Paper, pid) if pid else None
    if p is None:
        return list(LEVELS)
    saved = [x for x in (p.levels or "").split(",") if x]
    if saved:
        return saved
    have = {v for (v,) in db.query(Question.version).filter_by(paper_id=pid).distinct()}
    if not have:
        return list(LEVELS)
    return [x for x in LEVELS if x in have] + sorted(have - set(LEVELS))


def all_levels(db):
    """Every grade in use anywhere (interviews, bank), the usual ones first."""
    out = list(LEVELS)
    for p in db.query(Paper).order_by(Paper.id):
        for x in paper_levels(db, p.id):
            if x not in out:
                out.append(x)
    for (x,) in db.query(BankQuestion.level).distinct():
        if x and x not in out:
            out.append(x)
    return out


def level_scored(db, pid, level):
    """True once a child of this grade has a score in a session using this interview."""
    q = (
        db.query(ItemRecord.id)
        .join(Student, ItemRecord.student_id == Student.id)
        .join(AssessSession, Student.session_id == AssessSession.id)
        .filter(Student.level == level)
    )
    if pid == default_paper_id(db):
        q = q.filter((AssessSession.paper_id == pid) | (AssessSession.paper_id.is_(None)))
    else:
        q = q.filter(AssessSession.paper_id == pid)
    return q.first() is not None


def add_level(db, pid, level, copy_from=""):
    """Add a grade to an interview, optionally starting from a copy of another grade's questions."""
    p = db.get(Paper, pid)
    levels = paper_levels(db, pid)
    if level in levels:
        return False
    if copy_from in levels:
        skip = {"id", "version"}
        for q in db.query(Question).filter_by(paper_id=pid, version=copy_from).order_by(Question.sort, Question.id).all():
            nq = Question(version=level, **{c.name: getattr(q, c.name) for c in Question.__table__.columns if c.name not in skip})
            db.add(nq)
            db.flush()
            copy_media(db, q.media, question_id=nq.id)
    p.levels = ",".join(levels + [level])
    return True


def remove_level(db, pid, level):
    """Take a grade out of an interview together with its questions."""
    p = db.get(Paper, pid)
    levels = paper_levels(db, pid)
    for q in db.query(Question).filter_by(paper_id=pid, version=level).all():
        db.delete(q)
    p.levels = ",".join(x for x in levels if x != level)
PREFIX = {"Mathematics": "M", "English": "E"}

# default rubric wording per type (the card text stays English, like the existing papers)
DEFAULT_RUBRIC = {
    "r": ("Independent correct answer", "Correct after guidance", "No correct answer after guidance"),
    "drag_r": ("Every piece in the right place", "Some pieces right, or the right places but a wrong direction",
               "No piece in the right place"),
    "count_r": (
        "Independently gets all {n}",
        "Independently gets some, or more after a cue",
        "None established after support",
    ),
    "e": ("Relevant complete sentence", "Relevant word / short phrase", "No relevant oral response"),
}

# key ability + home practice + curriculum links (also filled by the spreadsheet import)
EXTRA_FIELDS = ["key_ability", "practice", "practice_answer", "home_game",
                "ta_topic", "ta_lesson", "ccss_module", "ccss_codes", "scope_note", "score_caps", "drag", "evidence", "talk"]


def score_caps(q):
    """{2: (en, zh), 1: ..., 0: ...} - a question's own captions for the task-score buttons, where it set any.
    Stored as three lines (for 2, 1, 0), each "English | 中文"; a blank line keeps the standard caption."""
    out = {}
    lines = (getattr(q, "score_caps", "") or "").split("\n")
    for v, line in zip((2, 1, 0), lines):
        en, _, zh = line.partition("|")
        en, zh = en.strip(), zh.strip()
        if en or zh:
            out[v] = (en or zh, zh or en)
    return out


def talk_of(q):
    """{1: (en, zh), 0: (en, zh)} - the phrases a teacher can say to parents when the task scored 1 or 0.
    Stored as JSON {"1": {"en", "zh"}, "0": {...}}; a missing language falls back to the other one."""
    import json

    try:
        raw = json.loads(getattr(q, "talk", "") or "{}")
    except ValueError:
        return {}
    out = {}
    for v in (1, 0):
        d = raw.get(str(v)) if isinstance(raw, dict) else None
        if isinstance(d, dict):
            en, zh = str(d.get("en") or "").strip(), str(d.get("zh") or "").strip()
            if en or zh:
                out[v] = (en or zh, zh or en)
    return out


def talk_clean(parts):
    """{"1": {"en", "zh"}, "0": {...}} from the form's four boxes -> the stored JSON text ("" when all are empty)."""
    import json

    out = {}
    for v in ("1", "0"):
        en = " ".join(str(parts.get(f"talk{v}_en") or "").split())[:600]
        zh = " ".join(str(parts.get(f"talk{v}_zh") or "").split())[:600]
        if en or zh:
            out[v] = {"en": en, "zh": zh}
    return json.dumps(out, ensure_ascii=False, separators=(",", ":")) if out else ""


def talk_for(q, r, zh=False):
    """The phrase for this child's result on this task, or "" (full marks, not scored, or no phrase written).
    {right} and {total} in a phrase become the child's count on a counting task."""
    if r is None or r.status != "scored" or r.academic is None or r.academic >= 2:
        return ""
    pair = talk_of(q).get(r.academic)
    if not pair:
        return ""
    text = pair[1] if zh else pair[0]
    if q.trial_max and r.trial is not None:
        text = text.replace("{right}", str(r.trial)).replace("{total}", str(q.trial_max))
    elif "{right}" in text or "{total}" in text:  # no count recorded: drop the sentence that needs it
        import re

        text = " ".join(s for s in re.split(r"(?<=[.!?。！？])\s*", text) if "{right}" not in s and "{total}" not in s)
    return text


FIELDS = ["domain", "ability", "title", "prompt", "target", "setup", "r2", "r1", "r0", "e2", "e1", "e0",
          "trial_max"] + EXTRA_FIELDS

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


def count_cuts(n):
    """(hi, mid) for a "count x of N" question: x >= hi scores 2, x >= mid scores 1, less scores 0.
    6 items: 5-6 / 3-4 / 0-2.  3 items: 3 / 2 / 0-1.  Other sizes follow the same proportions."""
    n = int(n or 0)
    return -(-5 * n // 6), -(-n // 2)


def count_score(n, x):
    """The task score of a count question, from the number of items the child got right - nothing else."""
    if x is None or not n:
        return None
    hi, mid = count_cuts(n)
    return 2 if x >= hi else 1 if x >= mid else 0


def count_spans(n):
    """("5–6", "3–4", "0–2") for 6 items; ("3", "2", "0–1") for 3: how many right gives 2 / 1 / 0."""
    hi, mid = count_cuts(n)
    span = lambda a, b: f"{a}" if a == b else f"{a}–{b}"  # noqa: E731
    return span(hi, int(n)), span(mid, hi - 1), span(0, mid - 1)


def count_rubric(n):
    """Rubric wording (2, 1, 0) for a count question of n items."""
    hi, mid = count_cuts(n)
    span = lambda a, b: f"{a}" if a == b else f"{a}–{b}"  # noqa: E731
    return (f"{span(hi, n)} of {n} correct", f"{span(mid, hi - 1)} of {n} correct", f"{span(0, mid - 1)} of {n} correct")


def default_rubric(qtype, n=6):
    r = count_rubric(n) if qtype == "count" else DEFAULT_RUBRIC["drag_r"] if qtype == "drag" else DEFAULT_RUBRIC["r"]
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


# ---------- spreadsheet: key abilities, curriculum links and home practice ----------

SHEET_COLUMNS = [  # (field, words that must all appear in the column header)
    ("id", ("question", "id")),
    ("task", ("original", "task")),
    ("key_ability", ("ability",)),
    ("ta_topic", ("topic", "match")),
    ("ta_lesson", ("lesson",)),
    ("ccss_module", ("ccss", "module")),
    ("ccss_codes", ("ccss", "code")),
    ("scope_note", ("scope",)),
    ("practice_answer", ("practice", "answer")),
    ("practice", ("extra", "practice")),
    ("home_game", ("game",)),
]


def _clean_cell(v):
    """Spreadsheet text -> plain text (drops the wrapping quotes some exports add)."""
    s = "" if v is None else str(v).replace("\r\n", "\n").replace("\r", "\n").strip()
    if len(s) >= 2 and s[0] == '"' and s[-1] == '"':
        s = s[1:-1].replace('""', '"').strip()
    return s


def parse_ability_sheet(data):
    """.xlsx bytes -> ([{id, level, code, task, key_ability, practice, ...}], [problems]).
    Each sheet has a header row containing "Question ID"; rows are like "TK M01"."""
    import io
    import re

    import openpyxl

    import warnings

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # "no default style" noise from some exports
        wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    rows, problems = [], []
    for ws in wb.worksheets:
        cols = None
        for r in ws.iter_rows(values_only=True):
            cells = [_clean_cell(c) for c in r]
            if cols is None:
                low = [c.lower() for c in cells]
                if any("question" in c and "id" in c for c in low):
                    cols = {}
                    for field, words in SHEET_COLUMNS:
                        for i, h in enumerate(low):
                            if i not in cols.values() and all(w in h for w in words):
                                cols[field] = i
                                break
                continue
            qid = cells[cols["id"]] if cols.get("id") is not None and cols["id"] < len(cells) else ""
            m = re.match(r"^\s*([A-Za-z0-9+\-]{1,8}?)\s*[-_ ]?\s*([A-Za-z]\d{1,2})\s*$", qid)  # "TK M01", "K E03", "G1 M02"
            if not m:
                continue
            row = {"id": qid, "level": m.group(1).upper(), "code": m.group(2).upper()}
            for field, i in cols.items():
                if field != "id":
                    row[field] = cells[i] if i < len(cells) else ""
            rows.append(row)
        if cols is None:
            problems.append(f"{ws.title}: no 'Question ID' header row")
    return rows, problems


def apply_ability_sheet(db, pid, rows):
    """Fill the interview's questions (and their bank entries) from parsed rows.
    Only non-empty cells overwrite. -> (updated ids, ids not in this interview, title mismatches)"""
    import re

    def stems(s):
        """Significant words, shortened, so 'sentences' matches 'sentence'."""
        return {w[:5] for w in re.findall(r"[a-z0-9]+", (s or "").lower().replace("'", "")) if len(w) > 3}

    updated, missing, mismatched = [], [], []
    for row in rows:
        q = db.query(Question).filter_by(paper_id=pid, version=row["level"], code=row["code"]).first()
        if q is None:
            missing.append(row["id"])
            continue
        targets = [q] + ([db.get(BankQuestion, q.bank_id)] if q.bank_id else [])
        for obj in filter(None, targets):
            for f in EXTRA_FIELDS:
                v = row.get(f, "")
                if v:
                    setattr(obj, f, v[:255] if f in ("ta_lesson", "ccss_module", "ccss_codes") else v)
        first = (row.get("task") or "").split("\n")[0]
        a, b = stems(first), stems(q.title)
        if a and b and not (a <= b or b <= a):  # same task when one title's words contain the other's
            mismatched.append((row["id"], first.strip(), q.title))
        updated.append(row["id"])
    db.flush()
    return updated, missing, mismatched


# ---------- drag-and-drop builder ----------

def reorder(db, pid, version, domain, ids):
    """Put one section's questions in the given order (ids = question ids); codes renumber."""
    qs = {q.id: q for q in db.query(Question).filter_by(paper_id=pid, version=version, domain=domain)}
    order = [i for i in ids if i in qs] + [i for i in sorted(qs, key=lambda i: (qs[i].sort, i)) if i not in ids]
    for n, qid in enumerate(order):
        qs[qid].sort = n
    db.flush()
    _park_codes(db, pid, version)
    renumber(db, pid, version)


def add_at(db, bank, pid, version, index=None):
    """Cite a bank question into a section, at a position (None = end)."""
    q = cite(db, bank, pid, version)
    if index is not None:
        same = db.query(Question).filter_by(paper_id=pid, version=version, domain=q.domain).order_by(Question.sort, Question.id).all()
        ids = [x.id for x in same if x.id != q.id]
        ids.insert(max(0, min(index, len(ids))), q.id)
        reorder(db, pid, version, q.domain, ids)
    return q


def set_stage_stem(db, pid, activity, stage=None):
    """Use a bank stem for one team part of an interview (snapshot of text + files).
    stage = which part it goes into (default: the part the stem was written for)."""
    from .models import StageMaterial

    stage = stage or activity.stage
    m = db.query(StageMaterial).filter_by(paper_id=pid, stage=stage).first()
    if m is None:
        m = StageMaterial(paper_id=pid, stage=stage)
        db.add(m)
    m.title, m.text, m.activity_id = activity.title, activity.prompt, activity.id
    db.query(QuestionMedia).filter_by(paper_id=pid, stage=stage).delete()
    copy_media(db, activity.media, paper_id=pid, stage=stage)
    return m


def clear_stage_stem(db, pid, stage):
    from .models import StageMaterial

    db.query(StageMaterial).filter_by(paper_id=pid, stage=stage).delete()
    db.query(QuestionMedia).filter_by(paper_id=pid, stage=stage).delete()
