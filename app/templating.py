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
