"""044 - 性能索引（缓解「系统经常卡顿」）

背景：首页 dashboard、试卷记录列表、错题/学习错误统计等高频只读接口，
在 users / wrong_records / study_errors / exam_records / vocab_* / classical_* 等表上
按 (user_id, ...) 与 created_at/learn_date 频繁过滤、排序、分组，但缺少相应索引，
大表下全表扫描导致首页与列表接口明显变慢。

修复：为热点过滤/排序/分组列补复合/单列索引。全部幂等（information_schema 检测，
已存在则跳过），MySQL-only，启动由 runner 顺序执行。
"""
import logging

from sqlalchemy import text

logger = logging.getLogger("migrations")

# (表名, 索引名, [列...])
_INDEXES = [
    ("wrong_records", "ix_wrong_records_user_mastered", ["user_id", "is_mastered"]),
    ("study_errors", "ix_study_errors_user_src_mastered", ["user_id", "source_type", "is_mastered"]),
    ("questions", "ix_questions_subject", ["subject"]),
    ("vocab_progress", "ix_vocab_progress_user_word", ["user_id", "word_id"]),
    ("classical_progress", "ix_classical_progress_user_text", ["user_id", "text_id"]),
    ("vocab_daily_log", "ix_vocab_daily_log_user_date", ["user_id", "learn_date"]),
    ("classical_daily_log", "ix_classical_daily_log_user_date", ["user_id", "learn_date"]),
    ("exam_records", "ix_exam_records_created_at", ["created_at"]),
    ("word_books", "ix_word_books_grade", ["grade"]),
    ("words", "ix_words_book_id", ["book_id"]),
    ("classical_texts", "ix_classical_texts_grade", ["grade"]),
    ("grammar_exercises", "ix_grammar_exercises_grade", ["grade"]),
    ("ai_usage_log", "ix_ai_usage_log_created_at", ["created_at"]),
    ("diamond_ledger", "ix_diamond_ledger_created_at", ["created_at"]),
    ("users", "ix_users_last_login_date", ["last_login_date"]),
    ("users", "ix_users_created_at", ["created_at"]),
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
            logger.info("044: 索引 %s 已存在，跳过", name)
            continue
        col_sql = ", ".join(cols)
        try:
            db.execute(text(
                f"CREATE INDEX {name} ON {table} ({col_sql})"
            ))
            logger.info("044: 已创建索引 %s ON %s(%s)", name, table, col_sql)
        except Exception as e:  # noqa: BLE001
            # 列不存在/索引名冲突等：记录但不阻断其余索引（保持幂等、可重试）
            logger.warning("044: 创建索引 %s 失败（已跳过）：%s", name, e)
