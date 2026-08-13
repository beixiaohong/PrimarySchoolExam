# 智学学堂（PrimarySchoolExam）· 服务器部署指南

## 环境要求

- CentOS 7+ / Ubuntu 20.04+
- Python 3.12+
- Nginx
- 域名（HTTPS 需要）

## 一、上传项目

```bash
scp -r ./PrimarySchoolExam root@服务器IP:/home/PrimarySchoolExam
```

## 二、一键部署

```bash
cd /home/PrimarySchoolExam
sudo bash deploy.sh
```

脚本自动完成：创建虚拟环境 → 安装依赖 → 构建孩子端前端（web/dist，Vite + Vue 3）→ 构建管理后台前端（admin/dist）→ 配置 systemd（自动注入 `.env` 环境变量）→ 配置 nginx → 启动服务 → `/health` 健康自检（失败即报错退出）。无 Node 时 web/admin 构建均跳过（启动后 `/` 或 `/admin` 会返回「前端未构建」提示）。

> 部署前请先创建 `.env`（参考 `.env.example`：MySQL 连接、AI API key、邮件配置等），否则应用将使用默认 MySQL 连接（127.0.0.1:3306）与内置配置。

### 常见问题：status=217/USER

CentOS 没有 `www-data` 用户，需要改为 `nginx`：

```bash
sed -i 's/User=www-data/User=nginx/' /etc/systemd/system/exam-app.service
chown -R nginx:nginx /home/PrimarySchoolExam
systemctl daemon-reload
systemctl restart exam-app
```

## 三、配置 HTTPS（Let's Encrypt 免费证书）

前提：域名 A 记录已解析到服务器公网 IP。

```bash
# 安装 certbot
yum install -y certbot python3-certbot-nginx    # CentOS
# apt install -y certbot python3-certbot-nginx  # Ubuntu

# 先确保 nginx 配置中 server_name 是你的域名
sed -i 's/server_name _;/server_name www.你的域名.com;/' /etc/nginx/conf.d/exam-app.conf
nginx -t && systemctl reload nginx

# 签发证书并自动配置 nginx
certbot --nginx -d www.你的域名.com

# 如果提示 "Could not install certificate"，手动安装：
certbot install --cert-name www.你的域名.com
```

证书 90 天自动续期，验证：

```bash
certbot renew --dry-run
```

## 四、防火墙 / 安全组

确保放行 80 和 443 端口：

```bash
# CentOS firewalld
firewall-cmd --permanent --add-port=80/tcp
firewall-cmd --permanent --add-port=443/tcp
firewall-cmd --reload

# Ubuntu ufw
ufw allow 80/tcp
ufw allow 443/tcp
```

阿里云 ECS 还需在控制台 → 安全组 → 入方向添加 80/tcp 和 443/tcp。

## 五、常用运维命令

```bash
# 查看应用状态
systemctl status exam-app

# 查看实时日志
journalctl -u exam-app -f

# 重启应用
systemctl restart exam-app

# 重启 nginx
systemctl restart nginx

# 查看端口占用
ss -tlnp | grep -E ':80|:443|:8000'
```

## 六、更新代码

```bash
cd /home/PrimarySchoolExam
git pull
# 孩子端前端（web/）有改动时需重新构建
cd web && npm ci && npm run build && cd ..
# 管理后台前端（admin/）有改动时也需重新构建（/admin 托管 admin/dist）
cd admin && npm ci && npm run build && cd ..
systemctl restart exam-app
```

> 简化：直接 `sudo bash deploy.sh` 会**每次都重新构建 web 与 admin 两个前端**，无需手动逐条 build（见第二章）。

## 七、工程化前端（web/，Vite + Vue 3 + Pinia）

孩子端新前端位于 `web/`（Vite + Vue 3 + Pinia），构建产物 `web/dist` 由后端直接托管：
存在时访问 `/` 托管新前端；若不存在，应用返回 404 JSON 提示「前端未构建，请先 `npm run build`」。

```bash
# 服务器需 Node.js 18+（仅构建时需要）
cd /home/PrimarySchoolExam/web
npm install
npm run build        # 产物输出到 web/dist
systemctl restart exam-app
```

本地开发联调（热更新 + /api 代理到 8000）：

```bash
cd web
npm run dev          # http://localhost:5173
```

## 七·五、管理后台前端（admin/，Vite 独立工程）

管理后台是**独立的 Vite 工程** `admin/`，构建产物 `admin/dist` 由后端托管在 `/admin`：

- 访问入口：`http://<域名>/admin`（Vue Router 使用 hash 模式，路由形如 `/admin#/users`，无需服务端 SPA 回退）。
- 构建（服务器需 Node.js 18+）：

```bash
cd /home/PrimarySchoolExam/admin
npm ci
npm run build        # 产物输出到 admin/dist
systemctl restart exam-app
```

- 若 `admin/dist` 不存在，访问 `/admin` 会返回提示「管理后台未托管，请先 `cd admin && npm ci && npm run build`」。
- 管理接口本身（`/api/admin/*`）由后端 `admin.router` 提供，使用独立的 `_require_admin` 管理员鉴权（默认账号见部署脚本末尾提示）。
- 本地开发联调：`cd admin && npm run dev`（Vite 默认 5173 端口，自带 /api 代理）。

## 八、自动化测试（pytest）

API 回归测试位于 `tests/`，使用独立 MySQL 测试库（`DB_NAME` + `_test`，与线上库隔离），不依赖外部服务（AI 判题与邮件发送均已打桩），不污染真实数据库。

```bash
# 安装开发依赖（不影响生产 requirements.txt）
pip install -r requirements-dev.txt

# 运行全部测试
python -m pytest tests -q
```

覆盖范围：系统冒烟（/health）、注册/昵称登录/验证码、家长密码守卫（X-Parent-Pwd）、任务配置读写、试卷生成/交卷判分/错题本、管理后台登录与接口。AI 相关接口依赖外部 API key，不纳入自动化测试。

## 九、项目结构

```
/home/PrimarySchoolExam/
├── app/                      # FastAPI 后端（31 个路由模块）
│   ├── main.py               # 应用工厂：注册 31 个路由、lifespan 启动
│   ├── config.py             # 全局配置（DB_DRIVER、AI Key、输出目录等）
│   ├── database.py           # SQLAlchemy 引擎 / 会话 / Base / init_db
│   ├── models/               # 数据模型（User / Word / Exam / Classical …）
│   ├── schemas/              # Pydantic 请求 / 响应模型
│   ├── routers/              # API 路由（31 个文件）
│   ├── services/             # 业务逻辑（出题 / 生成 docx / AI 路由 …）
│   ├── migrations/           # 数据库迁移系统（40 个版本脚本，MySQL-only）
│   └── data/                 # 种子 CSV（小学/初中单词、词组、句子）
├── web/                      # 孩子端生产前端（Vue 3 + Vite + Pinia），产物 web/dist 由后端托管
├── admin/                    # 管理后台生产前端（独立 Vite 工程），产物 admin/dist 由后端托管在 /admin
├── tools/                    # 运维 / 迁移 / 题库发布工具（qb_release 等）
├── tests/                    # pytest 回归套件（58 用例 / 9 文件）
├── output/                   # 生成文件（docx / figures / audio，gitignore）
├── run.py                    # 启动入口
├── deploy.sh                 # 一键部署脚本
├── requirements.txt          # 生产依赖
├── requirements-dev.txt      # 开发依赖（测试）
├── .env.example              # 环境变量模板
└── docs/ROADMAP.md           # 产品优化落地路线
```

## 十、访问地址

部署完成后浏览器访问：`https://www.你的域名.com`
