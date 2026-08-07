"""添加 wrong_records.is_unanswered 列：区分「答错」与「未答」"""
from sqlalchemy import text


def upgrade(db):
    # 检查列是否已存在（create_all 可能已创建）
    cols = [row[1] for row in db.execute(text("PRAGMA table_info(wrong_records)"))]
    if "is_unanswered" not in cols:
        db.execute(text(
            "ALTER TABLE wrong_records ADD COLUMN is_unanswered BOOLEAN DEFAULT 0"
        ))
    # 回写：user_answer 为空的 AttemptAnswer 对应的 WrongRecord 标记为未答
    # 注意 AND 优先级高于 OR，必须加括号
    db.execute(text("""
        UPDATE wrong_records SET is_unanswered = 1
        WHERE (is_unanswered IS NULL OR is_unanswered = 0)
        AND EXISTS (
            SELECT 1 FROM attempt_answers aa
            JOIN exam_attempts ea ON aa.attempt_id = ea.id
            WHERE aa.question_id = wrong_records.question_id
              AND ea.user_id = wrong_records.user_id
              AND (aa.user_answer IS NULL OR TRIM(aa.user_answer) = '')
        )
    """))
    # 修正：有实际作答的 WrongRecord 不应标记为未答（修复先前 OR 优先级 bug 导致的误标）
    db.execute(text("""
        UPDATE wrong_records SET is_unanswered = 0
        WHERE is_unanswered = 1
        AND EXISTS (
            SELECT 1 FROM attempt_answers aa
            JOIN exam_attempts ea ON aa.attempt_id = ea.id
            WHERE aa.question_id = wrong_records.question_id
              AND ea.user_id = wrong_records.user_id
              AND aa.user_answer IS NOT NULL AND TRIM(aa.user_answer) != ''
        )
    """))


def downgrade(db):
    pass  # 不删列，保持向前兼容
