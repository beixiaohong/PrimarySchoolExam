"""把模型层的 comment= 注释同步到线上 MySQL 存量表。

原理：
- 表注释：ALTER TABLE `t` COMMENT='...'（轻量，不涉及数据）
- 列注释：MySQL 改列注释必须 MODIFY COLUMN 重述完整列定义，
  因此先从 information_schema 读出列的现有定义（类型/NULL/默认值/EXTRA），
  原样重述并追加 COMMENT，避免误改列类型。
- 只处理注释与模型不一致的列/表，最小化 ALTER 次数。
- sqlpub 代理可能限制部分 DDL，每条语句独立容错，失败不中断。

用法：
    python tools/sync_db_comments.py            # 实际执行
    python tools/sync_db_comments.py --dry-run  # 只打印不执行
"""
import os
import sys
from pathlib import Path

os.environ["DB_DRIVER"] = "mysql"
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sqlalchemy import create_engine, text  # noqa: E402
from app.config import DATABASE_URL  # noqa: E402
from app.database import Base  # noqa: E402
import app.models  # noqa: E402,F401  确保所有模型注册到 Base.metadata

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

DRY = "--dry-run" in sys.argv


def esc(s: str) -> str:
    """SQL 字符串字面量转义"""
    return s.replace("\\", "\\\\").replace("'", "''")


def fetch_remote(conn, table: str):
    """读取线上表的注释与列定义"""
    row = conn.execute(text(
        "SELECT TABLE_COMMENT FROM information_schema.TABLES "
        "WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME=:t"), {"t": table}).first()
    if row is None:
        return None, {}
    table_comment = row[0]
    cols = {}
    for r in conn.execute(text(
            "SELECT COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE, COLUMN_DEFAULT, EXTRA, COLUMN_COMMENT "
            "FROM information_schema.COLUMNS "
            "WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME=:t"), {"t": table}):
        cols[r[0]] = {"type": r[1], "nullable": r[2], "default": r[3],
                      "extra": r[4], "comment": r[5]}
    return table_comment, cols


def build_column_def(name: str, info: dict, comment: str) -> str:
    """按现有列定义原样重述并追加 COMMENT"""
    parts = [f"`{name}` {info['type']}"]
    if info["nullable"] == "NO":
        parts.append("NOT NULL")
    d = info["default"]
    if d is not None:
        up = d.upper()
        if up in ("CURRENT_TIMESTAMP", "NULL") or d.lstrip("-").replace(".", "").isdigit():
            parts.append(f"DEFAULT {d}")
        else:
            parts.append(f"DEFAULT '{esc(d)}'")
    if info["extra"]:
        parts.append(info["extra"])
    parts.append(f"COMMENT '{esc(comment)}'")
    return " ".join(parts)


def main():
    eng = create_engine(DATABASE_URL, pool_pre_ping=True)
    altered_col, altered_tbl, skipped, failed = 0, 0, 0, 0
    conn = eng.connect()  # DDL 隐式提交，逐条执行互不影响
    try:
        for tname, table in sorted(Base.metadata.tables.items()):
            tbl_comment, remote_cols = fetch_remote(conn, tname)
            if tbl_comment is None and not remote_cols:
                print(f"[miss] 表 {tname} 线上不存在，跳过")
                skipped += 1
                continue

            # ── 表注释 ──
            want_tbl = table.comment or ""
            if want_tbl and tbl_comment != want_tbl:
                stmt = f"ALTER TABLE `{tname}` COMMENT='{esc(want_tbl)}'"
                if DRY:
                    print(f"[dry-table] {stmt}")
                    altered_tbl += 1
                else:
                    try:
                        conn.execute(text(stmt))
                        print(f"[table] {tname}: {want_tbl}")
                        altered_tbl += 1
                    except Exception as e:
                        print(f"[fail-table] {tname}: {type(e).__name__} {str(e)[:100]}")
                        failed += 1

            # ── 列注释 ──
            for col in table.columns:
                want = col.comment or ""
                if not want:
                    continue
                info = remote_cols.get(col.name)
                if info is None:
                    print(f"[miss] {tname}.{col.name} 线上不存在，跳过")
                    skipped += 1
                    continue
                if info["comment"] == want:
                    continue
                coldef = build_column_def(col.name, info, want)
                stmt = f"ALTER TABLE `{tname}` MODIFY COLUMN {coldef}"
                if DRY:
                    print(f"[dry-col] {stmt}")
                    altered_col += 1
                else:
                    try:
                        conn.execute(text(stmt))
                        print(f"[col] {tname}.{col.name}")
                        altered_col += 1
                    except Exception as e:
                        print(f"[fail-col] {tname}.{col.name}: {type(e).__name__} {str(e)[:100]}")
                        failed += 1

    finally:
        conn.close()
    print(f"\n完成：表注释 {altered_tbl} 条，列注释 {altered_col} 条，"
          f"跳过 {skipped}，失败 {failed}{'（dry-run 未实际执行）' if DRY else ''}")


if __name__ == "__main__":
    main()
