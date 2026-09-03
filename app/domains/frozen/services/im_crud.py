"""
IM即时通讯系统 - CRUD操作层（适配自 temp/wulala/crud_im.py）

适配点：
- from backend.model import model_im  ->  from app.models import im as model_im
- from backend.model.model_user import ModUser  ->  from app.models.user import User
- ModUser.user_id  ->  User.user_id
- 返回模型对象（非 pydantic）。
"""
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.models import im as model_im
from app.models.im import *  # noqa: F401,F403 兼容 model_im.X 形式的引用
from app.models.user import User
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any


# ==================== 消息 CRUD ====================

def create_message(db: Session, chat_id: str, sender_id: str,
                   content: str = None, message_type: model_im.MessageType = model_im.MessageType.TEXT,
                   file_path: str = None, file_name: str = None, file_size: int = None) -> model_im.Message:
    """创建消息记录"""
    message = model_im.Message(
        chat_id=chat_id, sender_id=sender_id, content=content,
        message_type=message_type, file_path=file_path,
        file_name=file_name, file_size=file_size
    )
    db.add(message)
    db.commit()
    db.refresh(message)
    return message


def get_messages(db: Session, chat_id: str, skip: int = 0, limit: int = 50) -> List[model_im.Message]:
    """获取聊天消息列表（排除已删除消息）"""
    return db.query(model_im.Message).filter(
        model_im.Message.chat_id == chat_id,
        model_im.Message.is_deleted == False
    ).order_by(model_im.Message.created_at.desc()).offset(skip).limit(limit).all()


def get_message_by_id(db: Session, message_id: str) -> Optional[model_im.Message]:
    """根据ID获取消息"""
    return db.query(model_im.Message).filter(model_im.Message.id == message_id).first()


def recall_message(db: Session, message_id: str, user_id: str) -> Optional[model_im.Message]:
    """
    撤回消息（仅允许发送者撤回自己的消息）

    Returns:
        撤回成功返回消息对象，失败返回 None
    """
    message = get_message_by_id(db, message_id)
    if not message or message.sender_id != user_id or message.is_deleted:
        return None
    message.is_deleted = True
    message.content = "[消息已撤回]"
    db.commit()
    db.refresh(message)
    return message


def delete_message(db: Session, message_id: str, user_id: str) -> bool:
    """
    删除消息（软删除，仅发送者可操作）

    Returns:
        成功返回 True
    """
    message = get_message_by_id(db, message_id)
    if not message or message.sender_id != user_id:
        return False
    message.is_deleted = True
    db.commit()
    return True


# ==================== 好友 CRUD ====================

def get_friends(db: Session, user_id: str) -> List[User]:
    """获取用户的好友列表"""
    friendships = db.query(model_im.Friendship).filter(
        ((model_im.Friendship.requester_id == user_id) | (model_im.Friendship.addressee_id == user_id)) &
        (model_im.Friendship.status == model_im.FriendStatus.ACCEPTED)
    ).all()

    friends = []
    for f in friendships:
        friend_id = f.addressee_id if f.requester_id == user_id else f.requester_id
        friend = db.query(User).filter(User.user_id == friend_id).first()
        if friend:
            friends.append(friend)
    return friends


def get_pending_requests(db: Session, user_id: str) -> List[model_im.Friendship]:
    """获取待处理的好友请求"""
    return db.query(model_im.Friendship).filter(
        model_im.Friendship.addressee_id == user_id,
        model_im.Friendship.status == model_im.FriendStatus.PENDING
    ).all()


def block_user(db: Session, blocker_id: str, blocked_id: str) -> Optional[model_im.Friendship]:
    """
    拉黑用户

    如果已有好友关系，将状态改为 BLOCKED；否则创建一条 BLOCKED 记录。
    """
    friendship = db.query(model_im.Friendship).filter(
        ((model_im.Friendship.requester_id == blocker_id) & (model_im.Friendship.addressee_id == blocked_id)) |
        ((model_im.Friendship.requester_id == blocked_id) & (model_im.Friendship.addressee_id == blocker_id))
    ).first()

    if friendship:
        friendship.status = model_im.FriendStatus.BLOCKED
        friendship.updated_at = datetime.now(timezone.utc)
    else:
        friendship = model_im.Friendship(
            requester_id=blocker_id, addressee_id=blocked_id,
            status=model_im.FriendStatus.BLOCKED
        )
        db.add(friendship)
    db.commit()
    db.refresh(friendship)
    return friendship


def unblock_user(db: Session, blocker_id: str, blocked_id: str) -> bool:
    """解除拉黑"""
    friendship = db.query(model_im.Friendship).filter(
        ((model_im.Friendship.requester_id == blocker_id) & (model_im.Friendship.addressee_id == blocked_id)) |
        ((model_im.Friendship.requester_id == blocked_id) & (model_im.Friendship.addressee_id == blocker_id)),
        model_im.Friendship.status == model_im.FriendStatus.BLOCKED
    ).first()

    if not friendship:
        return False
    db.delete(friendship)
    db.commit()
    return True


def get_blocked_list(db: Session, user_id: str) -> List[User]:
    """获取黑名单列表"""
    friendships = db.query(model_im.Friendship).filter(
        ((model_im.Friendship.requester_id == user_id) | (model_im.Friendship.addressee_id == user_id)),
        model_im.Friendship.status == model_im.FriendStatus.BLOCKED
    ).all()

    blocked_users = []
    for f in friendships:
        blocked_id = f.addressee_id if f.requester_id == user_id else f.requester_id
        user = db.query(User).filter(User.user_id == blocked_id).first()
        if user:
            blocked_users.append(user)
    return blocked_users


# ==================== 聊天室 CRUD ====================

def get_private_chat(db: Session, user_id_1: str, user_id_2: str) -> Optional[model_im.Chat]:
    """查找两个用户之间已有的私聊"""
    user1_chat_ids = db.query(model_im.GroupMember.chat_id).filter(
        model_im.GroupMember.user_id == user_id_1
    ).subquery()
    user2_chat_ids = db.query(model_im.GroupMember.chat_id).filter(
        model_im.GroupMember.user_id == user_id_2
    ).subquery()
    return db.query(model_im.Chat).filter(
        model_im.Chat.id.in_(user1_chat_ids),
        model_im.Chat.id.in_(user2_chat_ids),
        model_im.Chat.chat_type == model_im.ChatType.PRIVATE.value
    ).first()


def get_user_chats(db: Session, user_id: str) -> List[model_im.Chat]:
    """获取用户参与的所有群聊"""
    member_chat_ids = db.query(model_im.GroupMember.chat_id).filter(
        model_im.GroupMember.user_id == user_id
    ).subquery()
    return db.query(model_im.Chat).filter(
        model_im.Chat.id.in_(member_chat_ids),
        model_im.Chat.chat_type == model_im.ChatType.GROUP.value
    ).all()


def get_chat_by_id(db: Session, chat_id: str) -> Optional[model_im.Chat]:
    """根据ID获取聊天室"""
    return db.query(model_im.Chat).filter(model_im.Chat.id == chat_id).first()


def update_announcement(db: Session, chat_id: str, user_id: str, content: str) -> Optional[model_im.Chat]:
    """
    更新群公告（仅管理员可操作）

    Returns:
        成功返回 Chat 对象，失败返回 None
    """
    admin = db.query(model_im.GroupMember).filter(
        model_im.GroupMember.chat_id == chat_id,
        model_im.GroupMember.user_id == user_id,
        model_im.GroupMember.is_admin == True
    ).first()
    if not admin:
        return None

    chat = get_chat_by_id(db, chat_id)
    if not chat:
        return None
    chat.announcement = content
    chat.announcement_at = datetime.now(timezone.utc)
    chat.announcement_by = user_id
    db.commit()
    db.refresh(chat)
    return chat


# ==================== 群成员 CRUD ====================

def leave_group(db: Session, chat_id: str, user_id: str) -> bool:
    """
    退出群聊

    Returns:
        成功返回 True，群主不能退出
    """
    member = db.query(model_im.GroupMember).filter(
        model_im.GroupMember.chat_id == chat_id,
        model_im.GroupMember.user_id == user_id
    ).first()
    if not member:
        return False
    chat = get_chat_by_id(db, chat_id)
    if chat and chat.created_by == user_id:
        return False
    db.delete(member)
    db.commit()
    return True


def is_group_member(db: Session, chat_id: str, user_id: str) -> bool:
    """检查用户是否是群成员"""
    return db.query(model_im.GroupMember).filter(
        model_im.GroupMember.chat_id == chat_id,
        model_im.GroupMember.user_id == user_id
    ).first() is not None


def is_group_admin(db: Session, chat_id: str, user_id: str) -> bool:
    """检查用户是否是群管理员"""
    return db.query(model_im.GroupMember).filter(
        model_im.GroupMember.chat_id == chat_id,
        model_im.GroupMember.user_id == user_id,
        model_im.GroupMember.is_admin == True
    ).first() is not None


# ==================== 已读回执 ====================

def update_read_receipt(db: Session, chat_id: str, user_id: str, message_id: str) -> model_im.ReadReceipt:
    """更新已读回执"""
    receipt = db.query(model_im.ReadReceipt).filter(
        model_im.ReadReceipt.chat_id == chat_id,
        model_im.ReadReceipt.user_id == user_id
    ).first()

    if receipt:
        receipt.last_read_message_id = message_id
        receipt.updated_at = datetime.now(timezone.utc)
    else:
        receipt = model_im.ReadReceipt(
            chat_id=chat_id, user_id=user_id,
            last_read_message_id=message_id
        )
        db.add(receipt)
    db.commit()
    db.refresh(receipt)
    return receipt


def get_unread_counts(db: Session, user_id: str) -> Dict[str, int]:
    """
    获取用户所有群聊的未读消息数

    Returns:
        {chat_id: unread_count, ...}
    """
    chat_ids = [m.chat_id for m in db.query(model_im.GroupMember).filter(
        model_im.GroupMember.user_id == user_id
    ).all()]

    result = {}
    for chat_id in chat_ids:
        receipt = db.query(model_im.ReadReceipt).filter(
            model_im.ReadReceipt.chat_id == chat_id,
            model_im.ReadReceipt.user_id == user_id
        ).first()

        if receipt and receipt.last_read_message_id:
            last_read_msg = db.query(model_im.Message).filter(
                model_im.Message.id == receipt.last_read_message_id
            ).first()
            if last_read_msg:
                unread = db.query(model_im.Message).filter(
                    model_im.Message.chat_id == chat_id,
                    model_im.Message.is_deleted == False,
                    model_im.Message.sender_id != user_id,
                    model_im.Message.created_at > last_read_msg.created_at
                ).count()
            else:
                unread = 0
        else:
            unread = db.query(model_im.Message).filter(
                model_im.Message.chat_id == chat_id,
                model_im.Message.is_deleted == False,
                model_im.Message.sender_id != user_id
            ).count()

        if unread > 0:
            result[chat_id] = unread

    return result
