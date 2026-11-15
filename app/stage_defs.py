"""Paper-owned group-activity evaluation content.

The dimensions/option vocabularies (formerly seed.STAGE_DIMS) and the
Story Time "Let's Talk" prompts (formerly seed.STORY_PROMPTS) now live
in the database per paper, editable in the paper admin. seed.py keeps
the originals as the defaults that every paper starts from.
"""

import json
import re

from .models import PaperStage, StageDimDef, StoryPromptDef
from .report_i18n import DIM_LABEL_ZH, DIM_VALUE_ZH
from .seed import STAGE_DIMS, STORY_PROMPTS

# stages that carry a rubric, in canonical display order
DIM_STAGE_ORDER = ["Self Introduction", "Story Time", "Cutting & Drawing"]

# every interview starts with these team parts; each interview can then add, rename,
# reorder or remove parts (PaperStage)
DEFAULT_STAGES = [
    ("Separation", "separation"),
    ("Self Introduction", "rubric"),
    ("Story Time", "prompts"),
    ("Cutting & Drawing", "rubric"),
]
STAGE_KINDS = ["rubric", "prompts", "separation"]
NEW_STAGE_DIM = ("overall", "Overall", "整体表现", [["Good", "良好"], ["Fair", "一般"], ["Limited", "有限"]])


def ensure_paper_stages(db, paper_id):
    if db.query(PaperStage.id).filter_by(paper_id=paper_id).first() is None:
        for i, (key, kind) in enumerate(DEFAULT_STAGES):
            db.add(PaperStage(paper_id=paper_id, key=key, kind=kind, sort=i))
        db.flush()


def paper_stages(db, paper_id):
    """[{id, key, label, label_zh, kind}] in interview order.
    Also tells the page texts which interview's part names to show (t('stage.<key>'))."""
    from .i18n import stage_paper

    stage_paper.set(paper_id)
    rows = []
    if paper_id:
        rows = db.query(PaperStage).filter_by(paper_id=paper_id).order_by(PaperStage.sort, PaperStage.id).all()
    if not rows:
        return [{"id": None, "key": k, "label": "", "label_zh": "", "kind": kind} for k, kind in DEFAULT_STAGES]
    return [{"id": r.id, "key": r.key, "label": r.label or "", "label_zh": r.label_zh or "", "kind": r.kind} for r in rows]


def stage_kind(db, paper_id, key):
    return next((s["kind"] for s in paper_stages(db, paper_id) if s["key"] == key), "rubric")


def add_stage(db, paper_id, label, label_zh, kind):
    """A new team part at the end, with a starter rubric dimension to edit."""
    ensure_paper_stages(db, paper_id)
    kind = kind if kind in STAGE_KINDS else "rubric"
    taken = {r.key for r in db.query(PaperStage).filter_by(paper_id=paper_id)}
    base = " ".join(label.split())[:28] or "Part"
    key, n = base, 2
    while key in taken:
        key = f"{base} {n}"
        n += 1
    last = db.query(PaperStage).filter_by(paper_id=paper_id).order_by(PaperStage.sort.desc()).first()
    row = PaperStage(paper_id=paper_id, key=key, label=label.strip()[:80], label_zh=label_zh.strip()[:80],
                     kind=kind, sort=(last.sort + 1) if last else 0)
    db.add(row)
    if kind != "separation" and not db.query(StageDimDef).filter_by(paper_id=paper_id, stage=key).first():
        k, lab, zh, opts = NEW_STAGE_DIM
        db.add(StageDimDef(paper_id=paper_id, stage=key, key=k, label=lab, label_zh=zh,
                           options=json.dumps(opts, ensure_ascii=False), sort=0))
    db.flush()
    return row


def ensure_paper_defaults(db, paper_id):
    """Seed a paper's rubric + prompts from the built-in defaults.

    Idempotent per stage: a stage the paper already has rows for is left
    alone (edits survive), while a stage newly added to the product gets
    its default dimensions backfilled into existing papers.
    """
    ensure_paper_stages(db, paper_id)
    have = {r.key for r in db.query(PaperStage).filter_by(paper_id=paper_id)}
    for stage, dims in STAGE_DIMS.items():
        if stage not in have:  # this interview removed that part
            continue
        if db.query(StageDimDef).filter_by(paper_id=paper_id, stage=stage).first():
            continue
        for i, (key, label, options) in enumerate(dims):
            db.add(
                StageDimDef(
                    paper_id=paper_id,
                    stage=stage,
                    key=key,
                    label=label,
                    label_zh=DIM_LABEL_ZH.get(label, ""),
                    options=json.dumps(
                        [[o, DIM_VALUE_ZH.get(o, "")] for o in options],
                        ensure_ascii=False,
                    ),
                    sort=i,
                )
            )
    if "Story Time" in have and not db.query(StoryPromptDef).filter_by(paper_id=paper_id).first():
        for i, p in enumerate(STORY_PROMPTS, 1):
            db.add(StoryPromptDef(paper_id=paper_id, idx=i, text=p, stage="Story Time"))


def clone_paper_defs(db, src_paper_id, dst_paper_id):
    for d in db.query(StageDimDef).filter_by(paper_id=src_paper_id).all():
        db.add(
            StageDimDef(
                paper_id=dst_paper_id,
                stage=d.stage,
                key=d.key,
                label=d.label,
                label_zh=d.label_zh,
                options=d.options,
                sort=d.sort,
            )
        )
    for p in db.query(StoryPromptDef).filter_by(paper_id=src_paper_id).all():
        db.add(StoryPromptDef(paper_id=dst_paper_id, idx=p.idx, text=p.text, stage=p.stage or "Story Time"))
    for r in db.query(PaperStage).filter_by(paper_id=src_paper_id).all():
        db.add(PaperStage(paper_id=dst_paper_id, key=r.key, label=r.label, label_zh=r.label_zh, kind=r.kind, sort=r.sort))


def parse_options(raw):
    """JSON '[["Always","总是"],...]' -> [(en, zh), ...]."""
    try:
        return [
            (str(o[0]), str(o[1]) if len(o) > 1 and o[1] else "")
            for o in json.loads(raw)
            if o and str(o[0]).strip()
        ]
    except Exception:  # noqa: BLE001
        return []


def paper_dims(db, paper_id):
    """{stage: [{key, label, label_zh, options: [(en, zh), ...]}]}
    in canonical stage order; falls back to the built-in defaults when a
    paper has no rows (e.g. before the startup backfill ran)."""
    out = {}
    if paper_id:
        rows = (
            db.query(StageDimDef)
            .filter_by(paper_id=paper_id)
            .order_by(StageDimDef.sort, StageDimDef.id)
            .all()
        )
        for r in rows:
            opts = parse_options(r.options)
            if not opts:
                continue
            out.setdefault(r.stage, []).append(
                {"key": r.key, "label": r.label, "label_zh": r.label_zh or "", "options": opts}
            )
    if not out:
        for stage, dims in STAGE_DIMS.items():
            out[stage] = [
                {
                    "key": key,
                    "label": label,
                    "label_zh": DIM_LABEL_ZH.get(label, ""),
                    "options": [(o, DIM_VALUE_ZH.get(o, "")) for o in options],
                }
                for key, label, options in dims
            ]
    order = [s["key"] for s in paper_stages(db, paper_id)]
    return {s: out[s] for s in order if s in out}  # only parts this interview still has, in its order


def paper_prompts(db, paper_id, stage=None):
    """Prompts of one prompts-type part (default: the interview's first one)."""
    if stage is None:
        stage = next((s["key"] for s in paper_stages(db, paper_id) if s["kind"] == "prompts"), "Story Time")
    if paper_id:
        rows = (
            db.query(StoryPromptDef)
            .filter_by(paper_id=paper_id)
            .order_by(StoryPromptDef.idx)
            .all()
        )
        rows = [r for r in rows if (r.stage or "Story Time") == stage]
        if rows:
            return [r.text for r in rows]
    return list(STORY_PROMPTS) if stage == "Story Time" else []


def slug_key(label, taken):
    base = re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_")[:24] or "dim"
    key = base
    n = 2
    while key in taken:
        key = f"{base}{n}"
        n += 1
    return key
