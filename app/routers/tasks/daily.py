"""今日任务面板与手动确认/补签发起相关端点（/daily*）"""
from datetime import date

from fastapi import Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from . import router
from .common import *
from app.database import get_db
from app.services.parent_guard import ensure_parent_pwd
from app.models.makeup_card import MakeupCard, MakeupUsageLog
from app.models.daily_task import DailyTask


class ClaimRequest(BaseModel):
    """家长手动确认完成任务请求体：用户 ID，优先按 task_id 确认，兼容按 subject 确认强制任务。"""
    user_id: str
    subject: str = None
    task_id: int = None


class ChildSubmitRequest(BaseModel):
    """孩子提交任务完成申请请求体：用户 ID 与任务 ID（置为待家长确认）。"""
    user_id: str
    task_id: int


@router.get("/daily", summary="今日任务（3强制+3可选）")
def get_daily(user_id: str = Query(...), db: Session = Depends(get_db)):
    """返回今日任务面板（3 强制 + N 可选）。

    内部：确保今日任务行存在 → 按真实学习数据计算进度并自动完成非手动任务 →
         可选任务全完成发补签卡 → 强制全勤累计卡券 → 组装返回（含连续天数/补签卡余额）。
    参数（Query）：user_id。
    返回：{date, tasks[], mandatory_done/total, optional_done/total, streak_days, makeup_cards, ...}。
    副作用：可能更新 DailyTask 状态、发放补签卡、累计卡券进度。无需家长密码。
    """
    return _build_payload(db, user_id)


@router.post("/daily/child_submit", summary="孩子提交完成申请（待家长确认）")
def child_submit_task(req: ChildSubmitRequest, db: Session = Depends(get_db)):
    """孩子点击完成按钮，状态变为 pending_confirm，等家长确认"""
    today = date.today()
    row = db.query(DailyTask).filter(
        DailyTask.id == req.task_id, DailyTask.user_id == req.user_id,
        DailyTask.task_date == today).first()
    if not row:
        raise HTTPException(404, "未找到该任务")
    if row.status == "done":
        return _build_payload(db, req.user_id)
    if row.status == "pending_confirm":
        return _build_payload(db, req.user_id)
    row.status = "pending_confirm"
    row.progress = row.target
    db.commit()
    return _build_payload(db, req.user_id)


class MakeupCompleteRequest(BaseModel):
    """孩子用补签卡完成某任务请求体：用户 ID 与任务 ID（扣卡后生成待确认记录）。"""
    user_id: str
    task_id: int


@router.post("/daily/makeup_complete", summary="孩子发起：用补签卡完成任意任务（待家长确认）")
def makeup_complete_task(req: MakeupCompleteRequest, db: Session = Depends(get_db)):
    """孩子发起用补签卡完成某任务：立即扣卡并生成 pending 记录，任务暂不完成。

    需家长在「家长面板」确认后生效；家长拒绝则退回补签卡、任务保持不变。
    """
    today = date.today()
    row = db.query(DailyTask).filter(
        DailyTask.id == req.task_id, DailyTask.user_id == req.user_id,
        DailyTask.task_date == today).first()
    if not row:
        raise HTTPException(404, "未找到该任务")
    if row.status == "done":
        return _build_payload(db, req.user_id)
    # 同一任务已有待确认补签 → 不允许重复发起
    exist = db.query(MakeupUsageLog).filter(
        MakeupUsageLog.user_id == req.user_id,
        MakeupUsageLog.task_id == req.task_id,
        MakeupUsageLog.status == "pending",
    ).first()
    if exist:
        raise HTTPException(400, "该任务已有待确认的补签申请")
    # 检查补签卡余额
    balance = _get_makeup_balance(db, req.user_id)
    if balance <= 0:
        raise HTTPException(400, "没有可用的补签卡")
    # 立即扣卡
    card = db.query(MakeupCard).filter(MakeupCard.user_id == req.user_id).first()
    card.balance -= 1
    card.total_used += 1
    # 生成待确认记录（任务暂不完成）
    log = MakeupUsageLog(
        user_id=req.user_id, target_date=today,
        task_id=req.task_id, status="pending",
    )
    db.add(log)
    db.commit()
    return _build_payload(db, req.user_id)


@router.post("/daily/claim", summary="手动确认完成任务（需家长密码）")
def claim_task(req: ClaimRequest, request: Request, db: Session = Depends(get_db)):
    """家长手动确认完成一个手动任务（可选任务/家长自定义任务）。

    参数（Body）：user_id、task_id（优先）或 subject（兼容旧逻辑按学科确认强制任务）。
    请求头：必须携带 X-Parent-Pwd（ensure_parent_pwd，否则 403）——孩子不得自批。
    返回：刷新后的今日任务面板（_build_payload）。
    副作用：将对应 DailyTask 置 done 并发放金币 +5（仅手动类任务）；自动判定类任务拒绝手动确认。
    需要家长密码。
    """
    # 防刷：手动确认属于家长权限，孩子不得自批
    ensure_parent_pwd(db, req.user_id, request)
    today = date.today()
    row = None
    if req.task_id:
        # 按任务 id 精确确认（支持手动可选任务、家长自定义任务——同一学科可有多个）
        row = db.query(DailyTask).filter(
            DailyTask.id == req.task_id, DailyTask.user_id == req.user_id,
            DailyTask.task_date == today).first()
    else:
        if not req.subject:
            raise HTTPException(400, "需要提供 subject 或 task_id")
        # 兼容旧逻辑：按学科确认该科强制任务（每科默认唯一）
        rows = db.query(DailyTask).filter(
            DailyTask.user_id == req.user_id, DailyTask.task_date == today,
            DailyTask.subject == req.subject, DailyTask.task_type == "mandatory",
        ).all()
        row = rows[0] if rows else None
    if not row:
        raise HTTPException(404, "未找到该任务")
    if not row.manual:
        raise HTTPException(400, "该任务由学习数据自动判定，无需手动确认")
    if row.status == "done":
        return _build_payload(db, req.user_id)
    row.progress = row.target
    row.status = "done"
    # 心愿进度仅统计可选任务，强制任务手动确认不计入
    try:
        from app.routers.pet import _grant_coins
        _grant_coins(db, req.user_id, 5, "完成任务")
    except Exception:
        pass
    db.commit()
    return _build_payload(db, req.user_id)


__all__ = ["ClaimRequest", "ChildSubmitRequest", "MakeupCompleteRequest",
           "get_daily", "child_submit_task", "makeup_complete_task", "claim_task"]
