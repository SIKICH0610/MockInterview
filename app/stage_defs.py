"""Paper-owned group-activity evaluation content.

The dimensions/option vocabularies (formerly seed.STAGE_DIMS) and the
Circle Time "Let's Talk" prompts (formerly seed.STORY_PROMPTS) now live
in the database per paper, editable in the paper admin. seed.py keeps
the originals as the defaults that every paper starts from.
"""

import json
import re

from .models import StageDimDef, StoryPromptDef
from .report_i18n import DIM_LABEL_ZH, DIM_VALUE_ZH
from .seed import STAGE_DIMS, STORY_PROMPTS

# stages that carry a rubric, in canonical display order
DIM_STAGE_ORDER = ["Self Introduction", "Circle Time", "Show & Share", "Cutting & Drawing", "Ticket Making"]


def ensure_paper_defaults(db, paper_id):
    """Seed a paper's rubric + prompts from the built-in defaults.

    Idempotent per stage: a stage the paper already has rows for is left
    alone (edits survive), while a stage newly added to the product gets
    its default dimensions backfilled into existing papers.
    """
    for stage, dims in STAGE_DIMS.items():
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
    if not db.query(StoryPromptDef).filter_by(paper_id=paper_id).first():
        for i, p in enumerate(STORY_PROMPTS, 1):
            db.add(StoryPromptDef(paper_id=paper_id, idx=i, text=p))


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
        db.add(StoryPromptDef(paper_id=dst_paper_id, idx=p.idx, text=p.text))


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
    ordered = {s: out[s] for s in DIM_STAGE_ORDER if s in out}
    for s, v in out.items():
        if s not in ordered:
            ordered[s] = v
    return ordered


def paper_prompts(db, paper_id):
    if paper_id:
        rows = (
            db.query(StoryPromptDef)
            .filter_by(paper_id=paper_id)
            .order_by(StoryPromptDef.idx)
            .all()
        )
        if rows:
            return [r.text for r in rows]
    return list(STORY_PROMPTS)


def slug_key(label, taken):
    base = re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_")[:24] or "dim"
    key = base
    n = 2
    while key in taken:
        key = f"{base}{n}"
        n += 1
    return key
