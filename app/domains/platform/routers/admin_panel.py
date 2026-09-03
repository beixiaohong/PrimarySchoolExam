"""管理后台扩展功能：数据看板、系统公告

本模块与 app/routers/admin.py 共享 _require_admin / _audit：
- 数据看板：用户规模与活跃、各模块使用统计、账本/IM 体量。
- 系统公告：发布/列表/删除；学生端由 app/routers/announcement.py 拉取。

账本(ledger)/IM 数据管理端点已迁至 D9 冻结域（app/domains/frozen/routers/
admin_ledger.py / admin_im.py），受 ENABLE_LEDGER / ENABLE_IM 开关控制。
看板中的 ledger/im 体量统计仍直查 D9 归属表（既有跨域依赖，已记入契约债清单；
D9 下线时随看板一并移除）。

所有写操作落 admin_operation_logs 审计。
"""
import logging
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User, VipUser
from app.models.exam import ExamAttempt
from app.models.vocab import VocabDailyLog
from app.models.classical import ClassicalDailyLog
from app.models.sprint4 import ChallengeRecord
from app.models.daily_task import DailyTask
from app.models.ai_usage import AiQa
from app.models.ledger import Bill, Account, Category
from app.models.im import Chat, Message, Friendship, RedPacket
from app.models.admin import Admin
from app.models.announcement import Announcement
from app.routers.admin import _require_admin, _audit

logger = logging.getLogger(__name__)

router = APIRouter()


# ═══════════════════════ 数据看板 ═══════════════════════

@router.get("/stats/dashboard", summary="后台数据看板")
def dashboard_stats(admin: "Admin" = Depends(_require_admin), db: Session = Depends(get_db)):
    """汇总运营数据：用户规模与活跃、各学习模块使用量、账本/IM 体量。"""
    today = date.today()
    now = datetime.now()
    week_ago = now - timedelta(days=7)

    total_users = db.query(User).count()
    active_today = db.query(User).filter(User.last_login_date == today).count()
    new_today = db.query(User).filter(func.date(User.created_at) == today).count()
    active_7d = db.query(User).filter(User.last_login_at >= week_ago).count()
    vip_count = db.query(VipUser).count()

    # 年级分布
    grade_rows = db.query(User.grade, func.count(User.id)).group_by(User.grade).all()
    grade_dist = {str(g): c for g, c in grade_rows}

    module_usage = {
        "exam_attempts": db.query(ExamAttempt).count(),
        "daily_tasks": db.query(DailyTask).count(),
        "vocab_logs": db.query(VocabDailyLog).count(),
        "classical_logs": db.query(ClassicalDailyLog).count(),
        "ai_qa": db.query(AiQa).count(),
        "challenges": db.query(ChallengeRecord).count(),
    }
    ledger_stats = {
        "bills": db.query(Bill).count(),
        "accounts": db.query(Account).count(),
        "categories": db.query(Category).count(),
    }
    im_stats = {
        "chats": db.query(Chat).count(),
        "messages": db.query(Message).count(),
        "friendships": db.query(Friendship).count(),
        "red_packets": db.query(RedPacket).count(),
    }
    return {
        "generated_at": now.strftime("%Y-%m-%d %H:%M:%S"),
        "users": {
            "total": total_users,
            "active_today": active_today,
            "new_today": new_today,
            "active_7d": active_7d,
            "vip": vip_count,
            "grade_distribution": grade_dist,
        },
        "module_usage": module_usage,
        "ledger": ledger_stats,
        "im": im_stats,
    }


# ═══════════════════════ 系统公告 ═══════════════════════

class AnnouncementCreate(BaseModel):
    """发布系统公告请求：标题、内容、投放范围与目标、是否置顶。"""
    title: str
    content: str
    target_type: str = "all"   # all / grade / user
    target_value: str = None
    is_pinned: bool = False


@router.post("/announcements", summary="发布系统公告")
def create_announcement(req: AnnouncementCreate, admin: "Admin" = Depends(_require_admin), db: Session = Depends(get_db)):
    """发布系统公告并记审计日志。"""
    ann = Announcement(
        title=req.title, content=req.content, target_type=req.target_type,
        target_value=req.target_value, is_pinned=req.is_pinned,
        created_by=admin.username,
    )
    db.add(ann)
    db.commit()
    db.refresh(ann)
    _audit(db, admin, "announcement_create", str(ann.id), req.title)
    return {"ok": True, "id": ann.id}


@router.get("/announcements", summary="公告列表(后台)")
def list_announcements(admin: "Admin" = Depends(_require_admin), db: Session = Depends(get_db)):
    """后台公告列表（按置顶优先、创建时间倒序）。"""
    rows = db.query(Announcement).order_by(
        Announcement.is_pinned.desc(), Announcement.created_at.desc()).all()
    return {"total": len(rows), "items": [
        {"id": a.id, "title": a.title, "target_type": a.target_type,
         "target_value": a.target_value, "is_pinned": a.is_pinned,
         "created_by": a.created_by,
         "created_at": a.created_at.strftime("%Y-%m-%d %H:%M") if a.created_at else None}
        for a in rows]}


@router.delete("/announcements/{ann_id}", summary="删除公告")
def delete_announcement(ann_id: int, admin: "Admin" = Depends(_require_admin), db: Session = Depends(get_db)):
    """删除指定公告，并记审计日志。"""
    a = db.query(Announcement).filter(Announcement.id == ann_id).first()
    if not a:
        raise HTTPException(404, "公告不存在")
    db.delete(a)
    db.commit()
    _audit(db, admin, "announcement_delete", str(ann_id), a.title)
    return {"ok": True}
