import os

from fastapi.templating import Jinja2Templates

TEMPLATE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates")
STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
templates = Jinja2Templates(directory=TEMPLATE_DIR)


def asset_url(name: str) -> str:
    """/static/<name>?v=<mtime> — the version changes whenever the file does,
    so iPads/browsers fetch fresh CSS/JS instead of a stale cached copy."""
    try:
        v = int(os.path.getmtime(os.path.join(STATIC_DIR, name)))
    except OSError:
        v = 0
    return f"/static/{name}?v={v}"


templates.env.globals["asset_url"] = asset_url


def stem_parts(text):
    """Split a stem into a lead line, numbered steps and plain lines for display:
    [("lead", text) | ("step", num, label, rest) | ("line", text)]."""
    import re

    lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
    out = []
    for i, ln in enumerate(lines):
        m = re.match(r"^(\d{1,2})[.)、]\s*(.*)$", ln)
        if m:
            body = m.group(2)
            label, sep, rest = body.partition(":")
            if not sep or len(label) > 40:
                label, sep, rest = body.partition("：")
            if sep and len(label) <= 40:
                out.append(("step", m.group(1), label.strip(), rest.strip()))
            else:
                out.append(("step", m.group(1), "", body))
        elif i == 0 and len(lines) > 1:
            out.append(("lead", ln))
        else:
            out.append(("line", ln))
    return out


templates.env.globals["stem_parts"] = stem_parts


def _score_caps(q):
    from .bank import score_caps

    return score_caps(q)


templates.env.globals["score_caps"] = _score_caps


def _drag_cfg(q):
    """A question's drag-on-tablet task as a dict, or None."""
    from . import dragq

    return dragq.parse(q)


templates.env.globals["drag_cfg"] = _drag_cfg


def _drag_rec(rec):
    """What the child did in a drag task, as stored on the record (dict), or None."""
    import json

    try:
        return json.loads(rec.drag) if rec is not None and rec.drag else None
    except ValueError:
        return None


templates.env.globals["drag_rec"] = _drag_rec


def _count_cuts(n):
    from . import bank

    return bank.count_cuts(n)


templates.env.globals["count_cuts"] = _count_cuts


def _count_spans(n):
    from . import bank

    return bank.count_spans(n)


templates.env.globals["count_spans"] = _count_spans


def _dev_meta():
    """Measures and stages for the evidence-rule editor in the question form."""
    from . import devstage

    return {"measures": [[k, v[0], v[1], v[2]] for k, v in devstage.MEASURES.items()],
            "stages": [[s[0], s[3], s[4]] for s in devstage.STAGES]}


templates.env.globals["dev_meta"] = _dev_meta


def _talk_raw(q):
    """The stored talking points of a question as written ({"1": {"en", "zh"}, "0": {...}}), for the form."""
    import json

    try:
        v = json.loads(getattr(q, "talk", "") or "{}")
    except ValueError:
        v = {}
    return v if isinstance(v, dict) else {}


templates.env.globals["talk_raw"] = _talk_raw
