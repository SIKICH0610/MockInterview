"""Parent-facing assessment report.

Layout follows the agreed spec: two-line left-aligned title with "&",
four-dimension overview cards, the 7-ability radar on the Mathematics
detail (radar lives in the report only), task-by-task results that
distinguish independent vs guided, group-activity evidence, and the
SEL & Classroom Skills page last. Totals shown are the raw card totals
(Math /12, Expression pool /10, English /12, SEL & CS 50-point bases);
no unapproved composite formulas.
"""

import html as html_mod
import math
from datetime import date

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from fastapi import Body
from fastapi.responses import JSONResponse, Response

from ..db import get_db
from ..models import (
    AssessSession,
    Event,
    ItemRecord,
    Paper,
    Question,
    ReportPdf,
    Review,
    SessionArchive,
    StageObs,
    Student,
    Summary,
    Teacher,
)
from ..report_i18n import (
    ABILITY_ZH,
    ability_name,
    dim_label,
    dim_value,
    rl,
    stage_name,
    SEP_LABEL_EN,
    SEP_LABEL_ZH,
    RESP_LABEL_EN,
    RESP_LABEL_ZH,
)
from ..services.analysis import build_analysis
from ..stage_defs import paper_dims, paper_prompts
from ..templating import templates

router = APIRouter()

ABILITY_ORDER = [
    "Number Sense",
    "Spatial Sense",
    "Measurement & Data",
    "Reasoning",
    "Creativity",
    "Expression",
    "Critical Thinking",
]

GENERAL_STAGES = ["Self Introduction", "Cutting & Drawing"]

RESP_LABEL = {
    "independent": "Independent",
    "prompted": "With support",
    "none": "Not engaged",
}
SEP_LABEL = {
    "independent": "Separated independently",
    "brief": "Brief comfort needed",
    "support": "Ongoing support needed",
    "not_observed": "Not observed",
}


def _radar_svg(axes, student_name="Student", avg_label="Session average"):
    """axes: list of (label, pct 0..1 or None, avg_pct 0..1 or None)."""
    n = len(axes)
    cx, cy, radius = 200, 148, 96

    def pt(i, r):
        a = -math.pi / 2 + 2 * math.pi * i / n
        return (cx + r * math.cos(a), cy + r * math.sin(a))

    parts = []
    for frac in (0.25, 0.5, 0.75, 1.0):
        pts = " ".join(f"{x:.1f},{y:.1f}" for x, y in (pt(i, radius * frac) for i in range(n)))
        parts.append(f'<polygon points="{pts}" fill="none" stroke="#EFE0CF" stroke-width="1"/>')
    for i in range(n):
        x, y = pt(i, radius)
        parts.append(f'<line x1="{cx}" y1="{cy}" x2="{x:.1f}" y2="{y:.1f}" stroke="#EFE0CF" stroke-width="1"/>')

    has_avg = any(a[2] is not None for a in axes)
    if has_avg:
        apts = " ".join(
            f"{x:.1f},{y:.1f}"
            for x, y in (pt(i, radius * (axes[i][2] or 0)) for i in range(n))
        )
        parts.append(
            f'<polygon points="{apts}" fill="none" stroke="#8A7A6D" stroke-width="1.6" '
            'stroke-dasharray="5,4"/>'
        )

    dpts = " ".join(
        f"{x:.1f},{y:.1f}"
        for x, y in (pt(i, radius * (axes[i][1] or 0)) for i in range(n))
    )
    parts.append(
        f'<polygon points="{dpts}" fill="rgba(193,70,0,0.16)" stroke="#C14600" stroke-width="2"/>'
    )
    for i, ax in enumerate(axes):
        x, y = pt(i, radius * (ax[1] or 0))
        parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3.2" fill="#C14600"/>')

    # legend
    ly = 292
    parts.append(f'<circle cx="60" cy="{ly - 3}" r="4" fill="#C14600"/>')
    parts.append(
        f'<text x="70" y="{ly}" font-size="10.5" font-weight="700" fill="#3D2B1F">{html_mod.escape(student_name)}</text>'
    )
    if has_avg:
        parts.append(
            f'<line x1="200" y1="{ly - 3}" x2="228" y2="{ly - 3}" stroke="#8A7A6D" stroke-width="1.6" stroke-dasharray="5,4"/>'
        )
        parts.append(
            f'<text x="234" y="{ly}" font-size="10.5" font-weight="700" fill="#8A7A6D">{html_mod.escape(avg_label)}</text>'
        )

    for i, (label, _, _) in enumerate(axes):
        lx, ly = pt(i, radius + 14)
        anchor = "middle"
        if lx > cx + 8:
            anchor = "start"
        elif lx < cx - 8:
            anchor = "end"
        words = html_mod.escape(label).split(" ")
        if len(words) > 1 and len(label) > 12:
            line1, line2 = " ".join(words[:-1]), words[-1]
            parts.append(
                f'<text x="{lx:.1f}" y="{ly - 5:.1f}" font-size="10.5" font-weight="700" fill="#8A7A6D" text-anchor="{anchor}">{line1}</text>'
                f'<text x="{lx:.1f}" y="{ly + 7:.1f}" font-size="10.5" font-weight="700" fill="#8A7A6D" text-anchor="{anchor}">{line2}</text>'
            )
        else:
            parts.append(
                f'<text x="{lx:.1f}" y="{ly:.1f}" font-size="10.5" font-weight="700" fill="#8A7A6D" text-anchor="{anchor}" dominant-baseline="middle">{html_mod.escape(label)}</text>'
            )
    return (
        '<svg viewBox="0 0 400 304" xmlns="http://www.w3.org/2000/svg" role="img" '
        'style="width:100%;max-width:420px;height:auto">' + "".join(parts) + "</svg>"
    )


def _cohort_rows(db, session_ids, level, paper_id):
    """Per-student dimension scores for everyone in the given sessions at
    this level who has at least one scored record. Returns list of dicts."""
    if not session_ids:
        return [], [], []
    peers = (
        db.query(Student)
        .filter(Student.session_id.in_(session_ids), Student.level == level)
        .all()
    )
    qs = (
        db.query(Question)
        .filter_by(paper_id=paper_id, version=level)
        .order_by(Question.sort)
        .all()
    )
    math_codes = [q.code for q in qs if q.domain == "Mathematics"]
    eng_codes = [q.code for q in qs if q.domain == "English"]
    expr_codes = [q.code for q in qs if q.has_expression]
    ids = [p.id for p in peers]
    recs = {}
    if ids:
        for r in db.query(ItemRecord).filter(ItemRecord.student_id.in_(ids)).all():
            recs[(r.student_id, r.code)] = r
    ev_sums = {}
    if ids:
        for ev in db.query(Event).filter(Event.student_id.in_(ids)).all():
            key = (ev.student_id, ev.category)
            ev_sums[key] = ev_sums.get(key, 0) + ev.points

    rows = []
    for p in peers:
        has_any = any((p.id, c) in recs and recs[(p.id, c)].status for c in math_codes + eng_codes)
        if not has_any:
            continue
        row = {"sid": p.id, "abilities": {}, "expr": 0}
        m = e = 0
        for c in math_codes:
            r = recs.get((p.id, c))
            if _scored(r) and r.academic is not None:
                m += r.academic
                row["abilities"][c] = r.academic
        for c in eng_codes:
            r = recs.get((p.id, c))
            if _scored(r) and r.academic is not None:
                e += r.academic
        for c in expr_codes:
            r = recs.get((p.id, c))
            if _scored(r) and r.expression is not None:
                row["expr"] += r.expression
        row["math"] = m
        row["eng"] = e
        row["sel"] = max(0, 50 - ev_sums.get((p.id, "SEL"), 0))
        row["cs"] = max(0, 50 - ev_sums.get((p.id, "CS"), 0))
        rows.append(row)
    return rows, math_codes, expr_codes


def _dim_stats(rows, sid, key, mine):
    """Reference-report cohort stats: avg, rank, Top% (percentile with
    half-weight for ties)."""
    vals = [r[key] for r in rows]
    n = len(vals)
    if n <= 1:
        return {"n": n, "avg": None, "rank": None, "top": None, "mine": mine}
    avg = sum(vals) / n
    below = sum(1 for v in vals if v < mine)
    ties = sum(1 for v in vals if v == mine)
    percentile = (below + 0.5 * ties) / n * 100
    top = 100 - percentile
    rank = 1 + sum(1 for v in vals if v > mine)
    return {
        "n": n,
        "avg": round(avg, 1),
        "rank": f"{rank} / {n}",
        "top": f"Top {top:.0f}%",
        "mine": mine,
    }


def _scored(r):
    return r is not None and r.status == "scored"


def _can_view(teacher, st):
    if teacher is None:
        return False
    if teacher.role == "admin":
        return True
    return bool(st.group and st.group.teacher_id == teacher.id)


def collect_report_facts(db, st):
    """Plain-text fact sheet about one child, for the AI comment draft.
    Only states what was recorded; marks Not observed explicitly."""
    s = st.session
    paper_id = s.paper_id
    if not paper_id:
        p = db.query(Paper).order_by(Paper.id).first()
        paper_id = p.id if p else None
    qs = (
        db.query(Question)
        .filter_by(paper_id=paper_id, version=st.level)
        .order_by(Question.sort)
        .all()
    )
    recs = {r.code: r for r in db.query(ItemRecord).filter_by(student_id=st.id).all()}
    obs = db.query(StageObs).filter_by(student_id=st.id).order_by(StageObs.created_at).all()
    events = db.query(Event).filter_by(student_id=st.id).order_by(Event.created_at).all()

    lines = [f"Child: {st.name} ({st.level} level). Session: {s.date} {s.label}."]

    sep = next((o for o in obs if o.stage == "Separation"), None)
    if sep and sep.response:
        lines.append(f"Separation from parents: {SEP_LABEL.get(sep.response, sep.response)}."
                     + (f" Note: {sep.note}" if sep.note else ""))

    prompts = paper_prompts(db, paper_id)
    for o in obs:
        if o.stage == "Story Time" and o.prompt_index and not o.dim:
            prompt = (
                prompts[o.prompt_index - 1]
                if o.prompt_index <= len(prompts)
                else "story prompt"
            )
            lines.append(
                f"Story Time, prompt '{prompt}': {RESP_LABEL.get(o.response, o.response)}."
                + (f" The child: {o.note}" if o.note else "")
            )

    # multi-dimension rubric ratings
    dim_raw = {(o.stage, o.dim): o.response for o in obs if o.dim and o.response}
    for stage, dims in paper_dims(db, paper_id).items():
        vals = [
            f"{d['label']}: {dim_raw[(stage, d['key'])]}"
            for d in dims
            if (stage, d["key"]) in dim_raw
        ]
        if vals:
            lines.append(f"{stage} ratings — " + "; ".join(vals) + ".")

    for o in obs:
        if o.stage in GENERAL_STAGES and o.prompt_index is None and not o.dim and o.note:
            lines.append(f"{o.stage} note: {o.note}")

    for q in qs:
        r = recs.get(q.code)
        if _scored(r) and r.academic is not None:
            how = {2: "independent correct", 1: "correct after guidance", 0: "not yet established"}.get(
                r.academic, str(r.academic)
            )
            line = f"Task {q.code} ({q.title}, {q.ability}): {how}."
            if q.has_expression and r.expression is not None:
                eh = {2: "spoke in a complete sentence", 1: "answered with a word or short phrase",
                      0: "no relevant oral response"}.get(r.expression, "")
                if eh:
                    line += f" Oral expression: {eh}."
            if q.trial_max and r.trial is not None:
                line += f" Item-level correct: {r.trial} of {q.trial_max}."
            if r.note:
                line += f" Teacher note: {r.note}"
            lines.append(line)
        elif r and r.status == "not_observed":
            lines.append(f"Task {q.code} ({q.title}): Not observed (no valid opportunity).")
        elif r and r.status == "not_completed":
            lines.append(f"Task {q.code} ({q.title}): offered but not completed.")

    for ev in events:
        kind = "SEL" if ev.category == "SEL" else "Classroom"
        line = f"{kind} support event during {ev.stage}: {ev.reason}."
        if ev.support:
            line += f" Support given: {ev.support}."
        lines.append(line)

    return "\n".join(lines)


@router.get("/report/{stid}")
def report_page(stid: int, request: Request, db: Session = Depends(get_db)):
    st = db.get(Student, stid)
    teacher = request.state.teacher
    if not st:
        return RedirectResponse("/wb", status_code=303)
    if not _can_view(teacher, st):
        return RedirectResponse(f"/wb/list?session_id={st.session_id}", status_code=303)
    s = st.session

    rlang = request.query_params.get("rlang", "en")
    if rlang not in ("en", "zh"):
        rlang = "en"
    R = rl(rlang)

    paper_id = s.paper_id
    if not paper_id:
        p = db.query(Paper).order_by(Paper.id).first()
        paper_id = p.id if p else None
    qs = {
        q.code: q
        for q in db.query(Question)
        .filter_by(paper_id=paper_id, version=st.level)
        .order_by(Question.sort)
        .all()
    }
    recs = {r.code: r for r in db.query(ItemRecord).filter_by(student_id=st.id).all()}
    obs = db.query(StageObs).filter_by(student_id=st.id).order_by(StageObs.created_at).all()
    events = db.query(Event).filter_by(student_id=st.id).order_by(Event.created_at).all()
    review = db.query(Review).filter_by(student_id=st.id).first()
    summary = db.query(Summary).filter_by(student_id=st.id).first()
    teacher_names = {t.id: t.name for t in db.query(Teacher).all()}

    math_qs = [q for q in qs.values() if q.domain == "Mathematics"]
    eng_qs = [q for q in qs.values() if q.domain == "English"]

    # --- Mathematics academic ---
    math_rows = []
    math_total = 0
    math_max = 0
    indep = guided = 0
    math_missing = []
    for q in math_qs:
        r = recs.get(q.code)
        math_max += 2
        if _scored(r) and r.academic is not None:
            math_total += r.academic
            if r.academic == 2:
                indep += 1
            elif r.academic == 1:
                guided += 1
        elif not r or not r.status:
            math_missing.append(q.code)
        math_rows.append((q, r))

    # --- Expression pool (observed across M02-M06) ---
    expr_sum = 0
    expr_obs = 0
    expr_qn = 0
    for q in math_qs:
        if q.has_expression:
            expr_qn += 1
            r = recs.get(q.code)
            if _scored(r) and r.expression is not None:
                expr_sum += r.expression
                expr_obs += 1
    expr_max = 2 * expr_qn

    # --- English ---
    eng_rows = []
    eng_total = 0
    eng_max = 0
    eng_counts = []
    for q in eng_qs:
        r = recs.get(q.code)
        eng_max += 2
        if _scored(r) and r.academic is not None:
            eng_total += r.academic
        if q.trial_max and r is not None and r.trial is not None:
            eng_counts.append(f"{q.code}: {r.trial}/{q.trial_max}")
        eng_rows.append((q, r))

    # --- SEL / Classroom Skills ---
    sel_ded = sum(e.points for e in events if e.category == "SEL")
    cs_ded = sum(e.points for e in events if e.category == "CS")
    sel_score = max(0, 50 - sel_ded)
    cs_score = max(0, 50 - cs_ded)

    sep = next((o for o in obs if o.stage == "Separation" and not o.dim), None)
    circle = sorted(
        [o for o in obs if o.stage == "Story Time" and o.prompt_index and not o.dim],
        key=lambda o: (o.prompt_index or 0),
    )
    gen = {}
    for stage in GENERAL_STAGES:
        row = next(
            (o for o in obs if o.stage == stage and o.prompt_index is None and not o.dim), None
        )
        gen[stage] = row

    # multi-dimension rubric values per stage, in sheet order (localized),
    # plus tier classification for the auto analysis (option lists are
    # ordered best -> weakest in the paper's rubric)
    dim_raw = {(o.stage, o.dim): o.response for o in obs if o.dim and o.response}
    dims_map = paper_dims(db, paper_id)
    stage_dim_values = {}
    dim_strength_labels, dim_growth_labels = [], []
    has_dims = False
    for stage, dlist in dims_map.items():
        vals = []
        for d in dlist:
            raw = dim_raw.get((stage, d["key"]))
            if raw is None:
                continue
            has_dims = True
            if rlang == "zh":
                loc = d["label_zh"] or dim_label("zh", d["label"])
                pair = next(((en, zh) for en, zh in d["options"] if en == raw), None)
                disp_val = (pair[1] if pair and pair[1] else dim_value("zh", raw))
            else:
                loc = dim_label("en", d["label"])
                disp_val = dim_value("en", raw)
            vals.append((loc, disp_val))
            en_opts = [en for en, _ in d["options"]]
            if raw in en_opts:
                idx = en_opts.index(raw)
                if idx == 0 and loc not in dim_strength_labels:
                    dim_strength_labels.append(loc)
                elif idx == len(en_opts) - 1 and loc not in dim_growth_labels:
                    dim_growth_labels.append(loc)
        if vals:
            stage_dim_values[stage] = vals
    # a label rated top in one stage and bottom in another is mixed — drop both
    mixed = set(dim_strength_labels) & set(dim_growth_labels)
    dim_strength_labels = [x for x in dim_strength_labels if x not in mixed]
    dim_growth_labels = [x for x in dim_growth_labels if x not in mixed]

    gen_done = sum(1 for v in gen.values() if v and v.response == "independent")
    gen_any = sum(1 for v in gen.values() if v)

    # --- comparison cohort: session (default) / same paper / date range ---
    cmp_mode = request.query_params.get("cmp", "session")
    cmp_from = request.query_params.get("from", "")
    cmp_to = request.query_params.get("to", "")
    if cmp_mode == "paper":
        sess_ids = [x.id for x in db.query(AssessSession).filter_by(paper_id=paper_id).all()]
        cmp_label = R["cmp_paper"]
        cmp_desc = R["cmp_desc_paper"]
    elif cmp_mode == "range" and cmp_from and cmp_to:
        sess_ids = [
            x.id
            for x in db.query(AssessSession)
            .filter(
                AssessSession.paper_id == paper_id,
                AssessSession.date >= cmp_from,
                AssessSession.date <= cmp_to,
            )
            .all()
        ]
        if s.id not in sess_ids:
            sess_ids.append(s.id)
        cmp_label = R["cmp_range"].format(f=cmp_from, t=cmp_to)
        cmp_desc = R["cmp_desc_range"].format(f=cmp_from, t=cmp_to)
    else:
        cmp_mode = "session"
        sess_ids = [s.id]
        cmp_label = R["cmp_session"]
        cmp_desc = R["cmp_desc_session"]

    cohort, _mcodes, _ecodes = _cohort_rows(db, sess_ids, st.level, paper_id)
    dims = {
        "math": _dim_stats(cohort, st.id, "math", math_total),
        "eng": _dim_stats(cohort, st.id, "eng", eng_total),
        "sel": _dim_stats(cohort, st.id, "sel", sel_score),
        "cs": _dim_stats(cohort, st.id, "cs", cs_score),
    }
    cohort_n = dims["math"]["n"]

    def _ability_avg(code):
        vals = [r["abilities"][code] for r in cohort if code in r["abilities"]]
        return (sum(vals) / len(vals) / 2) if len(vals) > 1 else None

    expr_avg = None
    if expr_max and len(cohort) > 1:
        expr_avg = sum(r["expr"] for r in cohort) / len(cohort) / expr_max

    # --- 7 abilities for the radar + table ---
    abilities = []
    for name in ABILITY_ORDER:
        if name == "Expression":
            pct = (expr_sum / expr_max) if expr_max and expr_obs else (0 if expr_max else None)
            abilities.append(
                {
                    "name": name,
                    "disp": ability_name(rlang, name),
                    "score": expr_sum,
                    "max": expr_max,
                    "pct": pct,
                    "avg_pct": expr_avg,
                    "evidence": R["expr_evidence"].format(n=expr_qn, o=expr_obs),
                    "observed": expr_obs > 0,
                }
            )
            continue
        q = next((x for x in math_qs if x.ability == name), None)
        if q is None:
            continue
        r = recs.get(q.code)
        observed = _scored(r) and r.academic is not None
        abilities.append(
            {
                "name": name,
                "disp": ability_name(rlang, name),
                "score": r.academic if observed else None,
                "max": 2,
                "pct": (r.academic / 2) if observed else None,
                "avg_pct": _ability_avg(q.code),
                "evidence": f"{q.code} · {q.title}",
                "observed": observed,
            }
        )
    radar = _radar_svg(
        [(a["disp"], a["pct"], a["avg_pct"]) for a in abilities], st.name, cmp_label
    )

    # cover highlights: star the strongest observed abilities
    observed_p = [a for a in abilities if a["pct"] is not None]
    if observed_p:
        best = max(a["pct"] for a in observed_p)
        if best >= 0.75:
            for a in observed_p:
                a["is_top"] = a["pct"] == best

    # hide the notes column entirely when nobody wrote notes
    math_has_notes = any(r and r.note for _, r in math_rows)
    eng_has_notes = any(r and r.note for _, r in eng_rows)

    # rule-based bilingual analysis paragraphs
    _chal_m, _noobs_m, _str_m = [], [], []
    for q, r in math_rows:
        if _scored(r) and r.academic == 2:
            _str_m.append(ability_name(rlang, q.ability))
        elif (_scored(r) and r.academic == 0) or (r and r.status == "not_completed"):
            _chal_m.append(f"“{q.title}”" if rlang == "zh" else q.title)
        elif r and r.status == "not_observed":
            _noobs_m.append(f"“{q.title}”" if rlang == "zh" else q.title)
    _ind_e, _gui_e, _chal_e = [], [], []
    for q, r in eng_rows:
        title = f"“{q.title}”" if rlang == "zh" else q.title
        if _scored(r) and r.academic == 2:
            _ind_e.append(title)
        elif _scored(r) and r.academic == 1:
            _gui_e.append(title)
        elif (_scored(r) and r.academic == 0) or (r and r.status == "not_completed"):
            _chal_e.append(title)
    analysis = build_analysis(
        rlang,
        st.name,
        math_total=math_total,
        math_max=math_max,
        indep=indep,
        guided=guided,
        math_strengths=list(dict.fromkeys(_str_m)),
        math_challenges=_chal_m,
        math_not_observed=_noobs_m,
        eng_total=eng_total,
        eng_max=eng_max,
        eng_indep=_ind_e,
        eng_guided=_gui_e,
        eng_challenges=_chal_e,
        expr_sum=expr_sum,
        expr_max=expr_max,
        expr_obs=expr_obs,
        sep_resp=sep.response if sep else None,
        dim_strengths=dim_strength_labels,
        dim_growth=dim_growth_labels,
        has_dims=has_dims,
        sel_ded=sel_ded,
        cs_ded=cs_ded,
        n_events=len(events),
    )

    pdfs = (
        db.query(ReportPdf)
        .filter_by(student_id=st.id)
        .order_by(ReportPdf.created_at.desc())
        .all()
    )

    involved = sorted(
        {
            teacher_names.get(x)
            for x in (
                [r.teacher_id for r in recs.values()]
                + [o.teacher_id for o in obs]
                + [e.teacher_id for e in events]
            )
            if x and teacher_names.get(x)
        }
    )

    sep_map = SEP_LABEL_ZH if rlang == "zh" else SEP_LABEL_EN
    resp_map = RESP_LABEL_ZH if rlang == "zh" else RESP_LABEL_EN
    stage_disp = {
        x: stage_name(rlang, x)
        for x in (
            list(dims_map.keys()) + GENERAL_STAGES + ["Separation", "Story Time"]
            + [e.stage for e in events]
        )
    }
    base_qs = f"cmp={cmp_mode}"
    if cmp_mode == "range" and cmp_from and cmp_to:
        base_qs += f"&from={cmp_from}&to={cmp_to}"
    lang_urls = {x: f"?rlang={x}&{base_qs}" for x in ("en", "zh")}

    return templates.TemplateResponse(
        request,
        "report.html",
        {
            "s": s,
            "st": st,
            "teacher": teacher,
            "review": review,
            "summary": summary,
            "teacher_names": teacher_names,
            "involved": involved,
            "math_rows": math_rows,
            "math_total": math_total,
            "math_max": math_max,
            "indep": indep,
            "guided": guided,
            "math_missing": math_missing,
            "expr_sum": expr_sum,
            "expr_max": expr_max,
            "expr_obs": expr_obs,
            "expr_qn": expr_qn,
            "eng_rows": eng_rows,
            "eng_total": eng_total,
            "eng_max": eng_max,
            "eng_counts": eng_counts,
            "sel_score": sel_score,
            "cs_score": cs_score,
            "sel_ded": sel_ded,
            "cs_ded": cs_ded,
            "events": events,
            "sep": sep,
            "sep_label": sep_map.get(sep.response) if sep else None,
            "circle": circle,
            "prompts": paper_prompts(db, paper_id),
            "gen": gen,
            "gen_done": gen_done,
            "gen_any": gen_any,
            "stage_dim_values": stage_dim_values,
            "resp_label": resp_map,
            "R": R,
            "rlang": rlang,
            "ability_names": ABILITY_ZH if rlang == "zh" else {},
            "lang_urls": lang_urls,
            "stage_disp": stage_disp,
            "analysis": analysis,
            "math_has_notes": math_has_notes,
            "eng_has_notes": eng_has_notes,
            "abilities": abilities,
            "radar": radar,
            "dims": dims,
            "cohort_n": cohort_n,
            "cmp_mode": cmp_mode,
            "cmp_label": cmp_label,
            "cmp_desc": cmp_desc,
            "cmp_from": cmp_from,
            "cmp_to": cmp_to,
            "pdfs": pdfs,
            "today": date.today().isoformat(),
            "active": "wb",
        },
    )


def _pdf_footer(st, rlang):
    txt = rl(rlang)["pdf_footer"].format(name=st.name, lv=st.level)
    return (
        '<div style="width:100%;font-size:8px;color:#8A7A6D;'
        "font-family:Arial,'Microsoft YaHei',sans-serif;padding:0 13mm;display:flex;"
        'justify-content:space-between;">'
        f"<span>{html_mod.escape(txt)}</span>"
        '<span><span class="pageNumber"></span> / <span class="totalPages"></span></span>'
        "</div>"
    )


@router.post("/report/{stid}/pdf")
def generate_pdf(stid: int, request: Request, db: Session = Depends(get_db)):
    """Render the report with headless Chromium and store the PDF in the DB."""
    import os

    st = db.get(Student, stid)
    teacher = request.state.teacher
    if not st:
        return JSONResponse(status_code=404, content={"ok": False, "error": "not found"})
    if not _can_view(teacher, st):
        return JSONResponse(status_code=403, content={"ok": False, "error": "forbidden"})

    from ..auth import make_token

    rlang = request.query_params.get("rlang", "en")
    if rlang not in ("en", "zh"):
        rlang = "en"
    port = request.url.port or 8008
    base = os.environ.get("MI_SELF_URL", f"http://127.0.0.1:{port}")
    url = f"{base}/report/{st.id}?rlang={rlang}"

    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            context = browser.new_context()
            context.add_cookies([{"name": "auth", "value": make_token(teacher.id), "url": base}])
            page = context.new_page()
            page.goto(url, wait_until="networkidle", timeout=30000)
            pdf_bytes = page.pdf(
                format="Letter",
                print_background=True,
                display_header_footer=True,
                header_template="<span></span>",
                footer_template=_pdf_footer(st, rlang),
                margin={"top": "13mm", "bottom": "18mm", "left": "13mm", "right": "13mm"},
            )
            browser.close()
    except Exception as e:  # noqa: BLE001
        return JSONResponse(status_code=500, content={"ok": False, "error": f"pdf_failed: {e}"})

    filename = (
        f"{st.name.replace(' ', '_')}_{st.level}_Report_"
        f"{'CN' if rlang == 'zh' else 'EN'}_{date.today().isoformat()}.pdf"
    )
    row = ReportPdf(
        student_id=st.id,
        filename=filename,
        data=pdf_bytes,
        size=len(pdf_bytes),
        teacher_id=teacher.id,
    )
    db.add(row)
    db.commit()
    return {
        "ok": True,
        "id": row.id,
        "filename": filename,
        "size_kb": round(len(pdf_bytes) / 1024),
        "by": teacher.name,
        "time": row.created_at.strftime("%m-%d %H:%M"),
    }


def _session_score_table(db, s):
    """Per-student score summary rows for the archive CSV."""
    paper_id = s.paper_id
    if not paper_id:
        p = db.query(Paper).order_by(Paper.id).first()
        paper_id = p.id if p else None
    qs_all = db.query(Question).filter_by(paper_id=paper_id).order_by(Question.sort).all()
    by_level = {}
    for q in qs_all:
        by_level.setdefault(q.version, []).append(q)

    students = sorted(s.students, key=lambda x: ((x.group.name if x.group else "~"), x.name))
    ids = [st.id for st in students]
    recs = {}
    if ids:
        for r in db.query(ItemRecord).filter(ItemRecord.student_id.in_(ids)).all():
            recs[(r.student_id, r.code)] = r
    ev_sums = {}
    if ids:
        for ev in db.query(Event).filter(Event.student_id.in_(ids)).all():
            ev_sums[(ev.student_id, ev.category)] = ev_sums.get((ev.student_id, ev.category), 0) + ev.points
    reviews = {r.student_id: r for r in db.query(Review).filter(Review.student_id.in_(ids)).all()} if ids else {}
    tnames = {t.id: t.name for t in db.query(Teacher).all()}

    rows = []
    for st in students:
        qs = by_level.get(st.level, [])
        codes = [q.code for q in qs]
        math = eng = expr = 0
        done = 0
        for q in qs:
            r = recs.get((st.id, q.code))
            if r and r.status:
                done += 1
            if _scored(r) and r.academic is not None:
                if q.domain == "Mathematics":
                    math += r.academic
                else:
                    eng += r.academic
            if q.has_expression and _scored(r) and r.expression is not None:
                expr += r.expression
        rv = reviews.get(st.id)
        rows.append(
            {
                "name": st.name,
                "external_id": st.external_id,
                "level": st.level,
                "group": st.group.name if st.group else "",
                "completed": f"{done}/{len(codes)}" if codes else "",
                "math": math,
                "expression": expr,
                "english": eng,
                "sel": max(0, 50 - ev_sums.get((st.id, "SEL"), 0)),
                "cs": max(0, 50 - ev_sums.get((st.id, "CS"), 0)),
                "reviewed": (tnames.get(rv.teacher_id, "") + " " + rv.created_at.strftime("%Y-%m-%d %H:%M")) if rv else "",
                "has_records": done > 0,
                "student": st,
            }
        )
    return rows


@router.post("/report/batch/{sid}")
def batch_archive(sid: int, request: Request, db: Session = Depends(get_db)):
    """Admin: generate & store a PDF for every assessed child in the
    session, plus one scores CSV archived at session level."""
    import csv
    import io
    import os

    me = request.state.teacher
    if not me or me.role != "admin":
        return JSONResponse(status_code=403, content={"ok": False, "error": "admin only"})
    s = db.get(AssessSession, sid)
    if not s:
        return JSONResponse(status_code=404, content={"ok": False, "error": "not found"})

    rows = _session_score_table(db, s)
    targets = [r["student"] for r in rows if r["has_records"]]
    skipped = len(rows) - len(targets)

    from ..auth import make_token

    port = request.url.port or 8008
    base = os.environ.get("MI_SELF_URL", f"http://127.0.0.1:{port}")

    pdf_count = 0
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            context = browser.new_context()
            context.add_cookies([{"name": "auth", "value": make_token(me.id), "url": base}])
            page = context.new_page()
            for st in targets:
                for rlang in ("en", "zh"):
                    page.goto(
                        f"{base}/report/{st.id}?rlang={rlang}",
                        wait_until="networkidle",
                        timeout=30000,
                    )
                    pdf_bytes = page.pdf(
                        format="Letter",
                        print_background=True,
                        display_header_footer=True,
                        header_template="<span></span>",
                        footer_template=_pdf_footer(st, rlang),
                        margin={"top": "13mm", "bottom": "18mm", "left": "13mm", "right": "13mm"},
                    )
                    db.add(
                        ReportPdf(
                            student_id=st.id,
                            filename=(
                                f"{st.name.replace(' ', '_')}_{st.level}_Report_"
                                f"{'CN' if rlang == 'zh' else 'EN'}_{date.today().isoformat()}.pdf"
                            ),
                            data=pdf_bytes,
                            size=len(pdf_bytes),
                            teacher_id=me.id,
                        )
                    )
                    pdf_count += 1
            browser.close()
    except Exception as e:  # noqa: BLE001
        db.commit()
        return JSONResponse(
            status_code=500,
            content={"ok": False, "error": f"pdf_failed after {pdf_count}: {e}"},
        )

    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(
        ["Name", "Student ID", "Level", "Group", "Completed", "Math /12", "Expression /10",
         "English /12", "SEL /50", "Classroom Skills /50", "Reviewed by"]
    )
    for r in rows:
        w.writerow(
            [r["name"], r["external_id"], r["level"], r["group"], r["completed"],
             r["math"], r["expression"], r["english"], r["sel"], r["cs"], r["reviewed"]]
        )
    csv_bytes = ("﻿" + buf.getvalue()).encode("utf-8")
    arch = SessionArchive(
        session_id=s.id,
        kind="scores_csv",
        filename=f"{s.date}_{s.label.replace(' ', '_')}_scores.csv",
        data=csv_bytes,
        teacher_id=me.id,
    )
    db.add(arch)
    db.commit()
    return {
        "ok": True,
        "pdf_count": pdf_count,
        "skipped": skipped,
        "csv_id": arch.id,
        "csv_name": arch.filename,
        "time": arch.created_at.strftime("%m-%d %H:%M"),
    }


@router.get("/archive/{aid}")
def download_archive(aid: int, request: Request, db: Session = Depends(get_db)):
    me = request.state.teacher
    row = db.get(SessionArchive, aid)
    if not row or not me or me.role != "admin":
        return RedirectResponse("/wb", status_code=303)
    return Response(
        content=row.data,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{row.filename}"'},
    )


@router.get("/report/pdf/{pid}")
def download_pdf(pid: int, request: Request, db: Session = Depends(get_db)):
    row = db.get(ReportPdf, pid)
    if not row:
        return RedirectResponse("/wb", status_code=303)
    if not _can_view(request.state.teacher, row.student):
        return RedirectResponse("/wb", status_code=303)
    return Response(
        content=row.data,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{row.filename}"'},
    )
