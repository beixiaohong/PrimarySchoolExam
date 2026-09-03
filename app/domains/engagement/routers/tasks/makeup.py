"""补签卡相关端点（/makeup/*）——薄路由层

业务逻辑见 makeup_service.py（本模块只做参数解析与转发）。
"""
from fastapi import Body, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from . import router
from .service import _get_makeup_balance
from .makeup_service import use_makeup_card as _use_makeup_card
from .makeup_service import confirm_makeup as _confirm_makeup
from .makeup_service import list_pending_makeup as _list_pending_makeup
from app.database import get_db
from app.domains.identity.contracts import ensure_parent_pwd


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
    return _use_makeup_card(db, req.get("user_id", "").strip(), req.get("target_date", ""))


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
    return _confirm_makeup(db, req.user_id, req.log_id, req.action)


@router.get("/makeup/pending", summary="查询待家长确认的补签申请")
def list_pending_makeup(user_id: str = Query(...), db: Session = Depends(get_db)):
    """家长面板拉取孩子发起的、待确认的补签申请列表"""
    return {"items": _list_pending_makeup(db, user_id)}


__all__ = ["MakeupConfirmRequest", "use_makeup_card", "get_makeup_balance",
           "confirm_makeup", "list_pending_makeup"]
