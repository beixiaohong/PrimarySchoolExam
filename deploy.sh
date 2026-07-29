#!/bin/bash
#============================================================
# 小学试卷系统 - 一键部署脚本
# 用法: sudo bash deploy.sh
# 适用: Ubuntu 20.04+ / Debian 11+ / CentOS 7+
#============================================================

set -e

# ---------- 配置区（按需修改） ----------
APP_NAME="exam-app"
APP_DIR="/opt/PrimarySchoolExam"
APP_USER="www-data"
APP_PORT=8000
NGINX_PORT=80
DOMAIN="_"   # 有域名改成你的域名，没有就保持 _ 表示所有
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
echo "  应用端口:  ${APP_PORT} (内部)"
echo "  Nginx端口: ${NGINX_PORT} (对外)"
echo ""
echo "  常用命令:"
echo "    查看状态:  systemctl status ${APP_NAME}"
echo "    查看日志:  journalctl -u ${APP_NAME} -f"
echo "    重启应用:  systemctl restart ${APP_NAME}"
echo "    重启Nginx: systemctl restart nginx"
echo ""
echo "  更新代码后:"
echo "    cd ${APP_DIR} && git pull"
echo "    systemctl restart ${APP_NAME}"
echo ""
