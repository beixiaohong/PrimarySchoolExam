"""IM 即时通讯模块 - Pydantic Schema（pydantic v2）

重建自 temp/wulala/im/route_im.py 中使用的 im_schemas.* 模型。
源仓库没有提供 im_schemas 文件，这里根据路由中的实际字段用法重建。
"""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


# ───────────────── 好友 ─────────────────
class FriendAddRequest(BaseModel):
    """添加好友请求：接收者（按 user_id / 邮箱 / 昵称 定位）"""
    addressee_username: str = Field(..., description="接收者 user_id / 邮箱 / 昵称")


# 路由中原使用 FriendshipCreate，这里别名保持一致（两者等价）
FriendshipCreate = FriendAddRequest


# ───────────────── 用户资料响应 ─────────────────
class UserResponse(BaseModel):
    id: str
    username: Optional[str] = None
    email: Optional[str] = None
    nickname: Optional[str] = None
    avatar: Optional[str] = None
    points: int = 0
    is_online: bool = False
    last_seen: Optional[datetime] = None


# ───────────────── 聊天室 ─────────────────
class ChatCreate(BaseModel):
    name: Optional[str] = None
    chat_type: str = Field(..., description="private / group")
    description: Optional[str] = None
    target_user_id: Optional[str] = None


class ChatResponse(BaseModel):
    id: str
    name: Optional[str] = None
    chat_type: str
    avatar: Optional[str] = None
    description: Optional[str] = None
    created_at: Optional[datetime] = None
    member_count: int = 0


# ───────────────── 消息 ─────────────────
class MessageResponse(BaseModel):
    id: str
    chat_id: str
    sender_id: str
    sender_nickname: Optional[str] = None
    content: Optional[str] = None
    message_type: str
    file_path: Optional[str] = None
    file_name: Optional[str] = None
    file_size: Optional[int] = None
    created_at: Optional[datetime] = None


# ───────────────── 红包 ─────────────────
class RedPacketCreate(BaseModel):
    chat_id: str
    total_amount: int = Field(..., description="总金额（单位：分/积分）")
    total_count: int = Field(..., description="红包个数")
    blessing_words: Optional[str] = None


class RedPacketResponse(BaseModel):
    id: str
    total_amount: int
    total_count: int
    remaining_amount: int
    remaining_count: int
    blessing_words: Optional[str] = None
    status: str
    created_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
