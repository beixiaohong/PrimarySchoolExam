"""050 - 九科通用知识点表（knowledge_points）

背景（需求：采集浙江初中九科知识，录入系统）：
- 区别于仅英语语法的 GrammarPoint，本表承载初中九科（语数英 + 物化生 + 政史地）
  按 学科+年级+单元 组织的通用知识点；
- 由内容采集管线（tools/seed_junior_grade7.py）批量生成，后台「内容管理-知识点」可查。

幂等：checkfirst 建表，MySQL-only。
"""
import logging
from datetime import datetime

from sqlalchemy import (MetaData, Table, Column, Integer, String, Text,
                        DateTime, UniqueConstraint)

logger = logging.getLogger("migrations")


def upgrade(db):
    bind = db.get_bind()
    meta = MetaData()
    Table(
        "knowledge_points",
        meta,
        Column("id", Integer, primary_key=True, autoincrement=True),
        Column("subject", String(20), nullable=False, default="", index=True),
        Column("grade", Integer, nullable=False, default=7, index=True),
        Column("unit", String(100), nullable=False, default=""),
        Column("title", String(200), nullable=False),
        Column("summary", String(500), nullable=False, default=""),
        Column("content", Text, nullable=False, default=""),
        Column("examples", Text, nullable=False, default=""),
        Column("difficulty", Integer, nullable=False, default=2),
        Column("source", String(30), nullable=False, default="seed"),
        Column("created_at", DateTime, default=datetime.now),
        UniqueConstraint("subject", "grade", "unit", "title",
                         name="uq_kp_subject_grade_unit_title"),
    ).create(bind=bind, checkfirst=True)
    logger.info("knowledge_points 表已创建（九科通用知识点）")
