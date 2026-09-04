# -*- coding: utf-8 -*-
"""在测试库 schoolexam_test 上验证 db/seed_commerce_products.sql 的幂等性与正确性。

验证点：
  1. 第一遍执行 → 插入 9 个商品 + 10 条权益（组合 BUNDLE_VIP_DIAMOND 含 2 条）
  2. 第二遍执行 → 0 新增（幂等）
  3. 商品金额/状态/权益数正确

用法：
    DB_NAME=schoolexam_test .venv/Scripts/python.exe tools/verify_seed_products.py
"""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sqlalchemy import text  # noqa: E402

from app.database import SessionLocal, engine  # noqa: E402

SQL_FILE = ROOT / "db" / "seed_commerce_products.sql"

out = []


def P(msg=""):
    out.append(str(msg))


def split_statements(sql: str):
    """按分号切分 SQL，去掉纯注释块与空语句。"""
    stmts = []
    buf = []
    for line in sql.splitlines():
        stripped = line.strip()
        if stripped.startswith("--") or not stripped:
            continue
        buf.append(line)
        if stripped.endswith(";"):
            stmts.append("\n".join(buf).rstrip(";").strip())
            buf = []
    return [s for s in stmts if s]


def run_once(db, label):
    stmts = split_statements(SQL_FILE.read_text(encoding="utf-8"))
    executed = 0
    for s in stmts:
        if s.upper().startswith("SET NAMES"):
            continue
        db.execute(text(s))
        executed += 1
    db.commit()

    products = db.execute(text("SELECT COUNT(*) FROM products")).scalar()
    benefits = db.execute(text("SELECT COUNT(*) FROM product_benefits")).scalar()
    P(f"  {label}: 执行 {executed} 条语句 → products={products} product_benefits={benefits}")
    return products, benefits


def main():
    db = SessionLocal()
    try:
        url = str(engine.url)
        P(f"数据库：{url.split('@')[-1]}")
        if "_test" not in url:
            P("✗ 拒绝执行：当前连接的不是测试库（URL 中无 _test）")
            return 1
        P()

        # 0. 清空，模拟全新库
        db.execute(text("DELETE FROM product_benefits"))
        db.execute(text("DELETE FROM products"))
        db.commit()
        P("  [准备] 已清空 products / product_benefits")
        P()

        # 1. 第一遍
        p1, b1 = run_once(db, "第 1 遍")

        # 2. 第二遍（幂等）
        p2, b2 = run_once(db, "第 2 遍")
        P()

        ok = True
        if p1 != 9:
            P(f"  ✗ 商品数应为 9，实际 {p1}")
            ok = False
        if b1 != 10:
            P(f"  ✗ 权益数应为 10（组合含 2 条），实际 {b1}")
            ok = False
        if (p2, b2) != (p1, b1):
            P(f"  ✗ 幂等失败：第二遍后 {p2}/{b2}，应为 {p1}/{b1}")
            ok = False
        if ok:
            P("  ✓ 幂等性通过：第二遍零新增")

        # 3. 内容核对
        P()
        P("  ── 商品清单 ──")
        rows = db.execute(text("""
            SELECT p.sku, p.name, p.type, p.price_fen, p.original_fen,
                   p.duration_days, p.status,
                   (SELECT COUNT(*) FROM product_benefits b WHERE b.product_id = p.id) AS bn
            FROM products p ORDER BY p.sort_order
        """)).fetchall()
        for r in rows:
            P(f"    {r[0]:<20} {r[1]:<14} {r[2]:<11} "
              f"{r[3]/100:>6.0f}元 (原{r[4]/100:>5.0f})  天数={r[5]:<4} {r[6]:<7} 权益={r[7]}")

        # 4. 断言
        P()
        checks = []
        by_sku = {r[0]: r for r in rows}
        checks.append(("钻石档位 4 个", sum(1 for r in rows if r[2] == "diamond") == 4))
        checks.append(("会员档位 3 个", sum(1 for r in rows if r[2] == "membership") == 3))
        checks.append(("全部 online", all(r[6] == "online" for r in rows)))
        checks.append(("VIP_YEAR 天数 365", by_sku["VIP_YEAR"][5] == 365))
        checks.append(("VIP_YEAR 售价 298 元", by_sku["VIP_YEAR"][3] == 29800))
        checks.append(("组合包含 2 条权益", by_sku["BUNDLE_VIP_DIAMOND"][7] == 2))
        checks.append(("补签卡权益 makeup_card", db.execute(text("""
            SELECT COUNT(*) FROM product_benefits b JOIN products p ON p.id = b.product_id
            WHERE p.sku = 'MAKEUP_5' AND b.benefit_type = 'coupon'
              AND b.benefit_key = 'makeup_card' AND b.amount = 5
        """)).scalar() == 1))
        checks.append(("无浮点金额列（全为整型分）",
                       db.execute(text("""
            SELECT COUNT(*) FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'products'
              AND COLUMN_NAME IN ('price_fen','original_fen') AND DATA_TYPE = 'int'
        """)).scalar() == 2))

        for name, passed in checks:
            P(f"    {'✓' if passed else '✗'} {name}")
            if not passed:
                ok = False

        P()
        P("【结论】" + ("全部通过" if ok else "存在失败项"))
    except Exception as e:
        P(f"✗ 异常：{type(e).__name__}: {e}")
        import traceback

        P(traceback.format_exc())
        ok = False
    finally:
        db.close()

    text_out = "\n".join(out)
    (ROOT / ".pc_cache" / "verify_products_out.txt").write_text(text_out, encoding="utf-8")
    print(text_out)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
