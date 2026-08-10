"""SQLite → MySQL 数据迁移脚本（P1）

迁移策略（模型基线）：
- MySQL 侧不执行 001-025 旧迁移脚本（大量 SQLite 方言），
  改为 Base.metadata.create_all 直接由 SQLAlchemy 模型建全部表，
  然后把 versions 目录下所有迁移版本预置为「已执行」。
- 数据逐表从 SQLite 读取 → 批量 INSERT MySQL（每批 500 行），
  布尔/日期类型由 SQLAlchemy 反射自动转换。
- 按外键依赖拓扑排序导入（被引用表先于引用表）。

用法（先配好 .env 中 DB_* 与 DB_DRIVER=mysql，并提前建好空库）：
    python tools/sqlite_to_mysql.py --dry-run        # 只输出对账报告，不写库
    python tools/sqlite_to_mysql.py                  # 全量迁移
    python tools/sqlite_to_mysql.py --tables users,daily_tasks   # 指定表
"""
import argparse
import os
import sys
from contextlib import nullcontext
from datetime import datetime
from pathlib import Path

# 强制使用 MySQL 连接（无论 .env 中 DB_DRIVER 是什么）
os.environ["DB_DRIVER"] = "mysql"
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sqlalchemy import MetaData, create_engine, text  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.config import DATABASE_URL, DB_PATH  # noqa: E402
from app import models  # noqa: F401,E402  注册全部模型
from app.database import Base  # noqa: E402

BATCH = 500

# Windows 控制台 GBK 兼容：中文/emoji 输出不报错
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def _list_migration_versions() -> list:
    d = ROOT / "app" / "migrations" / "versions"
    return sorted(p.stem for p in d.glob("[0-9]*.py"))


def _topo_sort(tables: dict, inspector_fk: dict) -> list:
    """按外键依赖拓扑排序：被引用表排前面"""
    deps = {name: {fk["referred_table"] for fk in inspector_fk.get(name, [])
                   if fk["referred_table"] in tables and fk["referred_table"] != name}
            for name in tables}
    order, placed = [], set()
    remaining = set(tables)
    while remaining:
        ready = {n for n in remaining if deps[n] <= placed}
        if not ready:  # 循环依赖兜底：直接放剩余
            ready = remaining
        for n in sorted(ready):
            order.append(n)
            placed.add(n)
        remaining -= ready
    return order


def main():
    ap = argparse.ArgumentParser(description="SQLite → MySQL 数据迁移")
    ap.add_argument("--dry-run", action="store_true", help="只报告行数，不写入")
    ap.add_argument("--tables", default="", help="仅迁移指定表（逗号分隔）")
    ap.add_argument("--sqlite", default=str(DB_PATH), help="SQLite 文件路径（默认项目 primary_school.db）")
    args = ap.parse_args()

    if not Path(args.sqlite).exists():
        sys.exit(f"SQLite 文件不存在: {args.sqlite}")

    print(f"[1/4] 连接 MySQL: {DATABASE_URL.split('@')[-1]}")
    mysql_engine = create_engine(DATABASE_URL, pool_pre_ping=True)

    # 反射 SQLite
    sqlite_engine = create_engine(f"sqlite:///{args.sqlite}")
    sqlite_meta = MetaData()
    sqlite_meta.reflect(bind=sqlite_engine)

    # 目标表集合（模型中存在的表）
    model_tables = {t: Base.metadata.tables[t] for t in Base.metadata.tables}
    only = {t.strip() for t in args.tables.split(",") if t.strip()} if args.tables else None

    from sqlalchemy import inspect as sa_inspect
    insp = sa_inspect(sqlite_engine)
    fk_map = {t: insp.get_foreign_keys(t) for t in sqlite_meta.tables}
    ordered = _topo_sort(sqlite_meta.tables, fk_map)

    # ── 建表 + 预置迁移记录 ──
    if not args.dry_run:
        print("[2/4] Base.metadata.create_all 建表（模型基线）...")
        Base.metadata.create_all(bind=mysql_engine)
        versions = _list_migration_versions()
        with Session(mysql_engine) as db:
            db.execute(text(
                "CREATE TABLE IF NOT EXISTS schema_migrations ("
                "id INTEGER PRIMARY KEY AUTO_INCREMENT, "
                "version VARCHAR(100) NOT NULL UNIQUE, applied_at DATETIME)"))
            for v in versions:
                db.execute(text(
                    "INSERT IGNORE INTO schema_migrations (version, applied_at) VALUES (:v, :t)"),
                    {"v": v, "t": datetime.now()})
            db.commit()
        print(f"      已预置 {len(versions)} 个迁移版本为已执行")
    else:
        print("[2/4] dry-run：跳过建表")

    # ── 逐表迁移 ──
    print("[3/4] 数据迁移（每批 %d 行）..." % BATCH)
    report = []
    for name in ordered:
        if name not in model_tables:
            report.append((name, "SKIP-模型中不存在"))
            continue
        if only and name not in only:
            continue
        src_table = sqlite_meta.tables[name]
        dst_table = model_tables[name]
        dst_cols = {c.name for c in dst_table.columns}

        with sqlite_engine.connect() as conn:
            rows = conn.execute(src_table.select()).mappings().all()
        if not rows:
            report.append((name, "0 行（空表）"))
            continue

        # 只保留目标表存在的列
        cleaned = [{k: v for k, v in dict(r).items() if k in dst_cols} for r in rows]
        if not args.dry_run:
            with mysql_engine.begin() as conn:
                for i in range(0, len(cleaned), BATCH):
                    conn.execute(dst_table.insert(), cleaned[i:i + BATCH])
        report.append((name, f"{len(cleaned)} 行" + ("（dry-run 未写入）" if args.dry_run else " 已写入")))

    # ── 行数对账 ──
    print("[4/4] 行数对账报告")
    width = max(len(n) for n, _ in report) if report else 10
    fail = 0
    with sqlite_engine.connect() as sconn, (nullcontext() if args.dry_run else mysql_engine.connect()) as mconn:
        for name, note in report:
            if name not in model_tables or "SKIP" in note:
                print(f"  {name:<{width}}  {note}")
                continue
            s_cnt = sconn.execute(text(f"SELECT COUNT(*) FROM {name}")).scalar()
            if args.dry_run:
                print(f"  {name:<{width}}  SQLite={s_cnt}  {note}")
            else:
                m_cnt = mconn.execute(text(f"SELECT COUNT(*) FROM `{name}`")).scalar()
                ok = "✓" if s_cnt == m_cnt else "✗ 不一致"
                if s_cnt != m_cnt:
                    fail += 1
                print(f"  {name:<{width}}  SQLite={s_cnt}  MySQL={m_cnt}  {ok}")

    if fail:
        sys.exit(f"\n迁移完成但有 {fail} 张表行数不一致，请排查（多为外键/唯一约束冲突）")
    print("\n迁移完成 ✅  建议随后运行 python run.py 验证服务")


if __name__ == "__main__":
    main()
