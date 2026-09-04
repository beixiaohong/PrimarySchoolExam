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

# 1. 检查数据库
print("=" * 60)
print("【1/4】数据库关键表数据量检查（只读）")
print("=" * 60)

try:
    from app.database import SessionLocal
    from sqlalchemy import text
    db = SessionLocal()
    tables = [
        # 用户与基础数据
        "users",
        # 教材版本（S6 新增 region 列）
        "textbook_versions",
        # 充值订单（S4）
        "commerce_orders", "commerce_products",
        # RBAC（S1）
        "roles", "permissions", "admin_users",
        # 审计（S1）
        "audit_logs",
        # 知识点标注（S2）
        "kp_annotations", "knowledge_points",
        # 掌握度（S3）
        "user_kp_mastery",
        # 任务（S 0）
        "tasks", "daily_task_progress",
    ]
    for t in tables:
        try:
            r = db.execute(text(f"SELECT COUNT(*) FROM {t}")).scalar()
            print(f"  {t:<28} {r:>8} 行")
        except Exception as e:
            print(f"  {t:<28} [ERR] {str(e)[:60]}")
    db.close()
except Exception as e:
    print(f"  [DB 连接失败] {e}")
    sys.exit(1)


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