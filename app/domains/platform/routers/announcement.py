"""学生端公告/站内信接口

学生/家长登录后拉取属于自己的系统公告（受众=全部 / 按年级 / 指定用户）。
公告发布在后台（app/routers/admin_panel.py）；用户与管理员的实时沟通由 IM 模块承载。
"""
import logging

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.models.announcement import Announcement
from app.domains.identity.routers.auth import require_user

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("", summary="拉取我的系统公告/站内信")
def my_announcements(user: User = Depends(require_user), db: Session = Depends(get_db)):
    """返回当前用户可见的公告（全部 / 本年级 / 指定本人），置顶优先、按时间倒序。"""
    rows = db.query(Announcement).filter(
        (Announcement.target_type == "all")
        | ((Announcement.target_type == "grade") & (Announcement.target_value == str(user.grade)))
        | ((Announcement.target_type == "user") & (Announcement.target_value == user.user_id))
    ).order_by(Announcement.is_pinned.desc(), Announcement.created_at.desc()).all()
    return {
        "total": len(rows),
        "items": [
            {
                "id": a.id, "title": a.title, "content": a.content,
                "target_type": a.target_type, "is_pinned": a.is_pinned,
                "created_by": a.created_by,
                "created_at": a.created_at.strftime("%Y-%m-%d %H:%M") if a.created_at else None,
            }
            for a in rows
        ],
    }
