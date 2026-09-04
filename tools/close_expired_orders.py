#!/usr/bin/env python3
"""超时关单：扫描 PENDING_PAYMENT 且 expire_at < now 的订单，置 CLOSED(timeout)。

由 tools/scheduler.py 每 5 分钟调用（线上 crontab 驱动）。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal
from app.domains.commerce.services.order_service import OrderService


def main():
    db = SessionLocal()
    try:
        n = OrderService.scan_expired_orders(db)
        if n:
            print(f"[close_expired-orders] 关闭 {n} 笔超时订单")
        else:
            print("[close-expired-orders] 无超时订单")
    finally:
        db.close()


if __name__ == "__main__":
    main()
