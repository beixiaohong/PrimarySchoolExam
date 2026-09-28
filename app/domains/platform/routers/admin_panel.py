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
from app.core.permissions import require_perm

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
    """发布系统公告请求：标题、内容、投放范围与目标、是否置顶、是否同时推送。"""
    title: str
    content: str
    target_type: str = "all"   # all / grade / user
    target_value: str = None
    is_pinned: bool = False
    # 是否同时下发浏览器推送（OneSignal）。默认 False：公告是低频动作，
    # 但推送会即时打断所有在线用户，应由管理员显式勾选而非默认打扰。
    push: bool = False


def _send_announcement_push(ann_id: int, title: str, content: str,
                            target_type: str, target_value: str):
    """公告发布后联动推送（尽力而为，失败不影响公告本身）。

    调用前提：公告已 commit，且请求级 DB 会话**已关闭** ——
    本函数会发起外部 HTTP（OneSignal），持连等待会耗尽连接池。
    """
    try:
        from ..services import push

        if not push.push_configured():
            return {"ok": False, "reason": "not_configured", "message": "推送通道未配置"}
        # 推送正文取公告正文摘要：系统通知栏本身会截断，长正文只会被腰斩
        body = (content or "").strip().replace("\n", " ")[:120] or "点击查看详情"
        url = "/#/home"
        # announce 属运营类事件：不占用户每日推送额度（否则一条公告就把额度吃光）
        if target_type == "user" and target_value:
            return push.notify_user(str(target_value).strip(), title, body, url=url,
                                    event=push.EVENT_ANNOUNCE,
                                    data={"announcement_id": ann_id},
                                    dedup_key="announce:%d" % ann_id)
        if target_type == "grade" and target_value:
            try:
                grade = int(str(target_value).strip())
            except ValueError:
                return {"ok": False, "reason": "bad_target", "message": "年级取值非法"}
            from app.database import SessionLocal
            from app.models.user import User

            with SessionLocal() as db:
                uids = [r[0] for r in db.query(User.user_id)
                        .filter(User.grade == grade).limit(5000).all() if r[0]]
            if not uids:
                return {"ok": False, "reason": "no_recipient", "message": "该年级没有用户"}
            return push.send_to_users(uids, title, body, url=url,
                                      event=push.EVENT_ANNOUNCE,
                                      data={"announcement_id": ann_id},
                                      dedup_key="announce:%d" % ann_id)
        # 全体：走 OneSignal 分段广播（不逐个枚举用户）
        return push.send_to_all(title, body, url=url, event=push.EVENT_ANNOUNCE,
                                data={"announcement_id": ann_id})
    except Exception as e:                            # noqa: BLE001
        logger.warning("公告推送失败（公告本身已发布）：%s", e)
        return {"ok": False, "reason": "error", "message": str(e)[:120]}


@router.post("/announcements", summary="发布系统公告",
             dependencies=[Depends(require_perm("announcement:manage"))])
def create_announcement(req: AnnouncementCreate, admin: "Admin" = Depends(_require_admin), db: Session = Depends(get_db)):
    """发布系统公告并记审计日志；可选同时下发浏览器推送。"""
    ann = Announcement(
        title=req.title, content=req.content, target_type=req.target_type,
        target_value=req.target_value, is_pinned=req.is_pinned,
        created_by=admin.username,
    )
    db.add(ann)
    db.commit()
    db.refresh(ann)
    _audit(db, admin, "announcement_create", str(ann.id), req.title)
    ann_id, ann_title = ann.id, ann.title
    target_type, target_value = ann.target_type, ann.target_value

    push_res = None
    if req.push:
        # 🚨 先释放请求级 DB 会话再发外部 HTTP：推送最长 10s 超时，
        # 持连等待会占用连接池连接（历史上曾因此把全站拖到超时）。
        db.close()
        push_res = _send_announcement_push(ann_id, ann_title, req.content,
                                          target_type, target_value)
    return {"ok": True, "id": ann_id, "push": push_res}


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


@router.delete("/announcements/{ann_id}", summary="删除公告",
               dependencies=[Depends(require_perm("announcement:manage"))])
def delete_announcement(ann_id: int, admin: "Admin" = Depends(_require_admin), db: Session = Depends(get_db)):
    """删除指定公告，并记审计日志。"""
    a = db.query(Announcement).filter(Announcement.id == ann_id).first()
    if not a:
        raise HTTPException(404, "公告不存在")
    db.delete(a)
    db.commit()
    _audit(db, admin, "announcement_delete", str(ann_id), a.title)
    return {"ok": True}
