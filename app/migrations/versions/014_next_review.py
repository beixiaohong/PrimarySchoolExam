"""014 明日复习队列：错题「重做仍错 → 明天再来一次」

背景：PRD 3.3 错题温柔化规则 3——错题重做仍错时，不再强制继续硬磕，
提示「明天再来一次」并进入明日复习队列（状态好时再战，降低挫败感）。

字段：
- wrong_records.next_review_date：试卷错题的明日复习日期（YYYY-MM-DD，NULL=未入队）
- study_errors.next_review_date：学习错题（语法/古诗文）同上

规则（由 practice-submit 维护）：
- 重做失败（reactivated）→ next_review_date = 明天（每次失败都顺延）
- 掌握成功（mastered / 批量标记掌握）→ next_review_date = NULL（出队）
"""
import logging

from sqlalchemy import text
from sqlalchemy import inspect as sa_inspect

logger = logging.getLogger("migrations")


def upgrade(db):
    bind = db.get_bind()
    insp = sa_inspect(bind)
    # 为错题表补明日复习日期列（重做仍错 → 第二天再来一次）
    for table, col, ddl in [
        ("wrong_records", "next_review_date", "VARCHAR(10)"),
        ("study_errors", "next_review_date", "VARCHAR(10)"),
    ]:
        if table not in insp.get_table_names():
            continue
        cols = {c["name"] for c in insp.get_columns(table)}
        if col not in cols:
            db.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {ddl}"))
            logger.info(f"{table}.{col} 已添加")
