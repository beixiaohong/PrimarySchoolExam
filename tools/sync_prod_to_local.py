"""线上(SQLPub/生产) → 本地 MySQL 数据同步工具。

目的：把线上库的数据快照到本地（如 192.168.2.158），使线上问题可在本地用
      真实数据复现 / 调试；同时让依赖真实数据的集成测试可在本地跑通。

设计：
- 纯 Python（sqlalchemy + pymysql），不依赖 mysqldump / mysql CLI，跨平台可移植。
- 线上库：只读 SELECT，绝不做任何写操作（安全）。
- 本地库：先按「当前模型」重建 schema（drop_all + create_all），再全量拷贝数据。
  → 优点：本地 schema 永远与当前代码一致，便于复现「代码 + 线上数据」组合的问题。
  → 注意：会清空本地同名库的全部数据（本地本就是「副本」，符合预期）。
- 拷贝时关闭 FOREIGN_KEY_CHECKS，避免表顺序 / 外键依赖导致插入失败。
- 只拷贝「本地模型存在的列」，线上多出的列自动忽略（前向兼容）。

用法：
  # 1) 先准备线上连接配置（不要写进 .env，避免污染本地配置）
  cp .env.prod.example .env.prod
  #   编辑 .env.prod 填入 SQLPub 的 DB_HOST/DB_PORT/DB_USER/DB_PASSWORD/DB_NAME

  # 2) 试运行（只校验两份配置与会话连通性，不拷贝）
  python tools/sync_prod_to_local.py --check

  # 3) 正式同步（重建本地 schema + 全量拷贝）
  python tools/sync_prod_to_local.py

  # 4) 仅拷贝数据（假设本地 schema 已就绪，跳过 drop_all/create_all）
  python tools/sync_prod_to_local.py --no-schema

  # 5) 只同步指定表
  python tools/sync_prod_to_local.py --tables users exam_attempts questions

定时同步（如每天凌晨）：用系统 cron / Windows 任务计划程序调用上面的第 3 条命令即可。
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
from sqlalchemy import create_engine, text, MetaData, Table
from sqlalchemy.engine import Engine


def _load_cfg(env_file: str, prefix: str) -> dict:
    """从指定 .env 文件读取数据库连接配置。

    prefix 用于区分线上线下（prod / local），键名格式：{PREFIX}_DB_HOST 等。
    """
    p = Path(env_file)
    if p.exists():
        load_dotenv(p, override=False)
    cfg = {
        "host": os.environ.get(f"{prefix}_DB_HOST"),
        "port": os.environ.get(f"{prefix}_DB_PORT", "3306"),
        "user": os.environ.get(f"{prefix}_DB_USER"),
        "password": os.environ.get(f"{prefix}_DB_PASSWORD", ""),
        "name": os.environ.get(f"{prefix}_DB_NAME"),
    }
    return cfg


def _engine(cfg: dict, label: str) -> Engine:
    missing = [k for k in ("host", "user", "name") if not cfg.get(k)]
    if missing:
        raise SystemExit(
            f"[sync] {label} 连接信息缺失：{missing}。"
            f"请检查对应的 .env 文件（如 .env.prod）是否填写了 "
            f"{label}_DB_HOST / {label}_DB_USER / {label}_DB_NAME。"
        )
    from urllib.parse import quote_plus
    url = (
        f"mysql+pymysql://{quote_plus(cfg['user'])}:{quote_plus(cfg['password'])}"
        f"@{cfg['host']}:{cfg['port']}/{cfg['name']}?charset=utf8mb4"
    )
    return create_engine(url, pool_pre_ping=True)


def _list_tables(engine: Engine) -> list[str]:
    with engine.connect() as c:
        return [r[0] for r in c.execute(text("SHOW TABLES")).fetchall()]


def sync(prod_engine: Engine, local_engine: Engine, *, rebuild_schema: bool,
         tables: list[str] | None, chunk: int = 2000):
    # 本地元数据（当前模型）
    from app.database import Base
    from app import models  # noqa: F401 确保模型已注册

    local_tables = Base.metadata.tables
    want = tables or list(local_tables.keys())

    if rebuild_schema:
        print("[sync] 重建本地 schema（drop_all + create_all）...")
        Base.metadata.drop_all(bind=local_engine)
        Base.metadata.create_all(bind=local_engine)

    total_rows = 0
    with prod_engine.connect() as pconn, local_engine.connect() as lconn:
        lconn.execute(text("SET FOREIGN_KEY_CHECKS=0"))
        for name in want:
            if name not in local_tables:
                print(f"[sync] 跳过（本地模型无此表）: {name}")
                continue
            table: Table = local_tables[name]
            cols = {c.name for c in table.columns}
            # 线上全量读取
            rows = pconn.execute(text(f"SELECT * FROM `{name}`")).mappings().all()
            n = len(rows)
            if n == 0:
                print(f"[sync] {name}: 0 行（跳过写入）")
                total_rows += 0
                continue
            # 仅保留本地模型存在的列
            payload = [{k: v for k, v in dict(r).items() if k in cols} for r in rows]
            # 分块批量插入
            for i in range(0, n, chunk):
                lconn.execute(table.insert(), payload[i:i + chunk])
            lconn.commit()
            total_rows += n
            print(f"[sync] {name}: 写入 {n} 行")
        lconn.execute(text("SET FOREIGN_KEY_CHECKS=1"))
    print(f"[sync] 完成。共写入 {total_rows} 行。")


def main():
    ap = argparse.ArgumentParser(description="线上→本地 MySQL 数据同步")
    ap.add_argument("--prod-env", default=".env.prod",
                    help="线上库连接配置文件（默认 .env.prod）")
    ap.add_argument("--local-env", default=".env",
                    help="本地库连接配置文件（默认 .env）")
    ap.add_argument("--no-schema", action="store_true",
                    help="跳过 drop_all/create_all，仅拷贝数据")
    ap.add_argument("--tables", nargs="*", default=None,
                    help="仅同步指定表名（默认全部）")
    ap.add_argument("--chunk", type=int, default=2000,
                    help="批量插入分块大小（默认 2000）")
    ap.add_argument("--check", action="store_true",
                    help="仅校验两份配置与会话连通性，不拷贝")
    args = ap.parse_args()

    # 本地配置必须先加载（决定 DB_NAME 等）；线上配置从独立文件读取，互不污染。
    local_cfg = _load_cfg(args.local_env, "DB")
    prod_cfg = _load_cfg(args.prod_env, "PROD_DB")

    local_engine = _engine(local_cfg, "本地")
    prod_engine = _engine(prod_cfg, "线上")

    print(f"[sync] 线上库: {prod_cfg['host']}:{prod_cfg['port']}/{prod_cfg['name']}")
    print(f"[sync] 本地库: {local_cfg['host']}:{local_cfg['port']}/{local_cfg['name']}")

    # 连通性 + 库存在性校验
    try:
        prod_tables = _list_tables(prod_engine)
        print(f"[sync] 线上库连通 OK，表数={len(prod_tables)}")
    except Exception as e:
        raise SystemExit(f"[sync] 线上库连接失败：{e}")
    try:
        local_tables = _list_tables(local_engine)
        print(f"[sync] 本地库连通 OK，表数={len(local_tables)}")
    except Exception as e:
        raise SystemExit(f"[sync] 本地库连接失败：{e}")

    if args.check:
        print("[sync] --check 完成，未执行拷贝。")
        return

    sync(prod_engine, local_engine,
         rebuild_schema=not args.no_schema,
         tables=args.tables, chunk=args.chunk)


if __name__ == "__main__":
    main()
