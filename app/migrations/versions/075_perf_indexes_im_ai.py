"""075 - 补充性能索引（IM / AI 缓存 / 作答 / 错题）

扫描发现 `get_messages` 按 (chat_id, created_at) 倒序全表扫、`rejudge`/错题讲解按
(attempt_id, question_id)/(q_type, ref_id) 高频联查却缺索引，列表接口在大数据量下明显变慢。

`044` 已补一批通用索引，本迁移补齐 4 个高频热点索引（与 044 同款幂等写法）：
- db_im_messages(chat_id, created_at)    → IM 消息列表
- ai_qa(q_type, ref_id)                  → 错题讲解/问答缓存命中
- attempt_answers(attempt_id, question_id) → 重判/错题归因联查
- wrong_records(question_id)             → 错题归因按题联查

全部幂等（information_schema 检测，已存在则跳过），MySQL-only，启动由 runner 顺序执行。
"""
import logging

from sqlalchemy import text

logger = logging.getLogger("migrations")

# (表名, 索引名, [列...])
_INDEXES = [
    ("db_im_messages", "ix_im_msg_chat_time", ["chat_id", "created_at"]),
    ("ai_qa", "ix_aiqa_type_ref", ["q_type", "ref_id"]),
    ("attempt_answers", "ix_aa_attempt_q", ["attempt_id", "question_id"]),
    ("wrong_records", "ix_wrong_records_question", ["question_id"]),
]


def _index_exists(db, table: str, name: str) -> bool:
    row = db.execute(text(
        "SELECT COUNT(*) FROM information_schema.STATISTICS "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :t AND INDEX_NAME = :n"
    ), {"t": table, "n": name}).scalar()
    return (row or 0) > 0


def upgrade(db):
    for table, name, cols in _INDEXES:
        if _index_exists(db, table, name):
            logger.info("075: 索引 %s 已存在，跳过", name)
            continue
        col_sql = ", ".join(cols)
        try:
            db.execute(text(
                f"CREATE INDEX {name} ON {table} ({col_sql})"
            ))
            logger.info("075: 已创建索引 %s ON %s(%s)", name, table, col_sql)
        except Exception as e:  # noqa: BLE001
            logger.warning("075: 创建索引 %s 失败（已跳过）：%s", name, e)
    db.commit()
    logger.info("075 性能索引（IM/AI/作答/错题）已就绪")
