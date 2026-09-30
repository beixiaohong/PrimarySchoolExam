"""工作台应用使用记录服务（我的应用 / 最近使用）。

只存「用户 → 模块」的使用事实（app_key 由前端 apps.js 定义），
**不复制任何业务数据**（blog.md §32：首页适配业务，不为首页造冗余表）。
"""
import logging
from datetime import datetime
from typing import List

from sqlalchemy.orm import Session

from app.models.blog import WorkspaceAppUsage
from app.schemas.blog import AppUsageResponse

logger = logging.getLogger(__name__)


def record_app_usage(db: Session, user_id: str, app_key: str) -> AppUsageResponse:
    """记录一次模块访问：不存在则建、已存在则累加 visit_count 并刷新 last_visit_at。"""
    key = (app_key or "").strip()
    if not key:
        raise ValueError("app_key 不能为空")
    row = db.query(WorkspaceAppUsage).filter(
        WorkspaceAppUsage.user_id == user_id,
        WorkspaceAppUsage.app_key == key,
    ).first()
    now = datetime.now()
    if not row:
        row = WorkspaceAppUsage(user_id=user_id, app_key=key, visit_count=1, last_visit_at=now)
        db.add(row)
    else:
        row.visit_count = (row.visit_count or 0) + 1
        row.last_visit_at = now
    db.commit()
    return AppUsageResponse.model_validate(row)


def list_app_usage(db: Session, user_id: str) -> List[AppUsageResponse]:
    """取该用户全部模块使用记录（按最近访问倒序，供首页排「最近使用」）。"""
    rows = db.query(WorkspaceAppUsage).filter(
        WorkspaceAppUsage.user_id == user_id
    ).order_by(WorkspaceAppUsage.last_visit_at.desc()).all()
    return [AppUsageResponse.model_validate(r) for r in rows]
