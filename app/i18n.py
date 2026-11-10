"""Tiny server-side i18n: EN / ZH UI strings.

Assessment content (question titles, prompts, rubrics) intentionally stays
in English — it is the official card text. Only the UI chrome translates.
"""

from contextvars import ContextVar

current_lang = ContextVar("lang", default="en")

# key: (en, zh)
S = {
    # nav / common
    "nav.home": ("Home", "首页"),
    "nav.admin": ("Admin", "管理后台"),
    "nav.wb": ("Workbench", "工作台"),
    "btn.create": ("Create", "创建"),
    "btn.delete": ("Delete", "删除"),
    "btn.open": ("Open", "打开"),
    "btn.add": ("Add", "添加"),
    "btn.upload": ("Upload", "上传"),
    "btn.import": ("Import", "导入"),
    "btn.remove": ("Remove", "移除"),
    "btn.manage": ("Manage", "管理"),
    "btn.open_wb": ("Open workbench", "打开工作台"),
    "label.date": ("Date", "日期"),
    "label.label": ("Label", "名称"),
    "label.name": ("Name", "姓名"),
    "label.level": ("Level", "档位"),
    "label.id": ("ID", "编号"),
    "label.role": ("Role", "角色"),
    "label.session": ("Session", "场次"),
    "label.iam": ("I am", "我是"),
    "th.students": ("Students", "学生数"),
    "th.group": ("Group", "分组"),
    "th.status": ("Status", "状态"),
    "placeholder.optional": ("optional", "选填"),

    # home
    "home.kicker": ("TK / K IN-PERSON ASSESSMENT", "TK / K 现场测评"),
    "home.title": ("Assessment Workbench", "测评工作台"),
    "home.sub": (
        "Record scores, time and observations on site; every teacher's input merges into one report per child.",
        "现场记录成绩、用时与观察；多位老师的记录汇入同一名学生的同一份报告。",
    ),
    "home.admin.title": ("Admin Console", "管理后台"),
    "home.admin.desc": (
        "Create sessions, upload the student roster, build groups and assign teachers.",
        "创建场次、上传学生名单、建立分组并指派老师。",
    ),
    "home.wb.title": ("Teacher Workbench", "老师工作台"),
    "home.wb.desc": (
        "Observe the group activities, then open each student for the individual interview record.",
        "先记录集体环节观察，再进入单个学生的个人面试记录。",
    ),
    "home.sessions": ("SESSIONS", "场次"),

    # admin sessions
    "admin.sessions.title": ("Sessions", "场次管理"),
    "admin.teachers.link": ("Manage teachers", "老师管理"),
    "admin.create_session": ("Create a session", "创建场次"),
    "admin.all_sessions": ("All sessions", "全部场次"),
    "admin.no_sessions": ("No sessions yet. Create the first one above.", "还没有场次，在上方创建第一个。"),
    "confirm.delete_session": ("Delete this session and all its records?", "删除该场次及其全部记录？"),
    "placeholder.session_label": ("e.g. Nov 15 · Morning A", "如 Nov 15 · Morning A"),

    # admin session detail
    "admin.import": ("Import students", "导入学生"),
    "admin.upload_file": ("Upload file", "上传文件"),
    "admin.upload_hint": (
        "Upload the Think Academy class export (CSV / .xlsx) as-is — name, student id, grade and enrolled class are read automatically. A simple name, level, id file also works.",
        "直接上传 Think Academy 班级导出表（CSV / .xlsx），自动读取姓名、学员id、年级和报名课程；也兼容简单的「姓名, 档位, 编号」文件。",
    ),
    "admin.paste": ("Paste list", "粘贴名单"),
    "admin.paste_hint": (
        "One student per line: Name, TK or Name, K, S001",
        "每行一个学生：姓名, TK 或 姓名, K, S001",
    ),
    "admin.add_one": ("Add one", "单个添加"),
    "admin.groups": ("Groups & teacher assignment", "分组与老师指派"),
    "opt.no_teacher": ("— no teacher —", "—— 未指派 ——"),
    "opt.teacher": ("— teacher —", "—— 老师 ——"),
    "opt.none": ("— none —", "—— 无 ——"),
    "n.students": ("students", "名学生"),
    "confirm.delete_group": ("Delete this group? Students stay in the session.", "删除该组？学生仍保留在场次中。"),
    "btn.add_group": ("Add group", "新建组"),
    "placeholder.group_name": ("Group name (e.g. Group A)", "组名（如 Group A）"),
    "admin.need_teachers": ("No teachers yet —", "还没有老师——"),
    "admin.need_teachers2": ("first to assign groups.", "后才能指派分组。"),
    "admin.students": ("Students", "学生"),
    "admin.no_students": ("No students yet — import the roster above.", "还没有学生——请先在上方导入名单。"),
    "confirm.remove_student": ("Remove this student and their records?", "移除该学生及其全部记录？"),

    # admin teachers
    "admin.add_teacher": ("Add a teacher", "添加老师"),
    "admin.all_teachers": ("All teachers", "全部老师"),
    "admin.no_teachers": ("No teachers yet.", "还没有老师。"),
    "role.teacher": ("Teacher", "老师"),
    "role.admin": ("Admin", "管理员"),
    "status.active": ("Active", "启用中"),
    "status.inactive": ("Inactive", "已停用"),
    "btn.deactivate": ("Deactivate", "停用"),
    "btn.activate": ("Activate", "启用"),

    # workbench
    "wb.kicker": ("WORKBENCH", "工作台"),
    "wb.start": ("Start scoring", "开始打分"),
    "btn.group_scoring": ("Group scoring", "群面打分"),
    "btn.individual": ("Individual students", "个人面试"),
    "wb.no_sessions": ("No sessions yet — create one in the", "还没有场次——请先到"),
    "wb.no_teachers": ("No teachers yet — add them in the", "还没有老师——请先到"),
    "wb.console": ("Admin Console", "管理后台"),
    "wb.console_suffix": (".", "创建。"),
    "wb.group.title": ("Group scoring", "群面打分"),
    "wb.individual.title": ("Individual students", "个人面试"),
    "wb.no_group_students": (
        "No students in this group yet. Assign students to groups in the",
        "该组还没有学生——请到",
    ),
    "wb.no_group_students2": (".", "完成分组。"),
    "wb.no_assigned": (
        "No group is assigned to you in this session yet — ask the admin.",
        "本场次还没有给你指派分组——请联系管理员。",
    ),
    "btn.prev": ("← Previous", "← 上一题"),
    "btn.next": ("Next task →", "下一题 →"),
    "wb.recorded": ("recorded", "已记录"),
    "wb.recorded_by": ("recorded by", "记录人"),

    # stage observation
    "btn.stages": ("Group activities", "集体环节"),
    "stage.obs.title": ("Group activities", "集体环节观察"),
    "stage.Separation": ("Separation", "分离适应"),
    "stage.Circle Time": ("Circle Time", "Circle Time"),
    "stage.Show & Share": ("Show & Share", "Show & Share"),
    "stage.Cutting & Drawing": ("Cutting & Drawing", "剪纸绘画"),
    "stage.Ticket Making": ("Ticket Making", "Ticket 制作"),
    "stage.Station": ("Station", "Station"),
    "stage.Other": ("Other", "其他"),
    "circle.prompts": ("Let's Talk prompts", "Let's Talk 提问"),
    "circle.hint": (
        "Tap the current prompt, then record each child's response — one record per prompt per child (a new tap replaces it). No turn = leave blank (Not observed).",
        "先点选当前提问，再记录每个孩子的回应——每个提问每人只记一条，重复点击会覆盖。未轮到的孩子不用点，自动按未观察处理。",
    ),
    "general.hint": (
        "Pick ONE participation state per child (tap again to change it); use the note for details.",
        "为每个孩子选择一个参与状态（再点可更改），细节写在备注里。",
    ),
    "sep.hint": (
        "Observation starts the moment the child leaves the parents — record independence here, not at the station.",
        "从孩子离开父母那一刻就开始记录——分离适应在这里记，不要等到 Station。",
    ),
    "dims.head": ("Overall ratings for this stage", "本环节整体评价"),
    "dims.hint": (
        "Below each child's prompt log, rate the overall dimensions for this stage.",
        "每个孩子的回应记录下方，还可为本环节的整体表现打维度评价。",
    ),
    "dims.general_hint": (
        "Rate each dimension (tap again to clear); notes go in the box below.",
        "逐项选择评价档位（再点可取消），细节写在下方备注。",
    ),
    "resp.independent": ("Independent", "独立回应"),
    "resp.prompted": ("After prompt", "提示后回应"),
    "resp.none": ("No response", "无回应"),
    "resp.g.independent": ("Independent", "独立完成"),
    "resp.g.prompted": ("With support", "提示/协助后"),
    "resp.g.none": ("Not engaged", "未参与"),
    "sep.independent": ("Separated independently", "独立分离"),
    "sep.brief": ("Brief comfort needed", "短暂安抚后分离"),
    "sep.support": ("Ongoing support needed", "持续需要支持"),
    "sep.note.placeholder": (
        "First reaction, comfort given, recovery, joining the activity...",
        "最初反应、安抚方式、恢复及加入活动的情况……",
    ),
    "obs.note.placeholder": ("Actual answer / detail (optional)", "具体回答 / 细节（选填）"),

    # login
    "login.title": ("Sign in", "登录"),
    "login.name": ("Name", "姓名"),
    "login.password": ("Password", "密码"),
    "login.submit": ("Sign in", "登录"),
    "login.error": ("Wrong name or password.", "姓名或密码不正确。"),
    "login.hint": (
        "Accounts are created by the admin. Forgot your password? Ask the admin to reset it.",
        "账号由管理员创建；忘记密码请联系管理员重置。",
    ),
    "login.admin_only": ("That page needs an admin account.", "该页面需要管理员账号。"),
    "logout": ("Sign out", "退出"),
    "teachers.set_pw": ("Set password", "设置密码"),
    "teachers.impersonate": ("Enter as", "切换为该老师"),
    "teachers.make_admin": ("Make admin", "设为管理员"),
    "teachers.make_teacher": ("Make teacher", "设为老师"),
    "teachers.cant_self": ("You cannot change your own role.", "不能修改自己的角色。"),
    "switch.header": ("Switch account", "切换账号"),
    "impersonate.back": ("Back to admin", "返回管理员"),
    "impersonate.bar": ("You are viewing as", "当前正以该身份操作："),
    "teachers.pw_set": ("Password updated", "密码已设置"),
    "teachers.has_pw": ("Password set", "已设密码"),
    "teachers.no_pw": ("No password", "未设密码"),
    "placeholder.new_pw": ("new password", "新密码"),

    # papers (question bank editions)
    "btn.papers": ("Question papers", "题库管理"),
    "papers.title": ("Question papers", "题库管理"),
    "papers.create": ("New paper", "新建题库"),
    "papers.name": ("Paper name", "题库名称"),
    "papers.clone_from": ("Clone questions from", "复制题目自"),
    "papers.no_clone": ("— empty paper —", "—— 空题库 ——"),
    "papers.name_taken": ("That paper name already exists.", "题库名称已存在。"),
    "papers.in_use": ("This paper is used by sessions and cannot be deleted.", "该题库已被场次使用，不能删除。"),
    "papers.deleted": ("Paper deleted", "题库已删除"),
    "papers.versions": ("Versions", "版本"),
    "papers.count": ("Questions", "题目数"),
    "papers.sessions": ("Sessions using", "使用场次"),
    "papers.view": ("Open", "打开"),
    "papers.hint": (
        "Each session is tied to one paper. To prepare a new interview, clone an existing paper and edit its questions — old sessions keep their original paper.",
        "每个场次绑定一个题库。筹备新的测评时，复制现有题库再编辑题目——旧场次仍使用原题库，互不影响。",
    ),
    "label.paper": ("Paper", "题库"),
    "q.edit": ("Edit question", "编辑题目"),
    "q.saved": ("Question saved", "题目已保存"),
    "q.title": ("Title", "题目名称"),
    "q.prompt": ("Prompt (what the teacher says)", "题面 / 施测指令"),
    "q.domain": ("Domain", "维度"),
    "q.ability": ("Ability", "能力"),
    "q.r": ("Academic rubric", "学术评分标准"),
    "q.e": ("Expression rubric (leave empty to disable)", "表达评分标准（留空则该题不记表达）"),
    "q.trial_max": ("Sub-trial count (e.g. 6 letters; empty = none)", "子项计数上限（如 6 个字母；留空则无）"),
    "th.grade": ("Grade", "年级"),
    "th.course": ("Course", "课程"),
    "lv.unknown": ("Level not set — choose TK or K", "档位未识别——请选择 TK 或 K"),
    "msg.unenrolled": ("skipped {n} not enrolled", "跳过未入班 {n} 人"),
    "msg.unknown_level": ("{n} students need a level (TK/K) — set it in the student table", "{n} 名学生档位未识别，请在学生表中设置 TK/K"),

    # grouping board
    "btn.grouping": ("Grouping board", "现场分组"),
    "gb.title": ("Grouping", "现场分组"),
    "gb.steps": ("① Import students   ② Grouping   ③ Scoring", "① 导入学生 → ② 分组 → ③ 打分"),
    "gb.pool": ("Unassigned", "未分组"),
    "gb.randomize": ("Random assign", "随机分组"),
    "gb.confirm.randomize": (
        "Randomly re-assign ALL students across the groups? Current grouping will be replaced (TK/K balanced automatically).",
        "随机重新分配全部学生？当前分组将被打乱（TK/K 自动均衡）。",
    ),
    "gb.need_group": ("Create at least one group first.", "请先创建至少一个组。"),
    "gb.tap_hint": (
        "Drag the ⠿ handle to move a child between groups, or tap a child and then tap the target group.",
        "按住 ⠿ 把学生拖到别的组；或先点选学生、再点目标组。",
    ),
    "gb.done": ("Grouping complete — ready for scoring.", "分组完成——可以开始打分。"),
    "gb.not_done": ("students not grouped yet.", "名学生还未分组。"),
    "gb.start_scoring": ("Start scoring", "开始打分"),
    "gb.back_detail": ("Import / session settings", "导入学生 / 场次设置"),
    "wb.gate": (
        "Finish grouping first — every student must be in a group before scoring.",
        "请先完成分组——所有学生进组后才能开始打分。",
    ),

    # review page
    "btn.review": ("Review", "汇总复核"),
    "review.title": ("Review & confirm", "汇总复核"),
    "review.hint": (
        "Blank cells are missing records — tap any cell to open that task for the child. Confirm each child once the record is complete.",
        "空白格 = 缺记录——点任意格子直达该生该题补录。记录齐全后为每个孩子确认复核。",
    ),
    "review.sep": ("Separation", "分离"),
    "review.ct": ("Circle", "Circle"),
    "review.obs": ("Activities", "环节"),
    "review.events": ("Events", "事件"),
    "review.progress": ("Done", "完成"),
    "review.status": ("Status", "状态"),
    "review.eflag": ("Expression not recorded", "表达分未记"),
    "st.not_started": ("Not started", "未开始"),
    "st.in_progress": ("In progress", "进行中"),
    "st.ready": ("Ready to review", "待复核"),
    "st.reviewed": ("Reviewed", "已复核"),
    "btn.confirm_review": ("Confirm", "确认复核"),
    "btn.unconfirm": ("Undo", "撤销"),
    "confirm.unreview": ("Undo this child's review confirmation?", "撤销该生的复核确认？"),
    "js.tap_again": ("Tap again to undo", "再点一次撤销"),
    "js.tap_again_del": ("Tap again to delete", "再点一次删除"),
    "sep.cell.independent": ("Separated independently", "独立分离"),
    "sep.cell.brief": ("Brief comfort needed", "短暂安抚后分离"),
    "sep.cell.support": ("Ongoing support needed", "持续需要支持"),
    "sep.cell.not_observed": ("Not observed", "未观察"),
    "sep.cell.missing": ("No separation record", "无分离记录"),

    # report
    "btn.report": ("Report", "报告"),
    "report.print": ("Print / Export PDF", "打印 / 导出 PDF"),
    "report.summary_ph": (
        "Teacher's View — concrete, warm, parent-friendly. Describe what you observed, how the child responded to support, and what to practice next.",
        "老师评语——具体、温暖、适合家长阅读。描述观察到的行为、支持后的变化和下一步建议。",
    ),
    "report.summary_save": ("Save Teacher's View", "保存评语"),
    "report.ai_draft": ("AI draft", "AI 生成草稿"),
    "report.ai_drafting": ("Drafting…", "生成中…"),
    "report.ai_done": (
        "Draft filled in below — review, edit, then save.",
        "草稿已填入——请检查修改后保存。",
    ),
    "ai.not_configured": (
        "AI service not configured. Put the key in data/openai_key.txt (or data/anthropic_key.txt), then retry.",
        "AI 服务未配置。请把密钥存入 data/openai_key.txt（或 data/anthropic_key.txt）后重试。",
    ),
    "ai.failed": ("AI draft failed: ", "AI 生成失败："),
    "ai.billing": (
        "The OpenAI account has no credits. Top up at platform.openai.com → Settings → Billing, then retry.",
        "OpenAI 账户没有余额。请到 platform.openai.com → Settings → Billing 充值后重试。",
    ),
    "report.pdf_save": ("Save PDF to archive", "生成 PDF 存档"),
    "report.pdf_saving": ("Generating…", "生成中…"),
    "report.pdf_list": ("Archived PDFs", "已存档 PDF"),
    "report.pdf_none": ("No archived PDFs yet.", "还没有存档的 PDF。"),
    "report.pdf_failed": ("PDF generation failed: ", "PDF 生成失败："),
    "report.cmp.title": ("Comparison cohort", "对比基准"),
    "report.cmp.session": ("Compare: this session", "对比：本场"),
    "report.cmp.paper": ("Compare: all sessions on this paper", "对比：同题库全部场次"),
    "report.cmp.range": ("Compare: date range", "对比：日期范围"),
    "review.archive_btn": ("Archive session (PDFs + scores CSV)", "一键存档本场（PDF + 成绩表）"),
    "review.archiving": ("Archiving…", "存档生成中…"),
    "review.archives": ("Session archives", "场次存档"),
    "stats.title": ("Statistics", "统计汇总"),
    "stats.scope.session": ("One session", "单场考试"),
    "stats.scope.paper": ("One paper (all sessions)", "同一题库全部场次"),
    "stats.scope.range": ("Date range", "日期范围"),
    "stats.run": ("Generate", "生成统计"),
    "stats.participants": ("Assessed", "参评人数"),
    "stats.sessions_n": ("Sessions", "场次数"),
    "stats.completion": ("Fully completed", "全部完成率"),
    "stats.mean": ("Mean", "均值"),
    "stats.min": ("Min", "最低"),
    "stats.max": ("Max", "最高"),
    "stats.by_question": ("By question", "逐题统计"),
    "stats.indep_rate": ("Independent %", "独立完成率"),
    "stats.guided_n": ("Guided", "引导后"),
    "stats.no_n": ("Not observed", "未观察"),
    "stats.blank_n": ("Blank", "未录"),
    "stats.scored_n": ("Scored", "已评"),
    "stats.empty": ("No matching sessions / records.", "没有匹配的场次或记录。"),
    "stats.hint": (
        "Pick a scope and generate. Blocks are split by paper and level so scores stay on one scale; TK and K are never mixed into one ranking.",
        "选择统计范围后生成。结果按题库和档位分块（满分口径一致），TK 与 K 不会混在同一排名里。",
    ),

    # roster sidebar
    "roster.title": ("Roster", "学生名单"),
    "roster.ungrouped": ("Ungrouped", "未分组"),

    # scoring macros
    "macro.target": ("Target", "目标答案"),
    "macro.setup": ("Set-up", "施测说明"),
    "macro.academic": ("Academic", "学术"),
    "macro.expression": ("Expression", "表达"),
    "macro.task": ("Task score", "任务得分"),
    "macro.expr": ("Expression", "表达得分"),
    "macro.correct": ("Items correct", "答对小项"),
    "sbtn.a0": ("Not yet", "未能完成"),
    "sbtn.a1": ("Guided", "引导后完成"),
    "sbtn.a2": ("Independent", "独立完成"),
    "sbtn.e0": ("No response", "无有效回应"),
    "sbtn.e1": ("Word / phrase", "单词/短语"),
    "sbtn.e2": ("Full sentence", "完整句子"),
    "trial.hint": ("count the items answered correctly", "记录本题小项中答对的个数"),
    "pill.not_observed": ("Not observed", "未观察"),
    "pill.not_completed": ("Not completed", "未完成"),
    "btn.note": ("✎ Note", "✎ 备注"),
    "macro.by": ("by", "记录:"),
    "note.placeholder": (
        "Actual answer, strategy, support given...",
        "实际回答、策略、给予的支持……",
    ),

    # events
    "events.head": ("Support & deduction events", "支持与扣分事件"),
    "events.hint": (
        "Record events from Separation onward. An incorrect academic answer never automatically deducts behavior points.",
        "从 Separation（亲子分离）开始即可记录。学术答错不会自动扣行为分。",
    ),
    "events.cat.cs": ("Classroom Skills", "课堂技能"),
    "placeholder.what": ("What happened", "发生了什么"),
    "placeholder.support": ("Support given", "给予的支持"),
    "btn.add_event": ("Add event", "添加事件"),
    "events.support_prefix": ("Support:", "支持："),

    # js
    "js.saved": ("Saved", "已保存"),
    "js.save_failed": ("Save failed", "保存失败"),
    "js.updated_by": ("Updated by", "已被更新："),
    "js.load_latest": ("Load latest", "加载最新"),
    "js.another": ("another teacher", "其他老师"),
    "js.confirm_delete_event": ("Delete this event?", "删除该事件？"),

    # backend flash messages
    "msg.imported": ("Imported {added} students, skipped {skipped} duplicates", "导入 {added} 名学生，跳过 {skipped} 个重复"),
    "msg.rows_problem": ("rows with problems", "行有问题"),
    "msg.session_deleted": ("Session deleted", "场次已删除"),
    "msg.session_not_found": ("Session not found", "场次不存在"),
    "msg.student_added": ("Student added", "已添加学生"),
    "msg.duplicate_skipped": ("Duplicate skipped", "重复已跳过"),
    "msg.student_removed": ("Student removed", "已移除学生"),
    "msg.group_deleted": ("Group deleted", "组已删除"),
    "msg.level_err": ("Level must be TK or K", "档位必须是 TK 或 K"),
    "msg.decode_err": ("Could not decode file; use UTF-8 CSV or .xlsx", "无法解码文件；请使用 UTF-8 CSV 或 .xlsx"),
    "msg.import_failed": ("Import failed", "导入失败"),
}


def t(key):
    pair = S.get(key)
    if pair is None:
        return key
    return pair[1] if current_lang.get() == "zh" else pair[0]


def cur_lang():
    return current_lang.get()
