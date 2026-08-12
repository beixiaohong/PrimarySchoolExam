"""015 ai_qa 加 session_id 列：十万个为什么多轮对话会话标识

多轮对话：前端生成会话 id（uuid），携带在每次提问中；
同会话的历史问答（question/answer 对）在下次提问时作为上下文发给 AI。
session_id 为空的历史记录（单轮提问）行为不变（仍参与全局缓存命中）。
"""
import logging

from sqlalchemy import inspect, text

logger = logging.getLogger("migrations")


def upgrade(db):
    bind = db.get_bind()
    inspector = inspect(bind)
    cols = {c["name"] for c in inspector.get_columns("ai_qa")}
    if "session_id" not in cols:
        # ai_qa 新增 session_id 列：多轮对话会话标识（空=单轮，仍参与缓存命中）
        with bind.begin() as conn:
            conn.execute(text("ALTER TABLE ai_qa ADD COLUMN session_id VARCHAR(40)"))
        logger.info("015: ai_qa.session_id 列已添加")
    else:
        logger.info("015: ai_qa.session_id 已存在，跳过")
