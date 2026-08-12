"""010 新增 AI 问答缓存表 ai_qa（十万个为什么 + 题目讲解入库复用）

背景：新增「十万个为什么」模块——孩子向 AI 提问，可选模型（智谱/GPT/DeepSeek），
VIP 才可用 DeepSeek。所有 AI 对话（含错题讲解）统一入库：
- 相同问题全局共享答案，命中后不再请求 AI，直接展示（省 token、秒回）
- 历史页可回看全部提问与题目讲解记录

ai_qa：
- q_type: qa=十万个为什么提问 / explain=错题讲解
- ref_id: explain 时 = 题目 id（同题全局复用）
- degraded: 是否降级模板（降级内容不参与缓存命中）
"""
import logging
from datetime import datetime

from sqlalchemy import (Column, DateTime, Index, Integer, String, Text)
from sqlalchemy import text

logger = logging.getLogger("migrations")


def upgrade(db):
    # 新建 AI 问答缓存表（十万个为什么 + 错题讲解，全局答案复用）
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS ai_qa (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id VARCHAR(50) NOT NULL,
            question TEXT NOT NULL,
            answer TEXT NOT NULL,
            provider VARCHAR(30) NOT NULL DEFAULT '',
            model VARCHAR(50) NOT NULL DEFAULT '',
            q_type VARCHAR(10) NOT NULL DEFAULT 'qa',
            ref_id INTEGER,
            degraded INTEGER NOT NULL DEFAULT 0,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """))
    # 按 q_type 查询索引
    db.execute(text(
        "CREATE INDEX IF NOT EXISTS ix_ai_qa_type ON ai_qa (q_type)"))
    # 同题复用索引（q_type + ref_id）
    db.execute(text(
        "CREATE INDEX IF NOT EXISTS ix_ai_qa_type_ref ON ai_qa (q_type, ref_id)"))
    # 按用户+类型查历史索引
    db.execute(text(
        "CREATE INDEX IF NOT EXISTS ix_ai_qa_user ON ai_qa (user_id, q_type)"))
    db.commit()
    logger.info("ai_qa 表已创建（十万个为什么 + 题目讲解缓存）")
