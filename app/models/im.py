"""IM 即时通讯模块 - SQLAlchemy 模型

适配自 temp/wulala/model_im.py：
- Base 来自 app.database（统一 MySQL 引擎）。
- 用户外键全部指向 users.user_id（字符串主键）。
- 所有指向 User 的反向关系去掉 back_populates（User 模型不反向引用 IM），
  改为 relationship("User", foreign_keys=[...])。
- IM 模型之间的关系（Chat<->Message、Chat<->GroupMember、RedPacket<->RedPacketClaim）
  保留 back_populates。
- 枚举（MessageType / ChatType / FriendStatus / RedPacketStatus）保留为真正的 enum.Enum。
"""
from datetime import datetime
import uuid
from enum import Enum as PyEnum

from sqlalchemy import Boolean, Column, DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.database import Base
from app.models.user import User  # 确保 "User" 在映射注册表中可被关系解析


# ───────────────── 枚举类型 ─────────────────
class MessageType(PyEnum):
    TEXT = "text"
    IMAGE = "image"
    FILE = "file"
    VOICE = "voice"
    VIDEO = "video"
    RED_PACKET = "red_packet"
    SYSTEM = "system"


class ChatType(PyEnum):
    PRIVATE = "private"
    GROUP = "group"


class FriendStatus(PyEnum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    BLOCKED = "blocked"


class RedPacketStatus(PyEnum):
    ACTIVE = "active"
    EXPIRED = "expired"
    FINISHED = "finished"


class Chat(Base):
    """聊天室模型"""
    __tablename__ = "db_im_chats"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(100))
    chat_type = Column(String(20), nullable=False)  # 用字符串存储
    created_at = Column(DateTime, default=datetime.utcnow)
    created_by = Column(String(36), ForeignKey("users.user_id"))
    avatar = Column(String(255))
    description = Column(Text)
    # 群公告字段
    announcement = Column(Text)
    announcement_at = Column(DateTime)
    announcement_by = Column(String(36), ForeignKey("users.user_id"))

    # 关系（IM 模型之间，保留 back_populates）
    messages = relationship("Message", back_populates="chat")
    group_members = relationship("GroupMember", back_populates="chat")


class Message(Base):
    """消息模型"""
    __tablename__ = "db_im_messages"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    chat_id = Column(String(36), ForeignKey("db_im_chats.id"), nullable=False)
    sender_id = Column(String(36), ForeignKey("users.user_id"), nullable=False)
    content = Column(Text)
    message_type = Column(Enum(MessageType), nullable=False)
    file_path = Column(String(500))
    file_name = Column(String(255))
    file_size = Column(Integer)
    created_at = Column(DateTime, default=datetime.utcnow)
    edited_at = Column(DateTime)
    is_deleted = Column(Boolean, default=False)

    # 关系
    chat = relationship("Chat", back_populates="messages")
    # 指向 User：无 back_populates
    sender = relationship("User", foreign_keys=[sender_id])


class Friendship(Base):
    """好友关系模型"""
    __tablename__ = "db_im_friendships"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    requester_id = Column(String(36), ForeignKey("users.user_id"), nullable=False)
    addressee_id = Column(String(36), ForeignKey("users.user_id"), nullable=False)
    status = Column(Enum(FriendStatus), default=FriendStatus.PENDING)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)

    # 关系（指向 User，无 back_populates）
    requester = relationship("User", foreign_keys=[requester_id])
    addressee = relationship("User", foreign_keys=[addressee_id])


class GroupMember(Base):
    """群成员模型"""
    __tablename__ = "db_im_group_members"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    chat_id = Column(String(36), ForeignKey("db_im_chats.id"), nullable=False)
    user_id = Column(String(36), ForeignKey("users.user_id"), nullable=False)
    is_admin = Column(Boolean, default=False)
    joined_at = Column(DateTime, default=datetime.utcnow)

    # 关系
    chat = relationship("Chat", back_populates="group_members")
    # 指向 User，无 back_populates
    user = relationship("User", foreign_keys=[user_id])


class RedPacket(Base):
    """红包模型"""
    __tablename__ = "db_im_red_packets"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    sender_id = Column(String(36), ForeignKey("users.user_id"), nullable=False)
    chat_id = Column(String(36), ForeignKey("db_im_chats.id"), nullable=False)
    message_id = Column(String(36), ForeignKey("db_im_messages.id"), nullable=False)
    total_amount = Column(Integer, nullable=False)  # 总积分
    total_count = Column(Integer, nullable=False)   # 总个数
    remaining_amount = Column(Integer, nullable=False)
    remaining_count = Column(Integer, nullable=False)
    blessing_words = Column(String(200))
    status = Column(Enum(RedPacketStatus), default=RedPacketStatus.ACTIVE)
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)

    # 关系
    sender = relationship("User", foreign_keys=[sender_id])
    # IM 模型之间，保留 back_populates
    claims = relationship("RedPacketClaim", back_populates="red_packet")


class RedPacketClaim(Base):
    """红包领取记录模型"""
    __tablename__ = "db_im_red_packet_claims"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    red_packet_id = Column(String(36), ForeignKey("db_im_red_packets.id"), nullable=False)
    user_id = Column(String(36), ForeignKey("users.user_id"), nullable=False)
    amount = Column(Integer, nullable=False)
    claimed_at = Column(DateTime, default=datetime.utcnow)

    # 关系
    red_packet = relationship("RedPacket", back_populates="claims")
    # 指向 User，无 back_populates
    user = relationship("User", foreign_keys=[user_id])


class ReadReceipt(Base):
    """已读回执模型 — 记录用户在某个聊天中已读的最后一条消息"""
    __tablename__ = "db_im_read_receipts"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    chat_id = Column(String(36), ForeignKey("db_im_chats.id"), nullable=False)
    user_id = Column(String(36), ForeignKey("users.user_id"), nullable=False)
    last_read_message_id = Column(String(36), ForeignKey("db_im_messages.id"))
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # 关系
    chat = relationship("Chat")
    user = relationship("User", foreign_keys=[user_id])
    last_read_message = relationship("Message", foreign_keys=[last_read_message_id])
