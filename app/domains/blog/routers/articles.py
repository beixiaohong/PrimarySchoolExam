"""文章路由（/api/blog/articles、/api/blog/latest）

权限口径（blog.md §22：判定以后端为准，前端隐藏按钮不算数）：
- 读：登录用户可读全部「已发布」；草稿仅作者本人可见；
- 写（新建/编辑/删除/发布）：仅作者本人；后台 admin 走 /api/admin/blog 另开通道。
"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.domains.identity.contracts import require_user
from app.models.user import User
from app.schemas.blog import (
    ArticleCreate,
    ArticleListResponse,
    ArticleResponse,
    ArticleUpdate,
    LatestArticleItem,
)
from app.domains.blog.services import articles as articles_svc

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/articles", response_model=ArticleListResponse, summary="文章列表", tags=["内容/Blog"])
def list_articles(
    page: int = Query(1, ge=1, description="页码，从 1 开始"),
    page_size: int = Query(20, ge=1, le=200, description="每页条数"),
    category_id: Optional[int] = Query(None, description="按分类筛选"),
    tag_id: Optional[int] = Query(None, description="按标签筛选"),
    keyword: Optional[str] = Query(None, description="关键词（标题/摘要/正文模糊匹配）"),
    mine: bool = Query(False, description="只看我的（含草稿）"),
    recommend: bool = Query(False, description="只看推荐文章（blog.md §14.2「推荐内容」）"),
    sort: str = Query("latest", description="排序：latest=最新发布，hot=浏览量倒序"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_user),
):
    """文章分页列表。默认只返回已发布；mine=true 时返回当前用户的全部文章（含草稿）。

    recommend / sort 供前台「推荐内容」「热门内容」两块使用（纯字段筛排，不做推荐算法）。
    """
    common = dict(page=page, page_size=page_size, category_id=category_id,
                  tag_id=tag_id, keyword=keyword, recommend=recommend, sort=sort)
    if mine:
        rows, total = articles_svc.list_articles(db, author_id=current_user.user_id, **common)
    else:
        rows, total = articles_svc.list_articles(db, status="published", **common)
    return ArticleListResponse(items=rows, total=total, page=page, page_size=page_size)


@router.get("/latest", response_model=list[LatestArticleItem], summary="最新内容（工作台用）", tags=["内容/Blog"])
def latest(
    limit: int = Query(5, ge=1, le=20, description="返回条数"),
    category_id: Optional[int] = Query(None, description="按分类筛选"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_user),
):
    """工作台「最新内容」轻量聚合：只返回已发布的标题/摘要/封面/时间，不含正文。"""
    return articles_svc.latest_articles(db, limit=limit, category_id=category_id)


@router.get("/articles/{article_id}", response_model=ArticleResponse, summary="文章详情", tags=["内容/Blog"])
def get_article(
    article_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_user),
):
    """文章详情。草稿仅作者本人可见；已发布文章每次访问自增浏览量。"""
    art = articles_svc.get_article(db, article_id)
    if art.status != "published" and art.author_id != current_user.user_id:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="文章不存在")
    data = articles_svc.serialize(db, art)
    if art.status == "published":
        articles_svc.incr_view(db, art)
        data.view_count = art.view_count
    return data


@router.post("/articles", response_model=ArticleResponse, summary="新建文章", tags=["内容/Blog"])
def create_article(
    payload: ArticleCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_user),
):
    """新建文章。作者固定为当前登录用户（后端强制，不接受请求体里的 author_id）。"""
    return articles_svc.create_article(db, current_user.user_id, payload)


@router.put("/articles/{article_id}", response_model=ArticleResponse, summary="编辑文章", tags=["内容/Blog"])
def update_article(
    article_id: int,
    payload: ArticleUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_user),
):
    """编辑文章（仅作者本人；仅提交的字段生效）。"""
    art = articles_svc.get_article(db, article_id)
    articles_svc.assert_owner(art, current_user.user_id)
    return articles_svc.update_article(db, art, payload)


@router.delete("/articles/{article_id}", summary="删除文章", tags=["内容/Blog"])
def delete_article(
    article_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_user),
):
    """删除文章（仅作者本人，同时清理标签关联行）。"""
    art = articles_svc.get_article(db, article_id)
    articles_svc.assert_owner(art, current_user.user_id)
    articles_svc.delete_article(db, art)
    return {"message": "文章已删除"}


@router.post("/articles/{article_id}/publish", response_model=ArticleResponse, summary="发布文章", tags=["内容/Blog"])
def publish_article(
    article_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_user),
):
    """发布文章（仅作者本人；已发布时幂等，不重复刷新发布时间）。"""
    art = articles_svc.get_article(db, article_id)
    articles_svc.assert_owner(art, current_user.user_id)
    return articles_svc.set_published(db, art, True)


@router.post("/articles/{article_id}/unpublish", response_model=ArticleResponse, summary="取消发布", tags=["内容/Blog"])
def unpublish_article(
    article_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_user),
):
    """取消发布（仅作者本人；文章回退为草稿并清空发布时间）。"""
    art = articles_svc.get_article(db, article_id)
    articles_svc.assert_owner(art, current_user.user_id)
    return articles_svc.set_published(db, art, False)
