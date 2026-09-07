"""周期交易全量到期执行服务（B9）。

与路由内 POST /recurring/run-due（仅当前登录用户、手动触发）互补：
本服务遍历**全量**启用且到期（next_run <= now）的周期交易，为每条生成账单、
联动账户余额并推进 next_run，供 tools/run_due_recurring.py + scheduler 每日自动执行。

设计要点（见 docs/IM与账本前端实现方案.md §3.5 B9）：
- 复用 routers/ledger.py 的 _adjust_balance / _advance_next_run，保证与手动触发口径一致；
- 幂等：执行后立即推进 next_run 到未来，同一轮内不会重复生成；重跑不产生新账单；
- 单条失败不中断：逐条 commit，异常时 rollback + 记日志 + failed 计数，继续下一条。
"""
import logging
from datetime import datetime

from sqlalchemy.orm import Session

from app.models import ledger as model_ledger
from app.domains.frozen.routers.ledger import _adjust_balance, _advance_next_run

logger = logging.getLogger(__name__)


def run_due_recurring_all(db: Session) -> dict:
    """扫描全量到期周期交易并逐条执行。

    返回 {"scanned": 命中条数, "processed": 成功生成账单数, "failed": 失败条数}。
    """
    now = datetime.now()
    due = db.query(model_ledger.RecurringTransaction).filter(
        model_ledger.RecurringTransaction.is_active == True,  # noqa: E712
        model_ledger.RecurringTransaction.next_run <= now,
    ).all()

    scanned = len(due)
    processed = 0
    failed = 0
    for rt in due:
        try:
            # 账户必须仍属于该用户（可能已被删除）；不存在则本条无法记账。
            from_account = db.query(model_ledger.Account).filter(
                model_ledger.Account.id == rt.from_account_id,
                model_ledger.Account.user_id == rt.user_id,
            ).first()
            if not from_account:
                logger.warning(
                    "[ledger_recurring] rt=%s 账户 %s 不存在，跳过", rt.id, rt.from_account_id
                )
                failed += 1
                db.rollback()
                continue

            bill = model_ledger.Bill(
                user_id=rt.user_id,
                transaction_type=rt.transaction_type,
                amount=rt.amount,
                from_account_id=rt.from_account_id,
                category_id=rt.category_id,
                merchant_id=rt.merchant_id,
                project_id=rt.project_id,
                note=rt.note,
                transaction_time=now,
            )
            db.add(bill)
            db.flush()  # 取得 bill.id

            # 与手动触发端点复用同一套余额更新逻辑
            _adjust_balance(db, rt.transaction_type, rt.amount, rt.from_account_id, None, 1)

            rt.next_run = _advance_next_run(rt.next_run, rt.frequency, now)
            rt.updated_at = now
            db.commit()
            processed += 1
        except Exception:
            db.rollback()
            failed += 1
            logger.exception("[ledger_recurring] rt=%s 执行失败，已跳过", getattr(rt, "id", "?"))

    return {"scanned": scanned, "processed": processed, "failed": failed}
