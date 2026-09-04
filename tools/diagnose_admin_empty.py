#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""后台「页面空数据」精确诊断脚本（v2）

v1 的问题：表名靠人工猜（admin_users / commerce_orders / roles ...），
           结果大量误报「表不存在」，误导排查方向。

v2 的改进：
1. 从 app.models 自动导入所有 SQLAlchemy 模型，读取真实的 __tablename__，不再猜
2. 按「后台页面 → 依赖表」分组统计，直接定位是哪个页面缺哪张表
3. 关键接口联查表单独高亮（/api/admin/users 会因为缺 coin_ledger 直接 500）
4. admin/dist 验证改为扫描全部 chunk（v1 只看 4KB 主入口，永远查不到）

用法（必须在项目根目录执行，venv 环境）：
    venv/bin/python tools/diagnose_admin_empty.py
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# Python 运行脚本时只把脚本所在目录（tools/）加入 sys.path，
# 而 app/ 包在项目根下 —— 必须手动补，否则 import app 报 No module named 'app'
sys.path.insert(0, str(ROOT))

SEP = "=" * 68


def main():
    print(SEP)
    print("【1/3】数据库体检（表名取自 SQLAlchemy 模型，非猜测）")
    print(SEP)

    try:
        from app.database import SessionLocal
        from sqlalchemy import text
        from sqlalchemy import inspect as sa_inspect
    except Exception as e:
        print(f"  [导入失败] {e}")
        print("  → 确认在项目根目录执行，且用的是项目 venv 的 python")
        return 1

    db = SessionLocal()

    # ── 1a. 库内真实表名 ──
    try:
        db_tables = {r[0] for r in db.execute(text("SHOW TABLES")).fetchall()}
    except Exception as e:
        print(f"  [SHOW TABLES 失败] {e}")
        db.close()
        return 1
    print(f"  库内实际表数：{len(db_tables)}\n")

    # ── 1b. 从模型自动收集真实表名 ──
    # 后台各页面 / 接口依赖的模型（按页面分组，便于定位）
    PAGE_DEPS = {
        "用户管理 /api/admin/users": [
            ("app.models.user", "User"),
            ("app.models.user", "VipUser"),
            ("app.models.diamond", "DiamondAccount"),
            ("app.models.pet", "CoinLedger"),          # ← 表名 coin_ledger
            ("app.models.makeup_card", "MakeupCard"),  # ← 表名 makeup_cards
        ],
        "教材版本 /api/admin/textbooks": [
            ("app.models.textbook", "TextbookVersion"),
            ("app.models.textbook", "UserTextbookPref"),
        ],
        "充值订单 /api/admin/commerce": [
            ("app.models.commerce_product", "Product"),
            ("app.models.commerce_product", "ProductBenefit"),
            ("app.models.commerce_order", "Order"),
            ("app.models.commerce_payment", "PayTransaction"),
        ],
        "角色权限 /api/admin/rbac": [
            ("app.models.admin", "Admin"),
            ("app.models.admin", "AdminPermission"),
            ("app.models.admin", "AdminRolePermission"),
        ],
        "审计日志 /api/admin/audit": [
            ("app.models.admin", "AdminOperationLog"),
        ],
        "标注工作台 /api/admin/content": [
            ("app.models.knowledge", "KnowledgePoint"),
            ("app.models.kp_map", "QuestionKpMap"),
        ],
        "掌握度报表 /api/admin/mastery": [
            ("app.models.mastery", "MasteryRecord"),
            ("app.models.mastery", "MasterySnapshot"),
        ],
        "任务/激励": [
            ("app.models.daily_task", "DailyTask"),
            ("app.models.task_confirm", "TaskConfirm"),
        ],
    }

    missing_by_page = {}
    print("  ── 各后台页面依赖表检查 ──")
    for page, models in PAGE_DEPS.items():
        print(f"\n  ▶ {page}")
        page_missing = []
        for mod_path, cls_name in models:
            try:
                mod = __import__(mod_path, fromlist=[cls_name])
                cls = getattr(mod, cls_name)
            except Exception as e:
                print(f"      [模型导入失败] {mod_path}.{cls_name}: {str(e)[:45]}")
                continue
            tbl = getattr(cls, "__tablename__", None)
            if not tbl:
                continue
            if tbl in db_tables:
                try:
                    n = db.execute(text(f"SELECT COUNT(*) FROM `{tbl}`")).scalar()
                    mark = "✓" if n else "○"
                    empty = "   ← 空表（页面会显示无数据）" if n == 0 else ""
                    print(f"      {mark} {tbl:<24} {n:>6} 行{empty}")
                except Exception as e:
                    print(f"      ✗ {tbl:<24} [COUNT 失败] {str(e)[:40]}")
                    page_missing.append(tbl)
            else:
                print(f"      ✗ {tbl:<24} 表不存在 → 接口会 500")
                page_missing.append(tbl)
        if page_missing:
            missing_by_page[page] = page_missing

    db.close()

    print("\n" + "-" * 68)
    print("  ── 模拟 /api/admin/users 查询（定位「有数据却显示空」）──")
    print("-" * 68)
    # 直接复刻 app/routers/admin/users.py::list_users 的 ORM 逻辑，
    # 任何一步缺表/缺列都会在这里抛出精确异常。
    try:
        from sqlalchemy import func, or_
        from app.models.user import User, VipUser
        from app.models.diamond import DiamondAccount
        from app.models.pet import CoinLedger
        from app.models.makeup_card import MakeupCard

        db2 = None
        db2 = SessionLocal()
        print("  步骤 1: db.query(User).count()")
        total = db2.query(User).count()
        print(f"         → {total} 行")

        print("  步骤 2: order_by(User.created_at.desc()).limit(20)")
        users = db2.query(User).order_by(User.created_at.desc()).limit(20).all()
        print(f"         → 取到 {len(users)} 行")
        if users:
            print(f"         → 样例: {users[0].user_id} / {users[0].nickname}")

        uids = [u.user_id for u in users]
        print("  步骤 3: 联查 DiamondAccount（diamond_accounts）")
        diamonds = {d.user_id: d.balance for d in
                    db2.query(DiamondAccount).filter(DiamondAccount.user_id.in_(uids)).all()}
        print(f"         → {len(diamonds)} 条")

        print("  步骤 4: 联查 CoinLedger（coin_ledger）sum(amount)")
        coins = dict(db2.query(CoinLedger.user_id, func.sum(CoinLedger.amount))
                     .filter(CoinLedger.user_id.in_(uids))
                     .group_by(CoinLedger.user_id).all())
        print(f"         → {len(coins)} 条")

        print("  步骤 5: 联查 MakeupCard（makeup_cards）")
        makeups = {m.user_id: m.balance for m in
                   db2.query(MakeupCard).filter(MakeupCard.user_id.in_(uids)).all()}
        print(f"         → {len(makeups)} 条")

        print("  步骤 6: 联查 VipUser（vip_users）")
        n_vip = db2.query(VipUser).count()
        print(f"         → {n_vip} 行")

        db2.close()
        print("\n  ✓ 接口 ORM 逻辑全部跑通，/api/admin/users 应能正常返回数据")
        print("    → 若页面仍空，问题在【浏览器缓存】或【后端服务未重启】：")
        print("        · 硬刷新浏览器 Ctrl+Shift+R（或换无痕窗口）")
        print("        · 重启后端：sudo bash deploy.sh")
    except Exception as e:
        import traceback
        print(f"\n  ✗ 接口查询失败！这就是「有数据却显示空」的原因：")
        print(f"    {type(e).__name__}: {str(e)[:300]}")
        tb = traceback.format_exc().strip().split("\n")
        print("    关键堆栈：")
        for line in tb[-6:]:
            print(f"      {line.strip()}")
        try:
            if db2 is not None:
                db2.close()
        except Exception:
            pass

    # ── 1c. 结论 ──
    print("\n" + SEP)
    print("【结论】")
    if not missing_by_page:
        print("  ✓ 所有后台页面依赖的表都存在")
        print("  → 若页面仍空，属「表有数据但接口/前端问题」，见上面的模拟查询结果")
    else:
        print(f"  ✗ {len(missing_by_page)} 个页面依赖的表缺失：")
        for page, tbls in missing_by_page.items():
            print(f"     • {page}")
            for t in tbls:
                print(f"         - {t}")
        print("\n  → 这些表由迁移创建，需执行：")
        print("       sudo bash deploy.sh   （会跑 run_migrations 自动建表）")
        print("     或手动补跑迁移：")
        print("       venv/bin/python -c \"from app.database import run_migrations; run_migrations()\"")

    # ── 2. 全库兜底：所有模型表里，哪些还没建 ──
    print("\n" + SEP)
    print("【2/3】全量模型表覆盖率（兜底扫描）")
    print(SEP)
    try:
        import importlib
        import pkgutil
        import app.models as models_pkg

        all_tbl = {}
        for _, modname, _ in pkgutil.iter_modules(models_pkg.__path__):
            try:
                m = importlib.import_module(f"app.models.{modname}")
            except Exception:
                continue
            for attr in dir(m):
                obj = getattr(m, attr)
                tbl = getattr(obj, "__tablename__", None)
                if tbl and isinstance(tbl, str) and hasattr(obj, "__table__"):
                    all_tbl[tbl] = f"{modname}.{attr}"
        not_exist = sorted(t for t in all_tbl if t not in db_tables)
        print(f"  模型定义表 {len(all_tbl)} 张，库内缺失 {len(not_exist)} 张")
        if not_exist:
            print("\n  缺失清单：")
            for t in not_exist:
                print(f"     ✗ {t:<28} (模型 {all_tbl[t]})")
        else:
            print("  ✓ 模型定义的表全部存在")
    except Exception as e:
        print(f"  [兜底扫描失败] {e}")

    # ── 3. dist 验证（扫全部 chunk） ──
    print("\n" + SEP)
    print("【3/3】admin/dist 构建产物验证（扫描全部 chunk）")
    print(SEP)
    dist_assets = ROOT / "admin" / "dist" / "assets"
    index_html = ROOT / "admin" / "dist" / "index.html"
    if index_html.exists():
        import datetime
        mt = datetime.datetime.fromtimestamp(index_html.stat().st_mtime)
        print(f"  index.html 构建时间：{mt.strftime('%Y-%m-%d %H:%M:%S')}")
    if not dist_assets.exists():
        print("  ✗ admin/dist/assets 不存在，需 npm run build")
        return 1

    js_files = list(dist_assets.glob("*.js"))
    total_kb = sum(f.stat().st_size for f in js_files) // 1024
    print(f"  chunk 数量：{len(js_files)}，合计 {total_kb} KB\n")

    # 把所有 chunk 拼起来再查（页面代码被拆成独立文件，只看主入口会漏）
    bundle = "\n".join(f.read_text(encoding="utf-8", errors="ignore") for f in js_files)

    checks = [
        ("/api/admin/textbooks", "教材版本"),
        ("/api/admin/commerce", "充值订单"),
        ("/api/admin/rbac", "角色权限"),
        ("/api/admin/audit", "审计日志"),
        # 注意：标注工作台挂在 content 域下，路径是 /api/admin/content/annotation
        # （早期写成 /api/admin/annotation 会误报「dist 缺页面」）
        ("/api/admin/content/annotation", "标注工作台"),
        ("/api/admin/mastery", "掌握度报表"),
        ("/api/admin/users", "用户管理"),
    ]
    print("  后台接口是否已打进 dist：")
    all_ok = True
    for ep, name in checks:
        ok = ep in bundle
        all_ok = all_ok and ok
        print(f"     {'✓' if ok else '✗'} {ep:<28} {name}")

    # 页面路由 chunk
    print("\n  页面 chunk 是否存在：")
    for page in ["Commerce", "Rbac", "Audit", "Annotation", "Mastery", "Textbooks", "Content", "Users"]:
        hit = [f.name for f in js_files if f.name.startswith(page + "-")]
        print(f"     {'✓' if hit else '✗'} {page:<12} {hit[0] if hit else '(未生成)'}")

    print()
    if all_ok:
        print("  ✓ dist 已包含全部新页面，硬刷新浏览器即可（Ctrl+Shift+R）")
    else:
        print("  ✗ dist 缺部分页面，需重新 npm run build")

    return 0 if not missing_by_page else 1


if __name__ == "__main__":
    sys.exit(main())