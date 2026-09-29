"""084 - 高项知识点「已读明细」表

新增一张表（`create_all(checkfirst=True)` 幂等）：

    gx_knowledge_reads   知识点已读明细（user_id + knowledge_id 唯一）

**为什么必须新增表，而不是复用 gx_progress.knowledge_read**：
`knowledge_read` 是 `Integer` 计数，只能回答「读过几条」，回答不了「哪几条读过」——
而列表页要给每条打「已读」标记，这是按条查询，计数满足不了。
所以本表是真相源，`knowledge_read` 降级为它的**去重计数缓存**（进度页显示用，
沿用本项目「行为发生时增量累加、读时零聚合」的口径）。

**无历史数据需要回填**：在此之前详情接口从未调用过 `_bump_progress(knowledge_read=...)`
（全仓仅 quiz_total / case_count 两处调用），所有用户的 `knowledge_read` 都是 0，
不存在「有计数但查不到明细」的情况。上线后首次打开详情才开始计数。

计数语义（由 services/gaoxiang.mark_knowledge_read 保证）：
**只在首次阅读时 +1** → 「读过知识点」= 去重条数，反复打开同一条不会把数字刷大。
"""
import logging

from sqlalchemy import text

logger = logging.getLogger("migrations")

# (表名, 列名, MySQL 列定义)
# 本次为全新表，无需补列；后续给 gx_knowledge_reads 加字段时在此登记
# （_ensure_column 幂等，列已存在会跳过）。
_COLUMNS = []

# (表名, 索引名, 列, 是否唯一)
_INDEXES = [
    # 唯一索引 = 幂等的保证：同一条知识点重复打开只会命中已有行
    ("gx_knowledge_reads", "ux_gx_kread_user_kn", ["user_id", "knowledge_id"], True),
    # 列表页按 user 批量取已读集合；带上 read_at 便于日后做「最近读过」
    ("gx_knowledge_reads", "ix_gx_kread_user_time", ["user_id", "read_at"], False),
]


def _table_exists(db, table: str) -> bool:
    row = db.execute(text(
        "SELECT COUNT(*) FROM information_schema.TABLES "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :t"
    ), {"t": table}).scalar()
    return (row or 0) > 0


def _index_exists(db, table: str, name: str) -> bool:
    row = db.execute(text(
        "SELECT COUNT(*) FROM information_schema.STATISTICS "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :t AND INDEX_NAME = :n"
    ), {"t": table, "n": name}).scalar()
    return (row or 0) > 0


def _column_exists(db, table: str, name: str) -> bool:
    row = db.execute(text(
        "SELECT COUNT(*) FROM information_schema.COLUMNS "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :t AND COLUMN_NAME = :c"
    ), {"t": table, "c": name}).scalar()
    return (row or 0) > 0


def upgrade(db):
    from app.database import _ensure_column
    from app.models.gaoxiang import GxKnowledgeRead

    # 1) 建表（checkfirst 幂等：已存在则跳过，不会动既有数据）
    try:
        GxKnowledgeRead.__table__.create(bind=db.get_bind(), checkfirst=True)
        logger.info("084: 表 %s 已就绪", GxKnowledgeRead.__tablename__)
    except Exception as e:                           # noqa: BLE001
        logger.warning("084: 建表 %s 失败（已跳过）：%s", GxKnowledgeRead.__tablename__, e)

    # 2) 补列（本次为空，_COLUMNS 留给后续加字段时登记）
    for table, col, ddl in _COLUMNS:
        if _column_exists(db, table, col):
            continue
        if not _table_exists(db, table):
            logger.info("084: 跳过 %s.%s（表不存在）", table, col)
            continue
        _ensure_column(table, col, ddl)

    # 3) 建索引（必须在建表/补列之后；唯一索引失败只告警不阻断启动）
    for table, name, cols, unique in _INDEXES:
        if _index_exists(db, table, name):
            continue
        try:
            db.execute(text("CREATE %sINDEX %s ON %s (%s)"
                            % ("UNIQUE " if unique else "", name, table, ", ".join(cols))))
            logger.info("084: 已创建索引 %s ON %s(%s)", name, table, ", ".join(cols))
        except Exception as e:                       # noqa: BLE001
            logger.warning("084: 创建索引 %s 失败（已跳过）：%s", name, e)
            try:
                db.rollback()
            except Exception:                        # noqa: BLE001
                pass
    db.commit()
    logger.info("084 高项知识点已读明细表已就绪")
