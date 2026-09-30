"""分类与标签路由（/api/blog/categories、/api/blog/tags）——**只读**。

权限说明（重要）：
本路由挂在 `/api/blog` 下，而 main.py 对该前缀统一附加 `user_auth_deps`
（= `require_self`，要求 **用户** Bearer token）。管理员 token 与用户 token 无法在同一个
Authorization 头里共存，因此**分类/标签的写操作不能放这里**，统一放到后台
`app/routers/admin/blog.py`（挂在 `/api/admin`，走 `_require_admin`）——
这也是本项目既有范式（/api/admin 前缀不挂 user_auth_deps）。

前台只保留列表读取：分类导航、标签云都需要，登录用户即可访问。
"""
import logging

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.domains.identity.contracts import require_user
from app.models.user import User
from app.schemas.blog import CategoryResponse, TagResponse
from app.domains.blog.services import taxonomy as taxo_svc

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/categories", response_model=list[CategoryResponse], summary="分类列表", tags=["内容/Blog"])
def list_categories(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_user),
):
    """全部分类（sort_order 升序 → id 升序）。"""
    return taxo_svc.list_categories(db)


@router.get("/tags", response_model=list[TagResponse], summary="标签列表", tags=["内容/Blog"])
def list_tags(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_user),
):
    """全部标签（id 升序）。"""
    return taxo_svc.list_tags(db)


@router.get("/tags/with-count", summary="标签 + 文章数", tags=["内容/Blog"])
def tags_with_count(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_user),
):
    """标签列表附带关联文章数（前台标签云用）。"""
    return taxo_svc.tags_with_count(db)
