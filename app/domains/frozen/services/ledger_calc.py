"""账本余额/周期/报告计算工具（从 router 层抽离的纯函数）。

原位于 app/domains/frozen/routers/ledger.py（D9 冻结域 God-file），Tier 2 拆分时
抽到本模块以缩小 router 体积。均为纯逻辑：仅依赖传入的 db session，无模块级状态、
无副作用，行为与原实现完全一致。

调用方（ledger.py / ledger_recurring.py）通过
    from app.domains.frozen.services.ledger_calc import (
        _adjust_balance, _advance_next_run, generate_financial_report)
引用，函数名保持不变，对端点调用透明。
"""
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta, date
from decimal import Decimal
from calendar import monthrange

from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models import ledger as model_ledger


def _adjust_balance(db: Session, transaction_type, amount, from_account_id,
                    to_account_id=None, multiplier: int = 1):
    """按交易类型调整账户余额（带行锁，防并发丢失更新）。

    multiplier=1 应用交易影响；multiplier=-1 撤销交易影响。
    逻辑与账本原实现保持一致：
    - 支出：from_account.balance -= amount
    - 收入：from_account.balance += amount
    - 转账：from_account.balance -= amount, to_account.balance += amount

    账户行用 with_for_update() 加锁，并按 id 升序统一锁定（from/to 去重后排序），
    避免并发转账因加锁顺序不一致导致死锁；转账两账户一减一增，总资产负债守恒。

    注：balance 列为 Numeric(15,2)，MySQL 驱动返回 Decimal；amount 为 float，
    直接混算会 TypeError，故统一转 Decimal（经 str 避免浮点尾差）后运算。
    """
    delta = Decimal(str(amount)) * multiplier
    t = transaction_type

    # 收集需锁定的账户 id（去重 + 升序，保证全局一致的加锁顺序）
    lock_ids = sorted({aid for aid in (from_account_id, to_account_id) if aid is not None})
    accounts = {
        a.id: a
        for a in db.query(model_ledger.Account)
        .filter(model_ledger.Account.id.in_(lock_ids))
        .with_for_update()
        .all()
    } if lock_ids else {}

    from_account = accounts.get(from_account_id)
    if from_account is None:
        return
    to_account = accounts.get(to_account_id) if to_account_id is not None else None

    if t == model_ledger.TransactionType.EXPENSE:
        from_account.balance -= delta
    elif t == model_ledger.TransactionType.INCOME:
        from_account.balance += delta
    elif t == model_ledger.TransactionType.TRANSFER:
        from_account.balance -= delta
        if to_account is not None:
            to_account.balance += delta


def _advance_next_run(next_run: datetime, frequency: str, now: datetime) -> datetime:
    """根据频率把 next_run 推进到未来时间（处理漏跑的情况）。

    使用真实月/年推进（替代原 +30 / +365 天的近似，消除月末漂移与闰年误差）：
    - weekly  ：+7 天
    - monthly ：月份 +1，日夹紧到目标月最后一天（如 1/31 → 2/28；闰年 2/29 → 2/29）
    - yearly  ：年份 +1，月日不变、日夹紧到目标年该月最后一天（2/29 → 2/28）
    - 其它    ：+1 天（兜底，正常不会命中）
    """
    while next_run <= now:
        if frequency == "weekly":
            next_run = next_run + timedelta(weeks=1)
        elif frequency == "monthly":
            y, m = next_run.year, next_run.month
            ny, nm = (y + 1, 1) if m == 12 else (y, m + 1)
            last_day = monthrange(ny, nm)[1]
            nd = min(next_run.day, last_day)
            next_run = next_run.replace(year=ny, month=nm, day=nd)
        elif frequency == "yearly":
            ny = next_run.year + 1
            last_day = monthrange(ny, next_run.month)[1]
            nd = min(next_run.day, last_day)
            next_run = next_run.replace(year=ny, day=nd)
        else:
            next_run = next_run + timedelta(days=1)
    return next_run


def generate_financial_report(db: Session, user_id: str,
                              period_start: datetime, period_end: datetime,
                              period_type: str) -> Dict[str, Any]:
    """生成财务周期报告数据（返回 dict，不发邮件）。

    统计区间 [period_start, period_end]，并与上一周期对比（环比）。
    """
    current_income = db.query(func.sum(model_ledger.Bill.amount)).filter(
        model_ledger.Bill.user_id == user_id,
        model_ledger.Bill.transaction_type == model_ledger.TransactionType.INCOME,
        model_ledger.Bill.transaction_time >= period_start,
        model_ledger.Bill.transaction_time <= period_end
    ).scalar() or 0

    current_expense = db.query(func.sum(model_ledger.Bill.amount)).filter(
        model_ledger.Bill.user_id == user_id,
        model_ledger.Bill.transaction_type == model_ledger.TransactionType.EXPENSE,
        model_ledger.Bill.transaction_time >= period_start,
        model_ledger.Bill.transaction_time <= period_end
    ).scalar() or 0

    net_income = current_income - current_expense

    current_balance = db.query(func.sum(model_ledger.Account.balance)).filter(
        model_ledger.Account.user_id == user_id
    ).scalar() or 0

    top_expense_categories = db.query(
        model_ledger.Category.level1,
        model_ledger.Category.level2,
        model_ledger.Category.level3,
        func.sum(model_ledger.Bill.amount).label('amount'),
        func.count(model_ledger.Bill.id).label('count')
    ).join(
        model_ledger.Bill, model_ledger.Bill.category_id == model_ledger.Category.id
    ).filter(
        model_ledger.Bill.user_id == user_id,
        model_ledger.Bill.transaction_type == model_ledger.TransactionType.EXPENSE,
        model_ledger.Bill.transaction_time >= period_start,
        model_ledger.Bill.transaction_time <= period_end
    ).group_by(
        model_ledger.Category.level1, model_ledger.Category.level2, model_ledger.Category.level3
    ).order_by(
        func.sum(model_ledger.Bill.amount).desc()
    ).limit(5).all()

    top_income_categories = db.query(
        model_ledger.Category.level1,
        model_ledger.Category.level2,
        model_ledger.Category.level3,
        func.sum(model_ledger.Bill.amount).label('amount'),
        func.count(model_ledger.Bill.id).label('count')
    ).join(
        model_ledger.Bill, model_ledger.Bill.category_id == model_ledger.Category.id
    ).filter(
        model_ledger.Bill.user_id == user_id,
        model_ledger.Bill.transaction_type == model_ledger.TransactionType.INCOME,
        model_ledger.Bill.transaction_time >= period_start,
        model_ledger.Bill.transaction_time <= period_end
    ).group_by(
        model_ledger.Category.level1, model_ledger.Category.level2, model_ledger.Category.level3
    ).order_by(
        func.sum(model_ledger.Bill.amount).desc()
    ).limit(5).all()

    if period_type == "weekly":
        prev_start = period_start - timedelta(weeks=1)
        prev_end = period_end - timedelta(weeks=1)
    elif period_type == "monthly":
        prev_start = period_start - timedelta(days=30)
        prev_end = period_end - timedelta(days=30)
    else:  # yearly
        prev_start = period_start - timedelta(days=365)
        prev_end = period_end - timedelta(days=365)

    prev_income = db.query(func.sum(model_ledger.Bill.amount)).filter(
        model_ledger.Bill.user_id == user_id,
        model_ledger.Bill.transaction_type == model_ledger.TransactionType.INCOME,
        model_ledger.Bill.transaction_time >= prev_start,
        model_ledger.Bill.transaction_time <= prev_end
    ).scalar() or 0

    prev_expense = db.query(func.sum(model_ledger.Bill.amount)).filter(
        model_ledger.Bill.user_id == user_id,
        model_ledger.Bill.transaction_type == model_ledger.TransactionType.EXPENSE,
        model_ledger.Bill.transaction_time >= prev_start,
        model_ledger.Bill.transaction_time <= prev_end
    ).scalar() or 0

    income_change = ((current_income - prev_income) / prev_income * 100) if prev_income > 0 else 0
    expense_change = ((current_expense - prev_expense) / prev_expense * 100) if prev_expense > 0 else 0

    return {
        "period_type": period_type,
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "current_data": {
            "total_income": float(current_income),
            "total_expense": float(current_expense),
            "net_income": float(net_income),
            "account_balance": float(current_balance)
        },
        "top_expense_categories": [
            {
                "category": f"{cat.level1} > {cat.level2} > {cat.level3}",
                "amount": float(cat.amount),
                "count": cat.count,
                "percentage": round(float(cat.amount) / float(current_expense) * 100, 2) if current_expense > 0 else 0
            }
            for cat in top_expense_categories
        ],
        "top_income_categories": [
            {
                "category": f"{cat.level1} > {cat.level2} > {cat.level3}",
                "amount": float(cat.amount),
                "count": cat.count,
                "percentage": round(float(cat.amount) / float(current_income) * 100, 2) if current_income > 0 else 0
            }
            for cat in top_income_categories
        ],
        "comparison": {
            "prev_income": float(prev_income),
            "prev_expense": float(prev_expense),
            "income_change": round(income_change, 2),
            "expense_change": round(expense_change, 2),
            "income_change_amount": float(current_income - prev_income),
            "expense_change_amount": float(current_expense - prev_expense)
        }
    }
