"""Learning-foundations reference: which grade band a child's answers gave evidence of.

The bands follow California's Preschool/Transitional Kindergarten Learning Foundations (PTKLF), which describe
what children typically know and can do in two age ranges - Early (about 3 to 4 1/2 years, preschool) and
Later (about 4 to 5 1/2 years, TK) - plus kindergarten for skills beyond the PTKLF.

Three layers:
  * the framework below - areas and the grade bands;
  * evidence rules on a question (Question.evidence / BankQuestion.evidence, JSON, edited in the question
    form): "this result on this task is evidence of a skill at that band, in that area";
  * the child's records. Nothing is stored for a child: build() works the rows out when the report opens,
    so changing a rule changes every report.

A rule: {"m": area key, "st": band code or "" (recorded only, no band), "by": "score" | "count" | "expr",
         "full": n, "part": n or None, "en"/"zh": what the child showed, "nen"/"nzh": next step,
         "ren"/"rzh": a reference note, such as the PTKLF foundation number}.
"by" picks the number looked at - the task score (0-2), how many items were right, or the expression score
(0-2). At "full" or more the evidence was shown; from "part" up to it, partly shown; below, not yet shown.

One interview samples each area once or twice, so the report words this as "evidence seen", never as
"the child is at band X".
"""

import json

# the bands drawn on the report, youngest first: (code, English, 中文, age note English, age note 中文)
BANDS = [
    ("P", "Preschool", "学前", "PTKLF Early · about 3–4½ years", "PTKLF Early · 约 3–4 岁半"),
    ("TK", "TK", "TK", "PTKLF Later · about 4–5½ years", "PTKLF Later · 约 4–5 岁半"),
    ("K", "Kindergarten", "K", "kindergarten skills, beyond the PTKLF", "K 阶段技能，超出 PTKLF 范围"),
]
# what a rule can point at: a band, or the span "preschool to TK": code -> (lowest band, highest band, English, 中文)
STAGES = [
    ("P", 0, 0, "Preschool (PTKLF Early, about 3–4½ years)", "学前（PTKLF Early，约 3–4 岁半）"),
    ("P-TK", 0, 1, "Preschool to TK (PTKLF, about 3–5½ years)", "学前至 TK（PTKLF，约 3–5 岁半）"),
    ("TK", 1, 1, "TK (PTKLF Later, about 4–5½ years)", "TK（PTKLF Later，约 4–5 岁半）"),
    ("K", 2, 2, "Kindergarten (beyond the PTKLF)", "K（超出 PTKLF 范围）"),
]
STAGE_INDEX = {s[0]: s for s in STAGES}
LEVEL_BAND = {"TK": 1, "K": 2}  # the band of the child's own class, marked on each row

# key -> (code shown beside the name, English, 中文); the order here is the order on the report
MEASURES = {
    "MATH1": ("", "Spatial Thinking and Shapes", "空间与图形"),
    "MATH2": ("", "Classification", "分类"),
    "MATH3": ("", "Number and Counting", "数数与数量"),
    "MATH4": ("", "Number Operations", "数的运算"),
    "MATH5": ("", "Measurement", "测量"),
    "PATTERN": ("", "Patterning", "规律"),
    "ATL3": ("", "Problem Solving", "解决问题"),
    "FLD12": ("", "Understanding and Using Language", "语言理解与表达"),
    "FLD5": ("", "Letters and Phonics", "字母与拼读"),
    "READK": ("", "Reading", "阅读"),
}
# where the report's "What do these bands mean?" link goes: the official PTKLF page
SOURCE_URL = "https://www.cde.ca.gov/sp/cd/re/psfoundations.asp"
BYS = ("score", "count", "expr")
MAX_LEN = 20000


def _int(v, lo, hi):
    try:
        return max(lo, min(hi, int(v)))
    except (TypeError, ValueError):
        return None


def clean(text):
    """Normalised rules JSON as stored, or "" when there is nothing usable."""
    try:
        raw = json.loads(text or "")
    except (TypeError, ValueError):
        return ""
    if not isinstance(raw, list):
        return ""
    out = []
    for r in raw[:12]:
        if not isinstance(r, dict) or r.get("m") not in MEASURES:
            continue
        by = r.get("by") if r.get("by") in BYS else "score"
        hi = 30 if by == "count" else 2
        full = _int(r.get("full"), 1, hi)
        if full is None:
            continue
        part = _int(r.get("part"), 1, hi) if r.get("part") not in (None, "") else None
        if part is not None and part >= full:
            part = None
        txt = lambda k, n=300: " ".join(str(r.get(k) or "").split())[:n]  # noqa: E731
        if not (txt("en") or txt("zh")):
            continue
        out.append({"m": r["m"], "st": r.get("st") if r.get("st") in STAGE_INDEX else "", "by": by, "full": full, "part": part,
                    "en": txt("en"), "zh": txt("zh"), "nen": txt("nen"), "nzh": txt("nzh"), "ren": txt("ren", 80), "rzh": txt("rzh", 80)})
    text = json.dumps(out, ensure_ascii=False, separators=(",", ":")) if out else ""
    return text if len(text) <= MAX_LEN else ""


def rules(q):
    try:
        v = json.loads(getattr(q, "evidence", "") or "[]")
    except ValueError:
        return []
    return v if isinstance(v, list) else []


def _value(rule, q, r):
    if rule["by"] == "count":
        return r.trial
    if rule["by"] == "expr":
        return r.expression
    return r.academic


def build(rows, zh=False, level=""):
    """rows: [(question, record or None)] -> one dict per area the scored tasks gave rules for:
    {key, code, name, ladder: [{code, name, age, state: "top" | "on" | "part" | "", child: the child's own class}] or None,
     top: band wording or "", items: [{state: "full" | "part" | "none", text, task}], next, refs: [text], single}"""
    lang = lambda a, b: (b or a) if zh else (a or b)  # noqa: E731
    found = {}
    for q, r in rows:
        if r is None or r.status != "scored" or r.academic is None:
            continue
        for rule in rules(q):
            if rule.get("m") not in MEASURES:
                continue
            v = _value(rule, q, r)
            if v is None:
                continue
            state = "full" if v >= rule["full"] else "part" if rule.get("part") is not None and v >= rule["part"] else "none"
            text = lang(rule.get("en"), rule.get("zh"))
            if rule["by"] == "count" and q.trial_max:
                text += f" ({v}/{q.trial_max})"
            found.setdefault(rule["m"], []).append({
                "state": state, "text": text, "task": q.code, "st": rule.get("st") if rule.get("st") in STAGE_INDEX else "",
                "next": lang(rule.get("nen"), rule.get("nzh")), "ref": lang(rule.get("ren"), rule.get("rzh"))})
    out = []
    mine = LEVEL_BAND.get(level)
    for key, (code, en, zh_name) in MEASURES.items():
        items = found.get(key)
        if not items:
            continue
        staged = [it for it in items if it["st"]]
        hi = lambda it: STAGE_INDEX[it["st"]][2]  # noqa: E731
        full = [it for it in staged if it["state"] == "full"]
        best_band = max(full, key=hi, default=None)
        top = hi(best_band) if best_band else -1
        part = set()
        for it in staged:
            if it["state"] == "part":
                part.update(range(STAGE_INDEX[it["st"]][1], hi(it) + 1))
        ladder = None
        if staged:
            ladder = [{"code": b[0], "name": b[2] if zh else b[1], "age": b[4] if zh else b[3], "child": i == mine,
                       "state": "top" if i == top else "on" if i < top else "part" if i in part else ""}
                      for i, b in enumerate(BANDS)]
        best = max((it for it in items if it["state"] == "full" and it["next"]), key=lambda it: hi(it) if it["st"] else -1, default=None)
        if best is None:  # nothing fully shown: the next step of what was partly shown
            best = next((it for it in items if it["state"] == "part" and it["next"]), None)
        refs = []
        for it in items:
            if it["ref"] and it["ref"] not in refs:
                refs.append(it["ref"])
        out.append({
            "key": key, "code": code, "name": zh_name if zh else en, "ladder": ladder,
            "top": (STAGE_INDEX[best_band["st"]][4 if zh else 3]) if best_band else "",
            "items": items, "next": best["next"] if best else "", "refs": refs,
            "single": len({it["task"] for it in items}) == 1,
        })
    return out
