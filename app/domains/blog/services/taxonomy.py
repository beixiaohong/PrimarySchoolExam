"""文章分类与标签服务（taxonomy）。

分类 / 标签是全站共享的参照数据（不按作者隔离），但写操作在路由层受权限约束：
前台普通用户不可改，后台 admin 可全量管理（blog.md §22：权限判断以后端为准）。
"""
import logging
from typing import List, Tuple

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.pagination import paginate
from app.models.blog import BlogArticle, BlogArticleTag, BlogCategory, BlogTag
from app.schemas.blog import CategoryCreate, CategoryResponse, TagCreate, TagResponse

logger = logging.getLogger(__name__)


# ================================ 分类 ================================
def list_categories(db: Session) -> List[CategoryResponse]:
    """分类列表（sort_order 升序 → id 升序）。"""
    rows = db.query(BlogCategory).order_by(BlogCategory.sort_order.asc(), BlogCategory.id.asc()).all()
    return [CategoryResponse.model_validate(r) for r in rows]


def create_category(db: Session, payload: CategoryCreate) -> CategoryResponse:
    name = (payload.name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="分类名不能为空")
    cat = BlogCategory(
        name=name,
        slug=(payload.slug or "").strip() or None,
        description=(payload.description or "").strip() or None,
        sort_order=payload.sort_order or 0,
    )
    db.add(cat)
    db.commit()
    db.refresh(cat)
    return CategoryResponse.model_validate(cat)


def _get_category(db: Session, category_id: int) -> BlogCategory:
    cat = db.query(BlogCategory).filter(BlogCategory.id == category_id).first()
    if not cat:
        raise HTTPException(status_code=404, detail="分类不存在")
    return cat


def update_category(db: Session, category_id: int, payload) -> CategoryResponse:
    cat = _get_category(db, category_id)
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(cat, k, v)
    db.commit()
    db.refresh(cat)
    return CategoryResponse.model_validate(cat)


def delete_category(db: Session, category_id: int):
    """删除分类：仍被文章引用时拒绝（避免产生孤儿分类 id）。"""
    cat = _get_category(db, category_id)
    used = db.query(BlogArticle.id).filter(BlogArticle.category_id == category_id).first()
    if used:
        raise HTTPException(status_code=400, detail="该分类下仍有文章，请先移走或删除文章")
    db.delete(cat)
    db.commit()


# ================================ 标签 ================================
def list_tags(db: Session) -> List[TagResponse]:
    """标签列表（id 升序）。"""
    rows = db.query(BlogTag).order_by(BlogTag.id.asc()).all()
    return [TagResponse.model_validate(r) for r in rows]


def create_tag(db: Session, payload: TagCreate) -> TagResponse:
    name = (payload.name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="标签名不能为空")
    dup = db.query(BlogTag).filter(BlogTag.name == name).first()
    if dup:
        raise HTTPException(status_code=400, detail="同名标签已存在")
    tag = BlogTag(name=name, slug=(payload.slug or "").strip() or None)
    db.add(tag)
    db.commit()
    db.refresh(tag)
    return TagResponse.model_validate(tag)


def _get_tag(db: Session, tag_id: int) -> BlogTag:
    tag = db.query(BlogTag).filter(BlogTag.id == tag_id).first()
    if not tag:
        raise HTTPException(status_code=404, detail="标签不存在")
    return tag


def update_tag(db: Session, tag_id: int, payload) -> TagResponse:
    tag = _get_tag(db, tag_id)
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(tag, k, v)
    db.commit()
    db.refresh(tag)
    return TagResponse.model_validate(tag)


def delete_tag(db: Session, tag_id: int):
    """删除标签：同时清理文章关联行（关联表才是标签的真实使用处）。"""
    tag = _get_tag(db, tag_id)
    db.query(BlogArticleTag).filter(BlogArticleTag.tag_id == tag_id).delete()
    db.delete(tag)
    db.commit()


def tags_with_count(db: Session) -> List[dict]:
    """标签 + 关联文章数（前台标签云用；左连接统计，无文章的标签计数为 0）。"""
    tags = db.query(BlogTag).order_by(BlogTag.id.asc()).all()
    out = []
    for t in tags:
        n = db.query(BlogArticleTag).filter(BlogArticleTag.tag_id == t.id).count()
        out.append({"id": t.id, "name": t.name, "slug": t.slug, "count": n})
    return out
