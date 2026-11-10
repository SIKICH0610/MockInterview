from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from .db import Base


class Teacher(Base):
    __tablename__ = "teachers"
    id = Column(Integer, primary_key=True)
    name = Column(String(80), unique=True, nullable=False)
    role = Column(String(16), default="teacher")  # teacher / admin
    active = Column(Boolean, default=True)
    password_hash = Column(String(256), default="")


class AssessSession(Base):
    __tablename__ = "assess_sessions"
    id = Column(Integer, primary_key=True)
    date = Column(String(16), nullable=False)  # YYYY-MM-DD
    label = Column(String(120), nullable=False)  # e.g. "Morning Session A"
    paper_id = Column(Integer, ForeignKey("papers.id"), nullable=True)
    notes = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.now)

    paper = relationship("Paper")

    students = relationship("Student", back_populates="session", cascade="all, delete-orphan")
    groups = relationship("Group", back_populates="session", cascade="all, delete-orphan")


class Group(Base):
    __tablename__ = "groups"
    id = Column(Integer, primary_key=True)
    session_id = Column(Integer, ForeignKey("assess_sessions.id"), nullable=False)
    name = Column(String(80), nullable=False)
    teacher_id = Column(Integer, ForeignKey("teachers.id"), nullable=True)

    session = relationship("AssessSession", back_populates="groups")
    students = relationship("Student", back_populates="group")


class Student(Base):
    __tablename__ = "students"
    id = Column(Integer, primary_key=True)
    session_id = Column(Integer, ForeignKey("assess_sessions.id"), nullable=False)
    group_id = Column(Integer, ForeignKey("groups.id"), nullable=True)
    external_id = Column(String(64), default="")
    name = Column(String(120), nullable=False)
    level = Column(String(8), nullable=False)  # TK / K / ? (unresolved)
    grade = Column(String(64), default="")  # raw gradeName from the TA export
    course = Column(String(255), default="")  # enrolled class (interview content)
    created_at = Column(DateTime, default=datetime.now)

    session = relationship("AssessSession", back_populates="students")
    group = relationship("Group", back_populates="students")
    records = relationship("ItemRecord", back_populates="student", cascade="all, delete-orphan")
    events = relationship("Event", back_populates="student", cascade="all, delete-orphan")


class Paper(Base):
    """A question paper / interview edition. Sessions pick one paper;
    new assessments clone an existing paper and edit its questions."""

    __tablename__ = "papers"
    id = Column(Integer, primary_key=True)
    name = Column(String(120), unique=True, nullable=False)
    note = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.now)

    questions = relationship("Question", back_populates="paper")


class Question(Base):
    __tablename__ = "questions"
    __table_args__ = (UniqueConstraint("paper_id", "version", "code"),)
    id = Column(Integer, primary_key=True)
    paper_id = Column(Integer, ForeignKey("papers.id"), nullable=True)
    version = Column(String(8), nullable=False)  # TK / K (paper-defined)
    code = Column(String(8), nullable=False)  # M01..M06, E01..E06
    sort = Column(Integer, nullable=False)
    domain = Column(String(32), nullable=False)  # Mathematics / English
    ability = Column(String(48), nullable=False)  # Number Sense, Letter Names, ...
    title = Column(String(160), nullable=False)
    prompt = Column(Text, default="")
    target = Column(Text, default="")
    setup = Column(Text, default="")
    r2 = Column(Text, default="")
    r1 = Column(Text, default="")
    r0 = Column(Text, default="")
    e2 = Column(Text, nullable=True)
    e1 = Column(Text, nullable=True)
    e0 = Column(Text, nullable=True)
    has_expression = Column(Boolean, default=False)
    trial_max = Column(Integer, nullable=True)  # sub-trial count (/6, /3)

    paper = relationship("Paper", back_populates="questions")


class StageDimDef(Base):
    """Editable group-activity rubric dimension, owned by a paper.

    options holds a JSON list ordered best -> weakest: [[en, zh], ...].
    stage_obs.response stores the EN option string, so renaming an option
    does not rewrite history (old rows keep their recorded wording).
    """

    __tablename__ = "stage_dim_defs"
    __table_args__ = (UniqueConstraint("paper_id", "stage", "key"),)
    id = Column(Integer, primary_key=True)
    paper_id = Column(Integer, ForeignKey("papers.id"), nullable=False)
    stage = Column(String(32), nullable=False)
    key = Column(String(32), nullable=False)
    label = Column(String(160), nullable=False)
    label_zh = Column(String(160), default="")
    options = Column(Text, nullable=False)
    sort = Column(Integer, default=0)

    paper = relationship("Paper")


class StoryPromptDef(Base):
    """Editable Circle Time "Let's Talk" prompts, owned by a paper."""

    __tablename__ = "story_prompt_defs"
    id = Column(Integer, primary_key=True)
    paper_id = Column(Integer, ForeignKey("papers.id"), nullable=False)
    idx = Column(Integer, nullable=False)
    text = Column(Text, nullable=False)

    paper = relationship("Paper")


class ItemRecord(Base):
    __tablename__ = "item_records"
    __table_args__ = (UniqueConstraint("student_id", "code"),)
    id = Column(Integer, primary_key=True)
    student_id = Column(Integer, ForeignKey("students.id"), nullable=False)
    code = Column(String(8), nullable=False)
    # status: None=blank, scored / not_observed / not_completed
    status = Column(String(16), nullable=True)
    academic = Column(Integer, nullable=True)  # 0/1/2
    guided = Column(Boolean, default=False)  # reserved
    expression = Column(Integer, nullable=True)  # 0/1/2 for M02-M06
    trial = Column(Integer, nullable=True)  # correct sub-trial count
    note = Column(Text, default="")
    teacher_id = Column(Integer, ForeignKey("teachers.id"), nullable=True)
    rev = Column(Integer, default=1)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    student = relationship("Student", back_populates="records")
    teacher = relationship("Teacher")


class Event(Base):
    """SEL / Classroom Skills support & deduction events."""

    __tablename__ = "events"
    id = Column(Integer, primary_key=True)
    student_id = Column(Integer, ForeignKey("students.id"), nullable=False)
    category = Column(String(8), nullable=False)  # SEL / CS
    stage = Column(String(32), default="")
    code = Column(String(8), nullable=True)  # optional link to a question
    points = Column(Integer, default=1)  # points deducted
    reason = Column(Text, default="")
    support = Column(Text, default="")
    teacher_id = Column(Integer, ForeignKey("teachers.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.now)

    student = relationship("Student", back_populates="events")
    teacher = relationship("Teacher")


class StageObs(Base):
    """Observations during group activities (Separation, Circle Time, ...).

    - Separation: one row per student (upserted), response in
      independent / brief / support / not_observed.
    - Circle Time: append-only rows, one per response opportunity,
      prompt_index 1-8 (the Let's Talk prompts), response in
      independent / prompted / none. A child with no rows for a prompt
      simply was not given that opportunity (counts as not observed).
    - Other stages: append-only rows without prompt_index.
    """

    __tablename__ = "stage_obs"
    id = Column(Integer, primary_key=True)
    student_id = Column(Integer, ForeignKey("students.id"), nullable=False)
    stage = Column(String(32), nullable=False)
    prompt_index = Column(Integer, nullable=True)
    dim = Column(String(32), nullable=True)  # multi-dimension rubric key
    response = Column(String(32), nullable=False)
    note = Column(Text, default="")
    teacher_id = Column(Integer, ForeignKey("teachers.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.now)

    student = relationship("Student")
    teacher = relationship("Teacher")


class Summary(Base):
    """Teacher's View text on the report (editable, teacher-confirmed)."""

    __tablename__ = "summaries"
    id = Column(Integer, primary_key=True)
    student_id = Column(Integer, ForeignKey("students.id"), unique=True, nullable=False)
    text = Column(Text, default="")
    teacher_id = Column(Integer, ForeignKey("teachers.id"), nullable=True)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    student = relationship("Student")
    teacher = relationship("Teacher")


class Review(Base):
    """A row means this student's session record was reviewed & confirmed."""

    __tablename__ = "reviews"
    id = Column(Integer, primary_key=True)
    student_id = Column(Integer, ForeignKey("students.id"), unique=True, nullable=False)
    teacher_id = Column(Integer, ForeignKey("teachers.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.now)

    student = relationship("Student")
    teacher = relationship("Teacher")


class ReportPdf(Base):
    """Generated report PDFs, stored in the database (BLOB)."""

    __tablename__ = "report_pdfs"
    id = Column(Integer, primary_key=True)
    student_id = Column(Integer, ForeignKey("students.id"), nullable=False)
    filename = Column(String(255), nullable=False)
    data = Column(LargeBinary, nullable=False)
    size = Column(Integer, default=0)
    teacher_id = Column(Integer, ForeignKey("teachers.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.now)

    student = relationship("Student")
    teacher = relationship("Teacher")


class SessionArchive(Base):
    """Session-level archives (e.g. the scores CSV from a batch archive)."""

    __tablename__ = "session_archives"
    id = Column(Integer, primary_key=True)
    session_id = Column(Integer, ForeignKey("assess_sessions.id"), nullable=False)
    kind = Column(String(32), default="scores_csv")
    filename = Column(String(255), nullable=False)
    data = Column(LargeBinary, nullable=False)
    created_at = Column(DateTime, default=datetime.now)
    teacher_id = Column(Integer, ForeignKey("teachers.id"), nullable=True)

    session = relationship("AssessSession")
    teacher = relationship("Teacher")


class AudioNote(Base):
    """Placeholder for the voice-note phase: file on disk + ownership."""

    __tablename__ = "audio_notes"
    id = Column(Integer, primary_key=True)
    student_id = Column(Integer, ForeignKey("students.id"), nullable=False)
    code = Column(String(8), nullable=True)
    stage = Column(String(32), default="")
    path = Column(String(255), nullable=False)
    mime = Column(String(64), default="")
    transcript = Column(Text, default="")
    transcript_status = Column(String(16), default="none")  # none/pending/done
    teacher_id = Column(Integer, ForeignKey("teachers.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.now)
