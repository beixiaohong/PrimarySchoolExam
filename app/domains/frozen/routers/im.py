# app/routers/im.py
"""
IM即时通讯系统 - FastAPI路由（适配至「智学学堂」FastAPI 应用）

适配自 temp/wulala/im/route_im.py：
- 移除 backend.* / jwt / aiofiles / localconfig / user_auth / ModUser 依赖。
- REST 鉴权改用 require_user（Bearer token）+ Depends(get_db)。
- WebSocket 鉴权：从 query_params 读 token，用 SessionLocal 短会话校验。
- DB 连接池铁律：WebSocket 内每次 DB 操作开/关短会话（SessionLocal），
  绝不把会话跨 WS 生命周期持有；broadcast_to_chat 内部自行开短会话。
- 文件上传改用标准 open()/shutil，存到 output/im_uploads/。
"""
from fastapi import Depends, APIRouter, HTTPException, UploadFile, WebSocket, WebSocketDisconnect, File, Form
from sqlalchemy.orm import Session
from sqlalchemy import or_

from app.database import get_db, SessionLocal
from app.models.user import User
from app.models.im import *  # Chat, Message, Friendship, GroupMember, RedPacket, RedPacketClaim, ReadReceipt, *Type
from app.schemas.im import *
from app.domains.frozen.services.im_crud import (
    get_private_chat,
    get_chat_by_id,
    update_read_receipt,
    get_unread_counts,
    get_message_by_id,
    block_user as block_user_crud,
    unblock_user as unblock_user_crud,
    get_blocked_list as get_blocked_list_crud,
    leave_group as leave_group_crud,
    update_announcement as update_announcement_crud,
    recall_message as recall_message_crud,
    delete_message as delete_message_crud,
)
from app.domains.identity.contracts import require_user

import json
import os
import uuid
import random
import shutil
import mimetypes
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict, Any

router = APIRouter()

# ───────────────── 文件上传目录 ─────────────────
# 存到项目根 /output/im_uploads/（标准库 open() 写入，未使用 aiofiles）
try:
    from app.config import BASE_DIR
except Exception:  # pragma: no cover
    BASE_DIR = os.getcwd()
UPLOAD_ROOT = os.path.join(str(BASE_DIR), "output", "im_uploads")


# ───────────────── WebSocket 连接管理器 ─────────────────
class ConnectionManager:
    """WebSocket 连接管理器：用户级连接追踪 + 消息推送。"""
    def __init__(self):
        """初始化连接管理器：维护连接ID->WebSocket 与 user_id->连接ID列表两张索引。"""
        self.active_connections: Dict[str, WebSocket] = {}
        self.user_connections: Dict[str, list] = {}  # user_id -> [connection_id, ...]

    async def connect(self, websocket: WebSocket, user_id: str):
        """接受并登记一个 WebSocket 连接，返回本次连接的 connection_id。"""
        await websocket.accept()
        connection_id = str(uuid.uuid4())
        self.active_connections[connection_id] = websocket
        if user_id not in self.user_connections:
            self.user_connections[user_id] = []
        self.user_connections[user_id].append(connection_id)
        return connection_id

    def disconnect(self, connection_id: str, user_id: str):
        """移除指定连接，并清理该用户的连接索引（索引为空时删除 user_id 条目）。"""
        if connection_id in self.active_connections:
            del self.active_connections[connection_id]
        if user_id in self.user_connections:
            self.user_connections[user_id] = [
                cid for cid in self.user_connections[user_id] if cid != connection_id
            ]
            if not self.user_connections[user_id]:
                del self.user_connections[user_id]

    async def send_personal_message(self, message: str, user_id: str):
        """向用户的所有在线设备发送消息"""
        conn_ids = self.user_connections.get(user_id, [])
        for cid in conn_ids:
            if cid in self.active_connections:
                try:
                    await self.active_connections[cid].send_text(message)
                except Exception:
                    pass

    async def broadcast_to_chat(self, message: str, chat_id: str):
        """
        广播到聊天室所有在线成员。
        内部开短会话查询成员（DB 连接池铁律：查询完即关闭，不在 await 发送期间持有会话）。
        """
        with SessionLocal() as db:
            members = db.query(GroupMember).filter(GroupMember.chat_id == chat_id).all()
            user_ids = [str(m.user_id) for m in members]
        for uid in user_ids:
            await self.send_personal_message(message, uid)


manager = ConnectionManager()


# ───────────────── 好友系统接口 ─────────────────
@router.post("/friends/add")
async def add_friend(
    friendship: FriendshipCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_user),
):
    """添加好友（按 user_id / 邮箱 / 昵称 定位接收者）"""
    target_user = db.query(User).filter(
        or_(
            User.user_id == friendship.addressee_username,
            User.email == friendship.addressee_username,
            User.nickname == friendship.addressee_username,
        )
    ).first()
    if not target_user:
        raise HTTPException(status_code=404, detail="目标用户不存在")

    if target_user.user_id == current_user.user_id:
        raise HTTPException(status_code=400, detail="Cannot add yourself as friend")

    existing = db.query(Friendship).filter(
        ((Friendship.requester_id == current_user.user_id) & (Friendship.addressee_id == target_user.user_id)) |
        ((Friendship.requester_id == target_user.user_id) & (Friendship.addressee_id == current_user.user_id))
    ).first()

    if existing:
        raise HTTPException(status_code=400, detail="Friend request already exists or you are already friends")

    friendship_request = Friendship(
        requester_id=current_user.user_id,
        addressee_id=target_user.user_id,
        status=FriendStatus.PENDING,
    )
    db.add(friendship_request)
    db.commit()

    await manager.send_personal_message(
        json.dumps({
            "type": "friend_request",
            "from_user": current_user.nickname,
            "from_user_id": str(current_user.user_id),
            "message": f"{current_user.nickname} 想添加你为好友",
        }),
        str(target_user.user_id),
    )

    return {"message": "Friend request sent"}


@router.get("/friends")
async def get_friends(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_user),
):
    """获取好友列表"""
    friendships = db.query(Friendship).filter(
        ((Friendship.requester_id == current_user.user_id) | (Friendship.addressee_id == current_user.user_id)) &
        (Friendship.status == FriendStatus.ACCEPTED)
    ).all()

    friends = []
    for friendship in friendships:
        friend_id = friendship.addressee_id if friendship.requester_id == current_user.user_id else friendship.requester_id
        friend = db.query(User).filter(User.user_id == friend_id).first()
        if friend:
            friends.append(UserResponse(
                id=str(friend.user_id),
                username=friend.user_id,
                email=friend.email,
                nickname=friend.nickname,
                avatar=friend.avatar,
                points=friend.points,
                is_online=friend.is_online,
                last_seen=friend.last_seen,
            ))
    return friends


@router.post("/friends/accept/{friendship_id}")
async def accept_friend(
    friendship_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_user),
):
    """接受好友请求"""
    friendship = db.query(Friendship).filter(
        Friendship.id == friendship_id,
        Friendship.addressee_id == current_user.user_id,
        Friendship.status == FriendStatus.PENDING,
    ).first()

    if not friendship:
        raise HTTPException(status_code=404, detail="Friend request not found")
    friendship.status = FriendStatus.ACCEPTED
    friendship.updated_at = datetime.now(timezone.utc)
    db.commit()

    await manager.send_personal_message(
        json.dumps({
            "type": "friend_accepted",
            "from_user": current_user.nickname,
            "message": f"{current_user.nickname} 接受了你的好友请求",
        }),
        str(friendship.requester_id),
    )

    return {"message": "Friend request accepted"}


@router.get("/friends/pending")
async def get_pending_requests(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_user),
):
    """获取待处理的好友请求列表"""
    pending = db.query(Friendship).filter(
        (Friendship.addressee_id == current_user.user_id) &
        (Friendship.status == FriendStatus.PENDING)
    ).all()
    result = []
    for p in pending:
        requester = db.query(User).filter(User.user_id == p.requester_id).first()
        result.append({
            "friendship_id": p.id,
            "user_id": str(p.requester_id),
            "username": requester.user_id if requester else "",
            "nickname": requester.nickname if requester else "",
            "avatar": requester.avatar if requester else "",
            "created_at": str(p.created_at),
        })
    return result


# ───────────────── 聊天接口 ─────────────────
@router.post("/chats", response_model=ChatResponse)
async def create_chat(
    chat: ChatCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_user),
):
    """创建聊天室（群聊或私聊）"""
    # 私聊：查找或创建
    if chat.chat_type == ChatType.PRIVATE.value and chat.target_user_id:
        target_id = chat.target_user_id
        target_user = db.query(User).filter(User.user_id == target_id).first()
        if not target_user:
            raise HTTPException(status_code=404, detail="目标用户不存在")
        if target_id == str(current_user.user_id):
            raise HTTPException(status_code=400, detail="不能和自己创建私聊")

        existing = get_private_chat(db, str(current_user.user_id), target_id)
        if existing:
            return ChatResponse(
                id=str(existing.id),
                name=existing.name or target_user.nickname,
                chat_type=existing.chat_type,
                avatar=existing.avatar,
                description=existing.description,
                created_at=existing.created_at,
                member_count=2,
            )

        db_chat = Chat(
            name=None,
            chat_type=ChatType.PRIVATE.value,
            created_by=current_user.user_id,
        )
        db.add(db_chat)
        db.flush()
        db.add(GroupMember(chat_id=db_chat.id, user_id=str(current_user.user_id), is_admin=False))
        db.add(GroupMember(chat_id=db_chat.id, user_id=target_id, is_admin=False))
        db.commit()
        db.refresh(db_chat)
        return ChatResponse(
            id=str(db_chat.id),
            name=target_user.nickname,
            chat_type=db_chat.chat_type,
            avatar=db_chat.avatar,
            description=db_chat.description,
            created_at=db_chat.created_at,
            member_count=2,
        )

    # 群聊：需要名称
    if not chat.name:
        raise HTTPException(status_code=422, detail="群聊需要设置名称")

    db_chat = Chat(
        name=chat.name,
        chat_type=chat.chat_type,
        created_by=current_user.user_id,
        description=chat.description,
    )
    db.add(db_chat)
    db.commit()
    db.refresh(db_chat)

    member = GroupMember(chat_id=db_chat.id, user_id=current_user.user_id, is_admin=True)
    db.add(member)
    db.commit()

    return ChatResponse(
        id=str(db_chat.id),
        name=db_chat.name,
        chat_type=db_chat.chat_type,
        avatar=db_chat.avatar,
        description=db_chat.description,
        created_at=db_chat.created_at,
        member_count=1,
    )


@router.get("/chats")
async def get_chats(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_user),
):
    """获取用户参与的群聊与私聊"""
    group_chats = db.query(Chat).join(GroupMember).filter(
        GroupMember.user_id == current_user.user_id,
        Chat.chat_type == ChatType.GROUP.value,
    ).all()

    private_chats = db.query(Chat).join(GroupMember).filter(
        GroupMember.user_id == current_user.user_id,
        Chat.chat_type == ChatType.PRIVATE.value,
    ).all()

    chats = []

    for chat in group_chats:
        member_count = db.query(GroupMember).filter(GroupMember.chat_id == chat.id).count()
        chats.append(ChatResponse(
            id=str(chat.id),
            name=chat.name,
            chat_type=chat.chat_type,
            avatar=chat.avatar,
            description=chat.description,
            created_at=chat.created_at,
            member_count=member_count,
        ))

    for chat in private_chats:
        other_member = db.query(GroupMember).filter(
            GroupMember.chat_id == chat.id,
            GroupMember.user_id != current_user.user_id,
        ).first()
        if other_member:
            other_user = db.query(User).filter(User.user_id == other_member.user_id).first()
            if other_user:
                chats.append(ChatResponse(
                    id=str(chat.id),
                    name=other_user.nickname,
                    chat_type=ChatType.PRIVATE.value,
                    avatar=other_user.avatar,
                    description=chat.description,
                    created_at=chat.created_at,
                    member_count=2,
                ))

    return chats


@router.get("/chats/{chat_id}/messages")
async def get_messages(
    chat_id: str,
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_user),
):
    """获取聊天消息列表"""
    membership = db.query(GroupMember).filter(
        GroupMember.chat_id == chat_id,
        GroupMember.user_id == current_user.user_id,
    ).first()
    if not membership:
        raise HTTPException(status_code=403, detail="Access denied")

    messages = db.query(Message).filter(
        Message.chat_id == chat_id,
        Message.is_deleted == False,
    ).order_by(Message.created_at.desc()).offset(skip).limit(limit).all()

    result = []
    for message in messages:
        sender = db.query(User).filter(User.user_id == message.sender_id).first()
        result.append(MessageResponse(
            id=str(message.id),
            chat_id=str(message.chat_id),
            sender_id=str(message.sender_id),
            sender_nickname=sender.nickname if sender else "Unknown",
            content=message.content,
            message_type=message.message_type.value,
            file_path=message.file_path,
            file_name=message.file_name,
            file_size=message.file_size,
            created_at=message.created_at,
        ))
    return result


# ───────────────── 红包系统 ─────────────────
@router.post("/red-packets")
async def create_red_packet(
    red_packet: RedPacketCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_user),
):
    """创建红包（扣除积分，广播红包消息）"""
    if current_user.points < red_packet.total_amount:
        raise HTTPException(status_code=400, detail="Insufficient points")

    current_user.points -= red_packet.total_amount

    message = Message(
        chat_id=red_packet.chat_id,
        sender_id=current_user.user_id,
        content=f"[红包] {red_packet.blessing_words}",
        message_type=MessageType.RED_PACKET,
    )
    db.add(message)
    db.commit()
    db.refresh(message)

    db_red_packet = RedPacket(
        sender_id=current_user.user_id,
        chat_id=red_packet.chat_id,
        message_id=message.id,
        total_amount=red_packet.total_amount,
        total_count=red_packet.total_count,
        remaining_amount=red_packet.total_amount,
        remaining_count=red_packet.total_count,
        blessing_words=red_packet.blessing_words,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
    )
    db.add(db_red_packet)
    db.commit()
    db.refresh(db_red_packet)

    await manager.broadcast_to_chat(
        json.dumps({
            "type": "message",
            "message": {
                "id": str(message.id),
                "chat_id": str(message.chat_id),
                "sender_id": str(message.sender_id),
                "sender_nickname": current_user.nickname,
                "content": message.content,
                "message_type": message.message_type.value,
                "created_at": message.created_at.isoformat(),
                "red_packet_id": str(db_red_packet.id),
            }
        }),
        red_packet.chat_id,
    )

    return RedPacketResponse(
        id=str(db_red_packet.id),
        total_amount=db_red_packet.total_amount,
        total_count=db_red_packet.total_count,
        remaining_amount=db_red_packet.remaining_amount,
        remaining_count=db_red_packet.remaining_count,
        blessing_words=db_red_packet.blessing_words,
        status=db_red_packet.status.value,
        created_at=db_red_packet.created_at,
        expires_at=db_red_packet.expires_at,
    )


@router.post("/red-packets/{red_packet_id}/claim")
async def claim_red_packet(
    red_packet_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_user),
):
    """领取红包（随机分配金额，广播领取通知）"""
    red_packet = db.query(RedPacket).filter(RedPacket.id == red_packet_id).first()
    if not red_packet:
        raise HTTPException(status_code=404, detail="Red packet not found")

    if red_packet.status != RedPacketStatus.ACTIVE:
        raise HTTPException(status_code=400, detail="Red packet is not active")

    if red_packet.expires_at < datetime.now(timezone.utc):
        red_packet.status = RedPacketStatus.EXPIRED
        db.commit()
        raise HTTPException(status_code=400, detail="Red packet has expired")

    if red_packet.remaining_count <= 0:
        red_packet.status = RedPacketStatus.FINISHED
        db.commit()
        raise HTTPException(status_code=400, detail="Red packet is finished")

    existing_claim = db.query(RedPacketClaim).filter(
        RedPacketClaim.red_packet_id == red_packet_id,
        RedPacketClaim.user_id == current_user.user_id,
    ).first()
    if existing_claim:
        raise HTTPException(status_code=400, detail="You have already claimed this red packet")

    if red_packet.sender_id == current_user.user_id:
        raise HTTPException(status_code=400, detail="Cannot claim your own red packet")

    if red_packet.remaining_count == 1:
        claim_amount = red_packet.remaining_amount
    else:
        min_amount = red_packet.remaining_count - 1
        max_amount = red_packet.remaining_amount - min_amount
        claim_amount = random.randint(1, max_amount)

    claim = RedPacketClaim(
        red_packet_id=red_packet.id,
        user_id=current_user.user_id,
        amount=claim_amount,
    )
    db.add(claim)

    red_packet.remaining_amount -= claim_amount
    red_packet.remaining_count -= 1
    current_user.points += claim_amount

    if red_packet.remaining_count == 0:
        red_packet.status = RedPacketStatus.FINISHED

    db.commit()

    await manager.broadcast_to_chat(
        json.dumps({
            "type": "red_packet_claimed",
            "red_packet_id": str(red_packet.id),
            "user_nickname": current_user.nickname,
            "amount": claim_amount,
            "remaining_count": red_packet.remaining_count,
        }),
        str(red_packet.chat_id),
    )

    return {
        "amount": claim_amount,
        "remaining_count": red_packet.remaining_count,
        "remaining_amount": red_packet.remaining_amount,
    }


@router.get("/red-packets/{red_packet_id}/claims")
async def get_red_packet_claims(
    red_packet_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_user),
):
    """获取红包领取记录"""
    red_packet = db.query(RedPacket).filter(RedPacket.id == red_packet_id).first()
    if not red_packet:
        raise HTTPException(status_code=404, detail="Red packet not found")

    claims = db.query(RedPacketClaim).filter(RedPacketClaim.red_packet_id == red_packet_id).all()

    result = []
    for claim in claims:
        u = db.query(User).filter(User.user_id == claim.user_id).first()
        result.append({
            "user_id": str(claim.user_id),
            "user_nickname": u.nickname if u else "Unknown",
            "amount": claim.amount,
            "claimed_at": claim.claimed_at,
        })

    return {
        "red_packet": RedPacketResponse(
            id=str(red_packet.id),
            total_amount=red_packet.total_amount,
            total_count=red_packet.total_count,
            remaining_amount=red_packet.remaining_amount,
            remaining_count=red_packet.remaining_count,
            blessing_words=red_packet.blessing_words,
            status=red_packet.status.value,
            created_at=red_packet.created_at,
            expires_at=red_packet.expires_at,
        ),
        "claims": result,
    }


# ───────────────── WebSocket 连接 ─────────────────
@router.websocket("/ws/chat")
async def websocket_endpoint(websocket: WebSocket):
    """
    WebSocket 端点（鉴权：?token=...）。

    DB 连接池铁律：鉴权、在线状态更新、消息落库、广播成员查询，
    全部使用短生命周期 SessionLocal 会话，绝不跨 WS 生命周期持有。
    """
    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=1008)
        return

    # 鉴权（短会话）
    with SessionLocal() as db:
        user = db.query(User).filter(User.token == token).first()
        if not user:
            await websocket.close(code=1008)
            return
        # 加载后续需要的属性（会话关闭后对象脱管，但标量已读出）
        user_id = user.user_id
        nickname = user.nickname
        user.is_online = True
        user.last_seen = datetime.now(timezone.utc)
        db.commit()

    connection_id = await manager.connect(websocket, user_id)

    # 离线未读摘要（短会话）
    try:
        with SessionLocal() as db:
            unread = get_unread_counts(db, user_id)
        if unread:
            await websocket.send_text(json.dumps({
                "type": "offline_summary",
                "unread_counts": unread,
                "total": sum(unread.values()),
            }))
    except Exception:
        pass

    try:
        while True:
            data = await websocket.receive_text()
            try:
                message_data = json.loads(data)
            except Exception:
                continue

            typ = message_data.get("type")
            if typ == "message":
                await handle_message(message_data, user_id, nickname)
            elif typ == "typing":
                await handle_typing(message_data, user_id)
            elif typ == "read":
                await handle_read(message_data, user_id)
    except WebSocketDisconnect:
        manager.disconnect(connection_id, user_id)
        # 更新离线状态（短会话）
        try:
            with SessionLocal() as db:
                u = db.query(User).filter(User.user_id == user_id).first()
                if u:
                    u.is_online = False
                    u.last_seen = datetime.now(timezone.utc)
                    db.commit()
        except Exception:
            pass


async def handle_message(message_data: dict, user_id: str, nickname: str):
    """处理消息发送（权限校验 + 落库 + 广播，全程短会话）"""
    chat_id = message_data.get("chat_id")
    if not chat_id:
        return
    content = message_data.get("content")
    mt = message_data.get("message_type", MessageType.TEXT.value)
    message_type = mt if isinstance(mt, MessageType) else MessageType(mt)
    file_path = message_data.get("file_path")
    file_name = message_data.get("file_name")
    file_size = message_data.get("file_size")

    msg_id = None
    created_iso = None
    with SessionLocal() as db:
        membership = db.query(GroupMember).filter(
            GroupMember.chat_id == chat_id,
            GroupMember.user_id == user_id,
        ).first()
        if not membership:
            return
        message = Message(
            chat_id=chat_id,
            sender_id=user_id,
            content=content,
            message_type=message_type,
            file_path=file_path,
            file_name=file_name,
            file_size=file_size,
        )
        db.add(message)
        db.commit()
        db.refresh(message)
        msg_id = str(message.id)
        created_iso = message.created_at.isoformat() if message.created_at else None

    await manager.broadcast_to_chat(
        json.dumps({
            "type": "message",
            "message": {
                "id": msg_id,
                "chat_id": str(chat_id),
                "sender_id": str(user_id),
                "sender_nickname": nickname,
                "content": content,
                "message_type": message_type.value,
                "file_path": file_path,
                "file_name": file_name,
                "file_size": file_size,
                "created_at": created_iso,
            }
        }),
        chat_id,
    )


async def handle_typing(message_data: dict, user_id: str):
    """处理打字状态（仅实时广播，不落库）"""
    chat_id = message_data.get("chat_id")
    is_typing = message_data.get("is_typing", False)
    if not chat_id:
        return
    await manager.broadcast_to_chat(
        json.dumps({
            "type": "typing",
            "chat_id": chat_id,
            "user_id": str(user_id),
            "is_typing": is_typing,
        }),
        chat_id,
    )


async def handle_read(message_data: dict, user_id: str):
    """处理已读状态（更新回执 + 通知发送者）"""
    message_id = message_data.get("message_id")
    chat_id = message_data.get("chat_id")
    if message_id and chat_id:
        sender_id = None
        with SessionLocal() as db:
            update_read_receipt(db, chat_id, user_id, message_id)
            message = get_message_by_id(db, message_id)
            sender_id = message.sender_id if message else None
        if message and sender_id != user_id:
            await manager.send_personal_message(
                json.dumps({
                    "type": "message_read",
                    "message_id": message_id,
                    "chat_id": chat_id,
                    "read_by": str(user_id),
                }),
                sender_id,
            )


# ───────────────── 群聊管理接口 ─────────────────
@router.post("/chats/{chat_id}/members")
async def add_chat_member(
    chat_id: str,
    user_id: str = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_user),
):
    """添加群聊成员（仅管理员）"""
    membership = db.query(GroupMember).filter(
        GroupMember.chat_id == chat_id,
        GroupMember.user_id == current_user.user_id,
        GroupMember.is_admin == True,
    ).first()
    if not membership:
        raise HTTPException(status_code=403, detail="Only group admins can add members")

    target_user = db.query(User).filter(User.user_id == user_id).first()
    if not target_user:
        raise HTTPException(status_code=404, detail="目标用户不存在")

    existing_member = db.query(GroupMember).filter(
        GroupMember.chat_id == chat_id,
        GroupMember.user_id == user_id,
    ).first()
    if existing_member:
        raise HTTPException(status_code=400, detail="该用户已经是群成员")

    new_member = GroupMember(chat_id=chat_id, user_id=user_id, is_admin=False)
    db.add(new_member)
    db.commit()

    system_message = Message(
        chat_id=chat_id,
        sender_id=current_user.user_id,
        content=f"{target_user.nickname} 加入了群聊",
        message_type=MessageType.SYSTEM,
    )
    db.add(system_message)
    db.commit()

    await manager.broadcast_to_chat(
        json.dumps({
            "type": "message",
            "message": {
                "id": str(system_message.id),
                "chat_id": str(system_message.chat_id),
                "sender_id": str(system_message.sender_id),
                "sender_nickname": "系统",
                "content": system_message.content,
                "message_type": system_message.message_type.value,
                "created_at": system_message.created_at.isoformat(),
            }
        }),
        chat_id,
    )

    return {"message": "Member added successfully"}


@router.delete("/chats/{chat_id}/members/{user_id}")
async def remove_chat_member(
    chat_id: str,
    user_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_user),
):
    """移除群聊成员（仅管理员，不能移除自己）"""
    membership = db.query(GroupMember).filter(
        GroupMember.chat_id == chat_id,
        GroupMember.user_id == current_user.user_id,
        GroupMember.is_admin == True,
    ).first()
    if not membership:
        raise HTTPException(status_code=403, detail="Only group admins can remove members")

    target_member = db.query(GroupMember).filter(
        GroupMember.chat_id == chat_id,
        GroupMember.user_id == user_id,
    ).first()
    if not target_member:
        raise HTTPException(status_code=404, detail="Member not found")

    if user_id == str(current_user.user_id):
        raise HTTPException(status_code=400, detail="Cannot remove yourself")

    target_user = db.query(User).filter(User.user_id == user_id).first()

    db.delete(target_member)
    db.commit()

    system_message = Message(
        chat_id=chat_id,
        sender_id=current_user.user_id,
        content=f"{target_user.nickname if target_user else 'Unknown'} 被移出群聊",
        message_type=MessageType.SYSTEM,
    )
    db.add(system_message)
    db.commit()

    await manager.broadcast_to_chat(
        json.dumps({
            "type": "message",
            "message": {
                "id": str(system_message.id),
                "chat_id": str(system_message.chat_id),
                "sender_id": str(system_message.sender_id),
                "sender_nickname": "系统",
                "content": system_message.content,
                "message_type": system_message.message_type.value,
                "created_at": system_message.created_at.isoformat(),
            }
        }),
        chat_id,
    )

    return {"message": "Member removed successfully"}


@router.get("/chats/{chat_id}/members")
async def get_chat_members(
    chat_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_user),
):
    """获取群成员列表"""
    membership = db.query(GroupMember).filter(
        GroupMember.chat_id == chat_id,
        GroupMember.user_id == current_user.user_id,
    ).first()
    if not membership:
        raise HTTPException(status_code=403, detail="Access denied")

    members = db.query(GroupMember).filter(GroupMember.chat_id == chat_id).all()
    result = []
    for member in members:
        u = db.query(User).filter(User.user_id == member.user_id).first()
        if u:
            result.append({
                "user_id": str(u.user_id),
                "username": u.user_id,
                "nickname": u.nickname,
                "avatar": u.avatar,
                "is_admin": member.is_admin,
                "is_online": u.is_online,
                "joined_at": member.joined_at,
            })
    return result


# ───────────────── 用户个人资料接口 ─────────────────
@router.get("/users/me")
async def get_user_profile(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_user),
):
    """获取当前用户资料"""
    return UserResponse(
        id=str(current_user.user_id),
        username=current_user.user_id,
        email=current_user.email or '',
        nickname=current_user.nickname or '',
        avatar=current_user.avatar,
        points=current_user.points,
        is_online=current_user.is_online,
        last_seen=current_user.last_seen,
    )


@router.put("/users/me")
async def update_user_profile(
    nickname: Optional[str] = Form(None),
    avatar: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_user),
):
    """更新当前用户资料（昵称 / 头像）"""
    if nickname:
        current_user.nickname = nickname

    if avatar:
        if not avatar.content_type.startswith("image/"):
            raise HTTPException(status_code=400, detail="Invalid image file")

        os.makedirs(UPLOAD_ROOT, exist_ok=True)
        file_extension = avatar.filename.split(".")[-1] if "." in avatar.filename else "jpg"
        unique_filename = f"{uuid.uuid4()}.{file_extension}"
        file_path = os.path.join(UPLOAD_ROOT, unique_filename)

        content = await avatar.read()
        with open(file_path, "wb") as buffer:
            buffer.write(content)

        current_user.avatar = f"/output/im_uploads/{unique_filename}"

    db.commit()

    return UserResponse(
        id=str(current_user.user_id),
        username=current_user.user_id,
        email=current_user.email or '',
        nickname=current_user.nickname or '',
        avatar=current_user.avatar,
        points=current_user.points,
        is_online=current_user.is_online,
        last_seen=current_user.last_seen,
    )


@router.get("/users/search")
async def search_users(
    q: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_user),
):
    """搜索用户（按邮箱 / 昵称 / user_id 模糊匹配）"""
    if len(q) < 2:
        raise HTTPException(status_code=400, detail="Search query must be at least 2 characters")

    users = db.query(User).filter(
        or_(
            User.email.ilike(f"%{q}%"),
            User.nickname.ilike(f"%{q}%"),
            User.user_id.ilike(f"%{q}%"),
        )
    ).filter(User.user_id != current_user.user_id).limit(20).all()

    result = []
    for u in users:
        result.append({
            "id": str(u.user_id),
            "username": u.user_id,
            "nickname": u.nickname,
            "avatar": u.avatar,
            "is_online": u.is_online,
        })
    return result


# ───────────────── 消息撤回/删除/编辑 ─────────────────
@router.post("/messages/{message_id}/recall")
async def recall_message(
    message_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_user),
):
    """撤回消息（仅发送者可撤回）"""
    message = crud_recall_message(db, message_id, str(current_user.user_id))
    if not message:
        raise HTTPException(status_code=403, detail="无法撤回该消息")

    await manager.broadcast_to_chat(
        json.dumps({
            "type": "message_recalled",
            "message_id": message_id,
            "chat_id": message.chat_id,
        }),
        message.chat_id,
    )
    return {"message": "消息已撤回"}


@router.delete("/messages/{message_id}")
async def delete_message(
    message_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_user),
):
    """删除消息（软删除，仅发送者可操作）"""
    success = crud_delete_message(db, message_id, str(current_user.user_id))
    if not success:
        raise HTTPException(status_code=403, detail="无法删除该消息")
    return {"message": "消息已删除"}


@router.put("/messages/{message_id}")
async def edit_message(
    message_id: str,
    content: str = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_user),
):
    """编辑消息（仅发送者、仅文本消息）"""
    msg = get_message_by_id(db, message_id)
    if not msg:
        raise HTTPException(status_code=404, detail="消息不存在")
    if msg.sender_id != str(current_user.user_id):
        raise HTTPException(status_code=403, detail="只能编辑自己的消息")
    if msg.message_type != MessageType.TEXT:
        raise HTTPException(status_code=400, detail="只能编辑文本消息")

    msg.content = content
    msg.edited_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(msg)

    await manager.broadcast_to_chat(
        json.dumps({
            "type": "message_edited",
            "message_id": message_id,
            "chat_id": msg.chat_id,
            "content": content,
            "edited_at": msg.edited_at.isoformat(),
        }),
        msg.chat_id,
    )
    return {"message": "消息已编辑", "content": content}


# ───────────────── 黑名单功能 ─────────────────
@router.post("/friends/{target_user_id}/block")
async def block_user(
    target_user_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_user),
):
    """拉黑用户"""
    if target_user_id == str(current_user.user_id):
        raise HTTPException(status_code=400, detail="不能拉黑自己")

    target = db.query(User).filter(User.user_id == target_user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="用户不存在")

    block_user_crud(db, str(current_user.user_id), target_user_id)
    return {"message": f"已拉黑用户 {target.nickname}"}


@router.delete("/friends/{target_user_id}/block")
async def unblock_user(
    target_user_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_user),
):
    """解除拉黑"""
    success = unblock_user_crud(db, str(current_user.user_id), target_user_id)
    if not success:
        raise HTTPException(status_code=404, detail="该用户不在黑名单中")
    return {"message": "已解除拉黑"}


@router.get("/friends/blocked")
async def get_blocked_list(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_user),
):
    """获取黑名单列表"""
    blocked = get_blocked_list_crud(db, str(current_user.user_id))
    return [{"user_id": str(u.user_id), "nickname": u.nickname, "avatar": u.avatar} for u in blocked]


# ───────────────── 退出群聊 ─────────────────
@router.post("/chats/{chat_id}/leave")
async def leave_group(
    chat_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_user),
):
    """退出群聊（群主不能退出）"""
    success = leave_group_crud(db, chat_id, str(current_user.user_id))
    if not success:
        raise HTTPException(status_code=400, detail="无法退出群聊（可能是群主或不是成员）")

    system_msg = Message(
        chat_id=chat_id, sender_id=str(current_user.user_id),
        content=f"{current_user.nickname} 退出了群聊",
        message_type=MessageType.SYSTEM,
    )
    db.add(system_msg)
    db.commit()

    await manager.broadcast_to_chat(
        json.dumps({"type": "message", "message": {
            "content": f"{current_user.nickname} 退出了群聊",
            "message_type": "system", "chat_id": chat_id,
        }}),
        chat_id,
    )
    return {"message": "已退出群聊"}


# ───────────────── 群公告 ─────────────────
@router.put("/chats/{chat_id}/announcement")
async def update_announcement(
    chat_id: str,
    content: str = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_user),
):
    """更新群公告（仅管理员）"""
    chat = update_announcement_crud(db, chat_id, str(current_user.user_id), content)
    if not chat:
        raise HTTPException(status_code=403, detail="无权限或聊天室不存在")

    await manager.broadcast_to_chat(
        json.dumps({"type": "announcement", "chat_id": chat_id, "content": content, "by": current_user.nickname}),
        chat_id,
    )
    return {"message": "公告已更新", "announcement": chat.announcement}


@router.get("/chats/{chat_id}/announcement")
async def get_announcement(
    chat_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_user),
):
    """获取群公告"""
    chat = get_chat_by_id(db, chat_id)
    if not chat:
        raise HTTPException(status_code=404, detail="聊天室不存在")
    return {
        "announcement": chat.announcement,
        "announcement_at": chat.announcement_at.isoformat() if chat.announcement_at else None,
    }


# ───────────────── 已读回执 ─────────────────
@router.post("/messages/{message_id}/read")
async def mark_as_read(
    message_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_user),
):
    """标记消息为已读"""
    message = get_message_by_id(db, message_id)
    if not message:
        raise HTTPException(status_code=404, detail="消息不存在")

    update_read_receipt(db, message.chat_id, str(current_user.user_id), message_id)
    return {"message": "已标记为已读"}


@router.get("/messages/unread-count")
async def get_unread_count(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_user),
):
    """获取所有群聊的未读消息数"""
    counts = get_unread_counts(db, str(current_user.user_id))
    return {"unread_counts": counts, "total": sum(counts.values())}


# ───────────────── IM 文件上传 ─────────────────
ALLOWED_MIME_TYPES = {
    "image/jpeg", "image/png", "image/gif", "image/webp",
    "application/pdf", "text/plain",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB


@router.post("/upload/file")
async def upload_im_file(
    file: UploadFile = File(...),
    current_user: User = Depends(require_user),
):
    """IM 文件上传（MIME 白名单 + 大小限制，存到 output/im_uploads/）"""
    if file.content_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(status_code=400, detail=f"不支持的文件类型: {file.content_type}")

    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail=f"文件大小超过限制({MAX_FILE_SIZE // 1024 // 1024}MB)")

    os.makedirs(UPLOAD_ROOT, exist_ok=True)
    ext = mimetypes.guess_extension(file.content_type) or ".bin"
    unique_name = f"{uuid.uuid4()}{ext}"
    file_path = os.path.join(UPLOAD_ROOT, unique_name)

    with open(file_path, "wb") as f:
        f.write(content)

    file_url = f"/output/im_uploads/{unique_name}"
    return {
        "file_url": file_url,
        "file_name": file.filename,
        "file_size": len(content),
        "content_type": file.content_type,
    }


# ───────────────── 健康检查 ─────────────────
@router.get("/health")
async def health_check():
    """健康检查（公开接口）"""
    return {"status": "healthy", "timestamp": datetime.now(timezone.utc)}
