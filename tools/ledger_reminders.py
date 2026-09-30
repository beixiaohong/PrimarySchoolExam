# -*- coding: utf-8 -*-
"""账本提醒生产者（M4）：落库三类提醒到 NotificationLog，前端轮询展示，不接短信/邮件。

由 tools/scheduler.py 每日 08:00 调用（ledger_reminders_daily 任务）。三类提醒：
1. 记账提醒：用户当天无任何记账（收入/支出/转账）时，提醒「今天还没记账哦」；
2. 周期交易到期前 1 天提醒：is_active 且 next_run 落在 [now, now+1天) 的周期交易；
3. 信用卡还款日提醒：credit_card 账户且 due_day == 今天几号。

幂等：每条提醒按「用户 + 当天 + 内容」去重，重跑不会产生重复打扰。
"""
import json
import os
import sys
from datetime import datetime, timedelta, date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal
from app.models import ledger as model_ledger
from app.models.user import User


def _today_window(now: datetime):
    today_start = datetime.combine(now.date(), datetime.min.time())
    tomorrow_start = today_start + timedelta(days=1)
    return today_start, tomorrow_start


def _dedup_exists(db, uid, content: dict, today_start: datetime) -> bool:
    """同用户同天同内容的提醒是否已存在（避免重复）。"""
    content_str = json.dumps(content, ensure_ascii=False, sort_keys=True)
    return db.query(model_ledger.NotificationLog).filter(
        model_ledger.NotificationLog.user_id == uid,
        model_ledger.NotificationLog.period_start == today_start,
        model_ledger.NotificationLog.report_content == content_str,
    ).first() is not None


def _push(db, uid, content: dict, today_start: datetime, tomorrow_start: datetime, now: datetime) -> bool:
    """落一条 pending 提醒（去重）。返回是否新写入。"""
    if _dedup_exists(db, uid, content, today_start):
        return False
    db.add(model_ledger.NotificationLog(
        user_id=uid,
        report_period=model_ledger.ReportPeriod.MONTHLY,
        period_start=today_start,
        period_end=tomorrow_start - timedelta(seconds=1),
        report_content=json.dumps(content, ensure_ascii=False, sort_keys=True),
        status=model_ledger.NotificationStatus.PENDING,
    ))
    return True


def generate_user_reminders(db, uid: str, now: datetime) -> int:
    """为单个用户生成当日提醒，返回新写入条数。"""
    today_start, tomorrow_start = _today_window(now)
    count = 0

    # 1) 记账提醒：当天无记账则提醒
    has_tx = db.query(model_ledger.Bill).filter(
        model_ledger.Bill.user_id == uid,
        model_ledger.Bill.transaction_time >= today_start,
        model_ledger.Bill.transaction_time < tomorrow_start,
    ).first()
    if not has_tx:
        if _push(db, uid, {"kind": "daily_record", "message": "今天还没记账哦，随手记一笔吧~"},
                 today_start, tomorrow_start, now):
            count += 1

    # 2) 周期交易到期前 1 天提醒
    due_soon = db.query(model_ledger.RecurringTransaction).filter(
        model_ledger.RecurringTransaction.user_id == uid,
        model_ledger.RecurringTransaction.is_active == True,  # noqa: E712
        model_ledger.RecurringTransaction.next_run >= now,
        model_ledger.RecurringTransaction.next_run < now + timedelta(days=1),
    ).all()
    for rt in due_soon:
        if _push(db, uid, {"kind": "recurring_due", "recurring_id": rt.id, "name": rt.name,
                           "amount": float(rt.amount), "next_run": rt.next_run.isoformat()},
                 today_start, tomorrow_start, now):
            count += 1

    # 3) 信用卡还款日提醒（按当月 due_day 落在今天）
    cards = db.query(model_ledger.Account).filter(
        model_ledger.Account.user_id == uid,
        model_ledger.Account.account_type == model_ledger.AccountType.CREDIT_CARD,
        model_ledger.Account.due_day == now.day,
    ).all()
    for card in cards:
        if _push(db, uid, {"kind": "credit_card_due", "account_id": card.id,
                           "account_name": card.account_name, "due_day": card.due_day},
                 today_start, tomorrow_start, now):
            count += 1

    return count


def run_ledger_reminders(db) -> dict:
    """遍历全量用户生成提醒（供 scheduler 调用）。返回 {scanned, created}。"""
    now = datetime.now()
    users = db.query(User.user_id).all()
    created = 0
    for (uid,) in users:
        created += generate_user_reminders(db, uid, now)
    db.commit()
    return {"scanned": len(users), "created": created}


def main():
    db = SessionLocal()
    try:
        result = run_ledger_reminders(db)
        print("[ledger-reminders] scanned={scanned} created={created}".format(**result))
    finally:
        db.close()


if __name__ == "__main__":
    main()
