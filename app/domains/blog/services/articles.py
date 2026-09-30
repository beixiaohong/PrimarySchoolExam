"""文章服务：列表检索 / 详情 / 增删改 / 发布 / 标签关联 / 最新内容聚合。

设计约定：
- 服务层不持有鉴权判断，只做「数据 + 业务规则」；归属校验由路由层决定
  （前台要求 author_id == 当前用户，后台 admin 走 _require_admin 跳过归属校验）；
- 列表统一走 app.core.pagination.paginate（项目标准分页，page 从 1、page_size clamp 200）；
- 排序口径：置顶优先 → 发布时间倒序 → id 倒序（草稿 published_at 为空，DESC 下自然沉底）。
"""
import logging
from datetime import datetime
from typing import List, Optional, Tuple

from fastapi import HTTPException
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.pagination import paginate
from app.models.blog import BlogArticle, BlogArticleTag, BlogCategory, BlogTag
from app.schemas.blog import (
    ArticleCreate,
    ArticleResponse,
    LatestArticleItem,
    TagResponse,
)

logger = logging.getLogger(__name__)

VALID_STATUS = ("draft", "published")


def _category_name(db: Session, category_id: Optional[int]) -> Optional[str]:
    """分类 id → 分类名（无分类/分类已删返回 None）。"""
    if not category_id:
        return None
    cat = db.query(BlogCategory).filter(BlogCategory.id == category_id).first()
    return cat.name if cat else None


def _tags_of(db: Session, article_id: int) -> List[TagResponse]:
    """取某篇文章的标签列表（经关联表 join）。"""
    rows = db.query(BlogTag).join(
        BlogArticleTag, BlogArticleTag.tag_id == BlogTag.id
    ).filter(BlogArticleTag.article_id == article_id).all()
    return [TagResponse.model_validate(t) for t in rows]


def serialize(db: Session, art: BlogArticle) -> ArticleResponse:
    """ORM 文章 → 响应模型（补分类名与标签列表）。"""
    data = ArticleResponse.model_validate(art)
    data.category_name = _category_name(db, art.category_id)
    data.tags = _tags_of(db, art.id)
    return data


def _set_tags(db: Session, article_id: int, tag_ids: Optional[List[int]]):
    """整体覆盖文章的标签集合（先清后插；只保留确实存在的标签 id）。"""
    db.query(BlogArticleTag).filter(BlogArticleTag.article_id == article_id).delete()
    ids = {int(t) for t in (tag_ids or []) if t}
    if not ids:
        return
    exists = db.query(BlogTag.id).filter(BlogTag.id.in_(ids)).all()
    for (tid,) in exists:
        db.add(BlogArticleTag(article_id=article_id, tag_id=tid))


def list_articles(
    db: Session,
    *,
    page: int = 1,
    page_size: int = 20,
    status: Optional[str] = None,
    category_id: Optional[int] = None,
    tag_id: Optional[int] = None,
    keyword: Optional[str] = None,
    author_id: Optional[str] = None,
) -> Tuple[List[ArticleResponse], int]:
    """文章分页列表。

    status 为空表示不限状态；前台公开列表应显式传 status='published'。
    keyword 命中标题 / 摘要 / 正文（blog.md §18：优先用数据库能力，不上 ES）。
    """
    q = db.query(BlogArticle)
    if status:
        q = q.filter(BlogArticle.status == status)
    if category_id:
        q = q.filter(BlogArticle.category_id == category_id)
    if tag_id:
        q = q.join(BlogArticleTag, BlogArticleTag.article_id == BlogArticle.id)
        q = q.filter(BlogArticleTag.tag_id == tag_id)
    if author_id:
        q = q.filter(BlogArticle.author_id == author_id)
    kw = (keyword or "").strip()
    if kw:
        like = f"%{kw}%"
        q = q.filter(or_(
            BlogArticle.title.like(like),
            BlogArticle.summary.like(like),
            BlogArticle.content_md.like(like),
        ))
    q = q.order_by(BlogArticle.is_top.desc(), BlogArticle.published_at.desc(), BlogArticle.id.desc())
    rows, total = paginate(q, page, page_size)
    return [serialize(db, r) for r in rows], total


def get_article(db: Session, article_id: int) -> BlogArticle:
    """按 id 取文章 ORM 对象；不存在抛 404。"""
    art = db.query(BlogArticle).filter(BlogArticle.id == article_id).first()
    if not art:
        raise HTTPException(status_code=404, detail="文章不存在")
    return art


def assert_owner(art: BlogArticle, user_id: str):
    """归属校验：非作者本人抛 403（后台 admin 路由不调用本函数）。"""
    if art.author_id != user_id:
        raise HTTPException(status_code=403, detail="无权操作他人文章")


def create_article(db: Session, author_id: str, payload: ArticleCreate) -> ArticleResponse:
    """新建文章。status=published 时立即落 published_at；否则为草稿。"""
    title = (payload.title or "").strip()
    if not title:
        raise HTTPException(status_code=400, detail="标题不能为空")
    status = payload.status if payload.status in VALID_STATUS else "draft"
    now = datetime.now()
    art = BlogArticle(
        title=title,
        slug=(payload.slug or "").strip() or None,
        summary=(payload.summary or "").strip() or None,
        cover=(payload.cover or "").strip() or None,
        content_md=payload.content_md,
        author_id=author_id,
        category_id=payload.category_id,
        status=status,
        is_top=1 if payload.is_top else 0,
        is_recommend=1 if payload.is_recommend else 0,
        view_count=0,
        created_at=now,
        updated_at=now,
        published_at=now if status == "published" else None,
    )
    db.add(art)
    db.flush()                      # 取得 art.id 后再建标签关联
    _set_tags(db, art.id, payload.tag_ids)
    db.commit()
    db.refresh(art)
    return serialize(db, art)


def update_article(db: Session, art: BlogArticle, payload) -> ArticleResponse:
    """更新文章（仅提交的字段生效）。

    tag_ids 传列表即整体覆盖标签集合；不传则不动标签。
    status 变动时同步维护 published_at：发布补时间、取消发布置空。
    """
    data = payload.model_dump(exclude_unset=True)
    tag_ids = data.pop("tag_ids", None)
    if "status" in data and data["status"] not in VALID_STATUS:
        raise HTTPException(status_code=400, detail="status 仅支持 draft|published")
    new_status = data.get("status")
    if "is_top" in data:
        data["is_top"] = 1 if data["is_top"] else 0
    if "is_recommend" in data:
        data["is_recommend"] = 1 if data["is_recommend"] else 0
    if "title" in data:
        data["title"] = (data["title"] or "").strip()
        if not data["title"]:
            raise HTTPException(status_code=400, detail="标题不能为空")
    for k, v in data.items():
        setattr(art, k, v)
    # 发布态 ↔ 发布时间联动
    if new_status == "published" and not art.published_at:
        art.published_at = datetime.now()
    elif new_status == "draft":
        art.published_at = None
    art.updated_at = datetime.now()
    if tag_ids is not None:
        _set_tags(db, art.id, tag_ids)
    db.commit()
    db.refresh(art)
    return serialize(db, art)


def delete_article(db: Session, art: BlogArticle):
    """删除文章（关联标签行先清，避免脏关联）。"""
    db.query(BlogArticleTag).filter(BlogArticleTag.article_id == art.id).delete()
    db.delete(art)
    db.commit()


def set_published(db: Session, art: BlogArticle, published: bool) -> ArticleResponse:
    """发布 / 取消发布（与 update 走同一套 published_at 联动口径）。"""
    art.status = "published" if published else "draft"
    if published:
        if not art.published_at:
            art.published_at = datetime.now()
    else:
        art.published_at = None
    art.updated_at = datetime.now()
    db.commit()
    db.refresh(art)
    return serialize(db, art)


def incr_view(db: Session, art: BlogArticle):
    """详情页自增浏览量（失败不影响正文返回，故单独提交）。"""
    art.view_count = (art.view_count or 0) + 1
    db.commit()


def latest_articles(db: Session, limit: int = 5, category_id: Optional[int] = None) -> List[LatestArticleItem]:
    """工作台「最新内容」：只取已发布，返回轻量条目（不含正文，blog.md §49）。"""
    limit = max(1, min(int(limit), 20))
    q = db.query(BlogArticle).filter(BlogArticle.status == "published")
    if category_id:
        q = q.filter(BlogArticle.category_id == category_id)
    rows = q.order_by(BlogArticle.published_at.desc(), BlogArticle.id.desc()).limit(limit).all()
    out = []
    for a in rows:
        out.append(LatestArticleItem(
            id=a.id,
            title=a.title,
            summary=a.summary,
            cover=a.cover,
            category_name=_category_name(db, a.category_id),
            published_at=a.published_at,
        ))
    return out
