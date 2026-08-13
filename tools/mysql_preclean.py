"""MySQL 迁移前清理：备份 MySQL 现有行到 JSON → 清空业务表（保留 admins/system_config/schema_migrations）

背景：MySQL 中已有 P2~P5 验证期间产生的少量测试数据，与 SQLite 原始数据主键会冲突。
本脚本先整体备份再清空，保证可回滚（一次性迁移已完成后通常不再需要）。
"""
import json
import os
import sys
from datetime import datetime
from pathlib import Path

os.environ["DB_DRIVER"] = "mysql"
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sqlalchemy import MetaData, create_engine, text  # noqa: E402

from app.config import DATABASE_URL  # noqa: E402
from app import models  # noqa: F401,E402
from app.database import Base  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

KEEP = {"admins", "admin_operation_logs", "system_config", "schema_migrations"}


def main():
    """MySQL 迁移前清理：先整体备份现有行到 JSON，再清空业务表（保留 admins/system_config/schema_migrations）。

    参数：无（连接信息取自 app.config.DATABASE_URL；保留表见模块级 KEEP）。
    副作用：① 在 tools/ 下生成 mysql_backup_<时间戳>.json 备份；
            ② 对线上 MySQL 业务表执行 DELETE FROM 清空（已关闭外键检查以安全删子表）。
    注意：运行前务必确认已切到目标 MySQL 且接受清空；备份文件即回滚依据，删除前请妥善保存。
    """
    eng = create_engine(DATABASE_URL, pool_pre_ping=True)
    meta = MetaData()
    meta.reflect(bind=eng)

    # 1) 备份现有数据
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = ROOT / "tools" / f"mysql_backup_{stamp}.json"
    dump = {}
    with eng.connect() as conn:
        for name, tbl in meta.tables.items():
            rows = conn.execute(tbl.select()).mappings().all()
            if rows:
                dump[name] = [
                    {k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in dict(r).items()}
                    for r in rows
                ]
    backup_path.write_text(json.dumps(dump, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[backup] {backup_path.name}: " + ", ".join(f"{k}({len(v)})" for k, v in dump.items()))

    # 2) 清空业务表（外键顺序：先子表后父表——反射顺序反向 + FK 检查关闭）
    clear_tables = [t for t in meta.tables if t not in KEEP and t in Base.metadata.tables]
    from sqlalchemy import inspect as sa_inspect
    insp = sa_inspect(eng)
    fk_map = {t: insp.get_foreign_keys(t) for t in meta.tables}
    # 简单拓扑反序：有外键引用的表先删
    deps = {n: {fk["referred_table"] for fk in fks if fk["referred_table"] in clear_tables and fk["referred_table"] != n}
            for n, fks in fk_map.items() if n in clear_tables}
    order, placed, remaining = [], set(), set(clear_tables)
    while remaining:
        ready = {n for n in remaining if not (deps.get(n, set()) - placed)}
        if not ready:
            ready = remaining
        for n in sorted(ready):
            order.append(n)
            placed.add(n)
        remaining -= ready
    order.reverse()  # 依赖方先删

    with eng.begin() as conn:
        try:
            # 临时关闭外键检查，允许无条件删除子表（会话级，末尾重新开启）
            conn.execute(text("SET FOREIGN_KEY_CHECKS=0"))
        except Exception:
            pass
        for name in order:
            n = conn.execute(text(f"SELECT COUNT(*) FROM `{name}`")).scalar()
            if n:
                # 【危险操作】DELETE 清空整张表，不可回滚；务必先确认上方 JSON 备份已生成
                conn.execute(text(f"DELETE FROM `{name}`"))
                print(f"[clear] {name}: 删除 {n} 行")
        try:
            conn.execute(text("SET FOREIGN_KEY_CHECKS=1"))
        except Exception:
            pass
    print("[done] 清理完成（sqlite_to_mysql.py 已归档删除，无需再运行）")


if __name__ == "__main__":
    main()
