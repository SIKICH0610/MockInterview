# 上线部署指南（云服务器 + PostgreSQL）

本文是把测评工作台从本机（SQLite）搬到中台云服务器（PostgreSQL）的完整步骤。
配置文件都在 `deploy/` 目录。数据库相关代码已在本机 PostgreSQL 17 上实测（导入演示数据、全部页面、打分/复核/评语/删除、PDF 与整场存档）；
下面的安装命令已在中台 EC2（**Amazon Linux 2023**，x86_64，2 核 / 7.6 GB）上实际跑通：网站、中英文 PDF、AI 评语均验证可用。
用户名 `ec2-user`，SSH 端口 **22222**，只允许白名单 IP 登录。

**当前状态（2026-11-11）**：网站已切到中台 RDS PostgreSQL 18（库名 `activity`，账号 `activity_rw`），连接串只写在服务器 `/etc/mockinterview.env`。服务器走 RDS 的**内网地址**（办公网的 ELB 地址从服务器连不通，也不需要）。切换前的 SQLite 留档在 `/var/lib/mockinterview/backup/app_before_postgres.db`。
访问方式：公司办公网（白名单 IP）直接打开 `http://32.188.142.195`（80 端口已开，nginx → 8008，HTTP 所以 `MI_COOKIE_SECURE=0`）；
不在公司时用 Cloudflare 临时隧道地址（见第五节）。

---

## 一、需要中台提供

| 项目 | 要求 |
|---|---|
| 服务器 | Amazon Linux 2023（已就绪）。**Python 必须 ≥ 3.11**（系统自带 3.9，另装 python3.12） |
| 登录 | SSH 密钥登录 + sudo 权限（安装系统包、Chromium 依赖、配置服务需要） |
| 数据库 | PostgreSQL 一个**空库** + 账号（需要建表权限）。拿到 主机 / 端口 / 库名 / 用户名 / 密码 |
| 域名与 HTTPS | 一个域名指向服务器；HTTPS 证书由中台提供，或允许用 certbot 自动申请 |
| 外网访问 | 服务器能访问 PyPI（装依赖）、Playwright 下载源（装 Chromium）、OpenAI API（AI 评语） |

---

## 二、一次性安装

```bash
# 1. 系统包：Python 3.12、nginx、中文字体（没有它，中文 PDF 里的汉字会变成方框）
#    以及 Chromium 需要的库（Amazon Linux 不支持 playwright install-deps，所以手动列出）
sudo dnf install -y python3.12 git rsync nginx fontconfig \
  google-noto-sans-cjk-sc-fonts google-noto-sans-fonts liberation-sans-fonts \
  nss atk at-spi2-atk cups-libs libdrm libxkbcommon libXcomposite libXdamage libXrandr \
  libXfixes mesa-libgbm pango alsa-lib libXext libX11 libxcb cairo libatomic
sudo timedatectl set-timezone America/Los_Angeles

# 2. 专用运行账号 + 代码目录
sudo useradd --system --create-home --home-dir /var/lib/mockinterview --shell /sbin/nologin mockinterview
sudo mkdir -p /opt/mockinterview && sudo chown mockinterview: /opt/mockinterview
```

（`libatomic` 不装的话，`playwright install` 会报 `libatomic.so.1: cannot open shared object file`。）

3. 把代码放到 `/opt/mockinterview`（二选一）：
   - 从这台 Mac 直接同步（不需要服务器能访问 GitHub）：
     ```bash
     rsync -az -e "ssh -p 22222 -i ~/.ssh/mockinterview-ec2.pem" \
       --exclude .venv --exclude .git --exclude tools --exclude .claude --exclude '__pycache__' \
       --exclude 'data/*.key' --exclude 'data/*_key.txt' ./ ec2-user@服务器IP:/tmp/mockinterview/
     ssh -p 22222 -i ~/.ssh/mockinterview-ec2.pem ec2-user@服务器IP \
       'sudo rsync -a /tmp/mockinterview/ /opt/mockinterview/ && sudo chown -R mockinterview: /opt/mockinterview && rm -rf /tmp/mockinterview'
     ```
   - 或在服务器上 `git clone`（私有仓库需要先配置 deploy key）。

```bash
# 4. Python 环境与依赖（版本已在 requirements.txt 固定）
cd /opt/mockinterview
sudo -u mockinterview python3.12 -m venv .venv
sudo -u mockinterview .venv/bin/pip install -r requirements.txt

# 5. 生成 PDF 用的 Chromium（系统库已在第 1 步装好），装在运行账号下
sudo -u mockinterview HOME=/var/lib/mockinterview .venv/bin/python -m playwright install chromium
```

---

## 三、配置（密码和密钥只写在服务器上）

```bash
sudo cp deploy/mockinterview.env.example /etc/mockinterview.env
sudo chmod 600 /etc/mockinterview.env
sudo nano /etc/mockinterview.env
```

逐项填写（文件里每项都有说明）：
- `MI_DATABASE_URL`：`postgresql+psycopg://用户名:密码@主机:5432/库名`（密码里有 `@` `:` `/` 等符号时要 URL 编码）
- `MI_SECRET_KEY`：在服务器上运行 `python3 -c "import secrets; print(secrets.token_urlsafe(48))"` 生成后粘贴
- `OPENAI_API_KEY`：AI 评语用的 key
- 其余（`MI_COOKIE_SECURE=1`、`TZ=America/Los_Angeles`、`MI_SELF_URL`）保持默认即可

> 这个文件包含数据库密码和 API key：不要提交到 GitHub，不要发到聊天里。

---

## 四、导入演示数据（必须在第一次启动之前）

程序第一次连上空库时会自动建题库和默认 Admin；导入脚本只往**空库**里写，所以顺序是：**先导入，再启动**。

```bash
cd /opt/mockinterview
sudo systemd-run --pipe --wait --uid=mockinterview \
    -p EnvironmentFile=/etc/mockinterview.env -p WorkingDirectory=/opt/mockinterview \
    /opt/mockinterview/.venv/bin/python scripts/copy_sqlite_to_postgres.py --source data/app.db
```

（用 `systemd-run` 是为了和正式服务读同一份配置，不用把数据库密码写在命令行里。）

脚本会：先检查数据 → 建表 → **一个事务内**全部复制（失败则目标库保持为空）→ 修正 id 序列 → 逐表核对行数。
最后应看到 `Done: … rows … copied; row counts match.`

演示数据里有 15 行记录指向一个已删除的老师账号（#5）：这些记录照常导入，只是「记录人」显示为空（和现在网页上的显示一致）。

---

## 五、启动服务 + HTTPS

```bash
sudo cp deploy/mockinterview.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now mockinterview
systemctl status mockinterview            # 应为 active (running)
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8008/login   # 应为 200

# Amazon Linux 的 nginx 读 /etc/nginx/conf.d/*.conf（没有 sites-available）
sudo cp deploy/nginx-mockinterview.conf /etc/nginx/conf.d/mockinterview.conf
sudo nano /etc/nginx/conf.d/mockinterview.conf      # 把 interview.example.com 换成实际域名
sudo nginx -t && sudo systemctl enable --now nginx && sudo systemctl reload nginx
sudo dnf install -y certbot python3-certbot-nginx
sudo certbot --nginx -d 实际域名                     # 若中台已提供证书则按中台方式配置
```

HTTPS 配好后，把 `/etc/mockinterview.env` 里的 `MI_COOKIE_SECURE` 改为 `1`，再 `sudo systemctl restart mockinterview`。
（在只有 HTTP、还没有证书的阶段必须是 `0`，否则登录后的 cookie 发不出去，会一直跳回登录页。）

### 没有域名时：Cloudflare 临时隧道（当前在用）

服务器上常驻一个 `cloudflared`，给网站一个 `https://xxxx.trycloudflare.com` 地址，不需要域名、不需要开 80/443。
**地址在隧道服务一直运行期间不变**；服务器重启或隧道进程重启后会换新地址。

```bash
curl -fsSL https://pkg.cloudflare.com/cloudflared.repo | sudo tee /etc/yum.repos.d/cloudflared.repo
sudo dnf install -y cloudflared
sudo cp deploy/mockinterview-tunnel.service /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now mockinterview-tunnel
sudo cat /var/lib/mockinterview/tunnel_url.txt      # 当前地址（换地址后也在这里看）
```

只更新网站代码、`restart mockinterview` 不影响隧道地址；不要随手 `restart mockinterview-tunnel`。
Cloudflare 对单个请求有约 100 秒上限：整场一键存档如果学生很多可能超时，可分批生成。

**还没开 80/443 端口时**，也可以从白名单电脑用 SSH 转发先看网站：
`ssh -N -p 22222 -i ~/.ssh/mockinterview-ec2.pem -L 18008:127.0.0.1:8008 ec2-user@服务器IP`，然后浏览器打开 http://localhost:18008 。

---

### 发送报告邮件（家长邮箱 + 官方发件邮箱）

学生表有 `parent_email`（家长邮箱，多个用逗号隔开）：导入订单表时自动读「Parent/Guardian Email Address」和「邮箱」，
也可以在后台场次页逐个修改。发送页面：后台 → 场次 →「发送报告邮件」（汇总复核页也有同名按钮，仅管理员可见）。
每个家庭单独一封，只附自己孩子最近生成的 PDF；正文由老师填写；BCC 收到每封的隐藏副本；发送记录在 `email_logs` 表。

邮件通过 **Microsoft Graph** 从学校的 Microsoft 365 官方邮箱发出（不用 SMTP，不存邮箱密码）：

1. IT 在 Azure 注册应用（Redirect URI 留空；Authentication → Allow public client flows = Yes；
   Microsoft Graph **Delegated**：Mail.Send、offline_access，共享邮箱另加 Mail.Send.Shared；需要时 Grant admin consent）。
2. 把两个编号写进 `/etc/mockinterview.env`，然后 `sudo systemctl restart mockinterview`：
   ```bash
   MI_MS_CLIENT_ID=Application (client) ID
   MI_MS_TENANT_ID=Directory (tenant) ID
   MI_MAIL_BCC=默认密送邮箱（可选）
   ```
3. 管理员打开「管理后台 → 发件邮箱」，点「连接发件邮箱」，在 microsoft.com/devicelogin 输入验证码，用官方邮箱登录并同意。
   共享邮箱：先填共享邮箱地址，再用自己有 Send As 权限的账号登录。
4. 在同一页「发送测试」发给自己确认。

授权凭证（refresh token）用 `MI_SECRET_KEY` 派生的密钥加密后存在 `mail_account` 表。每天 3:10 自动续期一次，
所以不会因为长期不发信而过期；改了 `MI_SECRET_KEY`、邮箱改密码、IT 撤销授权或公司策略要求重新登录时，需要管理员重新连接。

```bash
sudo cp deploy/mockinterview-mailrefresh.{service,timer} /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now mockinterview-mailrefresh.timer
journalctl -u mockinterview-mailrefresh -n 5     # 最近一次续期结果
```服务器需能访问 login.microsoftonline.com 和 graph.microsoft.com（已确认可以）。

---

## 六、上线后检查清单

- [ ] 用 Admin 登录（密码与现在本机演示库里的 Admin 相同），**立即在「老师管理」确认/修改各账号密码**
- [ ] 汇总复核页、个人面试页、报告页都能打开，数据与本机一致
- [ ] 生成一份「PDF · 中文」：汉字正常显示（不是方框）、页脚中文正常
- [ ] 「AI 生成草稿」能同时填出英文和中文
- [ ] 复核时间、PDF 时间是加州时间
- [ ] 「一键存档整场」能跑完、不超时
- [ ] iPad 上打开，右上角退出图标可见

---

## 七、日常更新（发布新版本）

```bash
# 同步新代码（rsync 或 git pull，同第二节第 3 步），然后：
cd /opt/mockinterview
sudo -u mockinterview .venv/bin/pip install -r requirements.txt
sudo systemctl restart mockinterview
journalctl -u mockinterview -n 50     # 看启动日志
```

- **数据库结构**：新版本给已有表**新增字段**时，重启会自动补上（日志里出现 `schema upgrade: added …`）。
  **改名、删字段、改类型**不会自动处理，需要手动执行 SQL——发布前先确认。
- 静态文件（CSS/JS）带版本号，iPad 刷新即可拿到新样式，不必清缓存。

---

## 八、备份

数据（含所有 PDF 存档）都在 PostgreSQL 里。每天 2:30 自动 `pg_dump` 到
`/var/lib/mockinterview/backup/mi_日期.dump`，保留 14 天（`scripts/backup_db.py`；没设 `MI_DATABASE_URL` 时改为复制 SQLite 文件）。
连接信息直接读 `/etc/mockinterview.env`，不需要另外的密码文件。

```bash
# 一次性安装：pg_dump 版本必须 ≥ 数据库版本（当前库是 18）
sudo dnf install -y postgresql18
sudo cp deploy/mockinterview-backup.{service,timer} /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now mockinterview-backup.timer
sudo systemctl start mockinterview-backup && sudo ls -l /var/lib/mockinterview/backup   # 立即跑一次看看
```

恢复（会覆盖库里现有数据，先确认、先停网站）：
`pg_restore --clean --no-owner -h 主机 -U 用户名 -d 库名 备份文件.dump`。
备份放在服务器硬盘上：防误删、防误操作，但防不了整台服务器丢失——可再问中台 RDS 自带的自动备份保留几天。

---

## 九、注意事项

- 上线后 `data/app.db` 不再使用；线上真实学生数据只在 PostgreSQL 里，**不要导出后提交到 GitHub**。
- 若将来某次在**空库**上直接启动（不导入演示数据），先在 `/etc/mockinterview.env` 设好 `MI_INITIAL_ADMIN_PASSWORD`。（多个 worker 同时启动时，建表/补字段由数据库锁保证一次只跑一个，不需要改 `--workers`。）
- 本机开发不受影响：不设 `MI_DATABASE_URL` 时仍使用 `data/app.db`。
