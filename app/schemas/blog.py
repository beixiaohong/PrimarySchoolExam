"""内容 / Blog 模块 Pydantic 请求与响应模型。

沿用项目既有 schema 风格（见 app/schemas/ledger.py）：
- Create 模型承载「必填 + 有默认值」的创建入参；
- Update 模型字段全 Optional，配合 model_dump(exclude_unset=True) 做「仅提交的字段生效」；
- Response 模型统一 model_config = ConfigDict(from_attributes=True)，从 ORM 对象序列化。
"""
from typing import List, Optional
from datetime import datetime

from pydantic import BaseModel, ConfigDict


# ================================ 分类 ================================
class CategoryCreate(BaseModel):
    """新建分类请求模型。"""
    name: str
    slug: Optional[str] = None
    description: Optional[str] = None
    sort_order: int = 0


class CategoryUpdate(BaseModel):
    """更新分类请求模型（字段均可选）。"""
    name: Optional[str] = None
    slug: Optional[str] = None
    description: Optional[str] = None
    sort_order: Optional[int] = None


class CategoryResponse(BaseModel):
    """分类响应模型。"""
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    slug: Optional[str] = None
    description: Optional[str] = None
    sort_order: Optional[int] = 0
    created_at: Optional[datetime] = None


# ================================ 标签 ================================
class TagCreate(BaseModel):
    """新建标签请求模型。"""
    name: str
    slug: Optional[str] = None


class TagUpdate(BaseModel):
    """更新标签请求模型（字段均可选）。"""
    name: Optional[str] = None
    slug: Optional[str] = None


class TagResponse(BaseModel):
    """标签响应模型。"""
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    slug: Optional[str] = None
    created_at: Optional[datetime] = None


# ================================ 文章 ================================
class ArticleCreate(BaseModel):
    """新建文章请求模型。

    tag_ids 为空表示无标签；status 缺省 draft（保存草稿），传 published 即直接发布。
    """
    title: str
    slug: Optional[str] = None
    summary: Optional[str] = None
    cover: Optional[str] = None
    content_md: Optional[str] = None
    category_id: Optional[int] = None
    tag_ids: Optional[List[int]] = None
    status: str = "draft"
    is_top: bool = False
    is_recommend: bool = False


class ArticleUpdate(BaseModel):
    """更新文章请求模型（字段均可选，仅传需修改项）。

    tag_ids 语义：传列表即整体覆盖该文章的标签集合；不传则不动标签。
    """
    title: Optional[str] = None
    slug: Optional[str] = None
    summary: Optional[str] = None
    cover: Optional[str] = None
    content_md: Optional[str] = None
    category_id: Optional[int] = None
    tag_ids: Optional[List[int]] = None
    status: Optional[str] = None
    is_top: Optional[bool] = None
    is_recommend: Optional[bool] = None


class ArticleResponse(BaseModel):
    """文章响应模型（列表/详情共用；正文在列表接口不裁剪，由前端按需取字段）。"""
    model_config = ConfigDict(from_attributes=True)
    id: int
    title: str
    slug: Optional[str] = None
    summary: Optional[str] = None
    cover: Optional[str] = None
    content_md: Optional[str] = None
    author_id: str
    category_id: Optional[int] = None
    category_name: Optional[str] = None
    tags: List[TagResponse] = []
    status: str = "draft"
    is_top: Optional[int] = 0
    is_recommend: Optional[int] = 0
    view_count: Optional[int] = 0
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    published_at: Optional[datetime] = None


class ArticleListResponse(BaseModel):
    """文章分页列表响应。"""
    items: List[ArticleResponse]
    total: int
    page: int
    page_size: int


# ================================ 工作台 ================================
class AppUsageResponse(BaseModel):
    """工作台模块使用记录响应。"""
    model_config = ConfigDict(from_attributes=True)
    app_key: str
    visit_count: Optional[int] = 0
    last_visit_at: Optional[datetime] = None


class LatestArticleItem(BaseModel):
    """工作台「最新内容」用的轻量文章条目（不含正文，避免首页拉大字段）。"""
    id: int
    title: str
    summary: Optional[str] = None
    cover: Optional[str] = None
    category_name: Optional[str] = None
    published_at: Optional[datetime] = None
