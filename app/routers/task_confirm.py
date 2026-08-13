"""完成确认接口：孩子提交任务完成 → 家长确认/拒绝（含理由）

设计：
- /create ：孩子端调用（无需家长密码），生成一条 pending 确认请求；同用户同类型当天已有 pending 时改为更新，避免重复刷屏。
- /list  ：孩子端调用（无需家长密码），返回该用户全部确认记录（首页「完成确认」区块展示）。
- /resolve：家长端调用（需家长密码，由 X-Parent-Pwd 头校验），approve 通过 / reject 拒绝（必须填写理由）。
"""
from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.task_confirm import TaskConfirm
from ..services.parent_guard import ensure_parent_pwd

router = APIRouter()

MAX_SUMMARY = 255
MAX_REASON = 255


def _serialize(c: TaskConfirm) -> dict:
    return {
        "id": c.id,
        "user_id": c.user_id,
        "task_type": c.task_type,
        "title": c.title,
        "summary": c.summary,
        "status": c.status,
        "reject_reason": c.reject_reason or "",
        "created_at": str(c.created_at)[:16] if c.created_at else "",
        "resolved_at": str(c.resolved_at)[:16] if c.resolved_at else "",
    }


class CreateReq(BaseModel):
    user_id: str
    task_type: str = "recite"
    title: str = "学习任务完成"
    summary: str = ""


class ResolveReq(BaseModel):
    user_id: str
    id: int
    action: str          # approve / reject
    reject_reason: str = ""


@router.post("/create", summary="孩子提交任务完成，生成待家长确认记录")
def create_confirm(req: CreateReq, db: Session = Depends(get_db)):
    """孩子完成学习任务（如背诵）后提交，生成一条 pending 确认请求。

    参数（Body）：user_id、task_type（recite_word/recite_text/daily）、title、summary。
    去重：同用户同类型、且创建于今天的 pending 记录若存在，则更新其 summary/title/created_at，
          避免反复刷屏；否则新建。
    返回：{id, status, created_at}。无需家长密码（孩子端）。
    """
    uid = (req.user_id or "").strip()
    if not uid:
        raise HTTPException(400, "user_id 不能为空")
    today = date.today()
    existing = db.query(TaskConfirm).filter(
        TaskConfirm.user_id == uid,
        TaskConfirm.task_type == req.task_type,
        TaskConfirm.status == "pending",
        TaskConfirm.created_at >= datetime.combine(today, datetime.min.time()),
    ).first()
    if existing:
        existing.title = (req.title or "学习任务完成")[:100]
        existing.summary = (req.summary or "")[:MAX_SUMMARY]
        existing.created_at = datetime.now()
        db.commit()
        return _serialize(existing)

    c = TaskConfirm(
        user_id=uid,
        task_type=req.task_type,
        title=(req.title or "学习任务完成")[:100],
        summary=(req.summary or "")[:MAX_SUMMARY],
        status="pending",
    )
    db.add(c)
    db.commit()
    db.refresh(c)
    return _serialize(c)


@router.get("/list", summary="查询孩子的任务完成确认记录（首页展示）")
def list_confirms(user_id: str = "", limit: int = 200, offset: int = 0,
                  db: Session = Depends(get_db)):
    """返回该用户确认记录（倒序），供首页「完成确认」区块展示；支持分页与 total。

    参数（Query）：user_id、limit（默认 200，上限 500）、offset（默认 0）。
    返回：{items[{id, task_type, title, summary, status, reject_reason, created_at, resolved_at}], total}。
    副作用：无（只读）。无需家长密码。
    """
    uid = (user_id or "").strip()
    if not uid:
        return {"items": [], "total": 0}
    q = db.query(TaskConfirm).filter(TaskConfirm.user_id == uid)
    total = q.count()
    rows = q.order_by(TaskConfirm.created_at.desc()).offset(offset).limit(min(limit, 500)).all()
    return {"items": [_serialize(r) for r in rows], "total": total}


@router.post("/resolve", summary="家长确认/拒绝孩子的任务完成（需家长密码）")
def resolve_confirm(req: ResolveReq, request: Request, db: Session = Depends(get_db)):
    """家长对一条 pending 确认请求进行最终处理。

    - approve：状态置 approved（家长已通过）。
    - reject ：状态置 rejected，必须填写 reject_reason（家长拒绝理由）。
    需家长密码（由 http.js 自动附加 X-Parent-Pwd，服务端 ensure_parent_pwd 校验）。
    返回：{id, status, reject_reason}；记录不存在 404、已处理 400、reject 缺理由 400。
    """
    ensure_parent_pwd(db, req.user_id, request)
    c = db.query(TaskConfirm).filter(
        TaskConfirm.id == req.id, TaskConfirm.user_id == req.user_id).first()
    if not c:
        raise HTTPException(404, "未找到确认记录")
    if c.status != "pending":
        raise HTTPException(400, "该记录已被处理")

    if req.action == "approve":
        c.status = "approved"
        c.resolved_at = datetime.now()
        db.commit()
        return {"id": c.id, "status": "approved", "reject_reason": ""}
    elif req.action == "reject":
        reason = (req.reject_reason or "").strip()
        if not reason:
            raise HTTPException(400, "拒绝必须填写理由")
        c.status = "rejected"
        c.reject_reason = reason[:MAX_REASON]
        c.resolved_at = datetime.now()
        db.commit()
        return {"id": c.id, "status": "rejected", "reject_reason": c.reject_reason}
    else:
        raise HTTPException(400, "action 只能是 approve 或 reject")
