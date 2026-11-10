"""Rule-based bilingual analysis paragraphs for the report.

Deliberately simple: states only recorded facts in friendly sentences.
The AI comment pipeline can later polish these; until then every report
section still reads complete even when teachers had no time for notes.
"""


def _join(lang, items, limit=3):
    items = [str(x) for x in items if x]
    if not items:
        return ""
    more = len(items) - limit
    shown = items[:limit]
    if lang == "zh":
        txt = "、".join(shown)
        return txt + (f"等 {len(items)} 项" if more > 0 else "")
    if len(shown) == 1:
        txt = shown[0]
    else:
        txt = ", ".join(shown[:-1]) + " and " + shown[-1]
    return txt + (f" (among {len(items)} areas)" if more > 0 else "")


SEP_PHRASE_EN = {
    "independent": "separated from parents independently at drop-off",
    "brief": "needed a brief moment of comfort at separation, then settled in",
    "support": "needed ongoing support after separating from parents",
}
SEP_PHRASE_ZH = {
    "independent": "入场时与家长顺利独立分离",
    "brief": "入场分离时经过短暂安抚后进入状态",
    "support": "入场分离时需要持续的安抚支持",
}


def build_analysis(
    lang,
    name,
    *,
    math_total,
    math_max,
    indep,
    guided,
    math_strengths,       # ability names (already localized)
    math_challenges,      # task titles (English, factual)
    math_not_observed,    # task titles
    eng_total,
    eng_max,
    eng_indep,            # task titles
    eng_guided,
    eng_challenges,
    expr_sum,
    expr_max,
    expr_obs,
    sep_resp,             # raw separation response key or None
    dim_strengths,        # localized dim labels, deduped
    dim_growth,
    has_dims,
    sel_ded,
    cs_ded,
    n_events,
):
    zh = lang == "zh"
    out = {}

    # ---------------- mathematics ----------------
    m = []
    if math_total or indep or guided or math_challenges or math_not_observed:
        if zh:
            m.append(f"{name} 数学部分得 {math_total}/{math_max} 分：{indep} 道题独立完成、{guided} 道在老师引导后完成。")
            if math_strengths:
                m.append(f"在{_join(lang, math_strengths)}方面表现出独立、扎实的掌握。")
            if math_challenges:
                m.append(f"{_join(lang, math_challenges)}本次仍有挑战，适合作为接下来的练习方向。")
            if math_not_observed:
                m.append(f"{_join(lang, math_not_observed)}未观察，不计入得分。")
        else:
            m.append(
                f"{name} scored {math_total}/{math_max} in mathematics, completing "
                f"{indep} task{'s' if indep != 1 else ''} independently"
                + (f" and {guided} after teacher guidance" if guided else "")
                + "."
            )
            if math_strengths:
                m.append(f"Confident, independent work showed in {_join(lang, math_strengths)}.")
            if math_challenges:
                m.append(
                    f"{_join(lang, math_challenges)} felt challenging this time and "
                    + ("makes a natural next step" if len(math_challenges) == 1 else "make natural next steps")
                    + " for practice."
                )
            if math_not_observed:
                m.append(f"{_join(lang, math_not_observed)} had no valid opportunity and stayed out of scoring.")
    out["math"] = ("" if zh else " ").join(m)

    # ---------------- english ----------------
    e = []
    if eng_total or eng_indep or eng_guided or eng_challenges:
        if zh:
            e.append(f"英语部分得 {eng_total}/{eng_max} 分。")
            sub = []
            if eng_indep:
                sub.append(f"{_join(lang, eng_indep)}独立完成")
            if eng_guided:
                sub.append(f"{_join(lang, eng_guided)}在引导后完成")
            if eng_challenges:
                sub.append(f"{_join(lang, eng_challenges)}本次未完成，可作为下一步的练习重点")
            if sub:
                e.append("；".join(sub) + "。")
            out["eng"] = "".join(e)
        else:
            e.append(f"In English, {name} scored {eng_total}/{eng_max}.")
            if eng_indep:
                e.append(f"{_join(lang, eng_indep)} {'were' if len(eng_indep) > 1 else 'was'} handled independently.")
            if eng_guided:
                e.append(f"{_join(lang, eng_guided)} came together after some guidance.")
            if eng_challenges:
                e.append(f"{_join(lang, eng_challenges)} {'were' if len(eng_challenges) > 1 else 'was'} not completed this time — a natural next step.")
            out["eng"] = " ".join(e)
    else:
        out["eng"] = ""

    # ---------------- group activities ----------------
    g = []
    sep_phrase = (SEP_PHRASE_ZH if zh else SEP_PHRASE_EN).get(sep_resp)
    if sep_phrase:
        g.append((f"{name}{sep_phrase}。") if zh else (f"{name} {sep_phrase}."))
    if dim_strengths:
        g.append(
            (f"集体环节中，在{_join(lang, dim_strengths)}方面表现突出。")
            if zh
            else f"In the group activities, {name} stood out in {_join(lang, dim_strengths)}."
        )
    if dim_growth:
        g.append(
            (f"{_join(lang, dim_growth)}方面还可以多加练习。")
            if zh
            else f"{_join(lang, dim_growth)} will benefit from continued practice."
        )
    if sel_ded == 0 and cs_ded == 0 and n_events == 0:
        g.append("全程未记录社会情感或课堂行为方面的扣分事件。" if zh else "No social-emotional or classroom-behavior concerns were recorded.")
    elif n_events:
        g.append(
            (f"老师记录了 {n_events} 次支持事件，详见下方事件明细。")
            if zh
            else f"Teachers logged {n_events} support event{'s' if n_events != 1 else ''}; see the event log below."
        )
    out["group"] = ("" if zh else " ").join(g) if (sep_phrase or has_dims or n_events or dim_strengths) else ""

    # ---------------- overview ----------------
    o = []
    if math_total or eng_total or indep or guided:
        if zh:
            o.append(f"{name} 本场完成测评：数学 {math_total}/{math_max}，英语 {eng_total}/{eng_max}"
                     + (f"，口头表达 {expr_sum}/{expr_max}" if expr_obs else "")
                     + f"；其中 {indep} 道题完全独立完成。")
        else:
            o.append(
                f"{name} completed the session with Mathematics {math_total}/{math_max} and English {eng_total}/{eng_max}"
                + (f", with oral expression at {expr_sum}/{expr_max}" if expr_obs else "")
                + f"; {indep} task{'s were' if indep != 1 else ' was'} completed fully independently."
            )
    if sep_phrase:
        o.append((f"{sep_phrase.capitalize()}." if not zh else f"{sep_phrase}。"))
    if sel_ded == 0 and cs_ded == 0 and n_events == 0 and o:
        o.append("全程未记录行为或情绪方面的扣分。" if zh else "No behavior or SEL deductions were recorded.")
    out["overview"] = ("" if zh else " ").join(o)

    return out
