"""管理后台扩展功能：数据看板、账本/IM 数据管理、系统公告

本模块与 app/routers/admin.py 共享 _require_admin / _audit，集中承载「后台功能太单薄」
阶段新增的能力：
- 数据看板：用户规模与活跃、各模块使用统计、账本/IM 体量。
- 账本(ledger)数据管理：跨用户查看账单/账户/分类，并支持删除（运营兜底）。
- IM 数据管理：跨用户查看聊天/好友关系/红包，并支持删除。
- 系统公告：发布/列表/删除；学生端由 app/routers/announcement.py 拉取。

所有写操作落 admin_operation_logs 审计。
"""
import logging
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.user import User, VipUser
from ..models.exam import ExamAttempt
from ..models.vocab import VocabDailyLog
from ..models.classical import ClassicalDailyLog
from ..models.sprint4 import ChallengeRecord
from ..models.daily_task import DailyTask
from ..models.ai_usage import AiQa
from ..models.ledger import (
    Bill, Account, Category, Location, Merchant, Person, Project, RecurringTransaction,
)
from ..models.im import Chat, Message, Friendship, GroupMember, RedPacket, RedPacketClaim, ReadReceipt
from ..models.admin import Admin
from ..models.announcement import Announcement
from .admin import _require_admin, _audit

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


# ═══════════════════════ 账本(ledger)管理 ═══════════════════════

def _bill_to_dict(b: Bill) -> dict:
    return {
        "id": b.id, "user_id": b.user_id,
        "transaction_type": b.transaction_type.value if b.transaction_type else None,
        "amount": str(b.amount), "category_id": b.category_id,
        "note": b.note, "transaction_time": b.transaction_time.strftime("%Y-%m-%d %H:%M") if b.transaction_time else None,
    }


@router.get("/ledger/bills", summary="账本账单列表(跨用户)")
def list_bills(
    user_id: str = Query(None, description="按用户筛选"),
    skip: int = 0, limit: int = 50,
    admin: Admin = Depends(_require_admin), db: Session = Depends(get_db),
):
    q = db.query(Bill)
    if user_id:
        q = q.filter(Bill.user_id == user_id)
    total = q.count()
    rows = q.order_by(Bill.id.desc()).offset(skip).limit(limit).all()
    return {"total": total, "items": [_bill_to_dict(b) for b in rows]}


@router.delete("/ledger/bills/{bill_id}", summary="删除账单")
def delete_bill(bill_id: int, admin: "Admin" = Depends(_require_admin), db: Session = Depends(get_db)):
    b = db.query(Bill).filter(Bill.id == bill_id).first()
    if not b:
        raise HTTPException(404, "账单不存在")
    db.delete(b)
    db.commit()
    _audit(db, admin, "ledger_bill_delete", str(bill_id), f"user_id={b.user_id}")
    return {"ok": True}


@router.get("/ledger/accounts", summary="账本账户列表(跨用户)")
def list_accounts(user_id: str = None, admin: "Admin" = Depends(_require_admin), db: Session = Depends(get_db)):
    q = db.query(Account)
    if user_id:
        q = q.filter(Account.user_id == user_id)
    rows = q.order_by(Account.id.desc()).all()
    return {"total": len(rows), "items": [
        {"id": a.id, "user_id": a.user_id, "account_name": a.account_name,
         "account_type": a.account_type.value if a.account_type else None,
         "balance": str(a.balance)} for a in rows]}


@router.delete("/ledger/accounts/{account_id}", summary="删除账户")
def delete_account(account_id: int, admin: "Admin" = Depends(_require_admin), db: Session = Depends(get_db)):
    a = db.query(Account).filter(Account.id == account_id).first()
    if not a:
        raise HTTPException(404, "账户不存在")
    db.delete(a)
    db.commit()
    _audit(db, admin, "ledger_account_delete", str(account_id), f"user_id={a.user_id}")
    return {"ok": True}


@router.get("/ledger/categories", summary="账本分类列表(跨用户)")
def list_categories(user_id: str = None, admin: "Admin" = Depends(_require_admin), db: Session = Depends(get_db)):
    q = db.query(Category)
    if user_id:
        q = q.filter(Category.user_id == user_id)
    rows = q.order_by(Category.id.desc()).all()
    return {"total": len(rows), "items": [
        {"id": c.id, "user_id": c.user_id,
         "category_type": c.category_type.value if c.category_type else None,
         "level1": c.level1, "level2": c.level2, "level3": c.level3} for c in rows]}


@router.delete("/ledger/categories/{category_id}", summary="删除分类")
def delete_category(category_id: int, admin: "Admin" = Depends(_require_admin), db: Session = Depends(get_db)):
    c = db.query(Category).filter(Category.id == category_id).first()
    if not c:
        raise HTTPException(404, "分类不存在")
    db.delete(c)
    db.commit()
    _audit(db, admin, "ledger_category_delete", str(category_id), f"user_id={c.user_id}")
    return {"ok": True}


# ═══════════════════════ IM 管理 ═══════════════════════

@router.get("/im/chats", summary="IM 聊天列表(跨用户)")
def list_chats(
    chat_type: str = Query(None, description="private/group"),
    skip: int = 0, limit: int = 50,
    admin: Admin = Depends(_require_admin), db: Session = Depends(get_db),
):
    q = db.query(Chat)
    if chat_type:
        q = q.filter(Chat.chat_type == chat_type)
    total = q.count()
    rows = q.order_by(Chat.created_at.desc()).offset(skip).limit(limit).all()
    return {"total": total, "items": [
        {"id": c.id, "name": c.name, "chat_type": c.chat_type,
         "created_by": c.created_by, "member_count": db.query(GroupMember).filter(GroupMember.chat_id == c.id).count(),
         "message_count": db.query(Message).filter(Message.chat_id == c.id, Message.is_deleted == False).count()}
        for c in rows]}


@router.delete("/im/chats/{chat_id}", summary="删除聊天(含消息/成员)")
def delete_chat(chat_id: str, admin: "Admin" = Depends(_require_admin), db: Session = Depends(get_db)):
    c = db.query(Chat).filter(Chat.id == chat_id).first()
    if not c:
        raise HTTPException(404, "聊天不存在")
    db.query(Message).filter(Message.chat_id == chat_id).delete()
    db.query(GroupMember).filter(GroupMember.chat_id == chat_id).delete()
    db.query(ReadReceipt).filter(ReadReceipt.chat_id == chat_id).delete()
    db.delete(c)
    db.commit()
    _audit(db, admin, "im_chat_delete", chat_id, f"name={c.name}")
    return {"ok": True}


@router.get("/im/friendships", summary="IM 好友关系列表(跨用户)")
def list_friendships(
    status: str = Query(None), skip: int = 0, limit: int = 50,
    admin: Admin = Depends(_require_admin), db: Session = Depends(get_db),
):
    q = db.query(Friendship)
    if status:
        q = q.filter(Friendship.status == status)
    total = q.count()
    rows = q.order_by(Friendship.created_at.desc()).offset(skip).limit(limit).all()
    return {"total": total, "items": [
        {"id": f.id, "requester_id": f.requester_id, "addressee_id": f.addressee_id,
         "status": f.status.value if f.status else None} for f in rows]}


@router.delete("/im/friendships/{friendship_id}", summary="删除好友关系")
def delete_friendship(friendship_id: str, admin: "Admin" = Depends(_require_admin), db: Session = Depends(get_db)):
    f = db.query(Friendship).filter(Friendship.id == friendship_id).first()
    if not f:
        raise HTTPException(404, "好友关系不存在")
    db.delete(f)
    db.commit()
    _audit(db, admin, "im_friendship_delete", friendship_id, "")
    return {"ok": True}


@router.get("/im/red-packets", summary="IM 红包列表(跨用户)")
def list_red_packets(skip: int = 0, limit: int = 50, admin: "Admin" = Depends(_require_admin), db: Session = Depends(get_db)):
    total = db.query(RedPacket).count()
    rows = db.query(RedPacket).order_by(RedPacket.created_at.desc()).offset(skip).limit(limit).all()
    return {"total": total, "items": [
        {"id": r.id, "sender_id": r.sender_id, "chat_id": r.chat_id,
         "total_amount": r.total_amount, "total_count": r.total_count,
         "remaining_amount": r.remaining_amount, "status": r.status.value if r.status else None}
        for r in rows]}


@router.delete("/im/red-packets/{red_packet_id}", summary="删除红包")
def delete_red_packet(red_packet_id: str, admin: "Admin" = Depends(_require_admin), db: Session = Depends(get_db)):
    r = db.query(RedPacket).filter(RedPacket.id == red_packet_id).first()
    if not r:
        raise HTTPException(404, "红包不存在")
    db.query(RedPacketClaim).filter(RedPacketClaim.red_packet_id == red_packet_id).delete()
    db.delete(r)
    db.commit()
    _audit(db, admin, "im_red_packet_delete", red_packet_id, f"sender={r.sender_id}")
    return {"ok": True}


# ═══════════════════════ 系统公告 ═══════════════════════

class AnnouncementCreate(BaseModel):
    title: str
    content: str
    target_type: str = "all"   # all / grade / user
    target_value: str = None
    is_pinned: bool = False


@router.post("/announcements", summary="发布系统公告")
def create_announcement(req: AnnouncementCreate, admin: "Admin" = Depends(_require_admin), db: Session = Depends(get_db)):
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
    a = db.query(Announcement).filter(Announcement.id == ann_id).first()
    if not a:
        raise HTTPException(404, "公告不存在")
    db.delete(a)
    db.commit()
    _audit(db, admin, "announcement_delete", str(ann_id), a.title)
    return {"ok": True}
