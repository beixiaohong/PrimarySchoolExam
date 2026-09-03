"""每日任务 · 自定义任务子路由

本模块承载两套「自定义任务」，名称相近但语义完全不同，维护时务必分清：

1. 家长端 /custom-task（**现行**）—— 模型 ParentCustomTask（表 parent_custom_tasks）。
   家长在「任务设置」中定义，注入每日任务的强制/可选区，手动确认完成。
2. 孩子端 /custom（**已废弃 DEPRECATED**）—— 模型 CustomTask（表 custom_tasks）。
   孩子创建、家长确认。现状：web/src 与 admin/src 零引用，库内 custom_tasks 表 0 行。
   代码保留仅为日后可能复活孩子端任务，新需求一律走 /custom-task。

由 tasks 包 include 进主路由，对外路径仍为 /api/tasks/custom、/api/tasks/custom-task，
对调用方零影响。
"""
from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ...database import get_db
from app.domains.identity.services.parent_guard import ensure_parent_pwd
from ...models.custom_task import CustomTask
from ...models.parent_custom_task import ParentCustomTask
from ...models.daily_task import DailyTask
from .constants import MAX_TARGET

router = APIRouter()


# ═══════════ 孩子端自定义任务（DEPRECATED 已废弃，代码保留待复活） ═══════════
# 废弃原因：前端 web/src 与 admin/src 均无引用，库内 custom_tasks 表 0 行（无历史数据）。
# 现状：保留但不再迭代；新需求一律使用下方「家长自定义任务」/custom-task 系列。
# 复活方式：模型 CustomTask 与表 custom_tasks 均保留，直接复用本段端点即可。


class CustomTaskCreate(BaseModel):
    user_id: str
    title: str
    subject: str = "其他"


class CustomTaskAction(BaseModel):
    task_id: int


@router.post("/custom", summary="孩子创建自定义任务")
def create_custom_task(req: CustomTaskCreate, db: Session = Depends(get_db)):
    """孩子创建自定义任务（待家长确认）。

    参数（Body）：user_id、title、subject（默认其他）。
    返回：{id, title, status: "pending"}；title 为空返回 400。
    副作用：写 CustomTask（status=pending）。无需家长密码。
    """
    if not req.title.strip():
        raise HTTPException(400, "任务标题不能为空")
    task = CustomTask(
        user_id=req.user_id,
        title=req.title.strip()[:100],
        subject=req.subject or "其他",
        status="pending",
    )
    db.add(task)
    db.commit()
    return {"id": task.id, "title": task.title, "status": task.status}


@router.get("/custom", summary="查看自定义任务列表")
def list_custom_tasks(
    user_id: str = Query(...),
    status: str = Query(None, description="pending/confirmed/rejected，不传返回全部"),
    db: Session = Depends(get_db),
):
    """查看孩子的自定义任务列表（按状态过滤，最多 50 条倒序）。

    参数（Query）：user_id、status（可选）。
    返回：自定义任务数组（含 id/title/subject/status/created_at/confirmed_at）。
    副作用：无（只读）。无需家长密码。
    """
    q = db.query(CustomTask).filter(CustomTask.user_id == user_id)
    if status:
        q = q.filter(CustomTask.status == status)
    tasks = q.order_by(CustomTask.created_at.desc()).limit(50).all()
    return [
        {
            "id": t.id,
            "title": t.title,
            "subject": t.subject,
            "status": t.status,
            "created_at": str(t.created_at) if t.created_at else None,
            "confirmed_at": str(t.confirmed_at) if t.confirmed_at else None,
        }
        for t in tasks
    ]


@router.post("/custom/confirm", summary="家长确认自定义任务完成")
def confirm_custom_task(req: CustomTaskAction, db: Session = Depends(get_db)):
    """家长确认孩子创建的自定义任务完成（发放金币 +5）。

    参数（Body）：task_id。
    返回：{id, status: "confirmed", message}；任务不存在 404、非 pending 状态 400。
    副作用：置 status=confirmed、记 confirmed_at、发金币。无需家长密码（本接口不设密码校验）。
    """
    task = db.query(CustomTask).filter(CustomTask.id == req.task_id).first()
    if not task:
        raise HTTPException(404, "未找到该任务")
    if task.status != "pending":
        raise HTTPException(400, f"任务状态为 {task.status}，无法确认")
    task.status = "confirmed"
    task.confirmed_at = datetime.now()
    # 奖励金币
    try:
        from ...pet import _grant_coins
        _grant_coins(db, task.user_id, 5, "完成自定义任务")
    except Exception:
        pass
    db.commit()
    return {"id": task.id, "status": "confirmed", "message": "已确认完成"}


@router.post("/custom/reject", summary="家长驳回自定义任务")
def reject_custom_task(req: CustomTaskAction, db: Session = Depends(get_db)):
    """家长驳回孩子创建的自定义任务。

    参数（Body）：task_id。
    返回：{id, status: "rejected", message}；任务不存在 404、非 pending 状态 400。
    副作用：置 status=rejected。无需家长密码（本接口不设密码校验）。
    """
    task = db.query(CustomTask).filter(CustomTask.id == req.task_id).first()
    if not task:
        raise HTTPException(404, "未找到该任务")
    if task.status != "pending":
        raise HTTPException(400, f"任务状态为 {task.status}，无法驳回")
    task.status = "rejected"
    db.commit()
    return {"id": task.id, "status": "rejected", "message": "已驳回"}


# ═══════════════ 家长自定义任务（集成进每日任务，家长确认） ═══════════════

class ParentCustomTaskCreate(BaseModel):
    user_id: str
    title: str
    subject: str = "其他"
    task_type: str = "optional"   # mandatory / optional
    target: int = 1


class ParentCustomTaskUpdate(BaseModel):
    user_id: str
    title: str = None
    subject: str = None
    task_type: str = None
    target: int = None
    active: bool = None


@router.post("/custom-task", summary="家长添加自定义任务（集成进每日任务，需家长密码）")
def add_parent_custom_task(req: ParentCustomTaskCreate, request: Request, db: Session = Depends(get_db)):
    """家长添加自定义任务（次日注入每日任务，按 task_type 进强制/可选区，手动确认）。

    参数（Body）：user_id、title、subject、task_type（mandatory/optional）、target（默认 1）。
    请求头：必须携带 X-Parent-Pwd（ensure_parent_pwd，否则 403）。
    返回：{id, title, subject, task_type, target, active}；title 空/类型非法 返回 400。
    副作用：写 ParentCustomTask（active=True），target 夹到 1-MAX_TARGET(50)。需要家长密码。
    """
    ensure_parent_pwd(db, req.user_id, request)
    if not req.title or not req.title.strip():
        raise HTTPException(400, "任务标题不能为空")
    if req.task_type not in ("mandatory", "optional"):
        raise HTTPException(400, "task_type 必须为 mandatory 或 optional")
    t = ParentCustomTask(
        user_id=req.user_id,
        title=req.title.strip()[:100],
        subject=req.subject or "其他",
        task_type=req.task_type,
        target=max(1, min(MAX_TARGET, int(req.target or 1))),
        active=True,
    )
    db.add(t)
    db.commit()
    db.refresh(t)
    return {"id": t.id, "title": t.title, "subject": t.subject,
            "task_type": t.task_type, "target": t.target, "active": t.active}


@router.get("/custom-task", summary="查看家长自定义任务列表")
def list_parent_custom_tasks(user_id: str = Query(...), db: Session = Depends(get_db)):
    """查看家长自定义任务列表（按类型/排序）。

    参数（Query）：user_id。
    返回：家长自定义任务数组（含 id/title/subject/task_type/target/active/created_at）。
    副作用：无（只读）。无需家长密码。
    """
    # 仅返回生效中的任务（active=True）；软删除（active=False）的任务已从管理列表隐藏，
    # 与每日任务注入逻辑（common.py 按 active==True 注入）保持一致，避免「删除后仍在列表」的错觉。
    rows = db.query(ParentCustomTask).filter(
        ParentCustomTask.user_id == user_id,
        ParentCustomTask.active == True).order_by(
        ParentCustomTask.task_type, ParentCustomTask.sort_order, ParentCustomTask.id).all()
    return [{
        "id": t.id, "title": t.title, "subject": t.subject,
        "task_type": t.task_type, "target": t.target, "active": t.active,
        "created_at": str(t.created_at) if t.created_at else None,
    } for t in rows]


@router.put("/custom-task/{task_id}", summary="家长修改自定义任务（需家长密码）")
def update_parent_custom_task(task_id: int, req: ParentCustomTaskUpdate,
                              request: Request, db: Session = Depends(get_db)):
    """家长修改自定义任务（标题/学科/类型/数量/启用）。

    参数（Path）：task_id。参数（Body）：user_id + 可选字段。
    请求头：必须携带 X-Parent-Pwd（ensure_parent_pwd，否则 403）。
    返回：更新后的任务对象；不存在 404、类型非法 400。
    副作用：更新 ParentCustomTask；并删除今日未完成对应每日任务行（下次 /daily 按新定义重建）。需要家长密码。
    """
    ensure_parent_pwd(db, req.user_id, request)
    t = db.query(ParentCustomTask).filter(
        ParentCustomTask.id == task_id, ParentCustomTask.user_id == req.user_id).first()
    if not t:
        raise HTTPException(404, "未找到该自定义任务")
    if req.title is not None and req.title.strip():
        t.title = req.title.strip()[:100]
    if req.subject is not None:
        t.subject = req.subject or t.subject
    if req.task_type is not None:
        if req.task_type not in ("mandatory", "optional"):
            raise HTTPException(400, "task_type 必须为 mandatory 或 optional")
        t.task_type = req.task_type
    if req.target is not None:
        t.target = max(1, min(MAX_TARGET, int(req.target)))
    if req.active is not None:
        t.active = bool(req.active)
    t.updated_at = datetime.now()
    # 若标题/学科/类型/数量变化，删除今日未完成的对应每日任务行，下次 /daily 按新定义重建
    code = "custom:%d" % t.id
    db.query(DailyTask).filter(
        DailyTask.user_id == req.user_id, DailyTask.task_date == date.today(),
        DailyTask.task_code == code, DailyTask.status != "done").delete()
    db.commit()
    return {"id": t.id, "title": t.title, "subject": t.subject,
            "task_type": t.task_type, "target": t.target, "active": t.active}


@router.delete("/custom-task/{task_id}", summary="家长删除自定义任务（软删除，需家长密码）")
def delete_parent_custom_task(task_id: int, request: Request,
                              user_id: str = Query(...), db: Session = Depends(get_db)):
    """家长软删除自定义任务（active=False），并移除今日未完成的对应每日任务行。

    参数（Path）：task_id。参数（Query）：user_id。请求头：必须携带 X-Parent-Pwd。
    返回：{ok, id}；不存在 404。
    副作用：置 active=False、删除未完成每日任务行（已完成保留作历史）。需要家长密码。
    """
    ensure_parent_pwd(db, user_id, request)
    t = db.query(ParentCustomTask).filter(
        ParentCustomTask.id == task_id, ParentCustomTask.user_id == user_id).first()
    if not t:
        raise HTTPException(404, "未找到该自定义任务")
    t.active = False
    # 移除今日尚未完成的对应每日任务行（已完成的保留作历史）
    code = "custom:%d" % t.id
    db.query(DailyTask).filter(
        DailyTask.user_id == user_id, DailyTask.task_date == date.today(),
        DailyTask.task_code == code, DailyTask.status != "done").delete()
    db.commit()
    return {"ok": True, "id": task_id}
