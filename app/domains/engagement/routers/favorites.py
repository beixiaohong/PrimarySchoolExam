"""收藏夹（新功能 D，2026Q4）

API（engagement 域，挂在 /api/favorites，依赖 user_auth_deps 鉴权）：
- POST   ""            收藏（幂等：已收藏返回现有记录，不重复插入）
- DELETE "/{fav_id}"   取消收藏（仅本人可操作，越权/不存在返回 404）
- GET    ""            列表（?item_type=&page=&page_size=，用 paginate 助手，
                           page_size 强制 clamp[1,200]）

设计约束：
- 纯 DB 操作，无外部/AI 调用，不持连接等阻塞调用（铁律合规）。
- item_type 仅接受 paper / question，其余 400。
- 跨域取详情：收藏仅存 id，列表展示依赖客户端传入的 title 快照；
  如需最新详情由各域经 contracts 提供，避免循环依赖。
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.pagination import paginate
from app.database import get_db
from app.domains.identity.contracts import require_self
from app.models.favorite import UserFavorite
from app.models.user import User

router = APIRouter(tags=["favorites"])

VALID_TYPES = ("paper", "question")


class FavoriteIn(BaseModel):
    item_type: str
    item_id: str
    title: Optional[str] = None
    # 注：user_id 不在此声明——服务端以鉴权用户为准，不信任客户端传入


def _serialize(f: UserFavorite) -> dict:
    return {
        "id": f.id,
        "user_id": f.user_id,
        "item_type": f.item_type,
        "item_id": f.item_id,
        "title": f.title,
        "created_at": f.created_at.isoformat() if f.created_at else None,
    }


@router.post("")
def add_favorite(payload: FavoriteIn,
                current_user: User = Depends(require_self),
                db: Session = Depends(get_db)) -> dict:
    """收藏一个试卷/题目（幂等：已收藏返回现有记录，不重复插入）。"""
    item_type = (payload.item_type or "").strip().lower()
    item_id = (payload.item_id or "").strip()
    if item_type not in VALID_TYPES:
        raise HTTPException(status_code=400, detail="item_type 必须是 paper 或 question")
    if not item_id:
        raise HTTPException(status_code=400, detail="item_id 不能为空")
    uid = current_user.user_id

    existing = db.query(UserFavorite).filter(
        UserFavorite.user_id == uid,
        UserFavorite.item_type == item_type,
        UserFavorite.item_id == item_id,
    ).first()
    if existing:
        return _serialize(existing)  # 已收藏：返回现有，不重复插入（幂等）

    fav = UserFavorite(
        user_id=uid,
        item_type=item_type,
        item_id=item_id,
        title=(payload.title or "").strip() or None,
    )
    db.add(fav)
    db.commit()
    db.refresh(fav)
    return _serialize(fav)


@router.delete("/{fav_id}")
def remove_favorite(fav_id: int,
                    current_user: User = Depends(require_self),
                    db: Session = Depends(get_db)) -> dict:
    """取消收藏（仅本人可操作，越权/不存在返回 404，避免泄露存在性）。"""
    fav = db.query(UserFavorite).filter(
        UserFavorite.id == fav_id,
        UserFavorite.user_id == current_user.user_id,
    ).first()
    if not fav:
        raise HTTPException(status_code=404, detail="收藏记录不存在")
    db.delete(fav)
    db.commit()
    return {"ok": True, "id": fav_id}


@router.get("")
def list_favorites(item_type: Optional[str] = Query(None),
                  page: int = Query(1, ge=1),
                  page_size: int = Query(20, ge=1, le=200),
                  current_user: User = Depends(require_self),
                  db: Session = Depends(get_db)) -> dict:
    """收藏列表（分页；item_type 可选过滤；按收藏时间倒序）。"""
    uid = current_user.user_id
    q = db.query(UserFavorite).filter(UserFavorite.user_id == uid)
    if item_type:
        it = item_type.strip().lower()
        if it not in VALID_TYPES:
            raise HTTPException(status_code=400, detail="item_type 非法")
        q = q.filter(UserFavorite.item_type == it)
    q = q.order_by(UserFavorite.created_at.desc(), UserFavorite.id.desc())
    items, total = paginate(q, page, page_size)
    return {
        "items": [_serialize(f) for f in items],
        "total": total,
        "page": page,
        "page_size": page_size,
    }
