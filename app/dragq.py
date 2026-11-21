"""Drag-on-tablet tasks: the child drags pieces onto places on the tablet (and, in some tasks,
turns them); the teacher taps Check and the score is worked out here.

A task is a JSON text on the question (Question.drag / BankQuestion.drag), drawn by the editor
in the question form (static/drag.js):

  {"v": 1, "ratio": 1.6, "rotate": false, "bg": <asset id or null>,
   "slots":  [{"id", "x", "y", "w", "h", "many", "shape", "show", "label", "pic": <asset id>, "accept": [kind, ...]}],
   "pieces": [{"id", "img": <asset id>, "kind", "x", "y", "w", "h", "rot", "free"}]}

Positions and sizes are percentages of the canvas (x, w of its width; y, h of its height; x, y are
centres). A place takes one piece, or many ("many": a sorting box; "pic" = a picture shown at its top,
for children who cannot read the label). "accept" lists the kinds of
piece that belong there; pieces made from the same picture share a kind. "rot" is how a piece is
turned at the start (0 / 90 / 180 / 270; upright = correct); "free" = any direction is fine.

What the child did is {piece id: {"slot": place id, "rot": degrees}}; pieces left in the tray are absent.

Score: 2 = everything right; 1 = some of it right, or the right places but a wrong direction; 0 = nothing right.
"""

import json

MAX_LEN = 60000


def _num(v, lo, hi, default):
    try:
        return max(lo, min(hi, round(float(v), 2)))
    except (TypeError, ValueError):
        return default


def _id(v):
    s = "".join(c for c in str(v or "") if c.isalnum() or c in "_-")
    return s[:24]


def clean(text):
    """Normalised task JSON as stored, or "" when there is nothing usable."""
    try:
        raw = json.loads(text or "")
    except (TypeError, ValueError):
        return ""
    if not isinstance(raw, dict):
        return ""
    slots, pieces, seen, seen_p = [], [], set(), set()  # places and pieces are named separately
    for s in (raw.get("slots") or [])[:40]:
        sid = _id(s.get("id"))
        if not sid or sid in seen:
            continue
        seen.add(sid)
        try:
            pic = int(s.get("pic")) if s.get("pic") not in (None, "") else None
        except (TypeError, ValueError):
            pic = None
        slots.append({
            "id": sid, "x": _num(s.get("x"), 0, 100, 50), "y": _num(s.get("y"), 0, 100, 50),
            "w": _num(s.get("w"), 2, 100, 12), "h": _num(s.get("h"), 2, 100, 18),
            "many": bool(s.get("many")), "shape": "circle" if s.get("shape") == "circle" else "rect",
            "show": bool(s.get("show", True)), "label": str(s.get("label") or "")[:40], "pic": pic,
            "accept": [k for k in (_id(a) for a in (s.get("accept") or [])[:40]) if k],
        })
    for p in (raw.get("pieces") or [])[:60]:
        pid = _id(p.get("id"))
        try:
            img = int(p.get("img"))
        except (TypeError, ValueError):
            continue
        if not pid or pid in seen_p:
            continue
        seen_p.add(pid)
        pieces.append({
            "id": pid, "img": img, "kind": _id(p.get("kind")) or pid,
            "x": _num(p.get("x"), 0, 100, 50), "y": _num(p.get("y"), 0, 100, 85),
            "w": _num(p.get("w"), 2, 100, 10), "h": _num(p.get("h"), 2, 100, 16),
            "rot": int(_num(p.get("rot"), 0, 270, 0)) // 90 * 90, "free": bool(p.get("free")),
        })
    if not pieces and not slots:
        return ""
    try:
        bg = int(raw.get("bg")) if raw.get("bg") not in (None, "") else None
    except (TypeError, ValueError):
        bg = None
    out = {"v": 1, "ratio": _num(raw.get("ratio"), 0.5, 3, 1.6), "rotate": bool(raw.get("rotate")), "bg": bg,
           "slots": slots, "pieces": pieces}
    text = json.dumps(out, separators=(",", ":"))
    return text if len(text) <= MAX_LEN else ""


def parse(q):
    """The task of a question as a dict, or None (no task, or nothing a child could do with it)."""
    text = getattr(q, "drag", "") or ""
    if not text:
        return None
    try:
        cfg = json.loads(text)
    except ValueError:
        return None
    return cfg if cfg.get("pieces") and cfg.get("slots") else None


def score(cfg, placement):
    """{"score": 0/1/2, "right", "total", "placed": pieces in the right place, "marks": {piece id: "ok" | "turn" | "no"}}."""
    placement = placement if isinstance(placement, dict) else {}
    slots = {s["id"]: s for s in cfg["slots"]}
    pieces = {p["id"]: p for p in cfg["pieces"]}
    where = {}  # piece id -> (slot, rot)
    for pid, v in placement.items():
        if pid in pieces and isinstance(v, dict) and v.get("slot") in slots:
            try:
                rot = int(v.get("rot") or 0) % 360
            except (TypeError, ValueError):
                rot = 0
            where[pid] = (slots[v["slot"]], rot)

    def turned_ok(p, rot):
        return not cfg.get("rotate") or p.get("free") or rot == 0

    marks, checks = {}, []  # checks: (in the right place, also turned right)
    homes = {k for s in cfg["slots"] if s["many"] for k in s["accept"]}  # kinds that belong in some box
    for s in cfg["slots"]:
        if s["many"] or not s["accept"]:
            continue
        inside = [(pid, rot) for pid, (sl, rot) in where.items() if sl["id"] == s["id"]]
        if not inside:
            checks.append((False, False))
            continue
        pid, rot = inside[0]
        pos = pieces[pid]["kind"] in s["accept"]
        ok = pos and turned_ok(pieces[pid], rot)
        checks.append((pos, ok))
        marks[pid] = "ok" if ok else "turn" if pos else "no"
    for pid, p in pieces.items():
        sl, rot = where.get(pid, (None, 0))
        if sl is not None and not sl["many"]:
            if not sl["accept"]:
                marks.setdefault(pid, "no")
            continue
        if p["kind"] in homes:
            pos = sl is not None and p["kind"] in sl["accept"]
            ok = pos and turned_ok(p, rot)
            checks.append((pos, ok))
            if sl is not None:
                marks[pid] = "ok" if ok else "turn" if pos else "no"
        elif sl is not None:  # a piece that belongs nowhere was put in a box
            checks.append((False, False))
            marks[pid] = "no"
    total = len(checks)
    placed = sum(1 for pos, _ in checks if pos)
    right = sum(1 for _, ok in checks if ok)
    pts = 2 if total and right == total else 1 if placed else 0
    return {"score": pts, "right": right, "total": total, "placed": placed, "marks": marks}
