"""补签卡业务逻辑层（makeup.py 路由瘦身后的纯逻辑层）

设计：路由文件只做「参数解析 + 调业务函数 + 返回」，本模块承载补签卡全部业务规则：
- use_makeup_card：孩子用 1 张补签卡把某过去日期补成全勤（立即生效）
- confirm_makeup  ：家长确认/拒绝补签申请（confirm 生效并奖励，reject 退卡）
- list_pending    ：家长面板待确认申请列表

与 service.py 的底层小函数（_get_makeup_balance/_has_makeup_card/_grant_makeup_card/_is_full_day）
同属补签卡域：本模块负责「一次业务操作」粒度，service.py 负责「可复用小函数」。
状态机统一为 pending/confirmed/rejected（与 TaskConfirm 一致，见 051 迁移）。
"""
from datetime import date

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.daily_task import DailyTask
from app.models.makeup_card import MakeupCard, MakeupUsageLog
from .service import _get_makeup_balance, _has_makeup_card


def use_makeup_card(db: Session, user_id: str, target_date: str) -> dict:
    """孩子直接补签过去某天为全勤（立即生效，扣 1 张补签卡）。

    校验：日期格式合法、必须早于今天；余额 > 0；该日期未补签过。
    副作用：写 MakeupUsageLog（默认 confirmed，补签某天即生效）、扣 card.balance。
    返回：{balance, target_date, message}。
    """
    if not user_id or not target_date:
        raise HTTPException(400, "需要 user_id 和 target_date")
    try:
        d = date.fromisoformat(target_date)
    except ValueError:
        raise HTTPException(400, "日期格式错误，用 YYYY-MM-DD")
    if d >= date.today():
        raise HTTPException(400, "只能补签过去的日期")
    balance = _get_makeup_balance(db, user_id)
    if balance <= 0:
        raise HTTPException(400, "没有可用的补签卡")
    if _has_makeup_card(db, user_id, d):
        raise HTTPException(400, "该日期已补签过")
    log = MakeupUsageLog(user_id=user_id, target_date=d)
    db.add(log)
    card = db.query(MakeupCard).filter(MakeupCard.user_id == user_id).first()
    card.balance -= 1
    card.total_used += 1
    db.commit()
    return {"balance": card.balance, "target_date": target_date, "message": "补签成功！当天算全勤"}


def confirm_makeup(db: Session, user_id: str, log_id: int, action: str) -> dict:
    """家长对「孩子发起的补签卡完成任务」进行最终确认或拒绝。

    - confirm：补签生效，关联任务标记完成并发放金币 +5；
    - reject ：补签卡退回（余额 +1、已用 -1），关联任务保持原状。
    校验：记录存在、仍为 pending（否则 400「已处理」）。
    返回：{status, message}。
    """
    log = db.query(MakeupUsageLog).filter(
        MakeupUsageLog.id == log_id, MakeupUsageLog.user_id == user_id).first()
    if not log:
        raise HTTPException(404, "未找到补签记录")
    if log.status != "pending":
        raise HTTPException(400, "该补签记录已处理")
    card = db.query(MakeupCard).filter(MakeupCard.user_id == user_id).first()

    if action == "confirm":
        log.status = "confirmed"
        if log.task_id:
            row = db.query(DailyTask).filter(DailyTask.id == log.task_id).first()
            if row and row.status != "done":
                row.progress = row.target
                row.status = "done"
                try:
                    from app.domains.engagement.contracts import PetService
                    PetService.grant_coins(db, user_id, 5, "使用补签卡完成任务")
                except Exception:
                    pass
        db.commit()
        return {"status": "confirmed", "message": "补签已生效，任务完成 ✅"}
    elif action == "reject":
        log.status = "rejected"
        if card:
            card.balance += 1
            card.total_used = max(0, card.total_used - 1)
        db.commit()
        return {"status": "rejected", "message": "已拒绝，补签卡已退回 🔄"}
    else:
        raise HTTPException(400, "action 只能是 confirm 或 reject")


def list_pending_makeup(db: Session, user_id: str) -> list:
    """家长面板拉取孩子发起的、待确认的补签申请列表。

    返回：[{log_id, task_id, task_title, target_date, used_at}]（倒序）。
    """
    logs = db.query(MakeupUsageLog).filter(
        MakeupUsageLog.user_id == user_id,
        MakeupUsageLog.status == "pending",
    ).order_by(MakeupUsageLog.used_at.desc()).all()
    items = []
    for l in logs:
        title = ""
        if l.task_id:
            row = db.query(DailyTask).filter(DailyTask.id == l.task_id).first()
            title = row.title if row else ""
        items.append({
            "log_id": l.id,
            "task_id": l.task_id,
            "task_title": title,
            "target_date": str(l.target_date),
            "used_at": str(l.used_at),
        })
    return items
