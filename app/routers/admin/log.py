"""管理后台：操作日志"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.admin import Admin, AdminOperationLog

from . import router
from .common import _require_admin


@router.get("/logs", summary="操作日志")
def list_logs(page: int = 1, page_size: int = 20,
              db: Session = Depends(get_db), admin: Admin = Depends(_require_admin)):
    """分页查询管理员操作日志（按 id 倒序）。

    参数：page / page_size：分页参数。
    返回：{"total","items": [{"admin","action","target","detail","created_at"}]}。
    副作用：只读。
    """
    q = db.query(AdminOperationLog)
    total = q.count()
    rows = q.order_by(AdminOperationLog.id.desc()).offset(
        max(0, (page - 1) * page_size)).limit(page_size).all()
    return {"total": total, "items": [{
        "admin": r.admin, "action": r.action, "target": r.target,
        "detail": r.detail,
        "created_at": r.created_at.strftime("%Y-%m-%d %H:%M:%S") if r.created_at else "",
    } for r in rows]}


__all__ = ["list_logs"]
