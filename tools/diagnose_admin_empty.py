#!/usr/bin/env python3
"""线上后台"空数据"诊断与修复脚本

适用场景：管理后台多页面空数据（只有首页/运营分析/数据中心有数据汇总，其余全空）

核心思路：
1. 检查数据库关键表是否有数据
2. 检查 admin/dist 是否最新
3. 重建 admin/dist
4. 报告结果

使用：
   venv/bin/python tools/diagnose_admin_empty.py
"""
import os
import sys
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# 关键：把项目根目录加入 sys.path，否则 `import app` 会报 No module named 'app'
# （Python 默认只把脚本所在目录 tools/ 加入 sys.path，而 app/ 在项目根下）
sys.path.insert(0, str(ROOT))

# 1. 检查数据库
print("=" * 60)
print("【1/4】数据库关键表数据量检查（只读）")
print("=" * 60)

try:
    from app.database import SessionLocal
    from sqlalchemy import text
    db = SessionLocal()
    # 先列出库里所有真实表名，只对存在的表做 COUNT，避免刷屏报错
    exist = {row[0] for row in db.execute(text("SHOW TABLES")).fetchall()}
    print(f"（库内共 {len(exist)} 张表）\n")

    # 候选表名 → 说明；只统计真实存在的
    candidates = [
        ("users", "用户（用户管理页）"),
        ("admin_users", "管理员账号"),
        ("vip_users", "VIP 用户"),
        ("textbook_versions", "教材版本（S6）"),
        ("commerce_products", "商品（充值订单·S4）"),
        ("commerce_orders", "订单（充值订单·S4）"),
        ("commerce_payments", "支付流水（S4）"),
        ("commerce_refunds", "退款（S4）"),
        ("roles", "角色（RBAC·S1）"),
        ("permissions", "权限点（RBAC·S1）"),
        ("role_permissions", "角色-权限关联"),
        ("admin_roles", "管理员-角色关联"),
        ("audit_logs", "审计日志（S1）"),
        ("knowledge_points", "知识点树（S2）"),
        ("kp_annotations", "知识点标注（S2）"),
        ("user_kp_mastery", "掌握度（S3）"),
        ("daily_tasks", "每日任务配置"),
        ("task_progress", "任务进度"),
        ("diamond_accounts", "钻石账户"),
    ]
    for t, desc in candidates:
        if t not in exist:
            print(f"  {t:<22} [表不存在]  {desc}")
            continue
        try:
            r = db.execute(text(f"SELECT COUNT(*) FROM `{t}`")).scalar()
            flag = "" if r else "   ← 空！"
            print(f"  {t:<22} {r:>8} 行  {desc}{flag}")
        except Exception as e:
            print(f"  {t:<22} [ERR] {str(e)[:50]}   {desc}")

    # 关键字段存在性（教材版本 region 列 = 迁移 061）
    print("\n--- 关键字段检查 ---")
    checks = [
        ("textbook_versions", "region", "迁移 061（教材省份适配）"),
        ("commerce_orders", "status", "迁移 057（订单状态机）"),
        ("users", "is_active", "用户停用字段"),
    ]
    for tbl, col, desc in checks:
        if tbl not in exist:
            print(f"  {tbl}.{col:<12} [表不存在]  {desc}")
            continue
        n = db.execute(text(
            "SELECT COUNT(*) FROM information_schema.COLUMNS "
            "WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME=:t AND COLUMN_NAME=:c"
        ), {"t": tbl, "c": col}).scalar()
        mark = "✓ 存在" if n else "✗ 缺失 → 需跑迁移"
        print(f"  {tbl}.{col:<12} {mark}   {desc}")

    db.close()
except Exception as e:
    print(f"  [DB 连接失败] {e}")
    print("  → 继续检查 dist（不中断）")


# 2. 检查 admin/dist 时间戳
print()
print("=" * 60)
print("【2/4】admin/dist 构建产物新鲜度")
print("=" * 60)
dist_dir = ROOT / "admin" / "dist"
index_html = dist_dir / "index.html"
if index_html.exists():
    import datetime
    mtime = datetime.datetime.fromtimestamp(index_html.stat().st_mtime)
    age_hours = (datetime.datetime.now() - mtime).total_seconds() / 3600
    print(f"  admin/dist/index.html  {mtime.strftime('%Y-%m-%d %H:%M:%S')}  ({age_hours:.1f} 小时前)")
    if age_hours > 24 * 7:
        print(f"  ⚠️ 构建产物 >7 天，需要重建")
    else:
        print(f"  ✓ 构建产物较新")
else:
    print(f"  ✗ admin/dist 不存在，需要先构建")


# 3. 重建 admin/dist
print()
print("=" * 60)
print("【3/4】重建 admin/dist")
print("=" * 60)
admin_dir = ROOT / "admin"
print(f"  cd {admin_dir}")
build = subprocess.run(
    ["npm", "run", "build"],
    cwd=admin_dir,
    capture_output=True, text=True,
)
print(f"  exit={build.returncode}")
if build.stdout:
    # 只打印最后 20 行
    lines = build.stdout.strip().split("\n")
    for line in lines[-20:]:
        print(f"    {line}")
if build.stderr:
    lines = [l for l in build.stderr.split("\n") if "warn" not in l.lower()][:10]
    for line in lines:
        print(f"    [stderr] {line}")


# 4. 验证重建结果
print()
print("=" * 60)
print("【4/4】验证 dist 内含新页面路由")
print("=" * 60)
if index_html.exists():
    import datetime
    mtime = datetime.datetime.fromtimestamp(index_html.stat().st_mtime)
    print(f"  新 dist/index.html  {mtime.strftime('%Y-%m-%d %H:%M:%S')}")

# 检查 dist 中的关键 API 端点
js_files = list((dist_dir / "assets").glob("index-*.js"))
if js_files:
    js = js_files[0].read_text(encoding="utf-8", errors="ignore")
    expected = ["/api/admin/textbooks", "/api/admin/commerce", "/api/admin/rbac",
                "/api/admin/audit", "/api/admin/annotation", "/api/admin/mastery"]
    print(f"  dist bundle: {js_files[0].name} ({js_files[0].stat().st_size//1024}KB)")
    for ep in expected:
        present = ep in js
        mark = "✓" if present else "✗"
        print(f"    {mark} {ep}")