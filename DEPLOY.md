# 小学试卷系统 - 服务器部署指南

## 环境要求

- CentOS 7+ / Ubuntu 20.04+
- Python 3.8+
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

脚本自动完成：创建虚拟环境 → 安装依赖 → 配置 systemd → 配置 nginx → 启动服务。

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
systemctl restart exam-app
```

## 七、P5 工程化前端（web/）

孩子端新前端位于 `web/`（Vite + Vue 3 + Pinia），构建产物 `web/dist` 由后端直接托管：
存在时访问 `/` 自动使用新前端，不存在时回退旧版 `frontend/`。

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

管理后台前端为 `frontend-admin/`（独立工程，/admin 访问），无需构建。

## 八、项目结构

```
/home/PrimarySchoolExam/
├── app/                  # FastAPI 后端
│   ├── main.py           # 入口
│   ├── models/           # 数据模型
│   ├── routers/          # 路由
│   ├── schemas/          # 请求/响应模型
│   └── services/         # 业务逻辑（出题、生成docx）
├── frontend/
│   └── index.html        # 旧版单体前端（web/dist 缺失时回退）
├── frontend-admin/       # 管理后台前端（/admin）
├── web/                  # P5 工程化前端（Vite+Vue3，构建到 web/dist）
├── data/                 # SQLite 数据库 + CSV 数据
├── output/               # 生成的试卷文件
├── venv/                 # Python 虚拟环境
├── requirements.txt
└── deploy.sh             # 一键部署脚本
```

## 九、访问地址

部署完成后浏览器访问：`https://www.你的域名.com`
