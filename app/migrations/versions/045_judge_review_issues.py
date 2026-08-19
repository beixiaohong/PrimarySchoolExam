"""045 - 系统判题错误题目沉淀表（judge_review_issues）

背景：错题复核（AI 判对 → 改判正确）与申诉（家长确认做对）会不断发现
「系统参考答案本身算错 / 本地判题把正确作答判错」的题目。此前这些错误
只能靠用户逐个报障，无法系统性修复判题代码。

建表：judge_review_issues，AI 复核/申诉确认时把这类题目单独落库
（题干、原参考答案、AI 修正值、孩子作答、学科、原因、来源），
status=open 表示待统一修复，修复判题代码/题库后置为 fixed。

幂等：Table.create(checkfirst=True)，MySQL-only，启动由 runner 顺序执行。
"""
import logging
from datetime import datetime

from sqlalchemy import (
    MetaData, Table, Column, Integer, String, DateTime, Text,
)

logger = logging.getLogger("migrations")


def upgrade(db):
    bind = db.get_bind()
    meta = MetaData()
    Table(
        "judge_review_issues",
        meta,
        Column("id", Integer, primary_key=True, autoincrement=True),
        Column("user_id", String(50), nullable=False, index=True),
        Column("question_id", Integer, nullable=True, index=True),
        Column("question", Text, nullable=False),
        Column("stored_answer", Text, nullable=True),
        Column("correct_answer", Text, nullable=True),
        Column("user_answer", Text, nullable=True),
        Column("subject", String(20), nullable=False, default=""),
        Column("reason", String(200), nullable=False, default=""),
        Column("source", String(20), nullable=False, default="judge"),
        Column("status", String(20), nullable=False, default="open"),
        Column("created_at", DateTime, default=datetime.now),
    ).create(bind=bind, checkfirst=True)

    logger.info("judge_review_issues 表已创建（系统判题错误题目沉淀）")
