# -*- coding: utf-8 -*-
"""周期交易每日自动执行：扫描全量到期（is_active 且 next_run <= now）的周期交易并生成账单。

由 tools/scheduler.py 每日 01:00 调用（ledger_recurring_daily 任务）。
幂等：执行后 next_run 已推进到未来，重复运行不会产生重复账单。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal
from app.domains.frozen.services.ledger_recurring import run_due_recurring_all


def main():
    db = SessionLocal()
    try:
        result = run_due_recurring_all(db)
        print(
            "[run-due-recurring] scanned={scanned} processed={processed} failed={failed}".format(**result)
        )
    finally:
        db.close()


if __name__ == "__main__":
    main()
