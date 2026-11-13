# Think Academy SV · Assessment Workbench

TK/K 现场测评工作台（FastAPI + SQLite，网页端，iPad 优先）。

## 启动

```
python -m uvicorn app.main:app --host 0.0.0.0 --port 8008
```

电脑上打开 http://localhost:8008 ；iPad 在同一 WiFi 下打开 `http://<电脑IP>:8008`
（电脑 IP 用 `ipconfig` 查看 IPv4 地址；打不开时用管理员 PowerShell 放行防火墙：
`netsh advfirewall firewall add rule name="MockInterview 8008" dir=in action=allow protocol=TCP localport=8008`）。

**临时公网访问**：双击项目根目录的 `start_tunnel.bat`（Cloudflare 免费隧道），窗口里出现的
`https://xxxx.trycloudflare.com` 就是公网地址，任何网络的设备都能打开（有登录保护）。
注意：每次重启隧道地址都会变；这是正式部署到中台服务器前的过渡方案。
Mac 上：`brew install cloudflared` 后运行 `cloudflared tunnel --url http://localhost:8008`。

**正式上线（云服务器 + PostgreSQL）**：见 [DEPLOY.md](DEPLOY.md)。

## 登录

- 所有页面需要登录。初始管理员账号：**Admin / admin123**（请登录后在老师管理页改掉）
- 角色：`admin`（后台 + 全部）/ `teacher`（仅工作台，录入自动归属本人）
- 老师账号由管理员在「老师管理」创建并设置密码；登录有效期 24 小时
- 密码为 PBKDF2 加盐哈希，存于 `data/app.db`；会话签名密钥在 `data/secret.key`

## 使用流程

1. **Admin → Teachers**：添加老师并设置密码
2. **Admin → Sessions**：建场次（选择题库）→ **直接上传 Think Academy 班级导出表**（自动读取 userName / 学员id / gradeName / className，自动识别 TK/K，识别不了的在学生表里补选）；也可直接上传**报名订单导出表**（姓名取「Child’s Full Name」——订单表的「学生姓名」是账号名，常是家长名/邮箱/手机号；档位取报名年级；同一学生 uid 多个订单只导入一次）→ **现场分组看板**：一键随机分组（TK/K 均衡）、拖 ⠿ 换组或点选换组、组上指派老师。**所有学生进组且档位齐全后才解锁打分**（流程：① 导入 → ② 分组 → ③ 打分）
   - **Admin → 题库管理**：每个场次绑定一个题库；新测评 = 复制现有题库 → 编辑题目（题面/目标/评分标准/表达/计数全可改），旧场次不受影响。**集体环节评价内容也随题库**：题库详情页底部可编辑各环节的评价维度（中英名称 + 档位词表，最好在前）与绘本故事 8 问（每行一条），支持增删维度；复制题库时一并复制。修改只影响之后的录入，已记录数据保持原值
3. **Workbench**：登录后选场次（身份即登录老师），三个环节：
   - **集体环节**（固定四个环节，多维度评价，数字化自纸质 Group 打分表）：① Separation 分离适应（三级单选 + 备注）；② Self Introduction 自我介绍（Initiative/Confidence/Fluency/Listen 四维）；③ Story Time 绘本故事（8 个 Let's Talk 提问逐条回应 **+ 整体维度** Participation/Focus/Listen/Empathy）；④ Cutting & Drawing 剪纸绘画（Follow Instruction/Fine Motor/Sharing/Problem Solving/Creativity/Attitude 六维）。每维单选档位、再点取消；维度词表在题库详情页可视化编辑（`seed.py` 里的只是新题库的默认值）。旧版的 Circle Time 已更名为 Story Time；与之重复的 Show & Share、Ticket Making 已移除（历史数据如含旧环节名仍可正常显示）
   - **个人面试**：12 道题逐题记录，左侧学生名单栏（竖屏为抽屉）+ SEL/课堂事件。**任务得分** = 该题学术分，按钮直接标注含义（0 未能完成 / 1 引导后完成 / 2 独立完成，具体标准见题旁 SCORE 原文）；**表达得分** = 口头表达（0 无回应 / 1 单词短语 / 2 完整句子）；**答对小项** = 该题含多个小项时（如 E01 的 6 个字母）记答对个数，报告里显示为 "6/6 correct"。选最优档变绿、中间档琥珀、最低档红
   - （原「群面打分」已删除——它与集体环节重复；旧链接自动跳转集体环节）
   - **Review 汇总复核**：全场学生 × 12 题状态矩阵，缺项高亮，点格子直达补录；分离/Circle/事件计数；逐生确认复核（记录确认人与时间）
4. 右上角「中文 / EN」切换界面语言（按设备记住）

## 数据

- 题库：TK/K 各 12 题（M01–M06 + E01–E06），评分标准原文取自官方题卡 SCORE 页，存在 `questions` 表
- 所有打分即时自动保存；并发冲突用版本号保护（旧版本提交返回 409，不会静默覆盖）
- 未作答的题保持空白（复核矩阵高亮缺项），不会被算成 0 分；历史数据中的 `Not observed` / `Not completed` 状态在报告/统计里仍单独显示（个面录入界面已简化为 0/1/2 + 备注）
- 数据库：本机默认 `data/app.db`（SQLite）。线上设置环境变量 `MI_DATABASE_URL=postgresql+psycopg://用户:密码@主机:5432/库名` 即切换到 PostgreSQL；演示数据用 `scripts/copy_sqlite_to_postgres.py` 导入；已有表新增字段会在启动时自动补上（`app/schema.py`），改名/删字段/改类型需手动处理。详见 [DEPLOY.md](DEPLOY.md)
- 删除场次 / 学生会一并删除其全部记录（打分、集体环节、评语、复核、PDF、存档）——PostgreSQL 强制检查数据关联，漏删会导致删除失败
- `sample_students.csv` 是导入格式示例

## 报告

- 汇总复核页每行「Report」按钮 / 个面页右上角进入 `/report/{学生id}`
- **中英双版**：报告工具栏右上 EN/中文 切换整份报告语言（题目内容保持英文）；「PDF · EN」「PDF · 中文」分别生成两种语言的存档（文件名带 `_EN`/`_CN`）；**一键存档整场会为每个学生同时生成中英两份 PDF**
- **每部分自带解释与「表现解读」**：各页标题下有家长向说明；数学/英语/集体环节各有一段按实际记录自动生成的解读（规则模板、只陈述事实；之后可接 AI 润色）。文案模板在 `app/services/analysis.py`，双语词表在 `app/report_i18n.py`
- **教师评语分中英两栏**：英文栏进英文报告/PDF，中文栏进中文报告/PDF（`summaries.text` / `summaries.text_zh`）。某一栏留空时，该语言的打印/PDF 版自动以该语言的「整体解读」填充，不会出现空白评语区
- 点「PDF · EN / PDF · 中文」时，若评语有未保存的修改，会先自动保存再生成，PDF 里一定是最新评语
- 教师备注：某个表格整列无备注时自动隐藏该列，避免整列空白
- 封面七彩标签 = 七项能力维度，带说明文字，并自动给本场表现最强的能力加 ★
- 版式（参考 Bellevue 私校模拟面试报告结构）：**封面页**（品牌、三行大标题、学生信息表、七项能力彩色气泡）→ **Performance Overview**（四维度卡 + 每卡「Session avg · 排名 · Top %」同场对比 + Teacher's View）→ **七项能力雷达**（本人 vs 本场平均双线 + Session avg 列）→ **Task-by-task**（数学/英语各带 四格统计条：得分/场均/排名/百分位）→ **集体环节 + SEL & Classroom Skills**（统计条 + 事件明细）→ **尾页**（品牌联系页，文案在 report.html 底部可改）
- 同场对比口径：同场次同档位、已录入成绩的学生；百分位 =（低于者 + 同分一半)/参评数，页脚有说明；参评 ≤1 人时显示 —
- PDF 页脚自动带「学生名 · 报告名 · 页码/总页数」
- **雷达对比基准可切换**（报告页工具栏下拉）：本场 / 同题库全部场次 / 日期范围——统计条、四卡对比行、雷达虚线全部跟随切换
- **一键存档整场**（admin，复核页顶部）：为本场所有有记录的学生批量生成 PDF 入库 + 全员成绩汇总 CSV 存档（`session_archives` 表，复核页可下载）
- **统计汇总**（Admin → 统计汇总）：按 单场 / 同题库 / 日期范围 生成基础统计——按题库×档位分块（TK/K 不混排名），五维均值/最低/最高、全部完成率、逐题均分/独立完成率/引导数/未观察/未录
- **「生成 PDF 存档」**：服务端 Chromium（Playwright）渲染，版式与网页一致、固定 Letter 版心，**PDF 以二进制存进数据库**（`report_pdfs` 表），报告页底部可查看/下载历次存档；「Print / Export PDF」仍可走浏览器打印。Playwright 不在 requirements.txt 里，新电脑需另装：`pip install playwright` 后运行 `python -m playwright install chromium`
- **「AI 生成草稿」**：Teacher's View 一键根据实际记录生成/润色英文评语——只用已记录事实、区分独立与引导、未观察不编造——并同时据此生成中文版（沿用报告里的中文术语，忠实转述、不增不减）；改完英文后可点「按英文重新翻译」只更新中文栏。**草稿只填入编辑框，老师改完手动保存才生效**。提示词在 `app/services/ai.py`。提供商自动识别：`data/openai_key.txt`（OpenAI，默认 gpt-4o，可用 `MI_OPENAI_MODEL` 改）或 `data/anthropic_key.txt`（Claude，两者都有时优先用 Claude）。key 文件已被 git 忽略，不会上传
- 未观察明确标注且不计为 0；汇总算法未定项（D02/D03）只展示原始分，不擅自合成

## 还未实现（按计划后续做）

- 录音（表结构已留好 `audio_notes`）
- 报告库集中检索与全体学生分析
- AI 语音转写（评语 AI 草稿已就绪，填入 key 即可用）
