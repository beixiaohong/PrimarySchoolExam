"""管理后台-IM 数据管理（D9 冻结域，自 app/routers/admin_panel.py 迁出，端点与逻辑不变）

跨用户查看聊天/好友关系/红包并支持删除；挂载受 ENABLE_IM 开关控制。
所有写操作落 admin_operation_logs 审计。
注：_require_admin/_audit 复用管理后台（admin 包），属既有跨域依赖，已记入契约债清单。
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.admin import Admin
from app.models.im import Chat, Message, Friendship, GroupMember, RedPacket, RedPacketClaim, ReadReceipt
from app.routers.admin import _require_admin, _audit

router = APIRouter()


# ═══════════════════════ IM 管理 ═══════════════════════

@router.get("/im/chats", summary="IM 聊天列表(跨用户)")
def list_chats(
    chat_type: str = Query(None, description="private/group"),
    skip: int = 0, limit: int = 50,
    admin: Admin = Depends(_require_admin), db: Session = Depends(get_db),
):
    """跨用户分页查询 IM 聊天列表，可按 chat_type 筛选，附带成员数与消息数。"""
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
    """删除指定聊天及其全部消息/成员/已读回执，并记审计日志。"""
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
    """跨用户分页查询 IM 好友关系列表，可按 status 筛选。"""
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
    """删除指定好友关系，并记审计日志。"""
    f = db.query(Friendship).filter(Friendship.id == friendship_id).first()
    if not f:
        raise HTTPException(404, "好友关系不存在")
    db.delete(f)
    db.commit()
    _audit(db, admin, "im_friendship_delete", friendship_id, "")
    return {"ok": True}


@router.get("/im/red-packets", summary="IM 红包列表(跨用户)")
def list_red_packets(skip: int = 0, limit: int = 50, admin: "Admin" = Depends(_require_admin), db: Session = Depends(get_db)):
    """跨用户分页查询 IM 红包列表（含金额与领取状态）。"""
    total = db.query(RedPacket).count()
    rows = db.query(RedPacket).order_by(RedPacket.created_at.desc()).offset(skip).limit(limit).all()
    return {"total": total, "items": [
        {"id": r.id, "sender_id": r.sender_id, "chat_id": r.chat_id,
         "total_amount": r.total_amount, "total_count": r.total_count,
         "remaining_amount": r.remaining_amount, "status": r.status.value if r.status else None}
        for r in rows]}


@router.delete("/im/red-packets/{red_packet_id}", summary="删除红包")
def delete_red_packet(red_packet_id: str, admin: "Admin" = Depends(_require_admin), db: Session = Depends(get_db)):
    """删除指定红包及其领取记录，并记审计日志。"""
    r = db.query(RedPacket).filter(RedPacket.id == red_packet_id).first()
    if not r:
        raise HTTPException(404, "红包不存在")
    db.query(RedPacketClaim).filter(RedPacketClaim.red_packet_id == red_packet_id).delete()
    db.delete(r)
    db.commit()
    _audit(db, admin, "im_red_packet_delete", red_packet_id, f"sender={r.sender_id}")
    return {"ok": True}
