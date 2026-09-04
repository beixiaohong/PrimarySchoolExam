#!/usr/bin/env python3
"""VIP 到期降级：物理删除 expire_at < NOW() 的 vip_users 记录。

由 tools/scheduler.py 每日 02:00 调用（线上 crontab 驱动）。
vip_users 是名单表非资金表，不受「永不删除订单/流水」DB-05 约束。
expire_at IS NULL 的记录（永久 VIP）不受影响。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from app.database import SessionLocal


def main():
    db = SessionLocal()
    try:
        result = db.execute(text(
            "DELETE FROM vip_users WHERE expire_at IS NOT NULL AND expire_at < NOW()"
        ))
        db.commit()
        n = result.rowcount
        if n:
            print(f"[vip-expire] 清理 {n} 条到期 VIP 记录")
        else:
            print("[vip-expire] 无到期 VIP")
    finally:
        db.close()


if __name__ == "__main__":
    main()
