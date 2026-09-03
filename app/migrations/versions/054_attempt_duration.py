"""054 - 答题用时采集（S2-M1 / 07-技术实施方案 §3.2.2 / 迁移 054）

`attempt_answers` 补 `started_at` / `duration_ms` / `seq` / `difficulty` / `created_at`
五列，打通掌握度模型的「用时」因子。

幂等：`_ensure_column` 异常兜底跳过已存在列。存量 `duration_ms` 统一为 0
（掌握度算法中 `duration_ms = 0` 视为「无用时数据」，用时因子取中性值 1.0，
不污染计算；见 07 §3.2.2 存量数据处理）。
"""
import logging

from app.database import _ensure_column

logger = logging.getLogger("migrations")


def upgrade(db):
    _ensure_column("attempt_answers", "started_at", "DATETIME NULL")
    _ensure_column("attempt_answers", "duration_ms", "INT NOT NULL DEFAULT 0")
    _ensure_column("attempt_answers", "seq", "INT NOT NULL DEFAULT 0")
    _ensure_column("attempt_answers", "difficulty", "SMALLINT NOT NULL DEFAULT 3")
    _ensure_column("attempt_answers", "created_at", "DATETIME NULL")
    db.commit()
    logger.info("054 答题用时采集列已就绪（started_at/duration_ms/seq/difficulty/created_at）")
