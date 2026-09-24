#!/bin/bash
#============================================================
# 小学试卷系统 - 一键部署脚本 (支持 HTTPS)
# 用法: sudo bash deploy.sh
# 适用: Ubuntu 20.04+ / Debian 11+ / CentOS 7+
# 域名: liusijin.com / www.liusijin.com
# 证书: /etc/letsencrypt/live/www.liusijin.com/
#============================================================

set -e

# ---------- 配置区（按需修改） ----------
APP_NAME="exam-app"
APP_DIR="/home/PrimarySchoolExam"
APP_PORT=8000
NGINX_PORT=80
DOMAIN="liusijin.com"          # 主域名
DOMAIN_WWW="www.liusijin.com"  # www 域名

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

# 服务启动失败时的回滚指引（自检已尽力拦截，但运行期问题仍可能发生，如数据库不可达）
rollback_hint() {
    echo -e "${YELLOW}[提示]${NC} 站点当前可能不可用，回滚步骤："
    echo "      cd ${APP_DIR} && git log --oneline -5        # 找到上一个正常版本"
    echo "      git reset --hard <正常版本的 commit>"
    echo "      sudo bash deploy.sh                          # 重新部署旧版本"
}

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

# ---------- 3.5 检查 .env ----------
if [ ! -f "$APP_DIR/.env" ]; then
    warn "未找到 $APP_DIR/.env，请先创建（参考 .env.example）"
fi

# ---------- 3.55 前置自检（early）：依赖完整性 + 应用可导入 + .env 必需键 ----------
# 为什么必须在**重启之前**查：原先的顺序是「重启服务 → 查进程/健康」，检查发生在重启之后，
# 一旦新版本有问题，坏版本已经被换上，systemd（Restart=always）反复崩溃重启 → 全站 502，
# 而 deploy.sh 虽然报错退出，站点却已经挂了、旧版本进程也没了。
# （2026-09-24 真实事故：requirements.txt 漏声明 httpx，线上 uvicorn 导入期即崩。）
# 放在前端构建之前，避免发现问题时已白跑几分钟 npm build。
if [ -f "$APP_DIR/tools/preflight.py" ]; then
    info "前置自检(early)：依赖 / 应用可导入 / 环境变量..."
    "$APP_DIR/venv/bin/python" "$APP_DIR/tools/preflight.py" \
        --app-dir "$APP_DIR" --python "$APP_DIR/venv/bin/python" \
        --app-user "$APP_USER" --stage early \
        || error "前置自检未通过 → 已中止部署。旧版本服务未受影响（站点保持可用），
    修好上面列出的问题后重新执行 deploy.sh"
else
    warn "未找到 tools/preflight.py，跳过前置自检（建议补齐以启用部署前校验）"
fi

# ---------- 3.6 构建前端（仅源码变化时重建；小内存服务器防 OOM/CPU 拖垮）----------
# 前端构建（vite build，admin 含 element-plus/echarts）在小内存服务器上容易把
# CPU/内存打满导致全站无响应。策略：
#   1) 判断重建：优先**源码内容指纹**（tools/build_info.py，见 frontend_needs_build），
#      判据不可用时退化为 mtime；源码没变时直接复用现有 dist，秒级完成；
#   2) 构建时 nice 降优先级 + 限制 Node 堆内存，避免拖垮 MySQL/Nginx；
#   3) 无 swap 时自动补 2G swapfile 兜底防 OOM。
frontend_needs_build() {
    local dir=$1
    [ -f "$dir/dist/index.html" ] || return 0  # 尚无产物 → 需要构建
    # 首选**源码内容指纹**判据（tools/build_info.py）：
    # 下面的 mtime 判据只看 src/、package.json、vite.config.js，会漏掉
    # index.html / novel.html / public/ 的改动，也看不出"源文件被删除"，
    # 漏判的后果是线上静默沿用旧 dist（界面与代码不一致，却毫无提示）。
    # 退出码约定：0=需要构建，1=无需构建；返回其它码按"需要构建"处理 ——
    # 多构建一次只是慢几分钟，漏构建却会一直没人发现。
    if [ -x "$APP_DIR/venv/bin/python" ] && [ -f "$APP_DIR/tools/build_info.py" ]; then
        local rc=0
        "$APP_DIR/venv/bin/python" "$APP_DIR/tools/build_info.py" needs-build --dir "$dir" \
            >/dev/null 2>&1 || rc=$?
        case $rc in
            0) return 0 ;;   # 需要构建
            1) return 1 ;;   # 无需构建
            *) warn "构建判据异常（build_info.py 退出码 $rc），按需要构建处理" ; return 0 ;;
        esac
    fi
    # 兜底：无 build_info.py（旧版本代码）时沿用 mtime 判据
    find "$dir/src" "$dir/package.json" "$dir/vite.config.js" \
         -newer "$dir/dist/index.html" 2>/dev/null | grep -q .
    return $?
}

# swap 兜底（仅首次创建一次；失败不影响部署）
if [ ! -f /swapfile ] && command -v fallocate &>/dev/null; then
    info "创建 2G swapfile 防编译 OOM..."
    fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile \
        || warn "swapfile 创建失败（忽略，继续部署）"
    grep -q '^/swapfile' /etc/fstab 2>/dev/null || echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi

if command -v npm &>/dev/null && [ -f "$APP_DIR/web/package.json" ]; then
    if frontend_needs_build "$APP_DIR/web"; then
        info "web 前端源码有变化，开始构建..."
        (cd "$APP_DIR/web" && export NODE_OPTIONS=--max-old-space-size=1024 && \
         nice -n 10 npm ci --prefer-offline --no-audit --no-fund && nice -n 10 npm run build) \
            && info "web 前端构建完成" \
            || error "web 前端构建失败：请检查 Node 版本(需 18+)"
        # 记录构建溯源：源码指纹 + 产物引用的 API 路径。
        # 部署前的 preflight 会据此确认「这份 dist 就是当前源码构建的」，
        # 并把产物里引用的 /api/... 与后端路由表比对（抓"接口改名漏改前端"）。
        if [ -f "$APP_DIR/tools/build_info.py" ]; then
            "$APP_DIR/venv/bin/python" "$APP_DIR/tools/build_info.py" write --dir "$APP_DIR/web" \
                || warn "web 构建信息写入失败（不影响部署；preflight 将跳过该产物的配对校验）"
        fi
        chown -R "$APP_USER:$APP_USER" "$APP_DIR/web/dist" 2>/dev/null || true
    else
        info "web 前端无源码变化，跳过构建（复用现有 dist）"
    fi
else
    error "未安装 Node.js/npm 或缺少 web/package.json"
fi

# ---------- 3.7 构建管理后台（仅源码变化时重建；内存受限 + 低优先级）----------
if ! command -v npm &>/dev/null; then
    error "未检测到 Node.js/npm"
fi
if [ ! -f "$APP_DIR/admin/package.json" ]; then
    error "缺少 $APP_DIR/admin/package.json"
fi
# 管理后台 element-plus/echarts 编译内存占用高：限制堆内存 + nice 降优先级，
# 小内存服务器用上方 swap 兜底，避免 OOM / CPU 跑满拖垮全站。
if frontend_needs_build "$APP_DIR/admin"; then
    info "admin 前端源码有变化，开始构建..."
    (cd "$APP_DIR/admin" && export NODE_OPTIONS=--max-old-space-size=1024 && \
     nice -n 10 npm ci --prefer-offline --no-audit --no-fund && nice -n 10 npm run build) \
        && info "管理后台构建完成" \
        || error "管理后台构建失败"
    if [ ! -f "$APP_DIR/admin/dist/index.html" ]; then
        error "管理后台构建产物缺失"
    fi
    # 同 web：记录构建溯源，供 preflight 校验产物与后端契约是否配对
    if [ -f "$APP_DIR/tools/build_info.py" ]; then
        "$APP_DIR/venv/bin/python" "$APP_DIR/tools/build_info.py" write --dir "$APP_DIR/admin" \
            || warn "管理后台构建信息写入失败（不影响部署；preflight 将跳过该产物的配对校验）"
    fi
    chown -R "$APP_USER:$APP_USER" "$APP_DIR/admin/dist" 2>/dev/null || true
else
    info "admin 前端无源码变化，跳过构建（复用现有 dist）"
fi

# ---------- 3.8 前置自检（full）：外部命令 + 前端产物 ----------
# 放在写 systemd/nginx 配置与重启服务之前 —— 让所有"有副作用的动作"都发生在闸门之后：
# 自检不过就彻底没碰过服务配置，站点保持旧版本正常运行。
if [ -f "$APP_DIR/tools/preflight.py" ]; then
    info "前置自检(full)：外部命令 / 前端产物..."
    "$APP_DIR/venv/bin/python" "$APP_DIR/tools/preflight.py" \
        --app-dir "$APP_DIR" --python "$APP_DIR/venv/bin/python" \
        --app-user "$APP_USER" --stage full \
        || error "前置自检未通过 → 已中止部署（未改服务配置、未重启，旧版本继续运行）"
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

# ---------- 5. 配置 Nginx (支持 HTTPS) ----------
info "配置 Nginx (HTTP 80 + HTTPS 443)..."

NGINX_CONF="/etc/nginx/sites-available/${APP_NAME}"
NGINX_LINK="/etc/nginx/sites-enabled/${APP_NAME}"

# CentOS 没有 sites-available 目录，用 conf.d
if [ ! -d "/etc/nginx/sites-available" ]; then
    NGINX_CONF="/etc/nginx/conf.d/${APP_NAME}.conf"
    NGINX_LINK=""
fi

cat > "$NGINX_CONF" <<EOF
# HTTPS 服务器配置（443 端口）
server {
    listen 443 ssl http2;
    server_name ${DOMAIN} ${DOMAIN_WWW};

    ssl_certificate /etc/letsencrypt/live/${DOMAIN_WWW}/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/${DOMAIN_WWW}/privkey.pem;

    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-RSA-AES256-GCM-SHA512:DHE-RSA-AES256-GCM-SHA512:ECDHE-RSA-AES256-GCM-SHA384:DHE-RSA-AES256-GCM-SHA384;
    ssl_prefer_server_ciphers off;

    client_max_body_size 50m;

    location / {
        proxy_pass http://127.0.0.1:${APP_PORT};
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_read_timeout 120s;
    }

    location /output/ {
        alias ${APP_DIR}/output/;
        expires 7d;
    }
}

# HTTP 跳转配置（80 端口）
server {
    listen 80;
    server_name ${DOMAIN} ${DOMAIN_WWW};
    return 301 https://\$server_name\$request_uri;
}
EOF

if [ -n "$NGINX_LINK" ]; then
    ln -sf "$NGINX_CONF" "$NGINX_LINK"
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
    echo -e "${RED}[ERROR]${NC} 应用启动失败，查看日志: journalctl -u ${APP_NAME} -n 50"
    rollback_hint
    exit 1
fi

# 健康检查
if command -v curl &>/dev/null; then
    if curl -fsS "http://127.0.0.1:${APP_PORT}/health" >/dev/null 2>&1; then
        info "健康检查通过 (/health)"
    else
        echo -e "${RED}[ERROR]${NC} 健康检查失败，查看日志: journalctl -u ${APP_NAME} -n 50"
        rollback_hint
        exit 1
    fi
fi

info "启动 Nginx..."
systemctl enable nginx
systemctl restart nginx

if systemctl is-active --quiet nginx; then
    info "Nginx 运行正常 (HTTP 80, HTTPS 443)"
else
    error "Nginx 启动失败，查看日志: journalctl -u nginx -n 50"
fi

# ---------- 7. 防火墙放行 HTTP 和 HTTPS ----------
if command -v ufw &>/dev/null; then
    ufw allow 80/tcp >/dev/null 2>&1
    ufw allow 443/tcp >/dev/null 2>&1
    info "UFW 已放行端口 80 和 443"
elif command -v firewall-cmd &>/dev/null; then
    firewall-cmd --permanent --add-port=80/tcp >/dev/null 2>&1
    firewall-cmd --permanent --add-port=443/tcp >/dev/null 2>&1
    firewall-cmd --reload >/dev/null 2>&1
    info "Firewalld 已放行端口 80 和 443"
fi

# ---------- 完成 ----------
echo ""
echo "=========================================="
echo -e "${GREEN} 部署完成！${NC}"
echo "=========================================="
echo ""
echo "  访问地址:  https://${DOMAIN}  /  https://${DOMAIN_WWW}"
echo "  管理后台:  https://${DOMAIN}/admin   （默认管理员 admin / Admin@123）"
echo "  应用端口:  ${APP_PORT} (内部)"
echo "  HTTP端口:  80 (自动跳转 HTTPS)"
echo "  HTTPS端口: 443 (加密传输)"
echo ""
echo "  常用命令:"
echo "    查看状态:  systemctl status ${APP_NAME}"
echo "    查看日志:  journalctl -u ${APP_NAME} -f"
echo "    重启应用:  systemctl restart ${APP_NAME}"
echo "    重启Nginx: systemctl restart nginx"
echo ""
echo "  更新代码后运行:"
echo "    cd ${APP_DIR} && git pull && sudo bash deploy.sh"
echo ""
echo "  部署前自检（可单独运行，重启前验证新版本能否跑起来）:"
echo "    ${APP_DIR}/venv/bin/python ${APP_DIR}/tools/preflight.py --stage full"
echo ""
echo "  前端产物与后端契约核对（dist 是否对应当前源码 / 接口是否已改名）:"
echo "    ${APP_DIR}/venv/bin/python ${APP_DIR}/tools/build_info.py check --dir ${APP_DIR}/web"
echo ""
echo "  部署失败需回滚:"
echo "    cd ${APP_DIR} && git log --oneline -5"
echo "    git reset --hard <上一个正常版本的 commit> && sudo bash deploy.sh"
echo ""
echo "  证书自动续期 (Let's Encrypt):"
echo "    certbot renew --dry-run  # 测试续期"
echo "=========================================="