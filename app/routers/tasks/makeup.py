"""补签卡相关端点（/makeup/*）"""
from datetime import date

from fastapi import Body, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from . import router
from .service import _get_makeup_balance, _has_makeup_card
from app.database import get_db
from app.services.parent_guard import ensure_parent_pwd
from app.models.makeup_card import MakeupCard, MakeupUsageLog
from app.models.daily_task import DailyTask


class MakeupConfirmRequest(BaseModel):
    """家长确认/拒绝补签卡使用请求体：用户 ID、补签记录 ID 与 action（confirm/reject）。"""
    user_id: str
    log_id: int
    action: str  # confirm / reject


@router.post("/makeup/use", summary="使用补签卡补签某天")
def use_makeup_card(
    req: dict = Body(...),
    db: Session = Depends(get_db),
):
    """孩子直接补签过去某天为全勤（立即生效，扣 1 张补签卡）。

    参数（Body）：user_id、target_date（YYYY-MM-DD，必须早于今天）。
    返回：{balance, target_date, message}；余额不足/已补签过/日期非法或未来 返回 400。
    副作用：写 MakeupUsageLog（默认confirmed，计入连续天数/全勤）、扣 card.balance。
    无需家长密码（补签仅作用于过去日期）。
    """
    user_id = req.get("user_id", "").strip()
    target = req.get("target_date", "")
    if not user_id or not target:
        raise HTTPException(400, "需要 user_id 和 target_date")
    try:
        d = date.fromisoformat(target)
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
    return {"balance": card.balance, "target_date": target, "message": "补签成功！当天算全勤"}


@router.get("/makeup/balance", summary="查询补签卡余额")
def get_makeup_balance(user_id: str = Query(...), db: Session = Depends(get_db)):
    """查询补签卡余额。

    参数（Query）：user_id。
    返回：{user_id, balance}（无记录则 0）。
    副作用：无（只读）。无需家长密码。
    """
    return {"user_id": user_id, "balance": _get_makeup_balance(db, user_id)}


@router.post("/makeup/confirm", summary="家长确认/拒绝补签卡使用")
def confirm_makeup(req: MakeupConfirmRequest, request: Request, db: Session = Depends(get_db)):
    """家长对「孩子发起的补签卡完成任务」进行最终确认或拒绝。

    - confirm：补签生效，关联任务标记为完成并发放金币；
    - reject ：补签卡退回（余额 +1、已用 -1），关联任务保持原状。
    需家长密码（由 http.js 自动附加 X-Parent-Pwd）。
    """
    ensure_parent_pwd(db, req.user_id, request)
    log = db.query(MakeupUsageLog).filter(
        MakeupUsageLog.id == req.log_id, MakeupUsageLog.user_id == req.user_id).first()
    if not log:
        raise HTTPException(404, "未找到补签记录")
    if log.status != "pending":
        raise HTTPException(400, "该补签记录已处理")
    card = db.query(MakeupCard).filter(MakeupCard.user_id == req.user_id).first()

    if req.action == "confirm":
        log.status = "confirmed"
        if log.task_id:
            row = db.query(DailyTask).filter(DailyTask.id == log.task_id).first()
            if row and row.status != "done":
                row.progress = row.target
                row.status = "done"
                try:
                    from app.routers.pet import _grant_coins
                    _grant_coins(db, req.user_id, 5, "使用补签卡完成任务")
                except Exception:
                    pass
        db.commit()
        return {"status": "confirmed", "message": "补签已生效，任务完成 ✅"}
    elif req.action == "reject":
        log.status = "rejected"
        if card:
            card.balance += 1
            card.total_used = max(0, card.total_used - 1)
        db.commit()
        return {"status": "rejected", "message": "已拒绝，补签卡已退回 🔄"}
    else:
        raise HTTPException(400, "action 只能是 confirm 或 reject")


@router.get("/makeup/pending", summary="查询待家长确认的补签申请")
def list_pending_makeup(user_id: str = Query(...), db: Session = Depends(get_db)):
    """家长面板拉取孩子发起的、待确认的补签申请列表"""
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
    return {"items": items}


__all__ = ["MakeupConfirmRequest", "use_makeup_card", "get_makeup_balance",
           "confirm_makeup", "list_pending_makeup"]
