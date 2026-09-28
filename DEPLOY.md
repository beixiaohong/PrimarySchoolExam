# 智学学堂 · 完整部署说明

> 最后更新：2026-09-07 · 对应代码版本：426 端点 / 86 表 / 65 迁移 / 268 测试 / 9 域
> 适用系统：Ubuntu 20.04+ / Debian 11+ / CentOS 7+

---

## 目录

1. [环境要求](#1-环境要求)
2. [快速部署（一键脚本）](#2-快速部署一键脚本)
3. [手动部署（分步）](#3-手动部署分步)
4. [环境变量参考](#4-环境变量参考)
5. [数据库配置](#5-数据库配置)
6. [前端构建](#6-前端构建)
7. [Nginx 配置](#7-nginx-配置)
8. [HTTPS 证书](#8-https-证书)
9. [防火墙与安全组](#9-防火墙与安全组)
10. [运维命令](#10-运维命令)
11. [更新流程](#11-更新流程)
12. [自动化测试](#12-自动化测试)
13. [项目结构](#13-项目结构)
14. [常见问题](#14-常见问题)
15. [定时任务（调度器）运维](#15-定时任务调度器运维)
16. [消息推送（OneSignal）](#16-消息推送onesignal)

---

## 1. 环境要求

| 组件 | 最低版本 | 说明 |
|---|---|---|
| Python | 3.12+ | 后端运行时 |
| Node.js | 18+ | 前端构建时（web/ + admin/） |
| MySQL | 8.0+ | 主数据库（已移除 SQLite 支持） |
| Nginx | 1.18+ | 反向代理 + 静态文件托管 |
| 内存 | 2 GB+ | 构建时 element-plus/echarts 编译需较大内存 |
| 磁盘 | 10 GB+ | 含日志、产物、数据库 |

**可选**：
- swap 2 GB+（deploy.sh 自动创建，防构建 OOM）
- 域名 + 公网 IP（HTTPS 需要）

---

## 2. 快速部署（一键脚本）

### 2.1 上传项目

```bash
scp -r ./PrimarySchoolExam root@服务器IP:/home/PrimarySchoolExam
```

### 2.2 配置环境变量

```bash
cd /home/PrimarySchoolExam
cp .env.example .env
# 编辑 .env 填入实际值（MySQL 连接、AI API Key、邮件配置等）
vi .env
```

### 2.3 执行部署

```bash
sudo bash deploy.sh
```

脚本自动完成：
1. 安装系统依赖（Python3、Nginx）
2. 创建 Python 虚拟环境 + 安装 pip 依赖
3. 构建 web/ 前端（Vite + Vue 3，仅源码有变化时重建）
4. 构建 admin/ 前端（独立 Vite 工程，仅源码有变化时重建）
5. 配置 systemd 服务（自动注入 `.env` 环境变量）
6. 配置 Nginx（HTTP 80 + HTTPS 443）
7. 启动服务 + `/health` 健康自检
8. 防火墙放行 80/443 端口

> 构建策略：deploy.sh 会对比 `src/` 与 `dist/` 的修改时间，仅源码有变化时才重建，纯后端更新可秒级完成。构建时 nice 降优先级 + 限制 Node 堆内存（1 GB），避免拖垮 MySQL/Nginx。

### 2.4 部署完成

```
访问地址:  https://你的域名
管理后台:  https://你的域名/admin   （默认管理员 admin / Admin@123）
应用端口:  8000 (内部)
```

---

## 3. 手动部署（分步）

### 3.1 安装系统依赖

```bash
# Ubuntu / Debian
sudo apt-get update
sudo apt-get install -y python3 python3-venv python3-pip nginx

# CentOS
sudo yum install -y python3 python3-pip nginx
```

### 3.2 创建虚拟环境

```bash
cd /home/PrimarySchoolExam
python3 -m venv venv
venv/bin/pip install --upgrade pip
venv/bin/pip install -r requirements.txt
```

### 3.3 配置 systemd 服务

```bash
sudo cat > /etc/systemd/system/exam-app.service <<EOF
[Unit]
Description=Primary School Exam System
After=network.target

[Service]
Type=simple
User=www-data
WorkingDirectory=/home/PrimarySchoolExam
ExecStart=/home/PrimarySchoolExam/venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 2
Restart=always
RestartSec=3
Environment=PYTHONUNBUFFERED=1
EnvironmentFile=-/home/PrimarySchoolExam/.env

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable exam-app
sudo systemctl start exam-app
```

> CentOS 用户改为 `User=nginx`，并 `chown -R nginx:nginx /home/PrimarySchoolExam`。

### 3.4 启动验证

```bash
curl -fsS http://127.0.0.1:8000/health
# 应返回 {"status":"ok","checks":{"db":"ok","migrations":"...","uptime_sec":...}}
```

---

## 4. 环境变量参考

> 完整模板见 `.env.example`，以下列出关键配置项。

### 4.1 数据库（必填）

| 变量 | 说明 | 示例 |
|---|---|---|
| `DB_DRIVER` | 固定 `mysql` | `mysql` |
| `DB_HOST` | MySQL 主机 | `127.0.0.1` 或 `mysql6.xxx.com` |
| `DB_PORT` | 端口 | `3306` 或 `3311` |
| `DB_USER` | 用户名 | `root` |
| `DB_PASSWORD` | 密码 | |
| `DB_NAME` | 数据库名 | `schoolexam` |

### 4.2 AI 提供商（可选，不配则降级为本地模板）

| 变量 | 说明 | 默认值 |
|---|---|---|
| `ZHIPU_API_KEY` | 智谱 API Key | 空 |
| `AI_MODEL` | 智谱模型 | `glm-4.7` |
| `AI_BASE_URL` | 智谱接口地址 | `https://open.bigmodel.cn/api/paas/v4` |
| `DEEPSEEK_API_KEY` | DeepSeek Key（VIP 付费链） | 空 |
| `RELAY_API_KEY` | 中转站 Key（备用兜底） | 空 |
| `RELAY_BASE_URL` | 中转站地址 | 空 |
| `RELAY_MODEL` | 中转站模型 | `gpt-4o-mini` |

### 4.3 邮件（注册/验证码）

| 变量 | 说明 |
|---|---|
| `MAIL_SERVER` | SMTP 服务器 |
| `MAIL_PORT` | 端口（465=SSL） |
| `MAIL_ADDRESS` | 发件人邮箱 |
| `MAIL_PASSWORD` | 邮箱密码/授权码 |

### 4.4 收款/客服二维码

| 变量 | 说明 | 默认值 |
|---|---|---|
| `RECHARGE_WECHAT_QR` | 微信收款码路径 | `/qr/wx.png` |
| `RECHARGE_ALIPAY_QR` | 支付宝收款码路径 | `/qr/zfb.jpg` |
| `RECHARGE_CS_QR` | 客服二维码路径 | `/qr/kefu.png` |
| `RECHARGE_CS_CONTACT` | 客服联系方式 | `beidou669` |

> 二维码图片放在 `web/public/qr/` 下，构建后由 `/qr` 静态路由托管。

### 4.5 功能开关

| 变量 | 说明 | 默认值 |
|---|---|---|
| `ENABLE_IM` | IM 模块（D9 冻结域） | `true` |
| `ENABLE_LEDGER` | 账本模块（D9 冻结域） | `true` |
| `ALLOW_NICKNAME_LOGIN` | 昵称快捷登录（正式上线前设为 false） | `true` |

---

## 5. 数据库配置

### 5.1 创建数据库

```sql
CREATE DATABASE schoolexam CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'app_user'@'%' IDENTIFIED BY 'your_password';
GRANT ALL PRIVILEGES ON schoolexam.* TO 'app_user'@'%';
FLUSH PRIVILEGES;
```

### 5.2 迁移系统

- 迁移脚本位于 `app/migrations/versions/`（当前 65 个，编号 001-065+）
- 启动时 `lifespan` 自动执行未应用的迁移（`app/migrations/runner.py`）
- 版本表：`schema_migrations`（非 alembic_version）
- 所有迁移幂等可重跑（026+ 使用 `_ensure_column` 等幂等工具）

### 5.3 测试库

- 测试使用独立数据库：`DB_NAME + "_test"`（如 `schoolexam_test`）
- conftest.py 自动 `drop_all` 重建 + 运行全部迁移 + 种子数据
- **绝不修改 `.env` 中的 `DB_NAME`**，测试库名由 conftest 自动计算
- 安全护栏：测试库名与生产库名相同时 pytest 直接报错退出

### 5.4 种子数据

| 数据 | 来源 | 说明 |
|---|---|---|
| 小学单词 1969 词 | `app/data/words_primary_school.csv` | 迁移 002 自动导入 |
| 初中单词 434 词 | `app/data/words_middle_school.csv` | 迁移 C1 自动导入 |
| 古诗文 48 篇 | 迁移 002/032 | 小学 + 初中必背 |
| 商城商品 9 个 | `db/seed_commerce_products.sql` | 需手动导入（线上库） |
| VIP 种子 | 迁移 009 | 「诗文」「橙子」两个种子 VIP |

---

### 5.5 高项备考资料导入（可选，一次性）

软考高项「PDF 备考资料 → 题库」分两段执行：**本地解析打包、线上写库**。
拆成两段的原因：解析依赖 PyMuPDF 与 LibreOffice（本地方便），而写库必须落在线上库
（本地 `.env` 指向的是线上库的**克隆**，铁律：绝不对克隆库跑写库脚本）。

```bash
# ① 本地：解析资料 → 数据包（不连数据库，约 45 秒）
.venv/Scripts/python.exe tools/gx_pack.py \
    --root "temp/软考【高项】2026年5月班备考资料" --out data/gx_materials
# 产出 4 个包 + 清单：pack_knowledge.json / pack_choice.json / pack_case.json /
#                      pack_essay.json / manifest.json（含分类明细与字段覆盖率）

# ② 上传数据包到服务器（只传数据包，不传原始资料）
scp -r data/gx_materials root@115.29.213.131:/home/PrimarySchoolExam/data/

# ③ 线上：写库（幂等，可重复跑）
cd /home/PrimarySchoolExam
venv/bin/python tools/import_gx_materials.py stats                    # 先看包里有几条
venv/bin/python tools/import_gx_materials.py load --dry-run --limit 200   # 试跑
venv/bin/python tools/import_gx_materials.py load                     # 正式入库
venv/bin/python tools/import_gx_materials.py materials --category 选择题练习
```

- 前置：迁移 `081_gaoxiang.py`（6 张备考表）与 `082_gx_materials.py`（资料归档表 + 资料维度列），
  `deploy.sh` 重启时会自动执行，先部署再导入。
- **幂等口径**：内容指纹（sha1 前 16 位，`gx_questions.fingerprint` / `gx_knowledge.fingerprint`
  唯一索引）—— 重复导入只更新既有行，不会产生重复题。
- 体量参考：602 个文件 → 442 个解析单元 → 去重后 3980 条（知识点 2287 / 选择题 1670 /
  案例 17 / 论文 6）；写库分钟级。
- 不导入也不影响使用：题库为空时刷题会退回 AI 现场出题（按 token 扣钻石，
  且前端需勾选「允许 AI 出题」，默认只刷已导入真题）。

---

## 6. 前端构建

### 6.1 孩子端（web/）

```bash
cd /home/PrimarySchoolExam/web
npm install        # 或 npm ci（生产环境推荐）
npm run build      # 产物输出到 web/dist
```

- 技术栈：Vue 3 + Vite 5 + Pinia 2
- 构建产物 `web/dist` 由后端直接托管（`/` 路径）
- 本地开发：`npm run dev`（http://localhost:5173，自动代理 `/api` 到 8000）

### 6.2 管理后台（admin/）

```bash
cd /home/PrimarySchoolExam/admin
npm ci
npm run build      # 产物输出到 admin/dist
```

- 技术栈：Vue 3 + Vite + Element Plus + ECharts
- 构建产物 `admin/dist` 由后端托管在 `/admin`
- 路由使用 hash 模式（`/admin#/users`），无需 SPA 回退
- 本地开发：`npm run dev`

### 6.3 构建后重启

```bash
sudo systemctl restart exam-app
```

> 若 `web/dist` 或 `admin/dist` 不存在，访问对应路径会返回「前端未构建」提示。

### 6.4 构建溯源与产物校验（tools/build_info.py）

前端是**编译产物**，后端是**源码直跑** —— 两者版本可以各自漂移，而且症状很隐蔽：
页面还是旧界面、按钮点了没反应，排查时容易误判成后端 bug。两类故障：

| 故障 | 症状 | 成因 |
|---|---|---|
| dist 过期 | 线上一直是旧界面，与代码对不上 | 前端源码改了但 dist 没重建（或构建失败被忽略） |
| 契约错位 | 线上 404、按钮静默失效 | 接口改名/删除后前端没跟上（本项目踩过：IM 私聊「点了没反应」） |

`deploy.sh` 每次构建完会自动记录溯源信息到 `dist/.build-info.json`
（源码逐文件指纹 + git sha + 产物引用的 `/api/...` 路径），`preflight.py` 在重启前据此校验。

手动排查：

```bash
cd /home/PrimarySchoolExam
venv/bin/python tools/build_info.py show  --dir web   # 这份 dist 是谁构建的、是否过期
venv/bin/python tools/build_info.py check --dir web   # 新鲜度 + 前后端契约一次性核对
```

`check` 输出示例：

```
[build-info] [ OK ] web 的 dist 与当前源码一致（源码未变（88 个文件，指纹 237717693842aaf0））
[build-info] [WARN] 2 个路径前端在调用但后端不存在（接口改名/删除后前端未跟上）：
          · /api/study/plan-removed
```

- 报「过期」时若想自己构建：`cd web && npm ci && npm run build`，然后
  `venv/bin/python tools/build_info.py write --dir web` 补记溯源信息。
- `needs-build --dir web` 是给脚本用的判据（退出码 **0=需要构建 / 1=无需构建**），
  `deploy.sh` 用它取代了原来的 mtime 判断。
- 未记录溯源信息（老产物）时，`preflight` 只提示「无法校验」并要求重建一次 ——
  首次部署本机制时会自动重建一轮，之后即收敛。

---

## 7. Nginx 配置

### 7.1 完整配置

```nginx
# /etc/nginx/conf.d/exam-app.conf

# HTTPS 主配置
server {
    listen 443 ssl http2;
    server_name www.你的域名.com;

    ssl_certificate     /etc/letsencrypt/live/www.你的域名.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/www.你的域名.com/privkey.pem;
    ssl_protocols       TLSv1.2 TLSv1.3;
    ssl_ciphers         ECDHE-RSA-AES256-GCM-SHA512:DHE-RSA-AES256-GCM-SHA512;
    ssl_prefer_server_ciphers off;

    client_max_body_size 50m;

    # WebSocket（IM 即时通讯）：必须显式升级协议
    # 缺失 Upgrade/Connection 头时，浏览器 wss 握手拿不到 101，前端会一直提示
    # 「正在连接中，请稍后再试」（消息走 WS 发送）。长连接超时也要放大，否则约
    # 每 2 分钟被 nginx 掐断一次。
    location /api/im/ws/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 3600s;
        proxy_send_timeout 3600s;
    }

    # 主应用（孩子端 + API）
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 120s;
    }

    # 生成文件（docx/图片/音频）
    location /output/ {
        alias /home/PrimarySchoolExam/output/;
        expires 7d;
    }

    # 二维码静态
    location /qr/ {
        alias /home/PrimarySchoolExam/web/public/qr/;
        expires 30d;
    }
}

# HTTP 跳转 HTTPS
server {
    listen 80;
    server_name www.你的域名.com;
    return 301 https://$server_name$request_uri;
}
```

### 7.2 检测并重载

```bash
sudo nginx -t
sudo systemctl reload nginx
```

---

## 8. HTTPS 证书

### 8.1 签发（Let's Encrypt 免费证书）

前提：域名 A 记录已解析到服务器公网 IP。

```bash
# 安装 certbot
# Ubuntu/Debian
sudo apt install -y certbot python3-certbot-nginx
# CentOS
sudo yum install -y certbot python3-certbot-nginx

# 确保 nginx 配置中 server_name 是域名
sudo sed -i 's/server_name _;/server_name www.你的域名.com;/' \
    /etc/nginx/conf.d/exam-app.conf
sudo nginx -t && sudo systemctl reload nginx

# 签发证书
sudo certbot --nginx -d www.你的域名.com
```

### 8.2 自动续期

证书 90 天有效，certbot 自动续期。验证：

```bash
sudo certbot renew --dry-run
```

---

## 9. 防火墙与安全组

### 9.1 系统防火墙

```bash
# Ubuntu (ufw)
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp

# CentOS (firewalld)
sudo firewall-cmd --permanent --add-port=80/tcp
sudo firewall-cmd --permanent --add-port=443/tcp
sudo firewall-cmd --reload
```

### 9.2 云安全组

阿里云/腾讯云等还需在控制台 → 安全组 → 入方向添加：
- 80/tcp（HTTP）
- 443/tcp（HTTPS）

---

## 10. 运维命令

```bash
# 查看应用状态
sudo systemctl status exam-app

# 查看实时日志
sudo journalctl -u exam-app -f

# 重启应用
sudo systemctl restart exam-app

# 重启 Nginx
sudo systemctl restart nginx

# 查看端口占用
ss -tlnp | grep -E ':80|:443|:8000'

# 查看数据库连接
mysql -u root -p -e "SHOW PROCESSLIST;" schoolexam

# 查看迁移版本
mysql -u root -p -e "SELECT * FROM schema_migrations ORDER BY version_num;" schoolexam
```

---

## 11. 更新流程

### 11.1 常规更新

```bash
cd /home/PrimarySchoolExam
git pull

# 后端有变更（含迁移）→ 重启即可（迁移自动执行）
sudo systemctl restart exam-app

# 前端有变更 → 重新构建
cd web && npm ci && npm run build && cd ..
cd admin && npm ci && npm run build && cd ..
sudo systemctl restart exam-app
```

### 11.2 简化：直接跑 deploy.sh

```bash
cd /home/PrimarySchoolExam
git pull
sudo bash deploy.sh
```

deploy.sh 会自动判断前端是否需要重建：优先用**源码内容指纹**（`tools/build_info.py`），
指纹不可用时退化为 mtime 对比。指纹判据覆盖了 `src/`、`index.html`、`novel.html`、
`public/`、`package.json`、`package-lock.json`、`vite.config.js` —— 而 mtime 判据只看
`src/`、`package.json`、`vite.config.js`，会漏掉「改了入口 HTML / 换了 public 图片」
和「删除了源文件」，漏判后果是线上静默沿用旧 dist（界面与代码不一致，却毫无提示）。

### 11.3 部署前置自检（deploy.sh 的"部署闸门"）

`deploy.sh` 会在**重启服务之前**跑两道自检，任一项 BLOCK 就中止部署 ——
**旧版本服务不受影响、站点保持可用**（只是这次没更新成功）。

| 阶段 | 位置 | 检查内容 |
|---|---|---|
| `early` | 装完依赖、修完属主后（前端构建**之前**） | 依赖完整性 + 应用可导入 + `.env` 必需键 |
| `full` | 写 systemd/nginx 配置与重启服务**之前** | 再加外部命令（ffmpeg/soffice/npm）+ 前端产物（存在性 / 引用完整 / 与源码及后端契约配对） |

单独运行（排查用，不改动任何东西）：

```bash
cd /home/PrimarySchoolExam
venv/bin/python tools/preflight.py --stage full
```

常见输出与处置：

| 输出 | 含义 | 处置 |
|---|---|---|
| `依赖未声明：X` | 代码模块级硬导入了 X，但 `requirements.txt` 没写 | 把 X（含版本）加进 `requirements.txt` |
| `应用可导入` BLOCK | 服务起不来（重启即全站 502） | 看提示区分：漏声明→补清单；已声明→`pip install -r requirements.txt` |
| `外部命令 ffmpeg` WARN | IM 语音转 MP3 不可用 | `apt install ffmpeg`（不阻断部署） |
| `.env 缺少 DB_HOST` BLOCK | 连不上数据库 | 在 `.env` 补上 |
| `主站前端产物过期` WARN | dist 不是当前源码构建的（构建被跳过/失败） | 重新构建（`deploy.sh` 会自动重建），详见 §6.4 |
| `前后端契约错位` WARN | 前端在调后端**不存在**的 `/api/...`（接口改名后前端没跟上） | 改前端源码或后端路由，然后重建前端，详见 §6.4 |
| `主站前端资源不完整` WARN | 入口 HTML 引用的 JS/CSS 在 dist 里找不到（构建中断/磁盘满） | 重新构建前端 |
| `定时任务资产` WARN | 调度任务配置有误/脚本不存在/依赖未声明 | 见 §15 |

> **闸门为什么必须在重启之前**：2026-09-24 事故中 deploy.sh 的顺序是「先重启、后检查」，
> 坏版本被换上后 systemd（`Restart=always`）不停崩溃重启，全站 502 ——
> deploy.sh 虽然报错退出，站点却已经挂了、旧版本进程也没了。
> 现在自检不过就**根本不重启**。
>
> **为什么前端配对只报 WARN 不阻断**：它不影响服务启动（站点可用，只是界面旧了/某个按钮失灵）。
> 闸门一旦误报就会被人绕过而失去意义，所以只让"真会致挂"的项 BLOCK ——
> 但这些 WARN 每次部署都会打印，不会悄悄溜过去。

### 11.4 回滚

```bash
cd /home/PrimarySchoolExam
git log --oneline -10   # 找到要回退的 commit
git reset --hard <commit_hash>
sudo bash deploy.sh     # 重新部署（会先跑前置自检再重启）
```

> 迁移只向前执行，不会自动回滚。如需回滚数据库，需手动恢复备份。

---

## 12. 自动化测试

### 12.1 运行测试

```bash
cd /home/PrimarySchoolExam
# 安装开发依赖
venv/bin/pip install -r requirements-dev.txt

# 运行全部测试（626 用例）
venv/bin/python -m pytest tests -q

# 运行特定测试文件
venv/bin/python -m pytest tests/test_ai_vip.py -v
venv/bin/python -m pytest tests/test_gaoxiang.py -v
```

> **不要给全量测试指定 `--basetemp` 到项目目录内**（例如 `--basetemp=temp/pt`）：
> pytest 收尾会 `rmtree` 该目录，用例多时会触发本机安全删除守护的「批量删除」拦截并抛
> `SystemExit`，导致 fixture finalizer 未消费 → **后续用例在 setup 阶段连锁报错**
> （`assert not self._finalizers`），表现为一片与代码无关的假失败。
> 用例少时不会触发（阈值是数量），所以会出现"小批量跑过、全量跑挂"的迷惑现象。
> 用默认临时目录即可；判"是否真通过"看 `--junit-xml` 的 failures/errors 计数。

### 12.2 测试隔离

- 测试使用独立 MySQL 测试库（`schoolexam_test`），与线上库完全隔离
- AI 判题复核已打桩（`no_ai_judge` fixture），不触达外部 AI 服务
- 邮件发送已打桩（`fake_mail` fixture），捕获验证码明文
- 每次测试会话 `drop_all` 重建，保证干净环境

### 12.3 端点快照

```bash
venv/bin/python tools/endpoint_snapshot.py
# 输出到 endpoint_baseline.txt，记录全部 METHOD + path
```

### 12.4 高项备考模块（面向非学生成人用户）

软考高级「信息系统项目管理师」备考入口，与小学侧**完全解耦**（独立建表、独立错题闭环、
独立进度口径），入口 `/api/gx`（19 个端点）+ 前端 tab `gaoxiang`。
模块细节见 [docs/高项备考模块说明.md](docs/高项备考模块说明.md)。

| 项 | 说明 |
|---|---|
| 数据表 | `gx_knowledge` / `gx_questions` / `gx_attempts` / `gx_wrongs` / `gx_case_grades` / `gx_progress` / `gx_materials`（迁移 `081_gaoxiang.py` + `082_gx_materials.py`，幂等） |
| 出题策略 | **题库优先**：先在 SQL 层排除该用户已做过的落库题（`NOT EXISTS` 子查询），不足才 AI 补生成并落库 → 同一内容不重复扣费 |
| 判分 | **服务端判分**（答案存库、不下发前端），多选须全对；资料里没抓到参考答案的题 `judged=false`，不判错不入库 |
| 错题闭环 | 答错（或案例/论文批改 < 60 分）→ 入错题本 → AI 错因分析落 `wrong_reason` 缓存 → 错题重练（错得多的先练），重做连对 3 次自动掌握 |
| 案例 / 论文 | 资料真题可直接做；案例 AI 按要点批改，论文 AI 四维评分（切题 35 / 结构 25 / 实践 25 / 文字 15） |
| 真题导入 | **已实现**：本地 `tools/gx_pack.py` 解析资料 → 数据包，线上 `tools/import_gx_materials.py load` 幂等入库（步骤见 [§5.5](#55-高项备考资料导入可选一次性)） |
| **不挂宵禁** | 该模块**不挂** `check_quiet_hours` —— 面向成人，晚间备考是核心场景；宵禁只针对未成年人护眼 |
| 移动端 | TabBar 固定 6 项已满，入口仅桌面侧边栏「学习」组 |
| 计费 | AI 调用按 token 扣钻（`gx_knowledge`/`gx_quiz`/`gx_case`/`gx_essay`/`gx_wrong`），计费失败不阻断 |

> 铁律依旧：AI 调用一律在 DB 会话之外执行（`chat_with` 可能重试数秒），成功后才开短会话
> 落库/扣费；`/quiz/generate` 因需回读 AI 刚落库的新行，全程使用独立短会话
> （请求级会话在 REPEATABLE READ 下快照冻结，读不到新行）。

---

## 13. 项目结构

```
/home/PrimarySchoolExam/
├── app/                          # FastAPI 后端
│   ├── main.py                   # 应用工厂：九域路由注册 + dist 挂载 + lifespan
│   ├── config.py                 # 全局配置
│   ├── database.py               # SQLAlchemy 引擎 / 会话 / 迁移工具
│   ├── domains/                  # 九域架构（S1-R 拆分）
│   │   ├── identity/             # D1 身份（注册/登录/Token）
│   │   ├── engagement/           # D2 学习（任务/背诵/听写/补签卡）
│   │   ├── assessment/           # D3 测评（出卷/判分/错题/申诉）
│   │   ├── engine/               # D4 引擎（出题/数学生成）
│   │   ├── family/               # D5 家庭（家长管理/留言/周报）
│   │   ├── platform/             # D6 平台（AI 服务/配置）
│   │   ├── commerce/             # D7 商城（商品/订单/支付/履约）
│   │   ├── content/              # D8 内容（教材版本/区域）
│   │   └── frozen/               # D9 冻结（IM + 账本，配置可关闭）
│   ├── models/                   # 数据模型（46 文件 / 86 表）
│   ├── migrations/versions/      # 迁移脚本（65 个，001-065+）
│   ├── schemas/                  # Pydantic 请求/响应模型
│   └── data/                     # 种子 CSV（单词/词组/句子）
├── web/                          # 孩子端前端（Vue 3 + Vite + Pinia）
│   ├── src/
│   │   ├── views/                # 23 个视图组件
│   │   ├── components/           # 公共组件（AppIcon 等）
│   │   ├── logic/                # 业务逻辑（appOptions.js 等）
│   │   ├── nav.js                # 导航配置
│   │   └── styles/style.css      # 全局样式（设计 Token）
│   └── dist/                     # 构建产物（后端托管 /）
├── admin/                        # 管理后台前端（独立 Vite 工程）
│   └── dist/                     # 构建产物（后端托管 /admin）
├── tools/                        # 运维工具
│   ├── endpoint_snapshot.py      # 端点快照
│   ├── scheduler.py              # 定时任务（超时关单/会员降级）
│   └── verify_seed_products.py   # 种子商品校验
├── tests/                        # pytest 测试（268 用例 / 39 文件）
├── docs/                         # 文档
│   └── enterprise/               # 企业级方案（00-09 共 10 篇）
├── log/                          # 运行日志（gitignore）
├── output/                       # 生成文件（gitignore）
├── run.py                        # 启动入口
├── deploy.sh                     # 一键部署脚本
├── requirements.txt              # 生产依赖
├── requirements-dev.txt          # 开发依赖（测试）
├── .env.example                  # 环境变量模板
└── .importlinter                 # 域间依赖护栏
```

---

## 14. 常见问题

### 14.1 status=217/USER（CentOS）

CentOS 没有 `www-data` 用户：

```bash
sudo sed -i 's/User=www-data/User=nginx/' /etc/systemd/system/exam-app.service
sudo chown -R nginx:nginx /home/PrimarySchoolExam
sudo systemctl daemon-reload
sudo systemctl restart exam-app
```

### 14.2 前端构建 OOM

小内存服务器（< 2 GB）构建 admin/ 时可能 OOM：

```bash
# deploy.sh 已自动创建 2G swapfile，若仍不够：
export NODE_OPTIONS=--max-old-space-size=512
cd admin && npm run build
```

### 14.3 迁移执行失败

```bash
# 查看已应用的迁移
mysql -u root -p -e "SELECT * FROM schema_migrations ORDER BY version_num;" schoolexam

# 手动执行特定迁移（谨慎）
venv/bin/python -c "
from app.database import SessionLocal
from app.migrations.versions.XXX_XXX import upgrade
db = SessionLocal()
upgrade(db)
db.close()
"
```

### 14.4 健康检查失败 / 服务启动失败

```bash
# 查看详细日志
sudo journalctl -u exam-app -n 50

# 手动启动看报错
cd /home/PrimarySchoolExam
./venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000

# 常见原因：
# 1. .env 未配置或 MySQL 连接失败
# 2. 迁移执行失败
# 3. 端口被占用
```

**如果日志停在某个 `import` 行（看不到真正的异常）**：`journalctl -n 50` 会把真正的报错行截掉，
只剩一串 import 调用栈。用下面两条定位真凶，别靠猜：

```bash
# ① 只打印异常类型，一眼看到「缺什么包 / 什么语法错」
journalctl -u exam-app -n 200 --no-pager | grep -iE "ModuleNotFoundError|ImportError|SyntaxError"

# ② 直接复现导入错误（不启动服务，最快）
cd /home/PrimarySchoolExam && venv/bin/python -c "import app.main"
# 或直接跑部署自检，它会一次列全问题
venv/bin/python tools/preflight.py --stage full
```

> ⚠️ **`ModuleNotFoundError` 的典型成因（2026-09-24 全站 502 事故）**：
> 代码里加了新的第三方包依赖，但 `requirements.txt` 漏声明 ——
> **本地能 `import` 不代表线上有**（本地 venv 常因跑测试多装了包，如 httpx 是
> starlette TestClient 的依赖）。线上 `deploy.sh` 只按 `requirements.txt` 装包，
> 于是在应用导入期直接崩溃。**修法：把包补进 `requirements.txt` 后重新部署。**
> 提交前跑 `python tools/dep_audit.py` 或 `tools/regression_check.py` 就能提前拦住。

### 14.5 管理后台账号与密码

首次部署后管理员账号：`admin` / `Admin@123`（**改过密码后此默认值即失效**）

```bash
# 正常改密码（需要知道旧密码，走 API）
curl -X POST https://你的域名/api/admin/change-password \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"old_password":"旧密码","new_password":"新密码"}'
```

**忘记密码**（不需要旧密码，改用运维脚本）：

`tools/reset_admin_pwd.py` 直接改写 `admins.password_hash` 并清空 token 强制重新登录；
密码规则 4–32 位；账号不存在时按默认凭证创建（`role=super`）。

```bash
# 线上（必须在服务器上跑，本地没有线上库凭据）
cd /home/PrimarySchoolExam
venv/bin/python tools/reset_admin_pwd.py --password "新密码"
# 指定其它账号：--username ops

# 本地（改的是本地 .env 指向的克隆库）
.venv/Scripts/python.exe tools/reset_admin_pwd.py --password "新密码"
```

> ⚠️ 两个必知点：
> 1. **脚本改的是「它连接的那个库」**——在本地跑只改克隆库，线上照样登不上；
>    要让线上生效必须在服务器上执行（这也是为什么它不能做成 HTTP 接口）。
> 2. 脚本会清空 `admins.token`，**该账号现有后台会话立即失效**，需重新登录。

> `admins` 是**单槽 token**（每个账号只有一列 `token`，不是多会话表）：任何一次新登录都会顶掉
> 该账号此前的会话，表现为「A 登录后 B 被登出」。需要多人并行使用后台时，各自建账号。

### 14.6 线上库安全

> **铁律**：`.env` 中的 `DB_HOST=192.168.2.158`（或 SQLPub 等托管 MySQL）是**线上库的本地克隆**，禁止对其执行任何写操作。
> - 不跑迁移
> - 不灌种子
> - 不改数据
> - 同步工具（`tools/sync_prod_to_local.py`）对线上库只读 SELECT

---

## 15. 定时任务（调度器）运维

线上定时任务由**代码内置**的 `tools/scheduler.py` 承担（随 git 提交、随 deploy 上线），
crontab 每 15 分钟唤醒它一次，由它决定哪些任务到期该跑。

### 15.1 当前任务清单

| 任务名 | 时刻 | 作用 | 幂等性 |
|---|---|---|---|
| `close_expired_orders` | 00:15 | 超时订单自动关闭 | 只处理未关闭的 |
| `ledger_recurring_daily` | 01:00 | 账本周期交易自动执行（生成账单 + 联动余额） | `next_run` 推进到未来，重跑不重复出账 |
| `im_red_packet_expire` | 01:10 | 24h 未领完的红包剩余钻石退回发送者 | 状态置 `EXPIRED` 后不再命中 |
| `vip_expire_downgrade` | 02:00 | 会员到期降级 | 只处理已过期未降级的 |
| `push_daily_reminder` | **19:00** | 每日学习提醒推送（作业未完成 / 即将断签） | `dedup_key=study:{uid}:{date}` 当天只发一次 |

> ⚠️ `push_daily_reminder` **刻意不排凌晨 01:00**（与其它采集/汇总类不同）：
> 推送必须在用户活跃时段才有意义 —— 凌晨推等于不推，还会被系统通知折叠。
> 19:00 是学生做作业的高峰，提醒转化最好。该时刻与 `check_quiet_hours` 不冲突：
> 宵禁只拦答题类接口，推送走的是 OneSignal 对外 HTTP，不经过那些端点。

> 另有 2 个任务处于 `enabled=False` 停用状态（`seed_junior_grade7` / `backfill_paper_answers`），
> 保留配置便于随时恢复 —— 改回 `True` 即可，不必重写定义。

### 15.2 安装（每台服务器只需一次）

```bash
crontab -e
# 加入下面一行（注意用项目自己的 venv 解释器）
*/15 * * * * cd /home/PrimarySchoolExam && /home/PrimarySchoolExam/venv/bin/python tools/scheduler.py >> /var/log/scheduler.log 2>&1
```

确认已安装：

```bash
crontab -l | grep scheduler
tail -f /var/log/scheduler.log        # 每 15 分钟会有一行「调度检查完成」
```

### 15.3 状态与日志

| 文件 | 位置 | 说明 |
|---|---|---|
| 任务状态 | `tools/.scheduler_state.json` | 每个任务的 `last_run` / `run_count` / `last_status` / `last_output`（截断 500 字） |
| 单实例锁 | `tools/.scheduler.lock` | 防上一个长任务没跑完又被 cron 起一个 |
| 运行日志 | `/var/log/scheduler.log` | cron 重定向输出，含每个任务的返回码与完整输出 |

> 这两个运行时文件已在 `.gitignore` 中（勿提交 —— 提交会把线上运行状态污染进仓库）。

### 15.4 体检（最重要的一步）

调度任务是**静默执行**的，没有告警通道：任务失败的症状就是「什么都不发生」
（订单不关单、会员不降级、红包不退回），可以安静积累成业务数据错误。所以：

```bash
cd /home/PrimarySchoolExam

# 静态体检：任务配置 / 脚本存在性 / 脚本依赖 / 运行时文件
venv/bin/python tools/ops_check.py

# 追加线上状态体检：上次是否失败、是否已静默停摆、是否已过期/达上限
venv/bin/python tools/ops_check.py --state tools/.scheduler_state.json
```

状态体检能发现这些问题（都会以 warn 列出来）：

| 现象 | 含义 |
|---|---|
| `任务上次执行失败` | 附 `last_error`/`last_output` 摘要，去日志看完整堆栈 |
| `已超过 26 小时未成功执行` | 可能 crontab 被删、服务器时间错、或任务被静默停掉 |
| `已过有效期` | `valid_until` 到期，任务不再执行（需延长或清理定义） |
| `已达次数上限` | `run_count >= max_runs` |
| `残留调度状态` | 状态里有、JOBS 里已无同名任务（改过名/删过任务） |

`tools/ops_check.py` 也已接入另外两处，无需手动调用：
- **提交前**：`tools/regression_check.py`（第 7 项，有错即 FAIL）
- **部署时**：`tools/preflight.py`（部署闸门，作为 WARN 项打印 —— 它不影响站点可用性，故不阻断部署）

### 15.5 新增/修改任务的正确姿势

1. 在 `tools/scheduler.py` 的 `JOBS` 里追加定义（或改现有项）；
2. **跑 `python tools/ops_check.py`** —— 配置笔误、脚本不存在、忘记 `git add`、依赖未声明都会在这里报出来；
3. `git add`（新脚本必须提交，否则线上 `git pull` 拿不到）→ commit → push；
4. 服务器 `git pull && sudo bash deploy.sh`（部署时的 preflight 会再核一遍）。

### 15.6 已知陷阱（加固于 2026-09-24，勿回退）

- **配置写错不会告警**：`kind` 拼错 → 任务永不执行；`at`/`valid_from` 写错 → 历史上会抛
  `ValueError` 冒泡出 `run_due_jobs`，**整轮调度中断**，排在它之后的任务永久停摆。
  现在：`validate_job()` 静态校验 + `_job_due()` 不再抛异常 + 单任务异常就地隔离
  （坏任务只跳过自己，并在日志里醒目打印）。
- **`enabled` 必须写布尔值**：写字符串 `"False"` 时 `job.get("enabled") is False` 判定不成立
  → **停用失效、任务照跑**。校验器会拦。
- **`command` 用仓库内相对路径**：写绝对路径在换服务器/换部署目录后必失效。
- **状态文件损坏不致命**：会按空状态继续（当日 daily 任务可能重复执行一次，任务多为幂等），
  日志里会打印提示。
- **排查不到任务为什么不跑**：`ops_check.py --state` 先看状态，再看
  `grep -E "跳过|配置错误|fail" /var/log/scheduler.log`。

---

## 16. 消息推送（OneSignal）

浏览器 Web Push：用户授权后即可收到**学习提醒 / 私信离线提醒 / 公告 / 成绩**四类通知，
管理员可在后台群发。通道未配置时整体降级为「不发送」，前端也不加载 SDK，不影响任何既有功能。

### 16.1 上线三步

```bash
# ① 拉代码并重启（迁移 083 会自动建 3 张 push_* 表）
cd <部署目录> && git pull && sudo bash deploy.sh

# ② 重建前端（SettingsView 新增了推送设置卡片，不重建则不显示）
cd web && npm run build && cd ..
cd admin && npm run build && cd ..          # 后台新增「消息推送」页
sudo systemctl restart <APP_NAME>

# ③ 填 OneSignal 密钥（**推荐在后台填，不用改 .env 也不用重启**）
#    管理后台 → 系统配置 → 「消息推送」分组：
#      ONESIGNAL_APP_ID        = OneSignal App ID
#      ONESIGNAL_REST_API_KEY  = REST API Key（机密，展示时自动脱敏）
#      ONESIGNAL_SAFARI_WEB_ID = Safari Web ID（可空；不填则 Safari 收不到）
#      PUSH_ENABLED            = true
#    也可写进 .env（同名字段），后台值优先；写入后 60 秒内生效。
```

### 16.2 OneSignal 控制台需要做的配置

1. 创建 **Web** 类型的 App，站点域名填**主域名 `www.liusijin.com`**（OneSignal 用它作为
   `chrome_web_origin` 校验域名归属）。
   ⚠️ 它必须与**用户实际访问的域名**以及后端 `SITE_URL` **三者一致**：`www.liusijin.com`
   与 `liusijin.com` 是两个独立 origin，不一致会导致订阅失败、或通知点开落到另一个源
   （详见《推送通知(OneSignal)接入说明》§15）。
2. **Platform → Web → 配置 Service Worker**：路径保持默认的 `/OneSignalSDKWorker.js`。
   本项目的 worker 由后端根路径托管（见 16.3），**不需要**把文件放到网站根目录。
3. 若使用 Safari：填好 Safari Web ID（否则 Safari 用户订阅不上）。
4. 取 `App ID` 与 `REST API Key`（Settings → Keys & IDs）。

### 16.3 Service Worker 为什么由后端托管

部署形态是 nginx 把 `location /` **全量反代**给 FastAPI，`web/dist` 并没有作为静态目录
暴露出去（只单独挂了 `/assets`、`/qr`）。而 OneSignal 要求的 worker 必须能通过
`https://域名/OneSignalSDKWorker.js` 访问（Service Worker 的默认作用域 = 文件所在目录，
只有放在根路径才能覆盖全站）。因此后端专门加了这条路由：

| 位置 | 作用 |
|---|---|
| `web/public/OneSignalSDKWorker.js` | 源文件，Vite 构建时原样拷到 `dist/` |
| `app/main.py` 的 `GET /OneSignalSDKWorker.js` | 运行时托管：优先读 `dist/`，缺失时返回内联等价内容 |
| `ONESIGNAL_WORKER_FALLBACK`（`app/main.py`） | dist 未构建时的兜底副本，内容须与上面文件一致 |

该路由响应头带 `Service-Worker-Allowed: /` 与 `Cache-Control: no-store` ——
**no-store 是必须的**：OneSignal 官方要求 worker 不可长期缓存，否则 SDK 升级后
老客户端仍跑旧 worker，表现为「后端已更新、老用户收不到推送」，极难排查。

### 16.4 数据表（迁移 `083_push_onesignal.py`）

| 表 | 用途 | 关键点 |
|---|---|---|
| `push_subscriptions` | 每条订阅 = 一个浏览器/设备 | `subscription_id` 唯一；`external_id` 就是 `users.user_id`；`revoked_at` 非空表示已解绑 |
| `push_prefs` | 用户逐场景开关 + 免打扰时段 | 缺行 = 全部开启（注册时不写行） |
| `push_logs` | 发送审计 + 幂等去重 | `dedup_key` 唯一索引**可空**：即时推送写 NULL，只有定时/事件类才占用去重键 |

> ⚠️ `dedup_key` 必须可空：MySQL 唯一索引允许多个 NULL，但只允许一个空串。
> 若给 `DEFAULT ''`，第二条不参与去重的推送就会撞唯一键而发不出去（与 082 的 `fingerprint` 同坑）。

### 16.5 防打扰四道闸（改动发送逻辑前务必先读）

1. **设备开关**：浏览器未授权/用户关掉 → 根本没有订阅，OneSignal 收不到。
2. **场景偏好**：`push_prefs` 的四个开关，关掉的类别后端**不放行**（`_PREF_FIELD`）。
3. **免打扰时段**：用户自设静音窗口，跨零点区间反向判断（如 22:00–07:00）。
   注意这与平台的 `check_quiet_hours`（未成年人护眼宵禁，会拦截接口）**语义不同，刻意不复用**。
4. **每人每日上限** `DAILY_CAP=8`：仅自动事件受限；公告/群发（`announce`/`broadcast`）不占额度 ——
   否则一条公告就能把用户的额度吃光，后续真实提醒全被吞掉。

### 16.6 常见问题

| 现象 | 原因与处理 |
|---|---|
| **推送一直失败，想知道是配置错还是没人订阅** | 先跑只读探测：`venv/bin/python tools/onesignal_probe.py` —— 它直接列出 OneSignal 侧的订阅构成。**订阅里没有 Web 就是「没人订阅」**（别去改密钥）；HTTP 401 才是密钥/App 不匹配 |
| 用户点「发送测试推送」提示「没有找到有效订阅」 | 先确认 OneSignal 侧确实没有 Web 订阅（见上条）。若确无：用户未在浏览器弹窗中允许通知，或**授权时未登录**导致订阅绑不上账号（`externalId` 为空）。注意 **HTTP 下浏览器不提供通知 API**，必须 HTTPS（本地可用 `127.0.0.1`，代码已放开 `allowLocalhostAsSecureOrigin`） |
| 后台显示「通道未配置」 | `ONESIGNAL_APP_ID` / `ONESIGNAL_REST_API_KEY` 未填，或 `PUSH_ENABLED=false` |
| OneSignal 返回 401 | 密钥与 App ID 不属于同一个 OneSignal 应用（最常见），或密钥已轮换 |
| 200 但没有消息 id | 靶向受众里没有任何有效订阅 —— 定向与段推送**两条路径都已判定为失败**（`reason=no_subscription`），不会假报成功 |
| 结果=失败但「错误」列空白 | 2026-09-28 前段推送漏写原因的缺陷，已修；历史记录仍可能为空，可看 `push_logs.http_status`（200 = 无订阅者） |
| 换账号后旧账号仍收到推送 | 登出时 `pushTeardown()` 会 `OneSignal.logout()` + 调 `/api/push/unsubscribe`；若用户是直接关标签页，可让其在设置页手动关闭设备开关 |
| 部署后 `/OneSignalSDKWorker.js` 404 | nginx `location /` 未反代到后端，或漏了 16.3 的路由。`curl -s -D - -o /dev/null https://域名/OneSignalSDKWorker.js` 应返回 200 + `application/javascript`（用 GET 取头；`curl -I` 发 HEAD，路由只注册 GET 时会返回 405 而非 404，别被误导） |
| 手机端收不到 | iOS Safari 要求「添加到主屏幕」后才支持 Web Push；微信内置浏览器不支持，需引导用户用系统浏览器打开 |
