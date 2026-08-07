"""013 孩子申诉表：批改判错 → 孩子「我做对了」→ 家长二次确认

背景：AI 复核（判题走 AI 接口，AI 判对即改判正确）之后仍判错的题目，
孩子可以发起申诉（answer_appeals），家长在「设置-家长管理」里二次确认：
- 确认做对了（approve）→ 该题改判正确、本卷得分重算、本次新建的错题记录移除
- 维持判错（reject）→ 申诉关闭，原判定不变

字段：
- source：exam=在线做题 / retry=错题重练（变式重练/掌握检测）
- question_id：题目 id（exam 时必有）
- record_id / record_kind：重练时的错题记录（WrongRecord / StudyError）
- wrong_record_id / wrong_new：本次提交新建的错题记录（确认后删除）
- status：pending / approved / rejected
"""
import logging
from datetime import datetime

from sqlalchemy import (
    MetaData, Table, Column, Integer, String, DateTime, Text, Boolean,
)

logger = logging.getLogger("migrations")


def upgrade(db):
    bind = db.get_bind()
    meta = MetaData()
    Table(
        "answer_appeals",
        meta,
        Column("id", Integer, primary_key=True, autoincrement=True),
        Column("user_id", String(50), nullable=False, index=True),
        Column("source", String(20), nullable=False, default="exam"),
        Column("question_id", Integer, nullable=True),
        Column("record_id", Integer, nullable=True),
        Column("record_kind", String(20), nullable=True),
        Column("question", Text, nullable=False),
        Column("user_answer", Text, nullable=False),
        Column("correct_answer", Text, nullable=False),
        Column("subject", String(20), nullable=False, default=""),
        Column("wrong_record_id", Integer, nullable=True),
        Column("wrong_new", Boolean, nullable=False, default=False),
        Column("status", String(20), nullable=False, default="pending"),
        Column("created_at", DateTime, default=datetime.now),
        Column("decided_at", DateTime, nullable=True),
    ).create(bind=bind, checkfirst=True)

    logger.info("answer_appeals 表已创建（孩子申诉 → 家长二次确认）")
