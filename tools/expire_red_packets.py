#!/usr/bin/env python3
"""红包过期原路退回：扫描 24h 到期红包，把剩余钻石退回发送者。

由 tools/scheduler.py 每日凌晨调用（与账本周期交易错峰 10 分钟）。
详见 docs/IM与账本前端实现方案.md §4.6.4（B12）。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal
from app.domains.frozen.services.red_packet_expire import expire_red_packets


def main():
    db = SessionLocal()
    try:
        stat = expire_red_packets(db)
        print(f"[red-packet-expire] 到期 {stat['scanned']} 个，退回 {stat['refunded']} 个，"
              f"失败 {stat['failed']} 个")
    finally:
        db.close()


if __name__ == "__main__":
    main()
