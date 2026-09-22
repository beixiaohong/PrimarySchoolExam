"""小说模块模型（074 迁移建表）

一个「小说站」模块的三张表，按 D2 内容域归属（不新增域，避免破坏九域契约）：

- `Novel`：一本书的元信息（标题/作者/分类/简介/封面/统计/上下架）。
  关键字段 `chapter_mode` 决定前端阅读方式：
    * `chapter`：TXT 成功自动分章 → 目录可用，下滑按「章」加载；
    * `stream` ：TXT 无法识别章节 → 目录不展示，下滑按「文本块」流式加载。
- `NovelChapter`：章节 / 文本块（两种模式共用一张表，靠 `chapter_mode` 区分语义）。
  stream 模式下 title 为空，前端不渲染章节标题，内容无缝拼接。
- `NovelReadProgress`：阅读进度 + 书架（登录用户才写；游客只读不写）。

设计取舍：不分「章节表 + 分块表」两套，因为两种模式的加载逻辑完全一致
（都是「按 idx 递增顺序拉下一段」），共用一张表可让前端只有一套分页代码。
大文本统一走 `_longtext()`（MySQL→MEDIUMTEXT，SQLite→TEXT），避免长章节被截断。
"""
from datetime import datetime

from sqlalchemy import (Boolean, Column, DateTime, Integer, String, Text,
                        UniqueConstraint, Index)
from sqlalchemy.dialects.mysql import MEDIUMTEXT
from sqlalchemy.ext.compiler import compiles

from ..database import Base


# 章节正文可能很长（长章节可达数万字），统一用 MEDIUMTEXT；
# SQLite 侧（采集暂存库/单测）无 MEDIUMTEXT，编译降级为 TEXT。
@compiles(MEDIUMTEXT, "sqlite")
def _compile_mediumtext_sqlite(element, compiler, **kw):
    return "TEXT"


def _longtext():
    """大文本：MySQL→MEDIUMTEXT，SQLite→TEXT。"""
    return MEDIUMTEXT()


class Novel(Base):
    """一本小说（书城条目）"""
    __tablename__ = "db_novels"
    __table_args__ = (
        Index("idx_novels_category_enabled", "category", "enabled"),
        {"comment": "小说：书城条目，chapter_mode 决定阅读方式（分章 / 流式分块）"},
    )

    id = Column(Integer, primary_key=True, autoincrement=True, comment="主键自增")
    title = Column(String(200), nullable=False, comment="书名")
    author = Column(String(100), default="", index=True, comment="作者（可空=佚名）")
    category = Column(String(50), default="", index=True, comment="分类（如 玄幻 / 都市 / 校园）")
    cover_url = Column(String(500), default="", comment="封面 URL（可选）")
    intro = Column(Text, default="", comment="简介")

    # ── 阅读方式 ──
    # chapter=TXT 已自动分章（目录可用）；stream=无法识别章节，按块流式加载
    chapter_mode = Column(String(20), default="chapter", comment="chapter=已分章 / stream=流式分块")
    status = Column(String(20), default="serial", comment="serial=连载 / finished=完本 / draft=草稿")

    # ── 统计（导入时算好，列表页免 COUNT）──
    word_count = Column(Integer, default=0, comment="总字数")
    chapter_count = Column(Integer, default=0, comment="章节数（stream 模式=分块数）")
    view_count = Column(Integer, default=0, comment="阅读人气（详情页访问累加）")

    enabled = Column(Boolean, default=True, index=True, comment="是否上架（False=读者端不可见）")
    sort_order = Column(Integer, default=0, comment="排序（小在前）")
    source_file = Column(String(500), default="", comment="原始 TXT 存放相对路径（便于重解析）")
    created_at = Column(DateTime, default=datetime.now, comment="创建时间")
    updated_at = Column(DateTime, default=datetime.now,
                        onupdate=datetime.now, comment="更新时间")

    def __repr__(self):
        return f"<Novel {self.id} {self.title}>"


class NovelChapter(Base):
    """章节（chapter_mode=chapter）或文本块（chapter_mode=stream）

    两种模式共用：stream 模式 title 为空、每块约 CHUNK_SIZE 字，前端不渲染标题。
    """
    __tablename__ = "db_novel_chapters"
    __table_args__ = (
        Index("idx_chapters_novel_idx", "novel_id", "idx"),
        {"comment": "小说章节/文本块：按 (novel_id, idx) 顺序读取，支持下滑增量加载"},
    )

    id = Column(Integer, primary_key=True, autoincrement=True, comment="主键自增")
    novel_id = Column(Integer, nullable=False, index=True, comment="所属小说 id")
    idx = Column(Integer, nullable=False, default=0, comment="顺序号（从 1 开始递增）")
    title = Column(String(300), default="", comment="章节标题（stream 模式为空）")
    content = Column(_longtext(), default="", comment="正文（MEDIUMTEXT，长章节不截断）")
    word_count = Column(Integer, default=0, comment="本段字数")
    created_at = Column(DateTime, default=datetime.now, comment="创建时间")

    def __repr__(self):
        return f"<NovelChapter {self.novel_id}#{self.idx} {self.title}>"


class NovelReadProgress(Base):
    """阅读进度 + 书架（登录用户；游客不写库）"""
    __tablename__ = "db_novel_read_progress"
    __table_args__ = (
        UniqueConstraint("user_id", "novel_id", name="uq_progress_user_novel"),
        {"comment": "小说阅读进度与书架：一人一本书一条记录"},
    )

    id = Column(Integer, primary_key=True, autoincrement=True, comment="主键自增")
    user_id = Column(String(50), nullable=False, index=True, comment="用户账号")
    novel_id = Column(Integer, nullable=False, index=True, comment="小说 id")
    chapter_idx = Column(Integer, default=1, comment="读到第几章/第几块（从 1 开始）")
    in_shelf = Column(Boolean, default=False, comment="是否在书架（收藏）")
    updated_at = Column(DateTime, default=datetime.now,
                        onupdate=datetime.now, comment="更新时间")

    def __repr__(self):
        return f"<NovelReadProgress {self.user_id}@{self.novel_id}#{self.chapter_idx}>"


class NovelBookmark(Base):
    """阅读书签（登录用户；游客不写库）

    同一 (user_id, novel_id, chapter_idx) 唯一，便于「在同一章再次标记 = 更新便签」
    而不会产生重复书签。仅有 (id, user_id, novel_id) 三列约束无法表达「按章去重」，
    故把 chapter_idx 纳入唯一键。
    """
    __tablename__ = "db_novel_bookmarks"
    __table_args__ = (
        UniqueConstraint("user_id", "novel_id", "chapter_idx",
                         name="uq_bookmark_user_novel_idx"),
        {"comment": "小说书签：读者在某一章/段做的标记，可附便签"},
    )

    id = Column(Integer, primary_key=True, autoincrement=True, comment="主键自增")
    user_id = Column(String(50), nullable=False, index=True, comment="用户账号")
    novel_id = Column(Integer, nullable=False, index=True, comment="小说 id")
    chapter_idx = Column(Integer, default=1, comment="书签所在章/段号（从 1 开始）")
    note = Column(String(500), default="", comment="便签（可选）")
    created_at = Column(DateTime, default=datetime.now, comment="创建时间")
    updated_at = Column(DateTime, default=datetime.now,
                        onupdate=datetime.now, comment="更新时间")

    def __repr__(self):
        return f"<NovelBookmark {self.user_id}@{self.novel_id}#{self.chapter_idx}>"


__all__ = ["Novel", "NovelChapter", "NovelReadProgress", "NovelBookmark"]
