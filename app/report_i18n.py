"""Bilingual copy for the parent-facing report (EN / zh-CN).

The workbench UI language (app.i18n) is independent from the report
language: a teacher can use the Chinese UI and still produce an English
report, and vice versa.  Question content itself stays English by design.
"""

# ---------------------------------------------------------------- abilities

ABILITY_ZH = {
    "Number Sense": "数感",
    "Spatial Sense": "空间认知",
    "Measurement & Data": "测量与数据",
    "Reasoning": "逻辑推理",
    "Creativity": "创造力",
    "Expression": "语言表达",
    "Critical Thinking": "思辨能力",
}

STAGE_ZH = {
    "Separation": "入场分离",
    "Circle Time": "绘本圆圈",
    "Show & Share": "展示分享",
    "Cutting & Drawing": "剪纸绘画",
    "Ticket Making": "门票制作",
    "Station": "小组活动",
    "Other": "其他",
}

SEP_LABEL_EN = {
    "independent": "Separated independently",
    "brief": "Brief comfort needed",
    "support": "Ongoing support needed",
    "not_observed": "Not observed",
}
SEP_LABEL_ZH = {
    "independent": "独立分离，顺利进入",
    "brief": "短暂安抚后进入",
    "support": "需要持续安抚",
    "not_observed": "未观察",
}

RESP_LABEL_EN = {
    "independent": "Independent",
    "prompted": "With support",
    "none": "Not engaged",
}
RESP_LABEL_ZH = {
    "independent": "独立回应",
    "prompted": "提示后回应",
    "none": "未参与",
}

# ------------------------------------------------- group-activity dimensions

DIM_LABEL_EN = {
    "Initiative to Participate (Raise Hand)": "Initiative to participate",
}
DIM_LABEL_ZH = {
    "Initiative to Participate (Raise Hand)": "主动举手参与",
    "Confidence": "自信程度",
    "Expression Fluency": "表达流利度",
    "Listen to Others": "倾听他人",
    "Participation": "参与度",
    "Focus": "专注度",
    "Empathy": "同理心",
    "Follow Instruction": "遵循指令",
    "Fine Motor Skills": "精细动作",
    "Sharing Tool": "分享工具",
    "Problem Solving": "问题解决",
    "Creativity": "创造力",
    "General Attitude": "整体态度",
}

# Raw rubric values -> parent-friendly wording.
DIM_VALUE_EN = {
    "Design Sth New": "Designed something new",
    "Similar to Example": "Similar to example",
    "Same as Example": "Same as example",
    "Most of Time": "Most of the time",
    "Need Reminder": "Needed reminders",
    "Cannot Follow": "Not yet following",
    "Cannot Share": "Not yet sharing",
    "Cannot Solve": "Needed full support",
    "Moderate Confident": "Moderately confident",
    "Little Nervous": "A little nervous",
    "Moderate Fluency": "Moderately fluent",
    "Cannot Complete": "Not yet able to complete",
    "Cannot Focus": "Hard to stay focused",
    "Cannot Listen": "Hard to keep listening",
    "Cannot Empathize": "Developing empathy",
}
DIM_VALUE_ZH = {
    "Yes": "是",
    "No": "否",
    "Confident": "自信",
    "Moderate Confident": "比较自信",
    "Little Nervous": "略有紧张",
    "Very Nervous": "明显紧张",
    "Fluent": "流利",
    "Moderate Fluency": "较流利",
    "Limited Fluency": "表达有限",
    "Cannot Complete": "暂未能完成",
    "Good": "良好",
    "Fair": "一般",
    "Limited": "有限",
    "Poor": "待提升",
    "Passive": "偏被动",
    "Active": "积极",
    "Engaged": "投入",
    "Disengaged": "游离",
    "Always": "总是",
    "Most of Time": "大多数时候",
    "Need Reminder": "需要提醒",
    "Cannot Follow": "暂难遵循",
    "Cannot Listen": "需提醒倾听",
    "Cannot Share": "暂难分享",
    "Cannot Solve": "需要较多帮助",
    "Cannot Focus": "难以专注",
    "Cannot Empathize": "同理心发展中",
    "Design Sth New": "能设计新作品",
    "Similar to Example": "与示例相近",
    "Same as Example": "与示例相同",
}


def dim_label(lang, raw):
    return (DIM_LABEL_ZH if lang == "zh" else DIM_LABEL_EN).get(raw, raw)


def dim_value(lang, raw):
    return (DIM_VALUE_ZH if lang == "zh" else DIM_VALUE_EN).get(raw, raw)


def ability_name(lang, raw):
    return ABILITY_ZH.get(raw, raw) if lang == "zh" else raw


def stage_name(lang, raw):
    return STAGE_ZH.get(raw, raw) if lang == "zh" else raw


# ---------------------------------------------------------------- page copy

_EN = {
    "cover_title": "{lv} Early Childhood Development<br>&amp; School Readiness<br>Assessment Report",
    "cover_sub": "In-Person Mock Interview Assessment",
    "student": "Student",
    "level": "Level",
    "session": "Session",
    "student_id": "Student ID",
    "group": "Group",
    "assessed_by": "Assessed by",
    "report_date": "Report date",
    "bubbles_cap": "Seven abilities assessed in this report",
    "bubbles_star": "★ strongest areas this session",

    "ov_title": "Performance Overview",
    "ov_sub": "Four dimensions · raw card scores, no composite weighting",
    "ov_explain": "Academic results, oral expression, classroom skills and social-emotional readiness are reported separately, so each can be read on its own terms.",
    "card_math": "Mathematics",
    "card_eng": "English",
    "card_cs": "Classroom Skills",
    "card_sel": "Social-Emotional (SEL)",
    "expr_label": "Expression",
    "expr_kept": "(kept separate)",
    "indep_note": "{i} task(s) completed independently",
    "guided_note": ", {g} after guidance",
    "not_recorded_pfx": "Not recorded: ",
    "item_counts": "Item-level correct counts: ",
    "cs_ded_note": "{n} point(s) deducted across classroom events",
    "cs_none": "No classroom-behavior deductions recorded",
    "hands_on": "Hands-on activities: {a} of {b} observed fully independent",
    "sep_pfx": "Separation: ",
    "sel_ded_note": "{n} point(s) deducted across SEL events",
    "sel_none": "No SEL deductions recorded",
    "teachers_view": "Teacher's View",
    "auto_note": "Auto-generated from this session's recorded results; the teacher may replace it with a personal comment.",
    "cohort_foot": "Comparison cohort: the {n} {lv} children with recorded scores in {desc}. Standing uses the percentile convention (children below + half of ties) ÷ cohort; it updates as more records come in.",

    "ab_title": "Mathematics · 7 Abilities",
    "ab_sub": "Child vs. {cmp}, each axis scaled to its own maximum",
    "ab_explain": "The radar places your child (solid) against the {cmp} (dashed) across seven early-math abilities.",
    "th_ability": "Ability",
    "th_evidence": "Evidence",
    "th_score": "Score",
    "th_cohort_avg": "Cohort avg",
    "not_observed": "Not observed",
    "expr_evidence": "Oral responses across {n} math tasks ({o} observed)",
    "ab_foot": "Radar axes show each ability as a share of its own maximum — evidence counts differ (five single tasks /2, the Creativity ticket /2, Expression pooled across {n} oral responses /{m}). Expression is one of the seven mathematics abilities and does not add to the academic total.",

    "task_title": "Task-by-task Results",
    "task_sub": "Every task scored 0–2 · Independent vs. after guidance",
    "task_explain": "2 = completed independently · 1 = completed after teacher guidance · 0 / not completed = not yet established. “Not observed” items had no valid opportunity and are excluded from scoring.",
    "sec_math": "Mathematics & Creativity",
    "sec_eng": "English",
    "th_task": "Task",
    "th_result": "Result",
    "th_expr": "Expression",
    "th_notes": "Teacher notes",
    "tag_indep": "Independent",
    "tag_guided": "After guidance",
    "not_completed": "Not completed",
    "n_correct": "{t} / {m} correct",
    "max_fmt": "{} max",
    "cap_score": "Score · ",
    "cap_rank": "Rank in cohort",
    "cap_standing": "Standing",
    "analysis": "Analysis",

    "grp_title": "Group Activities · SEL & Classroom Skills",
    "grp_sub": "Observed from Separation onward",
    "grp_explain": "Teachers observed each child through the group activities and rated what they saw on a shared rubric; ratings describe this one session.",
    "not_recorded": "Not recorded",
    "circle_overall": "Circle Time · overall ratings",
    "circle_story": "Circle Time · story responses",
    "th_prompt": "Prompt",
    "th_response": "Response",
    "th_said": "What the child said / did",
    "circle_indep": "Independent",
    "circle_prompted": "After prompt",
    "circle_none": "No response",
    "circle_foot": "Not every child is called on for every prompt; prompts without a record were simply not this child's turn.",
    "sel_head": "SEL",
    "cs_head": "Classroom Skills",
    "th_time": "Time",
    "th_stage": "Stage",
    "th_area": "Area",
    "th_points": "Points",
    "th_what": "What happened",
    "th_support": "Support given",
    "area_sel": "SEL",
    "area_cs": "Classroom",
    "no_events": "No support or deduction events were recorded during this session.",
    "grp_foot": "Each area starts at 50; recorded events deduct points. An incorrect academic answer never deducts behavior points. Items marked “Not observed” had no valid opportunity and are not counted as 0.",

    "back_line": "Inspiring a lifelong love of learning",
    "back_foot": "Scores reflect on-site observation during one session · Generated {d}",

    "cmp_session": "Session average",
    "cmp_paper": "Paper average",
    "cmp_range": "Avg {f} ~ {t}",
    "cmp_desc_session": "this session",
    "cmp_desc_paper": "all sessions using this paper",
    "cmp_desc_range": "sessions on this paper dated {f} to {t}",

    "pdf_footer": "{name} · {lv} Assessment Report · Think Academy Silicon Valley",
}

_ZH = {
    "cover_title": "{lv} 幼儿发展<br>与入学准备能力<br>测评报告",
    "cover_sub": "线下模拟面试测评",
    "student": "学生",
    "level": "档位",
    "session": "场次",
    "student_id": "学员号",
    "group": "分组",
    "assessed_by": "测评老师",
    "report_date": "报告日期",
    "bubbles_cap": "本报告考察的七项能力",
    "bubbles_star": "★ 为本场最突出的能力",

    "ov_title": "整体表现概览",
    "ov_sub": "四个维度 · 按题卡原始分呈现，不做加权合成",
    "ov_explain": "学业成绩、口头表达、课堂技能与社会情感准备分开呈现，便于家长单独解读每个维度。",
    "card_math": "数学",
    "card_eng": "英语",
    "card_cs": "课堂技能",
    "card_sel": "社会情感（SEL）",
    "expr_label": "表达",
    "expr_kept": "（单独计）",
    "indep_note": "{i} 道题独立完成",
    "guided_note": "，{g} 道经引导完成",
    "not_recorded_pfx": "未录入：",
    "item_counts": "逐项正确数：",
    "cs_ded_note": "课堂事件累计扣 {n} 分",
    "cs_none": "未记录课堂行为扣分",
    "hands_on": "动手活动：{b} 项中 {a} 项完全独立完成",
    "sep_pfx": "入场分离：",
    "sel_ded_note": "社会情感事件累计扣 {n} 分",
    "sel_none": "未记录社会情感扣分",
    "teachers_view": "教师评语",
    "auto_note": "以下内容由本场已录入结果自动生成，老师可替换为个性化评语。",
    "cohort_foot": "对比样本：{desc}中已录入成绩的 {n} 名 {lv} 档孩子。相对位置采用百分位口径（低于者 + 同分一半）÷ 样本数，随录入持续更新。",

    "ab_title": "数学 · 七项能力",
    "ab_sub": "孩子 vs {cmp}，每条轴按各自满分归一",
    "ab_explain": "雷达图将孩子（实线）与{cmp}（虚线）在七项早期数学能力上进行对比。",
    "th_ability": "能力",
    "th_evidence": "依据",
    "th_score": "得分",
    "th_cohort_avg": "样本平均",
    "not_observed": "未观察",
    "expr_evidence": "{n} 道数学题的口头回应（观察到 {o} 次）",
    "ab_foot": "雷达各轴为该能力得分占其自身满分的比例——各轴依据数量不同（五项单题 /2、创造力门票 /2、表达为 {n} 次口头回应合计 /{m}）。表达是数学七项能力之一，不计入学业总分。",

    "task_title": "逐题结果",
    "task_sub": "每题 0–2 分 · 区分独立完成与引导后完成",
    "task_explain": "2 分 = 独立完成 · 1 分 = 老师引导后完成 · 0 分 / 未完成 = 尚未掌握。“未观察”表示没有有效机会，不计入得分。",
    "sec_math": "数学与创造力",
    "sec_eng": "英语",
    "th_task": "题目",
    "th_result": "结果",
    "th_expr": "表达",
    "th_notes": "教师备注",
    "tag_indep": "独立完成",
    "tag_guided": "引导后完成",
    "not_completed": "未完成",
    "n_correct": "{t} / {m} 正确",
    "max_fmt": "满分 {}",
    "cap_score": "得分 · ",
    "cap_rank": "样本排名",
    "cap_standing": "相对位置",
    "analysis": "表现解读",

    "grp_title": "集体环节 · 社会情感与课堂技能",
    "grp_sub": "自入场分离起全程观察",
    "grp_explain": "老师在集体环节中按统一量表记录每位孩子的表现；评价仅描述本场观察。",
    "not_recorded": "未记录",
    "circle_overall": "绘本圆圈 · 整体评价",
    "circle_story": "绘本圆圈 · 逐题回应",
    "th_prompt": "提问",
    "th_response": "回应",
    "th_said": "孩子的表现",
    "circle_indep": "主动回应",
    "circle_prompted": "提示后回应",
    "circle_none": "未回应",
    "circle_foot": "并非每位孩子都会被点到每个提问；没有记录的提问只是未轮到这位孩子。",
    "sel_head": "社会情感",
    "cs_head": "课堂技能",
    "th_time": "时间",
    "th_stage": "环节",
    "th_area": "类别",
    "th_points": "分值",
    "th_what": "发生了什么",
    "th_support": "给予的支持",
    "area_sel": "社会情感",
    "area_cs": "课堂",
    "no_events": "本场未记录任何支持或扣分事件。",
    "grp_foot": "每个类别从 50 分起算，记录的事件按分值扣除；学业答错不扣行为分。标注“未观察”的项目没有有效机会，不按 0 分计。",

    "back_line": "激发受益一生的学习热情",
    "back_foot": "分数基于单场现场观察 · 生成于 {d}",

    "cmp_session": "本场平均",
    "cmp_paper": "同题库平均",
    "cmp_range": "{f} ~ {t} 平均",
    "cmp_desc_session": "本场",
    "cmp_desc_paper": "使用同一套题的全部场次",
    "cmp_desc_range": "{f} 至 {t} 使用本套题的场次",

    "pdf_footer": "{name} · {lv} 测评报告 · Think Academy Silicon Valley",
}

REPORT_L10N = {"en": _EN, "zh": _ZH}


def rl(lang):
    return REPORT_L10N.get(lang, _EN)
