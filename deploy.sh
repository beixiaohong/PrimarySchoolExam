#!/bin/bash
#============================================================
# 小学试卷系统 - 一键部署脚本
# 用法: sudo bash deploy.sh
# 适用: Ubuntu 20.04+ / Debian 11+ / CentOS 7+
#============================================================

set -e

# ---------- 配置区（按需修改） ----------
APP_NAME="exam-app"
APP_DIR="/home/PrimarySchoolExam"
APP_PORT=8000
NGINX_PORT=80
DOMAIN="_"   # 有域名改成你的域名，没有就保持 _ 表示所有

# 自动检测 web 用户（CentOS=nginx, Ubuntu=www-data）
if id "www-data" &>/dev/null; then
    APP_USER="www-data"
elif id "nginx" &>/dev/null; then
    APP_USER="nginx"
else
    APP_USER="root"
fi
# ----------------------------------------

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

info()  { echo -e "${GREEN}[INFO]${NC} $1"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

# 检查 root
if [ "$EUID" -ne 0 ]; then
    error "请使用 sudo 运行: sudo bash deploy.sh"
fi

# 检查项目目录
if [ ! -f "$APP_DIR/app/main.py" ]; then
    error "未找到 $APP_DIR/app/main.py，请先把项目上传到 $APP_DIR"
fi

info "===== 开始部署 ====="

# ---------- 1. 安装系统依赖 ----------
info "安装系统依赖..."
if command -v apt-get &>/dev/null; then
    apt-get update -qq
    apt-get install -y -qq python3 python3-venv python3-pip nginx >/dev/null 2>&1
elif command -v yum &>/dev/null; then
    yum install -y -q python3 python3-pip nginx >/dev/null 2>&1
else
    warn "未识别的包管理器，请手动安装 python3、nginx"
fi

# ---------- 2. 创建虚拟环境 ----------
info "创建 Python 虚拟环境..."
if [ ! -d "$APP_DIR/venv" ]; then
    python3 -m venv "$APP_DIR/venv"
fi
"$APP_DIR/venv/bin/pip" install --upgrade pip -q
"$APP_DIR/venv/bin/pip" install -r "$APP_DIR/requirements.txt" -q
info "依赖安装完成"

# ---------- 3. 创建数据目录 ----------
mkdir -p "$APP_DIR/data"
mkdir -p "$APP_DIR/output"
chown -R "$APP_USER:$APP_USER" "$APP_DIR" 2>/dev/null || true

# ---------- 3.5 检查 .env（MySQL 连接 / AI key / 邮件等由它注入） ----------
if [ ! -f "$APP_DIR/.env" ]; then
    warn "未找到 $APP_DIR/.env，请先创建（参考 .env.example：MySQL 连接 / AI_API_KEY / 邮件配置等）"
fi

# ---------- 3.6 构建前端（web/dist） ----------
# 重要：前端改动（App.vue / appOptions.js / style.css 等）只有在「重新构建」后才会生效。
# 因此每次部署都重新构建，不因为 web/dist 已存在而跳过——
# 否则拉取新代码后再跑本脚本，仍会服务旧的构建产物（界面不更新，如首页三块、兑换券输入框等）。
info "构建前端（npm ci + vite build）..."
if command -v npm &>/dev/null && [ -f "$APP_DIR/web/package.json" ]; then
    (cd "$APP_DIR/web" && npm ci --no-audit --no-fund && npm run build) \
        && info "前端构建完成" \
        || error "前端构建失败：请检查 Node 版本(需 18+) 与 web/package.json，构建未成功将导致前端不可用"
    chown -R "$APP_USER:$APP_USER" "$APP_DIR/web/dist" 2>/dev/null || true
else
    error "未安装 Node.js/npm 或缺少 web/package.json：无法构建前端。请先安装 Node 18+ 后重试。"
fi

# ---------- 3.7 构建管理后台前端（admin/dist） ----------
# 管理后台为独立 Vite 工程，构建产物 admin/dist 由后端在 /admin 托管（见 app/main.py）。
info "构建管理后台前端（npm ci + vite build）..."
if command -v npm &>/dev/null && [ -f "$APP_DIR/admin/package.json" ]; then
    (cd "$APP_DIR/admin" && npm ci --no-audit --no-fund && npm run build) \
        && info "管理后台构建完成" \
        || error "管理后台构建失败：请检查 Node 版本(需 18+) 与 admin/package.json"
    chown -R "$APP_USER:$APP_USER" "$APP_DIR/admin/dist" 2>/dev/null || true
else
    warn "未安装 Node.js/npm 或缺少 admin/package.json：跳过管理后台构建（/admin 将不可用）。"
fi

# ---------- 4. 配置 systemd 服务 ----------
info "配置 systemd 服务..."
cat > /etc/systemd/system/${APP_NAME}.service <<EOF
[Unit]
Description=Primary School Exam System
After=network.target

[Service]
Type=simple
User=${APP_USER}
WorkingDirectory=${APP_DIR}
ExecStart=${APP_DIR}/venv/bin/uvicorn app.main:app --host 127.0.0.1 --port ${APP_PORT} --workers 2
Restart=always
RestartSec=3
Environment=PYTHONUNBUFFERED=1
EnvironmentFile=-${APP_DIR}/.env

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable ${APP_NAME}
info "systemd 服务已配置并设为开机自启"

# ---------- 5. 配置 Nginx 反向代理 ----------
info "配置 Nginx (端口 ${NGINX_PORT})..."

NGINX_CONF="/etc/nginx/sites-available/${APP_NAME}"
NGINX_LINK="/etc/nginx/sites-enabled/${APP_NAME}"

# CentOS 没有 sites-available 目录，用 conf.d
if [ ! -d "/etc/nginx/sites-available" ]; then
    NGINX_CONF="/etc/nginx/conf.d/${APP_NAME}.conf"
    NGINX_LINK=""
fi

cat > "$NGINX_CONF" <<EOF
server {
    listen ${NGINX_PORT};
    server_name ${DOMAIN};

    client_max_body_size 50m;

    location / {
        proxy_pass http://127.0.0.1:${APP_PORT};
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_read_timeout 120s;
    }

    # 静态文件直接由 nginx 处理（可选优化）
    location /output/ {
        alias ${APP_DIR}/output/;
        expires 7d;
    }
}
EOF

if [ -n "$NGINX_LINK" ]; then
    ln -sf "$NGINX_CONF" "$NGINX_LINK"
    # 移除默认站点避免冲突
    rm -f /etc/nginx/sites-enabled/default
fi

nginx -t || error "Nginx 配置检测失败，请检查 $NGINX_CONF"
info "Nginx 配置完成"

# ---------- 6. 启动服务 ----------
info "启动应用服务..."
systemctl restart ${APP_NAME}
sleep 2

if systemctl is-active --quiet ${APP_NAME}; then
    info "应用服务运行正常 (端口 ${APP_PORT})"
else
    error "应用启动失败，查看日志: journalctl -u ${APP_NAME} -n 50"
fi

# 健康检查自检
if command -v curl &>/dev/null; then
    if curl -fsS "http://127.0.0.1:${APP_PORT}/health" >/dev/null 2>&1; then
        info "健康检查通过 (/health)"
    else
        error "健康检查失败: curl http://127.0.0.1:${APP_PORT}/health，查看日志: journalctl -u ${APP_NAME} -n 50"
    fi
fi

info "启动 Nginx..."
systemctl enable nginx
systemctl restart nginx

if systemctl is-active --quiet nginx; then
    info "Nginx 运行正常 (端口 ${NGINX_PORT})"
else
    error "Nginx 启动失败，查看日志: journalctl -u nginx -n 50"
fi

# ---------- 7. 防火墙放行 ----------
if command -v ufw &>/dev/null; then
    ufw allow ${NGINX_PORT}/tcp >/dev/null 2>&1
    info "UFW 已放行端口 ${NGINX_PORT}"
elif command -v firewall-cmd &>/dev/null; then
    firewall-cmd --permanent --add-port=${NGINX_PORT}/tcp >/dev/null 2>&1
    firewall-cmd --reload >/dev/null 2>&1
    info "Firewalld 已放行端口 ${NGINX_PORT}"
fi

# ---------- 完成 ----------
echo ""
echo "=========================================="
echo -e "${GREEN} 部署完成！${NC}"
echo "=========================================="
echo ""
echo "  访问地址:  http://<服务器IP>"
echo "  管理后台:  http://<服务器IP>/admin   （默认管理员 admin / Admin@123，请尽快修改密码）"
echo "  应用端口:  ${APP_PORT} (内部)"
echo "  Nginx端口: ${NGINX_PORT} (对外)"
echo ""
echo "  常用命令:"
echo "    查看状态:  systemctl status ${APP_NAME}"
echo "    查看日志:  journalctl -u ${APP_NAME} -f"
echo "    重启应用:  systemctl restart ${APP_NAME}"
echo "    重启Nginx: systemctl restart nginx"
echo ""
echo "  更新代码后（deploy.sh 已改为每次重新构建前端，无需手动 build）:"
echo "    cd ${APP_DIR} && git pull && sudo bash deploy.sh"
echo "    # 若只改了前端且已 pull，也可仅："
echo "    cd web && npm ci && npm run build && systemctl restart ${APP_NAME}"
echo "    # 若只改了管理后台："
echo "    cd admin && npm ci && npm run build && systemctl restart ${APP_NAME}"
echo ""
echo "  运行自动化测试（需先 pip install -r requirements-dev.txt）:"
echo "    ${APP_DIR}/venv/bin/python -m pytest tests -q"
echo ""
