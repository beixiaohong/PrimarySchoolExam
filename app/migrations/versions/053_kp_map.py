"""053 - 题目-知识点映射表 + knowledge_points 补列（S2-M1 / 07-技术实施方案 §3.2.1）

- 新建 `question_kp_map`：统一覆盖三种题源的一题多知识点映射；
- `knowledge_points` 补 `parent_id` / `code` / `sort_order` / `status` /
  `textbook_ver` / `updated_at` 六列（层级/编码/教材版本/状态）。

幂等：
- `question_kp_map` 由模型表 `checkfirst` 建（与 `app/models/kp_map.py` 单一真相源一致）；
- 补列用 `app.database._ensure_column`（异常兜底跳过已存在列，跨 dialect 安全）。
`create_all`（init_db）在本迁移前已建好表结构，本迁移对已存在表为 no-op，仅对
存量生产库补齐列/表。
"""
import logging

from app.database import _ensure_column
from app.models.kp_map import QuestionKpMap

logger = logging.getLogger("migrations")


def upgrade(db):
    # 1) knowledge_points 补列（create_all 不会改已有表，故必须走迁移）
    _ensure_column("knowledge_points", "parent_id", "INT NOT NULL DEFAULT 0")
    _ensure_column("knowledge_points", "code", "VARCHAR(64) NOT NULL DEFAULT ''")
    _ensure_column("knowledge_points", "sort_order", "INT NOT NULL DEFAULT 0")
    _ensure_column("knowledge_points", "status", "VARCHAR(16) NOT NULL DEFAULT 'active'")
    _ensure_column("knowledge_points", "textbook_ver", "VARCHAR(32) NOT NULL DEFAULT ''")
    _ensure_column("knowledge_points", "updated_at", "DATETIME NULL")

    # 2) question_kp_map 新表（与模型一致，幂等建）
    QuestionKpMap.__table__.create(bind=db.get_bind(), checkfirst=True)
    logger.info("053 题目-知识点映射表 + knowledge_points 补列已就绪")
    db.commit()
