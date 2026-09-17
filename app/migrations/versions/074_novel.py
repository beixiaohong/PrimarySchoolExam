"""074 - 小说站模块（书城 + 章节/流式分块 + 阅读进度）

新建三张表（与 `app/models/novel.py` 单一真相源一致，幂等建）：
- `db_novels`          ：书城条目（chapter_mode=chapter/stream 决定前端阅读方式）
- `db_novel_chapters`  ：章节（chapter 模式）或文本块（stream 模式），共用一张表
- `db_novel_read_progress`：阅读进度 + 书架（登录用户一人一书一条）

另做一次列类型加固：`db_novel_chapters.content` 若因历史原因建成了 TEXT（64KB），
升级为 MEDIUMTEXT（16MB），避免长章节写入被截断或报 Data too long。

不灌任何种子小说：内容由后台上传 TXT 导入（`POST /api/admin/novel/upload`）。
"""
import logging

from sqlalchemy import text

from app.models.novel import Novel, NovelChapter, NovelReadProgress

logger = logging.getLogger("migrations")


def upgrade(db):
    bind = db.get_bind()
    Novel.__table__.create(bind=bind, checkfirst=True)
    NovelChapter.__table__.create(bind=bind, checkfirst=True)
    NovelReadProgress.__table__.create(bind=bind, checkfirst=True)

    # MySQL only：把 content 从 TEXT 加固为 MEDIUMTEXT（长章节不截断）。
    # 表刚由模型建出时本就是 MEDIUMTEXT，此步骤对全新库是 no-op。
    if bind.dialect.name == "mysql":
        try:
            db.execute(text(
                "ALTER TABLE db_novel_chapters MODIFY content MEDIUMTEXT"
            ))
        except Exception as e:  # pragma: no cover - 权限不足时降级，不阻塞启动
            logger.warning("074 未能升级 db_novel_chapters.content 为 MEDIUMTEXT：%s", e)

    db.commit()
    logger.info("074 小说站模块已就绪（表 db_novels / db_novel_chapters / db_novel_read_progress）")
