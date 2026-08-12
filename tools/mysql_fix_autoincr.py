"""迁移后修复：把各表 AUTO_INCREMENT 重置为 MAX(id)+1，避免显式 id 导入后新增冲突。"""
import os
import sys
from pathlib import Path

os.environ["DB_DRIVER"] = "mysql"
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sqlalchemy import create_engine, text  # noqa: E402
from app.config import DATABASE_URL  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def main():
    """迁移后修复 AUTO_INCREMENT 计数器：将每张自增表重置为 MAX(id)+1。

    参数：无（连接信息取自 app.config.DATABASE_URL）。
    副作用：会对线上 MySQL 各业务表执行 ALTER TABLE ... AUTO_INCREMENT，修改自增起点。
    注意：运行前务必确认目标 MySQL 的 DB_DRIVER 已切到 mysql；此操作会改自增计数器，
          在并发写入或有显式 id 导入场景下需谨慎。
    """
    eng = create_engine(DATABASE_URL, pool_pre_ping=True)
    with eng.begin() as conn:
        tables = [r[0] for r in conn.execute(text(
            "SELECT TABLE_NAME FROM information_schema.COLUMNS "
            "WHERE TABLE_SCHEMA=DATABASE() AND EXTRA LIKE '%auto_increment%'"))]
        fixed, skipped = 0, 0
        for t in tables:
            mx = conn.execute(text(f"SELECT COALESCE(MAX(id),0) FROM `{t}`")).scalar()
            if not mx:
                skipped += 1
                continue
            try:
                # 【危险操作】ALTER TABLE 修改 AUTO_INCREMENT 自增起点，直接改动表结构
                conn.execute(text(f"ALTER TABLE `{t}` AUTO_INCREMENT = {mx + 1}"))
                print(f"[fix] {t}: AUTO_INCREMENT={mx + 1}")
                fixed += 1
            except Exception as e:
                print(f"[skip] {t}: {type(e).__name__} {str(e)[:80]}")
                skipped += 1
        print(f"\nfixed={fixed} skipped={skipped}")


if __name__ == "__main__":
    main()
