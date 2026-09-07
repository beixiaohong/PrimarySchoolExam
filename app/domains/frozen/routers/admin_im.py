"""管理后台-IM 数据管理（D9 冻结域，自 app/routers/admin_panel.py 迁出，端点与逻辑不变）

跨用户查看聊天/好友关系/红包并支持删除；挂载受 ENABLE_IM 开关控制。
所有写操作落 admin_operation_logs 审计。
注：_require_admin/_audit 复用管理后台（admin 包），属既有跨域依赖，已记入契约债清单。
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_

from app.database import get_db
from app.models.admin import Admin
from app.models.im import Chat, Message, Friendship, GroupMember, RedPacket, RedPacketClaim, ReadReceipt, SensitiveWord, SensitiveHit
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


# ═══════════════════════ IM 消息审计（D4 合规） ═══════════════════════

@router.get("/im/messages", summary="IM 消息检索（跨用户）")
def list_messages(
    chat_id: str = Query(None, description="按会话过滤"),
    user_id: str = Query(None, description="按发送者过滤"),
    keyword: str = Query(None, description="按内容关键词模糊匹配"),
    message_type: str = Query(None, description="text/image/voice/red_packet/..."),
    skip: int = 0, limit: int = 50,
    admin: Admin = Depends(_require_admin), db: Session = Depends(get_db),
):
    """跨用户分页检索 IM 消息，支持多条件组合（合规审计用）。"""
    q = db.query(Message).filter(Message.is_deleted == False)
    if chat_id:
        q = q.filter(Message.chat_id == chat_id)
    if user_id:
        q = q.filter(Message.sender_id == user_id)
    if keyword:
        kw = f"%{keyword}%"
        q = q.filter(Message.content.ilike(kw))
    if message_type:
        q = q.filter(Message.message_type == message_type)
    total = q.count()
    rows = q.order_by(Message.created_at.desc()).offset(skip).limit(limit).all()
    return {"total": total, "items": [
        {"id": m.id, "chat_id": m.chat_id, "sender_id": m.sender_id,
         "content": m.content, "message_type": m.message_type.value if m.message_type else None,
         "file_path": m.file_path, "created_at": m.created_at.isoformat() if m.created_at else None}
        for m in rows]}


@router.delete("/im/messages/{message_id}", summary="违规消息删除（合规）")
def delete_message(message_id: str, admin: "Admin" = Depends(_require_admin), db: Session = Depends(get_db)):
    """软删除指定消息（is_deleted=True），并记审计日志。合规刚需。"""
    m = db.query(Message).filter(Message.id == message_id).first()
    if not m:
        raise HTTPException(404, "消息不存在")
    m.is_deleted = True
    db.commit()
    _audit(db, admin, "im_message_delete", message_id, f"sender={m.sender_id} type={m.message_type}")
    return {"ok": True}


# ═══════════════════════ 敏感词管理（D4 合规） ═══════════════════════

@router.get("/im/sensitive-words", summary="敏感词列表")
def list_sensitive_words(
    scene: str = Query(None, description="message/group_name/blessing/announcement"),
    skip: int = 0, limit: int = 200,
    admin: Admin = Depends(_require_admin), db: Session = Depends(get_db),
):
    """分页查询敏感词词库。"""
    q = db.query(SensitiveWord)
    if scene:
        q = q.filter(SensitiveWord.scene == scene)
    total = q.count()
    rows = q.order_by(SensitiveWord.id.desc()).offset(skip).limit(limit).all()
    return {"total": total, "items": [
        {"id": w.id, "word": w.word, "scene": w.scene,
         "action": w.action.value if w.action else None,
         "category": w.category, "enabled": w.enabled,
         "created_at": w.created_at.isoformat() if w.created_at else None}
        for w in rows]}


@router.post("/im/sensitive-words", summary="新增敏感词")
def create_sensitive_word(
    payload: dict, admin: Admin = Depends(_require_admin), db: Session = Depends(get_db),
):
    """新增一条敏感词。word 唯一，重复时 409。"""
    word = (payload.get("word") or "").strip()
    if not word:
        raise HTTPException(400, "敏感词不能为空")
    if db.query(SensitiveWord).filter(SensitiveWord.word == word, SensitiveWord.scene == payload.get("scene", "message")).first():
        raise HTTPException(409, "该场景下敏感词已存在")
    w = SensitiveWord(
        word=word,
        scene=payload.get("scene", "message"),
        action=payload.get("action", "replace"),
        category=payload.get("category"),
        enabled=payload.get("enabled", True),
    )
    db.add(w)
    db.commit()
    db.refresh(w)
    _audit(db, admin, "sensitive_word_create", str(w.id), f"word={w.word} scene={w.scene}")
    # 触发缓存失效：下次发消息会重新读词表
    try:
        from app.domains.frozen.services.sensitive import invalidate_cache
        invalidate_cache()
    except Exception:
        pass
    return {"id": w.id, "word": w.word, "scene": w.scene, "action": w.action.value if w.action else None}


@router.put("/im/sensitive-words/{word_id}", summary="更新敏感词")
def update_sensitive_word(
    word_id: int, payload: dict,
    admin: Admin = Depends(_require_admin), db: Session = Depends(get_db),
):
    """更新敏感词的 action / enabled / category。"""
    w = db.query(SensitiveWord).filter(SensitiveWord.id == word_id).first()
    if not w:
        raise HTTPException(404, "敏感词不存在")
    if "action" in payload and payload["action"]:
        w.action = payload["action"]
    if "enabled" in payload:
        w.enabled = bool(payload["enabled"])
    if "category" in payload:
        w.category = payload["category"]
    db.commit()
    _audit(db, admin, "sensitive_word_update", str(w.id), f"action={w.action.value} enabled={w.enabled}")
    try:
        from app.domains.frozen.services.sensitive import invalidate_cache
        invalidate_cache()
    except Exception:
        pass
    return {"ok": True}


@router.delete("/im/sensitive-words/{word_id}", summary="删除敏感词")
def delete_sensitive_word(
    word_id: int, admin: Admin = Depends(_require_admin), db: Session = Depends(get_db),
):
    """删除指定敏感词。"""
    w = db.query(SensitiveWord).filter(SensitiveWord.id == word_id).first()
    if not w:
        raise HTTPException(404, "敏感词不存在")
    word_str = w.word
    db.delete(w)
    db.commit()
    _audit(db, admin, "sensitive_word_delete", str(word_id), f"word={word_str}")
    try:
        from app.domains.frozen.services.sensitive import invalidate_cache
        invalidate_cache()
    except Exception:
        pass
    return {"ok": True}


@router.get("/im/sensitive-hits", summary="敏感词命中记录")
def list_sensitive_hits(
    scene: str = Query(None), user_id: str = Query(None),
    skip: int = 0, limit: int = 50,
    admin: Admin = Depends(_require_admin), db: Session = Depends(get_db),
):
    """敏感词命中日志（合规审计：可看到被拦的原文 + 处理动作）。"""
    q = db.query(SensitiveHit)
    if scene:
        q = q.filter(SensitiveHit.scene == scene)
    if user_id:
        q = q.filter(SensitiveHit.user_id == user_id)
    total = q.count()
    rows = q.order_by(SensitiveHit.created_at.desc()).offset(skip).limit(limit).all()
    return {"total": total, "items": [
        {"id": h.id, "user_id": h.user_id, "chat_id": h.chat_id, "scene": h.scene,
         "matched_word": h.matched_word, "original_text": h.original_text,
         "action": h.action, "created_at": h.created_at.isoformat() if h.created_at else None}
        for h in rows]}


# ═══════════════════════ IM 统计端点 ═══════════════════════

@router.get("/im/stats", summary="IM 平台统计")
def im_stats(admin: Admin = Depends(_require_admin), db: Session = Depends(get_db)):
    """IM 域平台维度统计：会话数 / 消息数 / 红包总额 / 命中数。"""
    import sqlalchemy as sa
    chat_count = db.query(Chat).count()
    msg_count = db.query(Message).filter(Message.is_deleted == False).count()
    rp_total = db.query(sa.func.coalesce(sa.func.sum(RedPacket.total_amount), 0)).scalar() or 0
    rp_claimed = db.query(sa.func.coalesce(sa.func.sum(RedPacketClaim.amount), 0)).scalar() or 0
    hit_count = db.query(SensitiveHit).count()
    return {
        "chat_count": chat_count,
        "message_count": msg_count,
        "red_packet_total_milli": int(rp_total),       # 毫钻
        "red_packet_claimed_milli": int(rp_claimed),   # 毫钻
        "sensitive_hit_count": hit_count,
    }
