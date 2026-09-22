"""小说模块 - Pydantic Schema（pydantic v2）

读者端与后台共用；响应模型刻意不含章节正文 content（目录接口只给元信息，
正文由 /read 单独按段拉取，避免目录页一次拖回整本书）。
"""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


# ───────────────── 读者端：列表 / 详情 ─────────────────
class NovelBrief(BaseModel):
    """书城列表条目（不含正文，简介截断）"""
    id: int
    title: str
    author: str = ""
    category: str = ""
    cover_url: str = ""
    intro: str = ""
    chapter_mode: str = "chapter"
    status: str = "serial"
    word_count: int = 0
    chapter_count: int = 0
    view_count: int = 0
    sort_order: int = 0
    enabled: bool = True
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class NovelListResponse(BaseModel):
    items: list[NovelBrief] = Field(default_factory=list)
    total: int = 0
    page: int = 1
    page_size: int = 20


class NovelDetail(NovelBrief):
    """详情页：额外带上当前登录用户的阅读进度（未登录则 progress 为 None）"""
    chapter_idx: int = 0          # 本人读到第几段（0=未读）
    in_shelf: bool = False        # 是否已在书架


class CategoryItem(BaseModel):
    category: str
    count: int = 0


# ───────────────── 读者端：目录 / 阅读 ─────────────────
class ChapterBrief(BaseModel):
    """目录条目：只有元信息，正文走 /read"""
    id: int
    idx: int
    title: str = ""
    word_count: int = 0


class ChapterListResponse(BaseModel):
    items: list[ChapterBrief] = Field(default_factory=list)
    total: int = 0
    offset: int = 0
    limit: int = 100
    has_more: bool = False


class ChapterContent(BaseModel):
    """一段正文（章节模式下 title 有值；流式分块模式 title 为空）"""
    id: int
    idx: int
    title: str = ""
    content: str = ""
    word_count: int = 0


class ReadResponse(BaseModel):
    """下滑增量加载结果：next 为下一段起始 idx（None 表示已读完）"""
    items: list[ChapterContent] = Field(default_factory=list)
    total: int = 0
    next: Optional[int] = None
    has_more: bool = False


# ───────────────── 读者端：进度 / 书架 ─────────────────
class ProgressUpdate(BaseModel):
    chapter_idx: int = Field(1, ge=1, description="读到第几段（从 1 开始）")


class ShelfUpdate(BaseModel):
    in_shelf: bool = True


class BookmarkCreate(BaseModel):
    """添加书签：标记到某一章/段，可附便签"""
    chapter_idx: int = Field(1, ge=1, description="书签所在章/段号（从 1 开始）")
    note: str = ""


# ───────────────── 后台：导入 / 编辑 ─────────────────
class NovelImportResult(BaseModel):
    """TXT 导入结果（后台上传后立即回显，便于确认是否成功分章）"""
    id: int
    title: str
    mode: str = "chapter"          # chapter / stream
    encoding: str = ""
    chapter_count: int = 0
    word_count: int = 0


class NovelUpdate(BaseModel):
    """后台改元信息（全部可选，只传要改的字段）"""
    title: Optional[str] = None
    author: Optional[str] = None
    category: Optional[str] = None
    cover_url: Optional[str] = None
    intro: Optional[str] = None
    status: Optional[str] = None
    enabled: Optional[bool] = None
    sort_order: Optional[int] = None


class ChapterUpdate(BaseModel):
    """后台改章节"""
    title: Optional[str] = None
    content: Optional[str] = None
