"""管理后台审计接口（S1-B9 / 07-技术实施方案 §4.5）

路由清单（挂 /api/admin 前缀，统一 require_perm("audit:view") 鉴权）：
- GET /audit/logs        审计日志分页列表（支持按 action / admin / target_type 过滤）
- GET /audit/high-risk   高危操作审计（金额非空 或 命中高危权限分组的操作）

分页约定（API-03/API-07）：query 参数 page（默认 1）、page_size（默认 20，上限 100），
返回 {items, total, page, page_size}。审计表禁止物理删除（DB-05），仅查询。
"""
from fastapi import Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.core.permissions import PERMISSIONS, require_perm
from app.models.admin import AdminOperationLog

from . import router

# 高危操作分组：取权限点目录中 is_high_risk 权限 code 的「组前缀」（如 benefit/order/finance）
# 凡 action 以这些前缀开头的审计条目均视为高危。自维护：权限目录变动自动生效。
_HIGH_RISK_GROUPS = {
    p["code"].split(":", 1)[0] for p in PERMISSIONS if p["is_high_risk"]
}


def _is_high_risk(action: str, amount_fen) -> bool:
    if amount_fen is not None:
        return True
    return bool(action) and action.split(":", 1)[0] in _HIGH_RISK_GROUPS


def _serialize(row: AdminOperationLog) -> dict:
    return {
        "id": row.id,
        "admin": row.admin,
        "action": row.action,
        "target": row.target,
        "target_type": row.target_type,
        "detail": row.detail,
        "ip": row.ip,
        "user_agent": row.user_agent,
        "amount_fen": row.amount_fen,
        "extra_json": row.extra_json,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "is_high_risk": _is_high_risk(row.action, row.amount_fen),
    }


@router.get("/audit/logs", summary="审计日志分页列表")
def api_audit_logs(
    db: Session = Depends(get_db),
    admin=Depends(require_perm("audit:view")),
    page: int = Query(1, ge=1, description="页码，从 1 开始"),
    page_size: int = Query(20, ge=1, le=100, description="每页条数，上限 100"),
    action: str | None = Query(None, description="按操作类型过滤"),
    admin_name: str | None = Query(None, description="按操作管理员用户名过滤"),
    target_type: str | None = Query(None, description="按对象类型过滤"),
):
    """分页返回管理员操作审计日志，支持按 action / admin / target_type 过滤。"""
    q = db.query(AdminOperationLog)
    if action:
        q = q.filter(AdminOperationLog.action == action)
    if admin_name:
        q = q.filter(AdminOperationLog.admin == admin_name)
    if target_type:
        q = q.filter(AdminOperationLog.target_type == target_type)
    total = q.with_entities(func.count()).scalar() or 0
    rows = (q.order_by(AdminOperationLog.id.desc())
            .offset((page - 1) * page_size).limit(page_size).all())
    return {
        "items": [_serialize(r) for r in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/audit/high-risk", summary="高危操作审计列表")
def api_audit_high_risk(
    db: Session = Depends(get_db),
    admin=Depends(require_perm("audit:view")),
    page: int = Query(1, ge=1, description="页码，从 1 开始"),
    page_size: int = Query(20, ge=1, le=100, description="每页条数，上限 100"),
):
    """返回高危操作审计：金额非空（amount_fen 有值）或命中高危权限分组的操作，分页。"""
    all_rows = db.query(AdminOperationLog).order_by(AdminOperationLog.id.desc()).all()
    flagged = [r for r in all_rows if _is_high_risk(r.action, r.amount_fen)]
    total = len(flagged)
    start = (page - 1) * page_size
    page_rows = flagged[start:start + page_size]
    return {
        "items": [_serialize(r) for r in page_rows],
        "total": total,
        "page": page,
        "page_size": page_size,
    }
