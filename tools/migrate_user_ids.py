#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""存量账号 user_id 迁移为随机「字母+数字」格式（与新注册账号一致）。

背景
----
旧账号的 user_id 等于昵称（中文姓名），与新注册账号（u 前缀 + 9 位 a-z0-9）不一致。
本脚本把「不符合新格式」的旧 user_id 重映射为新的字母数字 id，并**自动发现所有引用
user_id 的表/列**（通过 information_schema 内省，无需手列），统一重映射，保证外键一致。

格式约定（与 app/routers/auth.py 的 _gen_user_id 一致）
    ^u[a-z0-9]{9}$   例如 u7k2m9x4p1

用法
----
  # 默认 dry-run：仅打印将要执行的改动，不写库
  python tools/migrate_user_ids.py

  # 真正执行（建议先 dry-run 确认无误，并已备份数据库）
  python tools/migrate_user_ids.py --apply

注意
----
- 执行前请务必对数据库做全量备份（例如 mysqldump）。
- 新生成的 id 会与现有 users 表全部 user_id 去重，避免与已存在的新格式 id 或旧 id 冲突。
- 脚本在一个事务内完成：先更新父表 users，再更新各子表，保证引用一致。
- 已在新格式（u + 9 位）的账号不会被改动；昵称（nickname）保持不变，仅作展示名。
"""
import argparse
import os
import re
import secrets
import string
import sys

# 让脚本能 import 项目配置
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from sqlalchemy import create_engine, text  # noqa: E402

try:
    from app.config import DATABASE_URL  # noqa: E402
except Exception as e:  # pragma: no cover
    print(f"无法加载 app.config.DATABASE_URL：{e}")
    sys.exit(1)

NEW_ID_RE = re.compile(r"^u[a-z0-9]{9}$")
ALPHABET = string.ascii_lowercase + string.digits


def gen_new_id(existing: set) -> str:
    """生成唯一的新格式 user_id（与 _gen_user_id 同规则）。"""
    for _ in range(50):
        uid = "u" + "".join(secrets.choice(ALPHABET) for _ in range(9))
        if uid not in existing:
            return uid
    raise RuntimeError("生成新 user_id 失败：重试次数过多，请稍后重试")


def build_case_sql(table: str, col: str, mapping: dict) -> tuple:
    """构造 UPDATE ... SET col = CASE col WHEN :o THEN :n ... END WHERE col IN (...)。"""
    whens, params, in_clause = [], {}, []
    for i, (old, new) in enumerate(mapping.items()):
        whens.append(f"WHEN :o{i} THEN :n{i}")
        in_clause.append(f":o{i}")
        params[f"o{i}"] = old
        params[f"n{i}"] = new
    sql = (
        f"UPDATE `{table}` SET `{col}` = CASE `{col}` "
        + " ".join(whens)
        + f" END WHERE `{col}` IN ({','.join(in_clause)})"
    )
    return sql, params


def main():
    ap = argparse.ArgumentParser(description="存量账号 user_id 迁移为字母数字格式")
    ap.add_argument("--apply", action="store_true", help="真正执行（默认仅 dry-run 预览）")
    args = ap.parse_args()

    engine = create_engine(DATABASE_URL, pool_pre_ping=True)

    with engine.begin() as conn:
        # 1) 读出全部 user_id
        rows = conn.execute(text("SELECT user_id FROM users")).fetchall()
        existing_ids = {r[0] for r in rows}
        mapping = {}
        for (old,) in rows:
            if NEW_ID_RE.match(old or ""):
                continue  # 已是新格式，跳过
            new = gen_new_id(existing_ids)
            existing_ids.add(new)
            mapping[old] = new

        if not mapping:
            print("✅ 没有需要迁移的旧 user_id（全部已为新格式）。")
            return

        # 2) 内省发现所有含 user_id 列的表
        cols = conn.execute(text(
            "SELECT TABLE_NAME, COLUMN_NAME FROM information_schema.COLUMNS "
            "WHERE TABLE_SCHEMA = DATABASE() AND COLUMN_NAME = 'user_id'"
        )).fetchall()
        tables = {t: c for t, c in cols}

        print(f"🔍 待迁移 user_id：{len(mapping)} 个")
        print(f"🔍 含 user_id 列的表：{len(tables)} 张")
        for old, new in mapping.items():
            print(f"   {old}  ->  {new}")

        if not args.apply:
            print("\n[DRY-RUN] 未执行任何写操作。确认无误后加 --apply 真正执行。")
            return

        # 3) 先更新父表 users（主键），再更新各子表
        users_sql, users_params = build_case_sql("users", "user_id", mapping)
        conn.execute(text(users_sql), users_params)
        print("\n✅ users 主键已更新。")

        counts = {}
        for t, c in tables.items():
            if t == "users":
                continue
            sql, params = build_case_sql(t, c, mapping)
            try:
                r = conn.execute(text(sql), params)
                if r.rowcount:
                    counts[t] = r.rowcount
            except Exception as e:
                print(f"⚠️  更新 {t}.{c} 失败：{e}")
                raise

        print("✅ 各子表已同步更新：")
        if counts:
            for t, n in sorted(counts.items()):
                print(f"   {t}.user_id: {n} 行")
        else:
            print("   （子表中无匹配旧 user_id 的行）")
        print("\n🎉 迁移完成。建议：登录验证、并在管理后台确认资产/学习记录归属无误。")


if __name__ == "__main__":
    main()
