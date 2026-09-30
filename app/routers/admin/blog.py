"""管理后台 —— 内容 / Blog 管理（/api/admin/blog/*）

为什么分类/标签的增删改在这里而不在 `/api/blog`：
`/api/blog` 前缀被 main.py 统一附加 `user_auth_deps`（require_self，要 **用户** token），
而管理操作要求 **管理员** token，两者无法在同一个 Authorization 头共存。
故后台管理一律走 `/api/admin` 前缀（不挂 user_auth_deps），用 `_require_admin` 鉴权。

覆盖（blog.md §21）：
- 文章管理：搜索/筛选/分页 + 新增/编辑/删除/发布/取消发布/置顶/推荐（可管理全部作者的文章）
- 分类管理：新增/编辑/删除/排序
- 标签管理：新增/编辑/删除

跨域纪律：只经 `app.domains.blog.contracts` 访问内容域
（`.importlinter` 白名单边 `app.routers.admin.** -> app.domains.*.contracts`）。
"""
import logging

from fastapi import Depends, Query
from sqlalchemy.orm import Session
from typing import Optional

from app.database import get_db
from app.domains.blog.contracts import articles as articles_svc
from app.domains.blog.contracts import taxonomy as taxo_svc
from app.models.admin import Admin
from app.schemas.blog import (
    ArticleCreate,
    ArticleListResponse,
    ArticleResponse,
    ArticleUpdate,
    CategoryCreate,
    CategoryResponse,
    CategoryUpdate,
    TagCreate,
    TagResponse,
    TagUpdate,
)

from . import router
from .common import _require_admin

logger = logging.getLogger(__name__)


# ================================ 文章管理 ================================
@router.get("/blog/articles", response_model=ArticleListResponse, summary="后台文章列表", tags=["管理后台-内容"])
def admin_list_articles(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    status: Optional[str] = Query(None, description="draft|published，空=全部"),
    category_id: Optional[int] = Query(None),
    keyword: Optional[str] = Query(None, description="标题/摘要/正文关键词"),
    db: Session = Depends(get_db),
    admin: Admin = Depends(_require_admin),
):
    """后台文章列表：不受作者限制，可看全部状态（含草稿）。"""
    rows, total = articles_svc.list_articles(
        db, page=page, page_size=page_size, status=status,
        category_id=category_id, keyword=keyword,
    )
    return ArticleListResponse(items=rows, total=total, page=page, page_size=page_size)


@router.get("/blog/articles/{article_id}", response_model=ArticleResponse, summary="后台文章详情", tags=["管理后台-内容"])
def admin_get_article(
    article_id: int,
    db: Session = Depends(get_db),
    admin: Admin = Depends(_require_admin),
):
    """后台文章详情（含草稿）。"""
    art = articles_svc.get_article(db, article_id)
    return articles_svc.serialize(db, art)


@router.post("/blog/articles", response_model=ArticleResponse, summary="后台新建文章", tags=["管理后台-内容"])
def admin_create_article(
    payload: ArticleCreate,
    db: Session = Depends(get_db),
    admin: Admin = Depends(_require_admin),
):
    """后台新建文章：作者记为当前管理员账号名，便于审计追溯。"""
    return articles_svc.create_article(db, f"admin:{admin.username}", payload)


@router.put("/blog/articles/{article_id}", response_model=ArticleResponse, summary="后台编辑文章", tags=["管理后台-内容"])
def admin_update_article(
    article_id: int,
    payload: ArticleUpdate,
    db: Session = Depends(get_db),
    admin: Admin = Depends(_require_admin),
):
    """后台编辑任意文章（不做作者归属校验，这是后台与前台接口的唯一差别）。"""
    art = articles_svc.get_article(db, article_id)
    return articles_svc.update_article(db, art, payload)


@router.delete("/blog/articles/{article_id}", summary="后台删除文章", tags=["管理后台-内容"])
def admin_delete_article(
    article_id: int,
    db: Session = Depends(get_db),
    admin: Admin = Depends(_require_admin),
):
    """后台删除任意文章。"""
    art = articles_svc.get_article(db, article_id)
    articles_svc.delete_article(db, art)
    return {"message": "文章已删除"}


@router.post("/blog/articles/{article_id}/publish", response_model=ArticleResponse, summary="后台发布文章", tags=["管理后台-内容"])
def admin_publish_article(
    article_id: int,
    db: Session = Depends(get_db),
    admin: Admin = Depends(_require_admin),
):
    """后台发布文章。"""
    art = articles_svc.get_article(db, article_id)
    return articles_svc.set_published(db, art, True)


@router.post("/blog/articles/{article_id}/unpublish", response_model=ArticleResponse, summary="后台取消发布", tags=["管理后台-内容"])
def admin_unpublish_article(
    article_id: int,
    db: Session = Depends(get_db),
    admin: Admin = Depends(_require_admin),
):
    """后台取消发布。"""
    art = articles_svc.get_article(db, article_id)
    return articles_svc.set_published(db, art, False)


# ================================ 分类管理 ================================
@router.get("/blog/categories", response_model=list[CategoryResponse], summary="后台分类列表", tags=["管理后台-内容"])
def admin_list_categories(
    db: Session = Depends(get_db),
    admin: Admin = Depends(_require_admin),
):
    return taxo_svc.list_categories(db)


@router.post("/blog/categories", response_model=CategoryResponse, summary="后台新建分类", tags=["管理后台-内容"])
def admin_create_category(
    payload: CategoryCreate,
    db: Session = Depends(get_db),
    admin: Admin = Depends(_require_admin),
):
    return taxo_svc.create_category(db, payload)


@router.put("/blog/categories/{category_id}", response_model=CategoryResponse, summary="后台编辑分类", tags=["管理后台-内容"])
def admin_update_category(
    category_id: int,
    payload: CategoryUpdate,
    db: Session = Depends(get_db),
    admin: Admin = Depends(_require_admin),
):
    """编辑分类（含 sort_order 排序值，blog.md §16）。"""
    return taxo_svc.update_category(db, category_id, payload)


@router.delete("/blog/categories/{category_id}", summary="后台删除分类", tags=["管理后台-内容"])
def admin_delete_category(
    category_id: int,
    db: Session = Depends(get_db),
    admin: Admin = Depends(_require_admin),
):
    """删除分类；分类下仍有文章时拒绝（避免产生孤儿分类 id）。"""
    taxo_svc.delete_category(db, category_id)
    return {"message": "分类已删除"}


# ================================ 标签管理 ================================
@router.get("/blog/tags", response_model=list[TagResponse], summary="后台标签列表", tags=["管理后台-内容"])
def admin_list_tags(
    db: Session = Depends(get_db),
    admin: Admin = Depends(_require_admin),
):
    return taxo_svc.list_tags(db)


@router.post("/blog/tags", response_model=TagResponse, summary="后台新建标签", tags=["管理后台-内容"])
def admin_create_tag(
    payload: TagCreate,
    db: Session = Depends(get_db),
    admin: Admin = Depends(_require_admin),
):
    """新建标签（同名拒绝）。"""
    return taxo_svc.create_tag(db, payload)


@router.put("/blog/tags/{tag_id}", response_model=TagResponse, summary="后台编辑标签", tags=["管理后台-内容"])
def admin_update_tag(
    tag_id: int,
    payload: TagUpdate,
    db: Session = Depends(get_db),
    admin: Admin = Depends(_require_admin),
):
    return taxo_svc.update_tag(db, tag_id, payload)


@router.delete("/blog/tags/{tag_id}", summary="后台删除标签", tags=["管理后台-内容"])
def admin_delete_tag(
    tag_id: int,
    db: Session = Depends(get_db),
    admin: Admin = Depends(_require_admin),
):
    """删除标签（同时清理文章关联行）。"""
    taxo_svc.delete_tag(db, tag_id)
    return {"message": "标签已删除"}
