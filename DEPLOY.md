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

    # 主应用（孩子端 + API）
    location / {
        proxy_pass http://127.0.0.1:8000;
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

deploy.sh 会自动判断前端是否需要重建（基于源码 mtime 对比）。

### 11.3 回滚

```bash
cd /home/PrimarySchoolExam
git log --oneline -10   # 找到要回退的 commit
git reset --hard <commit_hash>
sudo systemctl restart exam-app
```

> 迁移只向前执行，不会自动回滚。如需回滚数据库，需手动恢复备份。

---

## 12. 自动化测试

### 12.1 运行测试

```bash
cd /home/PrimarySchoolExam
# 安装开发依赖
venv/bin/pip install -r requirements-dev.txt

# 运行全部测试（268 用例 / 39 文件）
venv/bin/python -m pytest tests -q

# 运行特定测试文件
venv/bin/python -m pytest tests/test_ai_vip.py -v
venv/bin/python -m pytest tests/test_s4_fulfillment.py -v
```

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

### 14.4 健康检查失败

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

### 14.5 管理后台默认密码

首次部署后管理员账号：`admin` / `Admin@123`

```bash
# 修改密码（通过 API）
curl -X POST https://你的域名/api/admin/change-password \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"old_password":"Admin@123","new_password":"新密码"}'
```

### 14.6 线上库安全

> **铁律**：`.env` 中的 `DB_HOST=192.168.2.158`（或 SQLPub 等托管 MySQL）是**线上库的本地克隆**，禁止对其执行任何写操作。
> - 不跑迁移
> - 不灌种子
> - 不改数据
> - 同步工具（`tools/sync_prod_to_local.py`）对线上库只读 SELECT
