"""082 - 高项备考资料导入（分类入库 + 错题分析扩展）

把「软考高项备考资料」按四类（知识点 / 选择题练习 / 案例分析练习 / 论文练习）
导入题库后需要落库的字段，全部走 `database._ensure_column`（幂等，列已存在则跳过）。

一、新增字段
    gx_questions     title/chapter/source_kind/source_file/deck/seq/fingerprint
    gx_knowledge     chapter/kind/source_file/seq/fingerprint
    gx_wrongs        kind/best_score/last_score/wrong_reason/reason_at
    gx_case_grades   kind/rubric_json

二、新增索引
    ux_gx_question_fingerprint  唯一 —— 资料重复导入不翻倍（幂等键）
    ux_gx_knowledge_fingerprint 唯一
    ix_gx_question_kind_chapter 复合 —— 按「来源/章节」筛题

三、新增表
    gx_materials    资料归档清单（分类与解析审计，来源 manifest.json）

**fingerprint 必须可空**：MySQL 唯一索引允许多个 NULL，但只允许一个空串。
AI 动态生成的题目不参与去重（写 NULL），否则第二条 AI 题就会撞唯一键。
所以补列时不能给 DEFAULT ''。唯一索引在补列之后建，且先做 information_schema 探测。

MEDIUMTEXT 列（wrong_reason/rubric_json）不给 DEFAULT —— MySQL 的 TEXT/MEDIUMTEXT
不允许 DEFAULT，加了会直接报 1101。
"""
import logging

from sqlalchemy import text

logger = logging.getLogger("migrations")

# (表名, 列名, MySQL 列定义)
_COLUMNS = [
    # ── 题目：资料导入维度 ──
    ("gx_questions", "title", "VARCHAR(200) DEFAULT ''"),
    ("gx_questions", "chapter", "VARCHAR(50) DEFAULT ''"),
    ("gx_questions", "source_kind", "VARCHAR(20) DEFAULT ''"),
    ("gx_questions", "source_file", "VARCHAR(500) DEFAULT ''"),
    ("gx_questions", "deck", "VARCHAR(20) DEFAULT ''"),
    ("gx_questions", "seq", "INT DEFAULT 0"),
    # 可空、无默认 —— 见模块 docstring 的说明
    ("gx_questions", "fingerprint", "VARCHAR(32) NULL"),
    # ── 知识点：资料导入维度 ──
    ("gx_knowledge", "chapter", "VARCHAR(50) DEFAULT ''"),
    ("gx_knowledge", "kind", "VARCHAR(20) DEFAULT ''"),
    ("gx_knowledge", "source_file", "VARCHAR(500) DEFAULT ''"),
    ("gx_knowledge", "seq", "INT DEFAULT 0"),
    ("gx_knowledge", "fingerprint", "VARCHAR(32) NULL"),
    # ── 错题本：题型分栏 + AI 错因分析缓存 ──
    ("gx_wrongs", "kind", "VARCHAR(20) DEFAULT 'choice'"),
    ("gx_wrongs", "best_score", "INT DEFAULT 0"),
    ("gx_wrongs", "last_score", "INT DEFAULT 0"),
    ("gx_wrongs", "wrong_reason", "MEDIUMTEXT NULL"),
    ("gx_wrongs", "reason_at", "DATETIME NULL"),
    # ── 批改记录：区分案例/论文 + 四维评分明细 ──
    ("gx_case_grades", "kind", "VARCHAR(20) DEFAULT 'case'"),
    ("gx_case_grades", "rubric_json", "MEDIUMTEXT NULL"),
]

# (表名, 索引名, 列, 是否唯一)
_INDEXES = [
    ("gx_questions", "ux_gx_question_fingerprint", ["fingerprint"], True),
    ("gx_questions", "ix_gx_question_kind_chapter", ["source_kind", "chapter"], False),
    ("gx_knowledge", "ux_gx_knowledge_fingerprint", ["fingerprint"], True),
]


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

    # 1) 建/补齐表（gx_materials 是新表；其余已存在的表 checkfirst 会跳过）
    from app.models.gaoxiang import GxMaterial, GxKnowledge, GxQuestion
    for model in (GxMaterial, GxKnowledge, GxQuestion):
        try:
            model.__table__.create(bind=db.get_bind(), checkfirst=True)
        except Exception as e:                       # noqa: BLE001
            logger.warning("082: 建表 %s 失败（已跳过）：%s", model.__tablename__, e)

    # 2) 补列（幂等：列已存在时 _ensure_column 内部吞异常）
    for table, col, ddl in _COLUMNS:
        if _column_exists(db, table, col):
            continue
        if not _table_exists(db, table):
            logger.info("082: 跳过 %s.%s（表不存在）", table, col)
            continue
        _ensure_column(table, col, ddl)

    # 3) 建索引（必须在补列之后）
    for table, name, cols, unique in _INDEXES:
        if _index_exists(db, table, name):
            continue
        try:
            db.execute(text("CREATE %sINDEX %s ON %s (%s)"
                            % ("UNIQUE " if unique else "", name, table, ", ".join(cols))))
            logger.info("082: 已创建索引 %s ON %s(%s)", name, table, ", ".join(cols))
        except Exception as e:                       # noqa: BLE001
            # 唯一索引可能因为历史脏数据（重复指纹）建不上：不让它阻断启动，
            # 但要留下明确日志 —— 导入工具自身也会按指纹查重，不依赖该索引。
            logger.warning("082: 创建索引 %s 失败（已跳过）：%s", name, e)
            try:
                db.rollback()
            except Exception:                        # noqa: BLE001
                pass
    db.commit()
    logger.info("082 高项备考资料导入字段已就绪")


def _table_exists(db, table: str) -> bool:
    row = db.execute(text(
        "SELECT COUNT(*) FROM information_schema.TABLES "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :t"
    ), {"t": table}).scalar()
    return (row or 0) > 0
