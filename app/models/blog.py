"""内容 / Blog 模块 SQLAlchemy 模型

定义文章系统的四张表 + 工作台应用使用记录表：

- BlogCategory(db_blog_categories)：文章分类，支持排序；
- BlogTag(db_blog_tags)：文章标签；
- BlogArticle(db_blog_articles)：文章主体，Markdown 原文落 content_md；
- BlogArticleTag(db_blog_article_tags)：文章 ↔ 标签多对多关联；
- WorkspaceAppUsage(db_workspace_app_usage)：工作台「我的应用 / 最近使用」的按用户使用记录。

命名与约定（与现有模块保持一致）：
- 表前缀 db_blog_ / db_workspace_（同 db_ledger_*、db_novels 的模块归属命名）；
- 作者 author_id 直接引用 users.user_id（逻辑外键，不建物理 FK，与账本/IM 同款），
  不复制用户信息（blog.md §25.2）；
- 大文本用 Text；MySQL 下 TEXT 不允许 DEFAULT，故 content_md/summary 均不设 default；
- 时间字段统一 DateTime + 应用层赋值（默认 datetime.utcnow 侧由调用方/迁移保证）。
"""
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, UniqueConstraint, Index
from datetime import datetime

from app.database import Base


class BlogCategory(Base):
    """文章分类"""
    __tablename__ = "db_blog_categories"
    __table_args__ = {"comment": "内容/Blog 文章分类（支持排序）"}

    id = Column(Integer, primary_key=True, autoincrement=True, comment="主键自增")
    name = Column(String(64), nullable=False, comment="分类名")
    slug = Column(String(64), nullable=True, index=True, comment="URL 别名（可空）")
    description = Column(String(255), nullable=True, comment="分类描述")
    sort_order = Column(Integer, default=0, comment="排序值，越小越靠前")
    created_at = Column(DateTime, default=datetime.utcnow, comment="创建时间")


class BlogTag(Base):
    """文章标签"""
    __tablename__ = "db_blog_tags"
    __table_args__ = {"comment": "内容/Blog 文章标签"}

    id = Column(Integer, primary_key=True, autoincrement=True, comment="主键自增")
    name = Column(String(64), nullable=False, comment="标签名")
    slug = Column(String(64), nullable=True, index=True, comment="URL 别名（可空）")
    created_at = Column(DateTime, default=datetime.utcnow, comment="创建时间")


class BlogArticle(Base):
    """文章"""
    __tablename__ = "db_blog_articles"
    __table_args__ = (
        # 复合索引：已发布列表按发布时间倒序取页（索引列顺序与 ORDER BY 一致）
        Index("ix_blog_article_status_pub", "status", "published_at"),
        {"comment": "内容/Blog 文章主体（Markdown 原文 + 发布状态 + 置顶推荐）"},
    )

    id = Column(Integer, primary_key=True, autoincrement=True, comment="主键自增")
    title = Column(String(200), nullable=False, comment="标题")
    slug = Column(String(200), nullable=True, index=True, comment="URL 别名（可空，重复时用 id 兜底）")
    summary = Column(Text, nullable=True, comment="摘要")
    cover = Column(String(500), nullable=True, comment="封面图 URL")
    content_md = Column(Text, nullable=True, comment="正文 Markdown 原文")
    author_id = Column(String(64), nullable=False, index=True, comment="作者 user_id（引用 users.user_id）")
    category_id = Column(Integer, nullable=True, index=True, comment="分类 id（可空）")
    # draft 草稿 / published 已发布（blog.md §15.1）
    status = Column(String(16), default="draft", nullable=False, index=True, comment="状态：draft|published")
    is_top = Column(Integer, default=0, nullable=False, comment="是否置顶 0/1")
    is_recommend = Column(Integer, default=0, nullable=False, comment="是否推荐 0/1")
    view_count = Column(Integer, default=0, nullable=False, comment="浏览量")
    created_at = Column(DateTime, default=datetime.utcnow, comment="创建时间")
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, comment="更新时间")
    published_at = Column(DateTime, nullable=True, comment="发布时间（取消发布置空）")


class BlogArticleTag(Base):
    """文章 ↔ 标签 多对多关联"""
    __tablename__ = "db_blog_article_tags"
    __table_args__ = (
        UniqueConstraint("article_id", "tag_id", name="uq_blog_article_tag", comment="同一文章的同一标签只关联一次"),
        {"comment": "内容/Blog 文章与标签的多对多关联"},
    )

    id = Column(Integer, primary_key=True, autoincrement=True, comment="主键自增")
    article_id = Column(Integer, ForeignKey("db_blog_articles.id", ondelete="CASCADE"), nullable=False, index=True, comment="文章 id")
    tag_id = Column(Integer, ForeignKey("db_blog_tags.id", ondelete="CASCADE"), nullable=False, index=True, comment="标签 id")


class WorkspaceAppUsage(Base):
    """工作台应用使用记录（我的应用 / 最近使用）

    按 (user_id, app_key) 唯一：访问一次累加 visit_count 并刷新 last_visit_at。
    只存「用户 → 模块」的使用事实，不存业务数据（blog.md §32：首页不复制业务数据）。
    """
    __tablename__ = "db_workspace_app_usage"
    __table_args__ = (
        UniqueConstraint("user_id", "app_key", name="uq_workspace_user_app", comment="每用户每模块一条"),
        {"comment": "工作台模块使用记录（访问次数/最近访问时间），驱动我的应用与最近使用"},
    )

    id = Column(Integer, primary_key=True, autoincrement=True, comment="主键自增")
    user_id = Column(String(64), nullable=False, index=True, comment="用户 user_id")
    app_key = Column(String(32), nullable=False, comment="模块 key（见前端 apps.js）")
    visit_count = Column(Integer, default=0, nullable=False, comment="累计访问次数")
    last_visit_at = Column(DateTime, nullable=True, index=True, comment="最近一次访问时间")
