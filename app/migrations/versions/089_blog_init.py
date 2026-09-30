"""内容 / Blog 模块初始化：建文章/分类/标签/关联表 + 工作台应用使用记录表（迁移 089）

- 新建 db_blog_categories、db_blog_tags、db_blog_articles、db_blog_article_tags
  （blog.md §25：blog_* / content_* 二选一，本项目取 db_blog_ 前缀与 db_ledger_* 对齐）；
- 新建 db_workspace_app_usage：工作台「我的应用 / 最近使用」的按用户使用记录；
- 本迁移只 CREATE 新表，**不修改、不删除任何存量表或列**（blog.md §54 兼容要求）。

幂等：统一走 Base.metadata.create_all(checkfirst=True)，重复执行安全。
文章作者 author_id 只建索引不建物理外键（与账本/IM 同款，引用 users.user_id）。
"""
from app.database import Base, engine
from app.models.blog import (
    BlogArticle,
    BlogArticleTag,
    BlogCategory,
    BlogTag,
    WorkspaceAppUsage,
)


def upgrade(db):
    """Blog 模块初始化：一次性建全部新表（create_all 内部按外键依赖排序）。"""
    Base.metadata.create_all(
        bind=engine,
        tables=[
            BlogCategory.__table__,
            BlogTag.__table__,
            BlogArticle.__table__,
            BlogArticleTag.__table__,
            WorkspaceAppUsage.__table__,
        ],
    )
